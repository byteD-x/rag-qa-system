import request, { createIdempotencyKey, streamRequest, type StreamRequestOptions } from './request';

export interface ChatScope {
  mode: 'single' | 'multi' | 'all';
  corpus_ids: string[];
  document_ids: string[];
  allow_common_knowledge: boolean;
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

export function createChatSession(data: { title?: string; scope?: ChatScope }) {
  return request.post('/chat/sessions', data);
}

export function listChatSessions() {
  return request.get('/chat/sessions');
}

export function getChatSession(sessionId: string) {
  return request.get(`/chat/sessions/${sessionId}`);
}

export function updateChatSession(sessionId: string, data: { title?: string; scope?: ChatScope }) {
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
  data: { question: string; scope?: ChatScope },
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
  data: { question: string; scope?: ChatScope },
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
