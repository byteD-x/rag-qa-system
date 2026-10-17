<template>
  <article class="message-row" :class="message.role">
    <div class="message-avatar">
      <el-icon v-if="message.role === 'assistant'"><Platform /></el-icon>
      <el-icon v-else><User /></el-icon>
    </div>

    <div class="message-body">
      <div v-if="message.role === 'assistant'" class="message-meta-header">
        <span class="assistant-name">RAG 助手</span>
        <span v-if="message.execution_mode === 'agent'" class="meta-badge agent-badge">Agent</span>
      </div>

      <div v-if="message.role === 'assistant' && message.safety_notice" class="safety-alert" :class="message.safety_notice.level">
        <div class="safety-icon">!</div>
        <div class="safety-content">
          <strong>{{ message.safety_notice.title }}</strong>
          <p>{{ message.safety_notice.message }}</p>
        </div>
      </div>

      <div
        v-if="message.role === 'assistant' && message.message_kind !== 'interrupt' && (message.answer_basis?.label || message.grounding_score)"
        class="answer-basis"
      >
        <span v-if="message.answer_basis?.label" class="answer-basis__label">回答依据</span>
        <span v-if="message.answer_basis?.label" class="answer-basis__text">{{ message.answer_basis.label }}</span>
        <span v-if="message.grounding_score" class="answer-basis__score">可信度 {{ (message.grounding_score * 100).toFixed(1) }}%</span>
      </div>

      <div class="message-bubble" :class="message.role">
        <div
          v-if="message.role === 'assistant' && message.streaming && !message.content"
          class="typing-indicator"
          role="status"
          aria-live="polite"
        >
          <span class="dot"></span>
          <span>正在检索...</span>
        </div>
        <ChatInterruptCard v-else-if="message.message_kind === 'interrupt'" :message="message" />
        <div v-else class="message-content markdown-body" v-html="renderedContent" @click="handleContentClick"></div>
      </div>

      <div
        v-if="message.role === 'assistant' && message.message_kind !== 'interrupt' && (message.citations?.length || 0) > 0"
        ref="citationsArea"
        class="citations-area"
      >
        <CitationList :citations="message.citations" mode="kb" />
      </div>

      <div v-if="message.role === 'assistant' && message.message_kind !== 'interrupt'" class="message-footer-actions">
        <div class="action-left">
          <button v-if="message.workflow_run" class="text-action-btn" @click="$emit('show-workflow', message.workflow_run)">
            <el-icon><Connection /></el-icon> 轨迹
          </button>
        </div>

        <div class="action-right" v-if="!message.streaming && message.id && !message.id.startsWith('temp-')">
          <button
            type="button"
            class="feedback-btn"
            :class="{ active: message.feedback?.verdict === 'up' }"
            aria-label="回答有帮助"
            title="有帮助"
            @click="chatStore.handleFeedback(message, 'up')"
          >
            <el-icon><CircleCheckFilled /></el-icon>
          </button>
          <el-popover placement="top" :width="300" trigger="click" v-model:visible="popoverVisible">
            <template #reference>
              <button
                type="button"
                class="feedback-btn"
                :class="{ active: message.feedback?.verdict === 'down' }"
                aria-label="回答没帮助"
                title="没帮助"
                @click="openFeedback"
              >
                <el-icon><CircleCloseFilled /></el-icon>
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
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { CircleCheckFilled, CircleCloseFilled, User, Platform, Connection } from '@element-plus/icons-vue';
import { marked } from 'marked';
import CitationList from '@/components/CitationList.vue';
import { useChatStore } from '@/store/chat';
import ChatInterruptCard from './ChatInterruptCard.vue';

const props = defineProps<{ message: any }>();
defineEmits<{ (e: 'show-workflow', workflowInfo: any): void }>();

const chatStore = useChatStore();
const popoverVisible = ref(false);
const feedbackForm = ref({ reason_code: '', notes: '' });
const citationsArea = ref<HTMLElement | null>(null);

let copiedButton: HTMLButtonElement | null = null;
let copiedTimer: ReturnType<typeof setTimeout> | null = null;
let highlightTimer: ReturnType<typeof setTimeout> | null = null;

