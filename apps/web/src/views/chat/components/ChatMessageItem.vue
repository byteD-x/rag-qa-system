<template>
  <article class="message-row" :class="message.role">
    <div class="message-avatar">
      <el-icon v-if="message.role === 'assistant'"><Platform /></el-icon>
      <el-icon v-else><User /></el-icon>
    </div>

    <div class="message-body">
      <div v-if="message.role === 'assistant'" class="message-meta-header">
        <span class="assistant-name">RAG 助手</span>
        <span v-if="message.answer_mode" class="meta-badge">{{ answerModeLabel(message.answer_mode) }}</span>
        <span v-if="message.execution_mode === 'agent'" class="meta-badge agent-badge">Agent</span>
      </div>

      <div v-if="message.role === 'assistant' && message.safety_notice" class="safety-alert" :class="message.safety_notice.level">
        <div class="safety-icon">!</div>
        <div class="safety-content">
          <strong>{{ message.safety_notice.title }}</strong>
          <p>{{ message.safety_notice.message }}</p>
        </div>
      </div>

      <div v-if="message.role === 'assistant' && message.message_kind !== 'interrupt' && message.answer_basis?.label" class="answer-basis">
        <span class="answer-basis__label">回答依据</span>
        <span class="answer-basis__text">{{ message.answer_basis.label }}</span>
      </div>

      <div class="message-bubble" :class="message.role">
        <div v-if="message.role === 'assistant' && message.streaming && !message.content" class="typing-indicator">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          <span class="typing-text">{{ message.isRetrieving ? '正在检索...' : '正在思考中...' }}</span>
        </div>
        <ChatInterruptCard v-else-if="message.message_kind === 'interrupt'" :message="message" />
        <div v-else class="message-content markdown-body" v-html="renderedContent"></div>
      </div>

      <div v-if="message.role === 'assistant' && message.message_kind !== 'interrupt' && (message.citations?.length || 0) > 0" class="citations-area">
        <CitationList :citations="message.citations" mode="kb" />
      </div>

      <div v-if="message.role === 'assistant' && message.message_kind !== 'interrupt'" class="message-footer-actions">
        <div class="action-left">
          <span v-if="message.retrieval" class="perf-metric">检索 {{ message.retrieval.aggregate?.retrieval_ms || 0 }}ms</span>
          <span v-if="message.retrieval?.aggregate?.selected_candidates" class="perf-metric">召回 {{ message.retrieval.aggregate.selected_candidates }} 条</span>
          <span v-if="message.grounding_score" class="perf-metric">可信度 {{ (message.grounding_score * 100).toFixed(1) }}%</span>
          <button v-if="message.workflow_run" class="text-action-btn" @click="$emit('show-workflow', message.workflow_run)">
            <el-icon><Connection /></el-icon> 轨迹
          </button>
        </div>

        <div class="action-right" v-if="!message.streaming && message.id && !message.id.startsWith('temp-')">
          <button class="feedback-btn" :class="{ active: message.feedback?.verdict === 'up' }" @click="chatStore.handleFeedback(message, 'up')" title="有帮助">
            👍
          </button>
          <el-popover placement="top" :width="300" trigger="click" v-model:visible="popoverVisible">
            <template #reference>
              <button class="feedback-btn" :class="{ active: message.feedback?.verdict === 'down' }" @click="openFeedback" title="没帮助">
                👎
              </button>
            </template>
            <div class="feedback-panel">
              <h4>反馈问题</h4>
              <p class="feedback-desc">这些信息会帮助我们持续改进回答质量。</p>
              <el-select v-model="feedbackForm.reason_code" placeholder="问题类型" size="small" style="width: 100%; margin-bottom: 12px;">
                <el-option label="答非所问" value="irrelevant" />
                <el-option label="事实错误或幻觉" value="hallucination" />
                <el-option label="引用不准确" value="bad_citation" />
                <el-option label="信息不完整" value="incomplete" />
                <el-option label="其他" value="other" />
              </el-select>
              <el-input v-model="feedbackForm.notes" type="textarea" :rows="3" placeholder="补充说明（可选）" style="margin-bottom: 12px;" />
              <div class="feedback-panel-actions">
                <el-button size="small" @click="popoverVisible = false">取消</el-button>
                <el-button type="primary" size="small" @click="submitFeedback">提交</el-button>
              </div>
            </div>
          </el-popover>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { User, Platform, Connection } from '@element-plus/icons-vue';
import { marked } from 'marked';
import CitationList from '@/components/CitationList.vue';
import { useChatStore } from '@/store/chat';
import ChatInterruptCard from './ChatInterruptCard.vue';

