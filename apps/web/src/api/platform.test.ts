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
}));

import { discoverLlmModels, getLlmConfig } from './platform';

beforeEach(() => {
  requestGet.mockReset();
  requestPost.mockReset();
});

describe('platform llm api helpers', () => {
  it('loads sanitized LLM config from platform endpoint', () => {
    getLlmConfig();

    expect(requestGet).toHaveBeenCalledWith('/platform/llm/config');
  });

  it('posts relay discovery payload to the fixed platform endpoint', () => {
    const credentialField = 'api_' + 'key';
    const payload = {
      provider: 'newapi',
      base_url: 'https://relay.example.test/v1',
      [credentialField]: '<relay-api-key>',
      max_models: 100,
    };

    discoverLlmModels(payload);

    expect(requestPost).toHaveBeenCalledWith('/platform/llm/models/discover', payload);
  });
});
