<template>
  <div class="chat-page">
    <section class="chat-hero">
      <div>
        <el-tag type="primary" effect="dark">统一 QA</el-tag>
        <h1>企业知识库的有依据问答</h1>
        <p>支持单库、多库、全库检索；回答默认绑定证据，证据不足时明确拒答。</p>
      </div>
      <div class="hero-actions">
        <el-button plain @click="router.push('/workspace/kb/upload')">上传企业文档</el-button>
      </div>
    </section>

    <section class="chat-layout">
      <el-card shadow="hover" class="panel sessions-panel">
        <template #header>
          <div class="card-head">
            <div>
              <h2>会话</h2>
              <p>统一会话会记住当前检索范围。</p>
            </div>
            <el-button type="primary" plain @click="startDraftSession">新会话</el-button>
          </div>
        </template>

        <el-empty v-if="!sessions.length" description="当前还没有会话" />
        <div v-else class="session-list">
          <button
            v-for="session in sessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === activeSessionId }"
            @click="selectSession(session)"
          >
            <strong>{{ session.title || '未命名会话' }}</strong>
            <span>{{ summarizeScope(session.scope_json) }}</span>
          </button>
        </div>
      </el-card>

      <el-card shadow="hover" class="panel conversation-panel">
        <template #header>
          <div class="card-head">
            <div>
              <h2>{{ activeSessionTitle }}</h2>
              <p>{{ currentScopeSummary }}</p>
            </div>
            <el-tag :type="activeEvidenceStatus === 'grounded' ? 'success' : activeEvidenceStatus === 'partial' ? 'warning' : 'info'" effect="plain">
              {{ activeEvidenceStatusLabel }}
            </el-tag>
          </div>
        </template>

        <div class="message-list">
          <el-empty v-if="!messages.length" description="设定范围后开始提问" />
          <div v-else v-for="message in messages" :key="message.id" class="message-item" :class="message.role">
            <div class="message-bubble">
              <div class="message-meta">
                <strong>{{ message.role === 'user' ? '用户' : '助手' }}</strong>
                <span v-if="message.role === 'assistant'">{{ message.answer_mode || 'grounded' }}</span>
              </div>
              <p>{{ message.content }}</p>
            </div>
          </div>
        </div>

        <div class="composer">
          <el-input
            v-model="question"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="例如：报销审批需要哪些角色签字？试用期请假怎么走流程？"
            @keydown.ctrl.enter.prevent="ask"
          />
          <div class="composer-actions">
            <span>Ctrl + Enter 发送</span>
            <el-button type="primary" :loading="asking" @click="ask">发送</el-button>
          </div>
        </div>
      </el-card>

      <div class="side-column">
        <el-card shadow="hover" class="panel">
          <template #header>
            <div class="card-head">
              <div>
                <h2>检索范围</h2>
                <p>默认不允许知识库外常识补全。</p>
              </div>
            </div>
          </template>

          <el-form label-position="top">
            <el-form-item label="模式">
              <el-radio-group v-model="scopeMode" @change="handleScopeModeChange">
                <el-radio-button label="single">单库</el-radio-button>
                <el-radio-button label="multi">多库</el-radio-button>
                <el-radio-button label="all">全库</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="知识库">
              <el-select
                v-model="selectedCorpusIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                filterable
                placeholder="选择要参与检索的知识库"
                @change="handleCorpusChange"
              >
                <el-option
                  v-for="corpus in kbCorpora"
                  :key="corpus.corpus_id"
                  :label="`${corpus.name} (${corpus.queryable_document_count}/${corpus.document_count})`"
                  :value="corpus.corpus_id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="文档缩圈">
              <el-select
                v-model="selectedDocumentIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                filterable
                :disabled="!documentOptions.length"
                placeholder="可选，进一步缩小到具体文档"
              >
                <el-option
                  v-for="document in documentOptions"
                  :key="document.document_id"
                  :label="`${document.display_name} (${statusMeta(document.status).label})`"
                  :value="document.document_id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="hover" class="panel">
          <CitationList :citations="activeCitations" title="证据链" mode="kb" />
        </el-card>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import CitationList from '@/components/CitationList.vue';
import {
  createChatSession,
  defaultChatScope,
  listChatCorpora,
  listChatCorpusDocuments,
  listChatMessages,
  listChatSessions,
  sendChatMessage,
  type ChatScope
} from '@/api/chat';
import { statusMeta } from '@/utils/status';