const props = defineProps<{ message: any }>();
defineEmits<{ (e: 'show-workflow', workflowInfo: any): void }>();

const chatStore = useChatStore();
const popoverVisible = ref(false);
const feedbackForm = ref({ reason_code: '', notes: '' });

const renderer = new marked.Renderer();
renderer.code = (options: any) => {
  const code = options.text;
  const language = options.lang || 'text';
  return `
    <div class="code-block-wrapper">
      <div class="code-lang">
        <span>${language}</span>
        <button class="code-copy-btn" onclick="navigator.clipboard.writeText(decodeURIComponent('${encodeURIComponent(code)}'))">Copy</button>
      </div>
      <pre><code class="language-${language}">${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>
    </div>
  `;
};
marked.setOptions({ renderer });

const renderedContent = computed(() => {
  if (!props.message.content) return '';
  return marked.parse(props.message.content) as string;
});

function answerModeLabel(mode: string | undefined) {
  if (mode === 'grounded') return '有据回答';
  if (mode === 'weak_grounded') return '保守回答';
  if (mode === 'common_knowledge') return '常识兜底';
  if (mode === 'refusal') return '拒答';
  if (mode === 'clarification') return '待确认';
  return '标准';
}

function openFeedback() {
  chatStore.handleFeedback(props.message, 'down');
  feedbackForm.value = { reason_code: '', notes: '' };
  popoverVisible.value = true;
}

async function submitFeedback() {
  await chatStore.handleFeedback(props.message, 'down', {
    reason_code: feedbackForm.value.reason_code || undefined,
    notes: feedbackForm.value.notes || undefined
  });
  popoverVisible.value = false;
}
</script>

<style scoped>
.message-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #555;
}

.message-row.assistant .message-avatar {
  background: var(--blue-600);
  color: #fff;
}

.message-body {
  flex: 1;
  min-width: 0;
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-row.user .message-body {
  align-items: flex-end;
}

.message-meta-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 4px;
}

.assistant-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.meta-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  color: var(--text-muted);
}

.agent-badge {
  background: #ecfdf5;
  color: #059669;
}

.message-bubble {
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-primary);
  border-radius: var(--radius-md);
}

.message-bubble.user {
  background: #f4f4f5;
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
}

.message-bubble.assistant {
  background: transparent;
  padding: 4px 0;
}

.answer-basis {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f8fbff;
  border: 1px solid #dbe7fb;
  color: var(--text-secondary);
  font-size: 12px;
}

.answer-basis__label {
  font-weight: 600;
  color: #275dad;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 0;
  color: var(--text-muted);
  font-size: 14px;
}

.dot {
  width: 4px;
  height: 4px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.typing-text {
  margin-left: 8px;
}

.safety-alert {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  margin-bottom: 8px;
}

.safety-alert.error {
  background: #fef2f2;
  border-color: #fecaca;
}

.safety-icon {
  font-size: 16px;
}

.safety-content strong {
  display: block;
  font-size: 13px;
  color: #92400e;
}

.safety-alert.error .safety-content strong {
  color: #991b1b;
}

.safety-content p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #b45309;
}

.safety-alert.error .safety-content p {
  color: #b91c1c;
}

:deep(.markdown-body p) { margin-bottom: 1em; }
:deep(.markdown-body p:last-child) { margin-bottom: 0; }
:deep(.markdown-body pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 0 0 8px 8px;
  overflow-x: auto;
  font-size: 13px;
  margin: 0;
}

:deep(.code-block-wrapper) {
  border-radius: 8px;
  overflow: hidden;
  margin: 1em 0;
  background: #1e1e1e;
  border: 1px solid #333;
}

:deep(.code-lang) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #2d2d2d;
  color: #9cdcfe;
  font-size: 12px;
  font-family: var(--font-mono);
}

:deep(.code-copy-btn) {
  background: transparent;
  border: none;
  color: #858585;
  cursor: pointer;
  font-size: 11px;
}

:deep(.markdown-body code:not(pre code)) {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 4px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: #eb5757;
}

.message-footer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.action-left {
  display: flex;
  gap: 12px;
  align-items: center;
}

.perf-metric {
  font-size: 12px;
  color: var(--text-muted);
}

.text-action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--blue-600);
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
}

.feedback-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 18px;
  opacity: 0.6;
}

.feedback-btn.active,
.feedback-btn:hover {
  opacity: 1;
}

.feedback-panel h4 {
  margin: 0 0 8px;
  font-size: 14px;
}

.feedback-desc {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.feedback-panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
