import { defineStore } from 'pinia';
import { ref, computed, nextTick } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  createChatSession,
  deleteChatSession,
  defaultChatScope,
  listChatCorpora,
  listChatCorpusDocuments,
  listChatMessages,
  listChatSessions,
  streamChatMessage,
  updateChatSession,
  submitMessageFeedback,
  type ChatScope
} from '@/api/chat';
import { createIdempotencyKey, isAbortRequestError, isHandledRequestError } from '@/api/request';
import { buildSafetyNotice } from '@/utils/safety';

export const useChatStore = defineStore('chat', () => {
  const corpora = ref<any[]>([]);
  const sessions = ref<any[]>([]);
  const messages = ref<any[]>([]);
  const documentsByCorpus = ref<Record<string, any[]>>({});

  const activeSessionId = ref('');
  const asking = ref(false);
  let currentController: AbortController | null = null;

  const scopeMode = ref<'single' | 'multi' | 'all'>('all');
  const selectedCorpusIds = ref<string[]>([]);
  const selectedDocumentIds = ref<string[]>([]);
  const allowCommonKnowledge = ref(false);
  const executionMode = ref<'grounded' | 'agent'>('grounded');

  const kbCorpora = computed(() => corpora.value.filter((item) => item.corpus_type === 'kb'));

  const documentOptions = computed(() => {
    const ids = new Set(selectedCorpusIds.value);
    return Object.values(documentsByCorpus.value)
      .flat()
      .filter((item: any) => ids.has(item.corpus_id) && item.query_ready);
  });

  const activeSessionTitle = computed(() => {
    if (!activeSessionId.value) {
      return '新对话';
    }
    const session = sessions.value.find((item) => item.id === activeSessionId.value);
    return session?.title || '未命名对话';
  });

  const hasStreamingAssistant = computed(() => messages.value.some((item: any) => item.role === 'assistant' && item.streaming));

  function buildScope(): ChatScope {
    return {
      mode: scopeMode.value,
      corpus_ids: [...selectedCorpusIds.value],
      document_ids: [...selectedDocumentIds.value],
      allow_common_knowledge: allowCommonKnowledge.value
    };
  }

  function applyScope(scope: Partial<ChatScope> | Record<string, any> | null | undefined) {
    const normalized = {
      ...defaultChatScope(),
      ...(scope || {})
    };
    scopeMode.value = normalized.mode as 'single' | 'multi' | 'all';
    selectedCorpusIds.value = [...(normalized.corpus_ids || [])];
    selectedDocumentIds.value = [...(normalized.document_ids || [])];
    allowCommonKnowledge.value = Boolean(normalized.allow_common_knowledge);
  }

  function attachMessageSafety(message: any) {
    if (!message || message.role !== 'assistant') {
      return message;
    }
    return {
      ...message,
      safety_notice: buildSafetyNotice({
        answerMode: message.answer_mode,
        evidenceStatus: message.evidence_status,
        refusalReason: message.refusal_reason,
        safety: message.safety
      })
    };
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

  function stopStreaming() {
    currentController?.abort();
    currentController = null;
    messages.value = messages.value
      .filter((item: any) => !(item?.streaming && item.role === 'assistant' && !String(item.content || item.answer || '').trim()))
      .map((item: any) => item?.streaming ? attachMessageSafety({ ...item, streaming: false }) : item);
    asking.value = false;
  }

  async function selectSession(session: any) {
    stopStreaming();
    activeSessionId.value = String(session.id || '');
    applyScope(session.scope_json || defaultChatScope());
    executionMode.value = session.execution_mode === 'agent' ? 'agent' : 'grounded';
    await ensureDocuments(selectedCorpusIds.value);
    const res: any = await listChatMessages(activeSessionId.value);
    messages.value = (res.items || []).map((item: any) => attachMessageSafety(item));
  }

  function startDraftSession() {
    stopStreaming();
    activeSessionId.value = '';
    messages.value = [];
    applyScope(defaultChatScope());
    executionMode.value = 'grounded';
  }

  async function renameActiveSession() {
    if (!activeSessionId.value) {
      ElMessage.warning('请先选择会话');
      return;
    }
    const currentTitle = activeSessionTitle.value === '未命名对话' ? '' : activeSessionTitle.value;
    let value = '';
    try {
      const promptResult = await ElMessageBox.prompt('输入新的会话标题', '重命名', {
        inputValue: currentTitle,
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputPattern: /\\S+/,
        inputErrorMessage: '标题不能为空'
      });
      value = promptResult.value;
    } catch {
      return;
    }
    const nextTitle = value.trim();
    await updateChatSession(activeSessionId.value, { title: nextTitle });
    await loadSessions();
    ElMessage.success('已更新');
  }

  async function handleDeleteSession() {
    if (!activeSessionId.value) {
      ElMessage.warning('请先选择会话');
      return;
    }
    try {
      await ElMessageBox.confirm('删除后对话记录将不可恢复。', '确认删除?', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      });
    } catch {
      return;
    }
    const removedSessionId = activeSessionId.value;
    await deleteChatSession(removedSessionId);
    await loadSessions();
    const nextSession = sessions.value.find((item) => String(item.id) !== removedSessionId);
    if (nextSession) {
      await selectSession(nextSession);
    } else {
      startDraftSession();
    }
    ElMessage.success('已删除');
  }

  async function ensureSession(): Promise<string> {
    if (activeSessionId.value) {
      return activeSessionId.value;
    }
    const res: any = await createChatSession({
      scope: buildScope(),
      execution_mode: executionMode.value
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
    if (activeSessionId.value) {
      await updateChatSession(activeSessionId.value, { scope: buildScope() });
    }
  }

  async function handleExecutionModeChange() {
    if (activeSessionId.value) {
      await updateChatSession(activeSessionId.value, { execution_mode: executionMode.value });
      await loadSessions();
    }
  }

  async function handleCorpusChange() {
    if (scopeMode.value === 'single' && selectedCorpusIds.value.length > 1) {
      selectedCorpusIds.value = selectedCorpusIds.value.slice(-1);
    }
    await ensureDocuments(selectedCorpusIds.value);
    const validDocumentIds = new Set(documentOptions.value.map((item: any) => item.document_id));
    selectedDocumentIds.value = selectedDocumentIds.value.filter((item) => validDocumentIds.has(item));
    if (activeSessionId.value) {
      await updateChatSession(activeSessionId.value, { scope: buildScope() });
    }
  }

  function updateStreamingAssistant(messageId: string, updater: (current: any) => any) {
    const index = messages.value.findIndex((item: any) => item.id === messageId);
    if (index < 0) {
      return;
    }
    messages.value[index] = attachMessageSafety(updater({ ...messages.value[index] }));
  }

  async function ask(currentQuestion: string, onScrollRequest: (smooth: boolean) => void) {
    if (asking.value || !currentQuestion.trim()) return;

    if (scopeMode.value !== 'all' && !selectedCorpusIds.value.length) {
      ElMessage.warning('请先选择知识库范围');
      return;
    }

    stopStreaming();
    asking.value = true;
    try {
      const sessionId = await ensureSession();
      const streamMessageId = `local-assistant-${Date.now()}`;

      messages.value.push({
        id: `local-user-${Date.now()}`,
        role: 'user',
        content: currentQuestion
      });

      messages.value.push(attachMessageSafety({
        id: streamMessageId,
        session_id: sessionId,
        role: 'assistant',
        content: '',
        answer: '',
        answer_mode: '',
        execution_mode: executionMode.value,
        evidence_status: 'streaming',
        grounding_score: 0,
        refusal_reason: '',
        citations: [],
        evidence_path: [],
        retrieval: null,
        latency: null,
        cost: null,
        provider: '',
        model: '',
        usage: {},
        safety: null,
        streaming: true,
        isRetrieving: true // Use to distinguish between retrieval and generation phase
      }));

      await nextTick();
      onScrollRequest(true);

      const idempotencyKey = createIdempotencyKey(`chat:${sessionId}`);
      const controller = new AbortController();
      currentController = controller;

      await streamChatMessage(sessionId, {
        question: currentQuestion,
        scope: buildScope(),
        execution_mode: executionMode.value
      }, {
        idempotencyKey,
        signal: controller.signal,
        onEvent: (event) => {
          if (!event.data || typeof event.data !== 'object') return;
          const payload = event.data as Record<string, any>;
          const eventName = event.event;

          if (eventName === 'metadata') {
            updateStreamingAssistant(streamMessageId, (current) => ({
              ...current,
              answer_mode: String(payload.answer_mode || current.answer_mode || ''),
              execution_mode: String(payload.execution_mode || current.execution_mode || ''),
              evidence_status: String(payload.evidence_status || current.evidence_status || ''),
              grounding_score: Number(payload.grounding_score ?? current.grounding_score ?? 0),
              refusal_reason: String(payload.refusal_reason || current.refusal_reason || ''),
              safety: payload.safety ?? current.safety ?? null,
              retrieval: payload.retrieval || current.retrieval || null,
              strategy_used: String(payload.strategy_used || current.strategy_used || ''),
              workflow_run: payload.workflow_run || current.workflow_run || null,
              isRetrieving: false // Switch state once we have metadata
            }));
          } else if (eventName === 'citation') {
            updateStreamingAssistant(streamMessageId, (current) => {
              const citations = Array.isArray(current.citations) ? [...current.citations] : [];
              const citationKey = `${String(payload.unit_id || '')}:${String(payload.char_range || '')}`;
              const exists = citations.some((item: any) => `${String(item.unit_id || '')}:${String(item.char_range || '')}` === citationKey);
              if (!exists) citations.push(payload);
              return { ...current, citations, isRetrieving: false };
            });
          } else if (eventName === 'answer') {
            updateStreamingAssistant(streamMessageId, (current) => ({
              ...current,
              content: String(payload.answer || current.content || ''),
              answer: String(payload.answer || current.answer || ''),
              grounding_score: Number(payload.grounding_score ?? current.grounding_score ?? 0),
              refusal_reason: String(payload.refusal_reason || current.refusal_reason || ''),
              safety: payload.safety ?? current.safety ?? null,
              isRetrieving: false
            }));
            onScrollRequest(false);
          } else if (eventName === 'message') {
            updateStreamingAssistant(streamMessageId, (current) => ({
              ...current,
              ...payload,
              id: String(payload.id || current.id),
              content: String(payload.content || payload.answer || current.content || ''),
              answer: String(payload.answer || current.answer || ''),
              citations: Array.isArray(payload.citations) ? payload.citations : (current.citations || []),
              safety: payload.safety ?? current.safety ?? null,
              retrieval: payload.retrieval || current.retrieval || null,
              latency: payload.latency || current.latency || null,
              cost: payload.cost || current.cost || null,
              usage: payload.usage || current.usage || {},
              workflow_run: payload.workflow_run || current.workflow_run || null,
              streaming: false,
              isRetrieving: false
            }));
            onScrollRequest(true);
          } else if (eventName === 'done') {
            updateStreamingAssistant(streamMessageId, (current) => ({
              ...current,
              streaming: false,
              isRetrieving: false
            }));
          } else if (eventName === 'error') {
            updateStreamingAssistant(streamMessageId, (current) => ({
              ...current,
              streaming: false,
              isRetrieving: false
            }));
            throw new Error(String(payload.detail || 'stream chat failed'));
          }
        }
      });
      await loadSessions();
    } catch (error: any) {
      if (isAbortRequestError(error)) return;
      messages.value = messages.value.filter((item: any) => !(item?.streaming && item.role === 'assistant' && !String(item.content || item.answer || '').trim()));
      if (isHandledRequestError(error)) return;
      ElMessage.error('问答失败，请重试');
    } finally {
      currentController = null;
      messages.value = messages.value.map((item: any) => item?.streaming ? attachMessageSafety({ ...item, streaming: false }) : item);
      asking.value = false;
    }
  }

  async function handleFeedback(message: any, verdict: 'up' | 'down', feedbackData?: any) {
    if (!activeSessionId.value || !message || !message.id || message.id.startsWith('temp-')) return;
    const originalVerdict = message.feedback?.verdict;
    const newVerdict = originalVerdict === verdict && !feedbackData ? undefined : verdict;

    message.feedback = message.feedback || {};
    message.feedback.verdict = newVerdict;

    try {
      if (newVerdict) {
        await submitMessageFeedback(activeSessionId.value, message.id, {
          verdict: newVerdict,
          ...feedbackData
        });
      }
      if (newVerdict === 'up') {
        ElMessage.success('已提交好评，谢谢反馈！');
      } else if (feedbackData) {
        ElMessage.success('已提交详情，感谢帮助改进模型');
      }
    } catch (e: any) {
      message.feedback.verdict = originalVerdict;
      if (!isAbortRequestError(e) && !isHandledRequestError(e)) {
        ElMessage.error('提交反馈失败');
      }
      throw e;
    }
  }

  return {
    corpora,
    sessions,
    messages,
    documentsByCorpus,
    activeSessionId,
    asking,
    scopeMode,
    selectedCorpusIds,
    selectedDocumentIds,
    allowCommonKnowledge,
    executionMode,
    kbCorpora,
    documentOptions,
    activeSessionTitle,
    hasStreamingAssistant,
    loadCorpora,
    loadSessions,
    applyScope,
    selectSession,
    startDraftSession,
    renameActiveSession,
    handleDeleteSession,
    handleScopeModeChange,
    handleExecutionModeChange,
    handleCorpusChange,
    stopStreaming,
    ask,
    handleFeedback
  };
});
