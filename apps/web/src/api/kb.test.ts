import { describe, expect, it, vi } from 'vitest';

const { requestPost } = vi.hoisted(() => ({
  requestPost: vi.fn(),
}));

vi.mock('./request', () => ({
  default: {
    post: requestPost,
  },
  createIdempotencyKey: vi.fn((scope = 'req') => `${scope}-test-key`),
  streamRequest: vi.fn(),
}));

import {
  buildKnowledgeRebuildSignature,
  rebuildKnowledgeDocument,
} from './kb';

describe('kb api rebuild helpers', () => {
  it('posts controlled rebuild payload to fixed non-v1 endpoint', () => {
    const payload = {
      doc_id: 'doc-1',
      dry_run: true,
      signature: buildKnowledgeRebuildSignature({ doc_id: ' doc-1 ' }),
    };

    rebuildKnowledgeDocument(payload);

    expect(requestPost).toHaveBeenCalledWith(
      '/knowledge_base/rebuild',
      payload,
      { baseURL: '/api' },
    );
    expect(payload.signature).toBe(buildKnowledgeRebuildSignature({ doc_id: 'doc-1' }));
  });
});