const router = useRouter();
const route = useRoute();

const corpora = ref<any[]>([]);
const sessions = ref<any[]>([]);
const messages = ref<any[]>([]);
const documentsByCorpus = ref<Record<string, any[]>>({});

const activeSessionId = ref('');
const question = ref('');
const asking = ref(false);

const scopeMode = ref<'single' | 'multi' | 'all'>('all');
const selectedCorpusIds = ref<string[]>([]);
const selectedDocumentIds = ref<string[]>([]);

const kbCorpora = computed(() => corpora.value.filter((item) => item.corpus_type === 'kb'));

const documentOptions = computed(() => {
  const ids = new Set(selectedCorpusIds.value);
  return Object.values(documentsByCorpus.value)
    .flat()
    .filter((item: any) => ids.has(item.corpus_id) && item.query_ready);
});

const activeSessionTitle = computed(() => {
  if (!activeSessionId.value) {
    return '新会话';
  }
  const session = sessions.value.find((item) => item.id === activeSessionId.value);
  return session?.title || '未命名会话';
});

const activeAssistantMessage = computed(() => {
  const assistantMessages = messages.value.filter((item) => item.role === 'assistant');
  return assistantMessages[assistantMessages.length - 1] || null;
});

const activeCitations = computed(() => activeAssistantMessage.value?.citations || []);
const activeEvidenceStatus = computed(() => activeAssistantMessage.value?.evidence_status || '');
const activeEvidenceStatusLabel = computed(() => {
  if (activeEvidenceStatus.value === 'grounded') {
    return '证据充分';
  }
  if (activeEvidenceStatus.value === 'partial') {
    return '证据部分充分';
  }
  if (activeEvidenceStatus.value === 'insufficient') {
    return '证据不足';
  }
  return '待提问';
});

const currentScopeSummary = computed(() => summarizeScope(buildScope()));

function buildScope(): ChatScope {
  return {
    mode: scopeMode.value,
    corpus_ids: [...selectedCorpusIds.value],
    document_ids: [...selectedDocumentIds.value],
    allow_common_knowledge: false
  };
}

function summarizeScope(scope: Partial<ChatScope> | Record<string, any>): string {
  const mode = String(scope.mode || 'all');
  const corporaCount = Array.isArray(scope.corpus_ids) ? scope.corpus_ids.length : 0;
  const docsCount = Array.isArray(scope.document_ids) ? scope.document_ids.length : 0;
  if (mode === 'single') {
    return `单库 · ${corporaCount} 个知识库 · ${docsCount} 个文档`;
  }
  if (mode === 'multi') {
    return `多库 · ${corporaCount} 个知识库 · ${docsCount} 个文档`;
  }
  return docsCount ? `全库 · ${docsCount} 个文档缩圈` : '全库 · 全部可查文档';
}

async function loadCorpora() {
  const res: any = await listChatCorpora();
  corpora.value = res.items || [];
}

async function loadSessions() {
  const res: any = await listChatSessions();
  sessions.value = res.items || [];
}

async function ensureDocuments(corpusIds: string[]) {
  const targets = corpusIds.filter((corpusId) => !documentsByCorpus.value[corpusId]);
  if (!targets.length) {
    return;
  }
  const results = await Promise.all(targets.map((corpusId) => listChatCorpusDocuments(corpusId)));
  targets.forEach((corpusId, index) => {
    documentsByCorpus.value[corpusId] = (results[index] as any).items || [];
  });
}

function applyScope(scope: Partial<ChatScope> | Record<string, any> | null | undefined) {
  const normalized = {
    ...defaultChatScope(),
    ...(scope || {})
  };
  scopeMode.value = normalized.mode as 'single' | 'multi' | 'all';
  selectedCorpusIds.value = [...(normalized.corpus_ids || [])];
  selectedDocumentIds.value = [...(normalized.document_ids || [])];
}

async function selectSession(session: any) {
  activeSessionId.value = String(session.id || '');
  applyScope(session.scope_json || defaultChatScope());
  await ensureDocuments(selectedCorpusIds.value);
  const res: any = await listChatMessages(activeSessionId.value);
  messages.value = res.items || [];
}

