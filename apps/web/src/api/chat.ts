import request, { createIdempotencyKey, streamRequest, type StreamRequestOptions } from './request';

export interface ChatScope {
  mode: 'single' | 'multi' | 'all';
  corpus_ids: string[];
  document_ids: string[];
  allow_common_knowledge: boolean;
  agent_profile_id?: string;
  prompt_template_id?: string;
}

export interface WorkflowRun {
  id: string;
  session_id: string;
  execution_mode: string;
  workflow_kind: string;
  status: string;
  stage: string;
  trace_id?: string;
  message_id?: string;
  workflow_state?: any;
  workflow_events?: any[];
  tool_calls?: any[];
  llm_trace?: any;
  retried_from_run_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatInterruptOption {
  id: string;
  label: string;
  description: string;
  patch?: Record<string, any>;
  badges?: string[];
  meta?: Record<string, any>;
}

export interface ChatInterruptPayload {
  kind: string;
  title: string;
  detail: string;
  question?: string;
  options?: ChatInterruptOption[];
  recommended_option_id?: string;
  allow_free_text?: boolean;
  fallback_prompt?: string;
  subject?: {
    type: string;
    id: string;
    summary: string;
  };
}

export function defaultChatScope(): ChatScope {
  return {
    mode: 'all',
    corpus_ids: [],
    document_ids: [],
    allow_common_knowledge: false
  };
}

export function listChatCorpora() {
  return request.get('/chat/corpora');
}

export function listChatCorpusDocuments(corpusId: string) {
  return request.get(`/chat/corpora/${encodeURIComponent(corpusId)}/documents`);
}

export function createChatSession(data: { title?: string; scope?: ChatScope; execution_mode?: 'grounded' | 'agent' }) {
  return request.post('/chat/sessions', data);
}

export function listChatSessions() {
  return request.get('/chat/sessions');
}

export function getChatSession(sessionId: string) {
  return request.get(`/chat/sessions/${sessionId}`);
}

export function updateChatSession(sessionId: string, data: { title?: string; scope?: ChatScope; execution_mode?: 'grounded' | 'agent' }) {
  return request.patch(`/chat/sessions/${sessionId}`, data);
}

export function deleteChatSession(sessionId: string) {
  return request.delete(`/chat/sessions/${sessionId}`);
}

export function listChatMessages(sessionId: string) {
  return request.get(`/chat/sessions/${sessionId}/messages`);
}

export function sendChatMessage(
  sessionId: string,
  data: { question: string; scope?: ChatScope; execution_mode?: 'grounded' | 'agent' },
  options: { idempotencyKey?: string } = {}
) {
  return request.post(`/chat/sessions/${sessionId}/messages`, data, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('chat-message')
    }
  });
}

export function streamChatMessage(
  sessionId: string,
  data: { question: string; scope?: ChatScope; execution_mode?: 'grounded' | 'agent' },
  options: StreamRequestOptions & { idempotencyKey?: string } = {}
) {
  return streamRequest(`/api/v1/chat/sessions/${sessionId}/messages/stream`, data, {
    ...options,
    headers: {
      ...(options.headers || {}),
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('chat-message-stream')
    }
  });
}

export function listWorkflowRuns(sessionId: string) {
  return request.get(`/chat/sessions/${sessionId}/workflow-runs`);
}

export function getWorkflowRun(runId: string) {
  return request.get(`/chat/workflow-runs/${runId}`).then((response: any) => response.workflow_run || response);
}

export function retryWorkflowRun(runId: string, options: { idempotencyKey?: string } = {}) {
  return request.post(`/chat/workflow-runs/${runId}/retry`, {}, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('workflow-retry')
    }
  });
}

export function createChatRunV2(
  threadId: string,
  data: { question: string; scope?: ChatScope; execution_mode?: 'grounded' | 'agent' },
  options: { idempotencyKey?: string } = {}
) {
  return request.post(`/api/v2/chat/threads/${threadId}/runs`, data, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('chat-v2-run')
    }
  });
}

export function getChatRunV2(runId: string) {
  return request.get(`/api/v2/chat/runs/${runId}`);
}

export function resumeChatRunV2(
  runId: string,
  data: {
    question?: string;
    free_text?: string;
    allow_common_knowledge?: boolean;
    selected_option_ids?: string[];
    target_version_ids?: string[];
    effective_at?: string;
    override_scope?: ChatScope;
  },
  options: { idempotencyKey?: string } = {}
) {
  return request.post(`/api/v2/chat/runs/${runId}/resume`, data, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('chat-v2-resume')
    }
  });
}

export function submitMessageFeedback(
  sessionId: string,
  messageId: string,
  data: {
    verdict: 'up' | 'down';
    reason_code?: string;
    notes?: string;
  }
) {
  return request.put(`/chat/sessions/${sessionId}/messages/${messageId}/feedback`, data);
}
