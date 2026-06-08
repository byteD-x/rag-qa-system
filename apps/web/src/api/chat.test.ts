import { beforeEach, describe, expect, it, vi } from 'vitest';

const { requestGet, requestPost } = vi.hoisted(() => ({
  requestGet: vi.fn(),
  requestPost: vi.fn(),
}));

vi.mock('./request', () => ({
  default: {
    get: requestGet,
    post: requestPost,
  },
  createIdempotencyKey: vi.fn((scope = 'req') => `${scope}-test-key`),
  streamRequest: vi.fn(),
}));

import { createChatRunV2, getChatRunV2, resumeChatRunV2 } from './chat';

beforeEach(() => {
  requestGet.mockReset();
  requestPost.mockReset();
});

describe('chat v2 api helpers', () => {
  it('posts chat v2 runs without inheriting the v1 baseURL', () => {
    const payload = { question: 'hello' };

    createChatRunV2('thread-1', payload, { idempotencyKey: 'run-key' });

    expect(requestPost).toHaveBeenCalledWith(
      '/api/v2/chat/threads/thread-1/runs',
      payload,
      {
        baseURL: '',
        headers: { 'Idempotency-Key': 'run-key' },
      },
    );
  });

  it('loads and resumes chat v2 runs without inheriting the v1 baseURL', () => {
    getChatRunV2('run-1');
    resumeChatRunV2('run-1', { free_text: 'more' }, { idempotencyKey: 'resume-key' });

    expect(requestGet).toHaveBeenCalledWith('/api/v2/chat/runs/run-1', { baseURL: '' });
    expect(requestPost).toHaveBeenCalledWith(
      '/api/v2/chat/runs/run-1/resume',
      { free_text: 'more' },
      {
        baseURL: '',
        headers: { 'Idempotency-Key': 'resume-key' },
      },
    );
  });
});
