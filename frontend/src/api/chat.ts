import request from './request';

export interface ChatSession {
    id: string;
    title: string;
    created_at: string;
}

export function createSession(title?: string) {
    return request.post<ChatSession>('/chat/sessions', { title });
}

export function getSessions() {
    return request.get<{ items: ChatSession[]; count: number }>('/chat/sessions');
}

export interface ChatScope {
    mode: 'single' | 'multi';
    corpus_ids: string[];
    document_ids?: string[];
    allow_common_knowledge: boolean;
}

export interface SendMessageRequest {
    question: string;
    scope: ChatScope;
}

export function sendMessage(sessionId: string, data: SendMessageRequest) {
    return request.post<any>(`/chat/sessions/${sessionId}/messages`, data);
}
