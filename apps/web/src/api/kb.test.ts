import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  buildKnowledgeBatchSignature,
  buildKnowledgeRebuildSignature,
  dryRunKnowledgeDocuments,
  ingestKnowledgeDocuments,
  rebuildKnowledgeDocuments,
  rebuildKnowledgeDocument,
} from './kb';

beforeEach(() => {
  requestPost.mockReset();
});

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

  it('posts batch dry-run and ingest payloads to fixed non-v1 endpoints', () => {
    const payload = {
      documents: [
        {
          base_id: 'base-1',
          file_name: 'policy.txt',
          content: 'Policy content',
        },
      ],
    };

    dryRunKnowledgeDocuments(payload);
    ingestKnowledgeDocuments(payload);

    expect(requestPost).toHaveBeenNthCalledWith(
      1,
      '/knowledge_base/batch-dry-run',
      payload,
      { baseURL: '/api' },
    );
    expect(requestPost).toHaveBeenNthCalledWith(
      2,
      '/knowledge_base/batch-ingest',
      payload,
      { baseURL: '/api' },
    );
  });

  it('builds stable batch signatures independent of object key order', () => {
    const left = buildKnowledgeBatchSignature({
      documents: [{ base_id: 'base-1', file_name: 'a.txt', content: 'hello' }],
    });
    const right = buildKnowledgeBatchSignature({
      documents: [{ content: 'hello', file_name: 'a.txt', base_id: 'base-1' }],
    });

    expect(left).toBe(right);
  });

  it('rebuilds unique document ids through the existing fixed rebuild helper', async () => {
    requestPost.mockResolvedValue({ chunk_count: 3 });

    const result = await rebuildKnowledgeDocuments({ document_ids: [' doc-1 ', 'doc-1', 'doc-2'] });

    expect(requestPost).toHaveBeenCalledTimes(2);
    expect(requestPost).toHaveBeenNthCalledWith(
      1,
      '/knowledge_base/rebuild',
      {
        doc_id: 'doc-1',
        dry_run: false,
        signature: buildKnowledgeRebuildSignature({ doc_id: 'doc-1' }),
      },
      { baseURL: '/api' },
    );
    expect(requestPost).toHaveBeenNthCalledWith(
      2,
      '/knowledge_base/rebuild',
      {
        doc_id: 'doc-2',
        dry_run: false,
        signature: buildKnowledgeRebuildSignature({ doc_id: 'doc-2' }),
      },
      { baseURL: '/api' },
    );
    expect(result.succeeded_documents).toBe(2);
    expect(result.failed_documents).toBe(0);
  });
});
