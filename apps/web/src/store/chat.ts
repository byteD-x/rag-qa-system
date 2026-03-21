import { defineStore } from 'pinia';
import { ref, computed, nextTick } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  createChatSession,
  createChatRunV2,
  deleteChatSession,
  defaultChatScope,
  getChatRunV2,
  listChatCorpora,
  listChatCorpusDocuments,
  listChatMessages,
  listChatSessions,
  listWorkflowRuns,
  resumeChatRunV2,
  submitMessageFeedback,
  updateChatSession,
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
    if (!message || message.role !== 'assistant' || message.message_kind === 'interrupt') {
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

  function buildInterruptMessage(run: any, interrupt: any) {
    const payload = interrupt?.payload || run?.workflow_state?.interrupt || {};
    return {
      id: `interrupt-${String(run?.id || interrupt?.run_id || Date.now())}`,
      role: 'assistant',
      message_kind: 'interrupt',
      content: '',
      answer: '',
      answer_mode: 'clarification',
      execution_mode: String(run?.execution_mode || executionMode.value || 'grounded'),
      workflow_run: run || null,
      interrupt: {
        id: String(interrupt?.id || run?.interrupt_id || ''),
        run_id: String(run?.id || interrupt?.run_id || ''),
        kind: String(payload.kind || ''),
        title: String(payload.title || '需要补充信息'),
        detail: String(payload.detail || ''),
        question: String(payload.question || ''),
        options: Array.isArray(payload.options) ? payload.options.map((option: any) => ({
          ...option,
          badges: Array.isArray(option?.badges) ? option.badges : [],
          meta: option?.meta || {}
        })) : [],
        recommended_option_id: String(payload.recommended_option_id || ''),
        allow_free_text: Boolean(payload.allow_free_text),
        fallback_prompt: String(payload.fallback_prompt || ''),
        subject: payload?.subject || null
      },
      submitting: false,
      resolved: false
    };
  }

  function buildAssistantMessage(result: any) {
    const message = {
      ...(result?.message || {}),
      role: String(result?.message?.role || 'assistant'),
      content: String(result?.message?.content || result?.message?.answer || result?.answer || ''),
      answer: String(result?.message?.answer || result?.answer || result?.message?.content || ''),
      workflow_run: result?.run || null
    };
    return attachMessageSafety(message);
  }

  function appendPendingInterrupt(run: any, interrupt: any) {
    const nextMessage = buildInterruptMessage(run, interrupt);
    const existingIndex = messages.value.findIndex((item: any) => item.id === nextMessage.id);
    if (existingIndex >= 0) {
      messages.value[existingIndex] = nextMessage;
      return;
    }
    messages.value.push(nextMessage);
  }

  function resolveInterruptMessage(runId: string) {
    const interruptId = `interrupt-${runId}`;
    const index = messages.value.findIndex((item: any) => item.id === interruptId);
    if (index >= 0) {
      messages.value[index] = {
        ...messages.value[index],
        submitting: false,
        resolved: true
      };
    }
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

  async function hydratePendingInterrupt(sessionId: string) {
    const workflowRes: any = await listWorkflowRuns(sessionId);
    const runs = Array.isArray(workflowRes?.items) ? workflowRes.items : [];
    const pendingRun = [...runs].reverse().find((item: any) => item.status === 'interrupted' && item.interrupt_id);
    if (!pendingRun) {
      return;
    }
    const detail: any = await getChatRunV2(String(pendingRun.id));
    if (detail?.run?.status !== 'interrupted' || !detail?.interrupt?.payload) {
      return;
    }
    appendPendingInterrupt(detail.run, detail.interrupt);
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
    await hydratePendingInterrupt(activeSessionId.value);
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
        inputPattern: /\S+/,
        inputErrorMessage: '标题不能为空'
      });
      value = promptResult.value;
    } catch {
      return;
    }
    await updateChatSession(activeSessionId.value, { title: value.trim() });
    await loadSessions();
    ElMessage.success('已更新');
  }

  async function handleDeleteSession() {
    if (!activeSessionId.value) {
      ElMessage.warning('请先选择会话');
      return;
    }
    try {
      await ElMessageBox.confirm('删除后对话记录将不可恢复。', '确认删除', {
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

  async function ask(currentQuestion: string, onScrollRequest: (smooth: boolean) => void) {
    if (asking.value || !currentQuestion.trim()) return;

    if (scopeMode.value !== 'all' && !selectedCorpusIds.value.length) {
      ElMessage.warning('请先选择知识范围');
      return;
    }

    stopStreaming();
    asking.value = true;
    try {
      const sessionId = await ensureSession();
      const pendingMessageId = `local-assistant-${Date.now()}`;

      messages.value.push({
        id: `local-user-${Date.now()}`,
        role: 'user',
        content: currentQuestion
      });

      messages.value.push(attachMessageSafety({
        id: pendingMessageId,
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
        isRetrieving: true
      }));

      await nextTick();
      onScrollRequest(true);

      const result: any = await createChatRunV2(sessionId, {
        question: currentQuestion,
        scope: buildScope(),
        execution_mode: executionMode.value
      }, {
        idempotencyKey: createIdempotencyKey(`chat:${sessionId}`)
      });

      messages.value = messages.value.filter((item: any) => item.id !== pendingMessageId);
      if (result?.status === 'interrupted' && result?.run) {
        appendPendingInterrupt(result.run, result.interrupt);
      } else {
        messages.value.push(buildAssistantMessage(result));
      }
      await loadSessions();
      onScrollRequest(true);
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

  async function resumeInterrupt(message: any, payload: {
    selected_option_ids?: string[];
    free_text?: string;
    question?: string;
    allow_common_knowledge?: boolean;
    target_version_ids?: string[];
    effective_at?: string;
  }, onScrollRequest?: (smooth: boolean) => void) {
    const runId = String(message?.interrupt?.run_id || message?.workflow_run?.id || '');
    if (!runId || asking.value) return;
    asking.value = true;
    message.submitting = true;
    try {
      const result: any = await resumeChatRunV2(runId, payload, {
        idempotencyKey: createIdempotencyKey(`chat-resume:${runId}`)
      });
      if (result?.status === 'interrupted' && result?.run) {
        appendPendingInterrupt(result.run, result.interrupt);
      } else {
        resolveInterruptMessage(runId);
        messages.value.push(buildAssistantMessage(result));
      }
      await loadSessions();
      if (onScrollRequest) {
        onScrollRequest(true);
      }
    } catch (error: any) {
      if (!isHandledRequestError(error)) {
        ElMessage.error('补充信息提交失败，请重试');
      }
      throw error;
    } finally {
      message.submitting = false;
      asking.value = false;
    }
  }

  async function handleFeedback(message: any, verdict: 'up' | 'down', feedbackData?: any) {
    if (!activeSessionId.value || !message || !message.id || message.id.startsWith('temp-') || message.message_kind === 'interrupt') return;
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
        ElMessage.success('已提交好评，感谢反馈');
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
    resumeInterrupt,
    handleFeedback
  };
});