function startDraftSession() {
  activeSessionId.value = '';
  messages.value = [];
  question.value = '';
  applyScope(defaultChatScope());
}

async function ensureSession(): Promise<string> {
  if (activeSessionId.value) {
    return activeSessionId.value;
  }
  const res: any = await createChatSession({
    scope: buildScope()
  });
  activeSessionId.value = String(res.session_id || '');
  await loadSessions();
  return activeSessionId.value;
}

async function handleScopeModeChange() {
  if (scopeMode.value === 'single' && selectedCorpusIds.value.length > 1) {
    selectedCorpusIds.value = selectedCorpusIds.value.slice(0, 1);
  }
  if (scopeMode.value === 'all' && !selectedCorpusIds.value.length) {
    selectedDocumentIds.value = [];
  }
  await ensureDocuments(selectedCorpusIds.value);
}

async function handleCorpusChange() {
  if (scopeMode.value === 'single' && selectedCorpusIds.value.length > 1) {
    selectedCorpusIds.value = selectedCorpusIds.value.slice(-1);
  }
  await ensureDocuments(selectedCorpusIds.value);
  const validDocumentIds = new Set(documentOptions.value.map((item: any) => item.document_id));
  selectedDocumentIds.value = selectedDocumentIds.value.filter((item) => validDocumentIds.has(item));
}

async function applyRoutePreset() {
  const preset = String(route.query.preset || '');
  const baseId = String(route.query.baseId || '');
  const documentId = String(route.query.documentId || '');
  if (preset === 'kb' && baseId) {
    applyScope({
      mode: 'single',
      corpus_ids: [`kb:${baseId}`],
      document_ids: documentId ? [documentId] : []
    });
    await ensureDocuments(selectedCorpusIds.value);
  }
}

async function ask() {
  if (!question.value.trim()) {
    ElMessage.warning('请输入问题');
    return;
  }
  if (scopeMode.value !== 'all' && !selectedCorpusIds.value.length) {
    ElMessage.warning('请先选择知识库范围');
    return;
  }

  asking.value = true;
  try {
    const sessionId = await ensureSession();
    const currentQuestion = question.value.trim();
    messages.value.push({
      id: `local-user-${Date.now()}`,
      role: 'user',
      content: currentQuestion
    });
    question.value = '';
    const res: any = await sendChatMessage(sessionId, {
      question: currentQuestion,
      scope: buildScope()
    });
    messages.value.push(res.message);
    await loadSessions();
  } finally {
    asking.value = false;
  }
}

onMounted(async () => {
  await loadCorpora();
  await loadSessions();
  await applyRoutePreset();
  if (route.query.sessionId) {
    const session = sessions.value.find((item) => item.id === route.query.sessionId);
    if (session) {
      await selectSession(session);
      return;
    }
  }
  if (sessions.value.length) {
    await selectSession(sessions.value[0]);
  }
});
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chat-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 30px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(15, 118, 110, 0.18), transparent 30%),
    linear-gradient(135deg, #ffffff, #f8fafc);
}

.chat-hero h1 {
  margin: 12px 0 8px;
  font-size: 34px;
}

.chat-hero p {
  margin: 0;
  color: var(--text-regular);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.chat-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 360px;
  gap: 20px;
}

.panel {
  border-radius: 24px;
  border: none;
}

.panel :deep(.el-card__body) {
  padding: 24px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.card-head h2 {
  margin: 0;
}

.card-head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.session-item.active {
  border-color: rgba(37, 99, 235, 0.4);
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.08);
}

.session-item span {
  font-size: 12px;
  color: var(--text-secondary);
}

.conversation-panel {
  display: flex;
  flex-direction: column;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 420px;
  max-height: 640px;
  overflow: auto;
}

.message-item {
  display: flex;
}

.message-item.user {
  justify-content: flex-end;
}

.message-item.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 84%;
  padding: 16px 18px;
  border-radius: 20px;
  line-height: 1.7;
}

.message-item.user .message-bubble {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(15, 118, 110, 0.1));
}

.message-item.assistant .message-bubble {
  background: rgba(15, 23, 42, 0.04);
}

.message-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.message-bubble p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.composer-actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 12px;
}

.side-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

@media (max-width: 1280px) {
  .chat-layout {
    grid-template-columns: 1fr;
  }
}
</style>