const renderer = new marked.Renderer();
const escapeHtml = (value: string) => value
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');
renderer.code = (options: any) => {
  const code = String(options.text || '');
  const language = escapeHtml(String(options.lang || 'text'));
  return `
    <div class="code-block-wrapper">
      <div class="code-lang">
        <span>${language}</span>
        <button type="button" class="code-copy-btn" data-copy-code="${escapeHtml(encodeURIComponent(code))}">复制</button>
      </div>
      <pre><code class="language-${language}">${escapeHtml(code)}</code></pre>
    </div>
  `;
};
renderer.html = (token: any) => escapeHtml(String(token?.text || ''));
marked.setOptions({ renderer });

const renderedContent = computed(() => {
  if (!props.message.content) return '';
  const html = marked.parse(props.message.content) as string;
  return props.message.role === 'assistant' ? decorateCitationMarkers(html) : html;
});

// 角标只显示序号，来源信息仍由下方的来源卡片承载，二者靠点击定位联动。
function decorateCitationMarkers(html: string) {
  const citationCount = props.message.citations?.length || 0;
  if (!citationCount) return html;

  return html
    .split(/(<pre[\s\S]*?<\/pre>|<code[\s\S]*?<\/code>)/g)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;
      return segment.replace(/\[(\d{1,2})\]/g, (match, rawIndex) => {
        const markerIndex = Number(rawIndex);
        if (markerIndex < 1 || markerIndex > citationCount) return match;
        return `<button type="button" class="cite-marker" data-citation-index="${markerIndex}" aria-label="定位到第 ${markerIndex} 条来源" title="定位到第 ${markerIndex} 条来源">${markerIndex}</button>`;
      });
    })
    .join('');
}

async function handleContentClick(event: MouseEvent) {
  const element = event.target as HTMLElement | null;

  const copyButton = element?.closest<HTMLButtonElement>('[data-copy-code]');
  if (copyButton) {
    await copyCode(copyButton);
    return;
  }

  const marker = element?.closest<HTMLElement>('[data-citation-index]');
  if (marker) {
    await focusSourceCard(Number(marker.dataset.citationIndex || 0));
  }
}

async function copyCode(button: HTMLButtonElement) {
  try {
    await navigator.clipboard?.writeText(decodeURIComponent(button.dataset.copyCode || ''));
  } catch {
    // 剪贴板不可用时仍给出反馈，用户可手动选取复制。
  }
  markCodeCopied(button);
}

function markCodeCopied(button: HTMLButtonElement) {
  if (copiedTimer) clearTimeout(copiedTimer);
  if (copiedButton && copiedButton !== button) {
    copiedButton.classList.remove('is-copied');
    copiedButton.textContent = '复制';
  }
  copiedButton = button;
  button.classList.add('is-copied');
  button.textContent = '已复制';
  copiedTimer = setTimeout(() => {
    button.classList.remove('is-copied');
    button.textContent = '复制';
    copiedButton = null;
    copiedTimer = null;
  }, 1400);
}

async function focusSourceCard(markerIndex: number) {
  if (!markerIndex) return;
  await nextTick();

  const cards = citationsArea.value?.querySelectorAll<HTMLElement>('.source-card');
  const card = cards?.[markerIndex - 1];
  if (!card) return;

  const header = card.closest('.el-collapse-item')?.querySelector<HTMLElement>('.el-collapse-item__header');
  const collapsed = card.offsetParent === null || card.getBoundingClientRect().height === 0;
  if (header && collapsed) {
    header.click();
    await nextTick();
  }

  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  card.scrollIntoView?.({ block: 'center', behavior: reducedMotion ? 'auto' : 'smooth' });

  citationsArea.value?.querySelector('.source-card.is-citation-target')?.classList.remove('is-citation-target');
  card.classList.add('is-citation-target');
  if (highlightTimer) clearTimeout(highlightTimer);
  highlightTimer = setTimeout(() => {
    card.classList.remove('is-citation-target');
    highlightTimer = null;
  }, 1200);
}

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer);
  if (highlightTimer) clearTimeout(highlightTimer);
});

function openFeedback() {
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
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
}

.message-row.assistant .message-avatar {
  background: var(--blue-600);
  color: var(--el-color-white);
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
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.meta-badge {
  font-size: var(--text-caption);
  padding: 2px 6px;
  background: var(--bg-panel-muted);
  border-radius: var(--radius-xs);
  color: var(--text-muted);
}

.agent-badge {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.message-bubble {
  font-size: var(--text-body);
  line-height: 1.6;
  color: var(--text-primary);
  border-radius: var(--radius-md);
}

.message-bubble.user {
  background: var(--bg-panel-muted);
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
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  border: 1px solid var(--blue-50);
  color: var(--text-secondary);
  font-size: var(--text-caption);
}

.answer-basis__label {
  font-weight: 600;
  color: var(--text-info-strong);
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  color: var(--text-muted);
  font-size: var(--text-body);
}

.dot {
  width: 6px;
  height: 6px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing-pulse 1.2s var(--ease-enter) infinite;
}

@keyframes typing-pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.safety-alert {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  margin-bottom: 8px;
}

.safety-alert.error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-5);
}

.safety-icon {
  font-size: var(--text-body);
}

.safety-content strong {
  display: block;
  font-size: var(--text-caption);
  color: var(--text-warning-heading);
}

.safety-alert.error .safety-content strong {
  color: var(--text-danger-heading);
}

.safety-content p {
  margin: 4px 0 0;
  font-size: var(--text-caption);
  color: var(--text-warning-body);
}

.safety-alert.error .safety-content p {
  color: var(--text-danger-body);
}

/* 代码块配色为独立主题（GitHub-Dark 系），不并入全局语义 token；
   改配色请整体替换下面这一节，勿逐值拆散。 */
:deep(.markdown-body p) { margin-bottom: 1em; }
:deep(.markdown-body p:last-child) { margin-bottom: 0; }
:deep(.markdown-body pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  overflow-x: auto;
  font-size: var(--text-caption);
  margin: 0;
}

:deep(.code-block-wrapper) {
  border-radius: var(--radius-sm);
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
  font-size: var(--text-caption);
  font-family: var(--font-mono);
}

:deep(.code-copy-btn) {
  background: transparent;
  border: none;
  color: #858585;
  cursor: pointer;
  font-size: var(--text-caption);
  min-width: 3.2em;
  text-align: right;
  transition: color var(--transition-fast);
}

:deep(.code-copy-btn.is-copied) {
  color: var(--blue-500);
}

:deep(.markdown-body code:not(pre code)) {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 4px;
  border-radius: var(--radius-xs);
  font-family: var(--font-mono);
  font-size: var(--text-body);
  color: #eb5757;
}

:deep(.cite-marker) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin: 0 1px;
  vertical-align: text-top;
  border: none;
  border-radius: var(--radius-xs);
  background: var(--blue-50);
  color: var(--blue-600);
  font-family: var(--font-body);
  font-size: var(--text-caption);
  line-height: 1;
  cursor: pointer;
  transition: color var(--transition-fast), background-color var(--transition-fast);
}

@media (hover: hover) and (pointer: fine) {
  :deep(.cite-marker:hover) {
    background: var(--blue-600);
    color: var(--bg-panel);
  }
}

:deep(.source-card.is-citation-target) {
  outline: 2px solid var(--blue-500);
  outline-offset: 2px;
}

.answer-basis__score {
  color: var(--text-muted);
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

.text-action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-caption);
  color: var(--blue-600);
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
}

.feedback-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  font-size: var(--text-h2);
  opacity: 0.6;
}

.feedback-btn:focus-visible {
  outline: 2px solid var(--blue-600);
  outline-offset: 2px;
}

.feedback-btn.active {
  opacity: 1;
}

@media (hover: hover) and (pointer: fine) {
  .feedback-btn:hover {
    opacity: 1;
  }
}

.feedback-panel h4 {
  margin: 0 0 8px;
  font-size: var(--text-body);
}

.feedback-desc {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font-size: var(--text-caption);
}

.feedback-panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
