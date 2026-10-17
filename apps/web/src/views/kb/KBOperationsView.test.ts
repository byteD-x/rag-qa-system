import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  routerPush,
  getKBOperations,
  retryKBIngestJob,
  syncConnector,
  runDueConnectors,
  dryRunKnowledgeDocuments,
  ingestKnowledgeDocuments,
  rebuildKnowledgeDocuments,
  rebuildKnowledgeDocument,
  buildKnowledgeBatchSignature,
  buildKnowledgeRebuildSignature,
  messageSuccess,
  messageError,
  messageWarning,
  messageBoxConfirm,
} = vi.hoisted(() => ({
  routerPush: vi.fn(),
  getKBOperations: vi.fn(),
  retryKBIngestJob: vi.fn(),
  syncConnector: vi.fn(),
  runDueConnectors: vi.fn(),
  dryRunKnowledgeDocuments: vi.fn(),
  ingestKnowledgeDocuments: vi.fn(),
  rebuildKnowledgeDocuments: vi.fn(),
  rebuildKnowledgeDocument: vi.fn(),
  buildKnowledgeBatchSignature: vi.fn((payload: any) => `batch:${JSON.stringify(payload)}`),
  buildKnowledgeRebuildSignature: vi.fn((payload: { doc_id: string }) => `sig:${String(payload.doc_id || '').trim()}`),
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
  messageWarning: vi.fn(),
  messageBoxConfirm: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}));

// 视图经 @/api/request 间接引入 @/router 单例；这里按既有惯例桩掉它，
// 避免真实 createRouter 在部分 mock 的 vue-router 下缺失。
vi.mock('@/router', () => ({ default: { push: vi.fn() } }));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: messageSuccess,
    error: messageError,
    warning: messageWarning,
  },
  ElMessageBox: {
    confirm: messageBoxConfirm,
  },
}));

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    isAdmin: () => true,
    hasPermission: (permission: string) => permission === 'kb.manage' || permission === 'kb.write',
  }),
}));

vi.mock('@/api/kb', () => ({
  buildKnowledgeBatchSignature,
  buildKnowledgeRebuildSignature,
  dryRunKnowledgeDocuments,
  getKBOperations,
  ingestKnowledgeDocuments,
  rebuildKnowledgeDocument,
  rebuildKnowledgeDocuments,
  retryKBIngestJob,
  runDueConnectors,
  syncConnector,
}));

import KBOperationsView from './KBOperationsView.vue';

const payload = {
  view: 'admin',
  days: 14,
  generated_at: '2026-03-22T12:00:00+00:00',
  service_health: {
    status: 'ok',
    checks: {
      database: { status: 'ok' },
      object_storage: { status: 'ok' },
    },
  },
  ingest_ops: {
    summary: {
      total_documents: 10,
      ready_documents: 8,
      queryable_documents: 8,
      failed_documents: 1,
      unfinished_documents: 2,
      stalled_documents: 1,
      dead_letter_documents: 1,
      in_progress_documents: 1,
      stalled_threshold_hours: 24,
    },
    retryable_jobs: [
      {
        job_id: 'job-1',
        document_id: 'doc-1',
        base_id: 'base-1',
        base_name: '财务制度',
        file_name: 'expense-policy.pdf',
        document_status: 'failed',
        enhancement_status: '',
        job_status: 'failed',
        phase: 'chunking',
        error_message: 'parse failed',
        last_error_code: 'parse_error',
        attempt_count: 3,
        max_attempts: 5,
        updated_at: '2026-03-22T11:00:00+00:00',
        next_retry_at: null,
        retryable: true,
      },
    ],
    stalled_documents: [
      {
        document_id: 'doc-2',
        base_id: 'base-1',
        base_name: '财务制度',
        file_name: 'travel-policy.pdf',
        document_status: 'processing',
        enhancement_status: '',
        job_id: 'job-2',
        job_status: 'processing',
        phase: 'ocr',
        error_message: '',
        last_error_code: '',
        last_activity_at: '2026-03-21T10:00:00+00:00',
      },
    ],
  },
  connector_ops: {
    summary: {
      total_connectors: 2,
      scheduled_connectors: 1,
      due_connectors: 1,
      recent_failed_runs: 1,
    },
    items: [
      {
        connector_id: 'conn-1',
        base_id: 'base-1',
        base_name: '财务制度',
        name: 'Notion 财务库',
        connector_type: 'notion',
        status: 'active',
        schedule_enabled: true,
        next_run_at: '2026-03-22T12:30:00+00:00',
        last_run_at: '2026-03-22T10:00:00+00:00',
        last_run_outcome: 'failed',
        last_error: 'token invalid',
      },
    ],
  },
  incident_feed: {
    items: [
      {
        id: 'evt-1',
        trace_id: 'trace-1',
        resource_type: 'connector',
        resource_id: 'conn-1',
        action: 'kb.connector.sync',
        outcome: 'failed',
        created_at: '2026-03-22T12:00:00+00:00',
        details: { run_id: 'run-1' },
      },
    ],
  },
  data_quality: {
    unsupported_fields: [],
    degraded_sections: [],
  },
};

const stubs = {
  PageHeaderCompact: {
    props: ['title'],
    template: '<div><h1>{{ title }}</h1><slot name="subtitle" /><slot name="actions" /></div>',
  },
};

const batchPayload = {
  documents: [
    {
      base_id: 'base-1',
      doc_id: 'input-1',
      file_name: 'policy.txt',
      content: 'Policy content',
    },
  ],
};

const changedBatchPayload = {
  documents: [
    {
      base_id: 'base-1',
      doc_id: 'input-1',
      file_name: 'policy.txt',
      content: 'Changed content',
    },
  ],
};

describe('KBOperationsView', () => {
  beforeEach(() => {
    routerPush.mockReset();
    getKBOperations.mockReset();
    retryKBIngestJob.mockReset();
    syncConnector.mockReset();
    runDueConnectors.mockReset();
    dryRunKnowledgeDocuments.mockReset();
    ingestKnowledgeDocuments.mockReset();
    rebuildKnowledgeDocuments.mockReset();
    rebuildKnowledgeDocument.mockReset();
    buildKnowledgeBatchSignature.mockClear();
    buildKnowledgeRebuildSignature.mockClear();
    messageSuccess.mockReset();
    messageError.mockReset();
    messageWarning.mockReset();
    messageBoxConfirm.mockReset();
    messageBoxConfirm.mockResolvedValue('confirm');
    getKBOperations.mockResolvedValue(payload);
    retryKBIngestJob.mockResolvedValue({});
    syncConnector.mockResolvedValue({});
    runDueConnectors.mockResolvedValue({});
    dryRunKnowledgeDocuments.mockResolvedValue({
      dry_run: true,
      document_count: 1,
      total_content_chars: 14,
      total_sections: 1,
      total_chunks: 1,
      documents: [
        {
          doc_id: 'input-1',
          file_name: 'policy.txt',
          content_chars: 14,
          section_count: 1,
          chunk_count: 1,
        },
      ],
    });
    ingestKnowledgeDocuments.mockResolvedValue({
      success: true,
      batch: { task_id: 'batch-1', status: 'completed' },
      document_count: 1,
      succeeded_documents: 1,
      failed_documents: 0,
      section_count: 1,
      chunk_count: 1,
      indexed_sections: 1,
      indexed_chunks: 1,
      skipped_chunks: 0,
      documents: [
        {
          index: 0,
          ok: true,
          input_doc_id: 'input-1',
          document_id: 'generated-doc-1',
          base_id: 'base-1',
          file_name: 'policy.txt',
          section_count: 1,
          chunk_count: 1,
          indexed_sections: 1,
          indexed_chunks: 1,
          skipped_chunks: 0,
          status: 'ready',
        },
      ],
    });
    rebuildKnowledgeDocuments.mockResolvedValue({
      document_count: 1,
      succeeded_documents: 1,
      failed_documents: 0,
      documents: [{ doc_id: 'generated-doc-1', ok: true, result: { chunk_count: 1 } }],
    });
    rebuildKnowledgeDocument.mockImplementation((request: any) => {
      if (request.dry_run) {
        return Promise.resolve({ dry_run: true, signature: request.signature });
      }
      return Promise.resolve({
        doc_id: request.doc_id,
        version: 'v3',
        chunk_count: 12,
        indexed_chunks: 12,
        deleted_previous: 8,
      });
    });
  });

  it('renders operations data and triggers safe actions', async () => {
    const wrapper = mount(KBOperationsView, { global: { stubs } });

    await flushPromises();

    expect(wrapper.text()).toContain('知识库运维');
    expect(wrapper.text()).toContain('expense-policy.pdf');
    expect(wrapper.text()).toContain('Notion 财务库');
    expect(wrapper.text()).toContain('kb.connector.sync');

    await wrapper.get('[data-testid="retry-job-job-1"]').trigger('click');
    await flushPromises();
    expect(retryKBIngestJob).toHaveBeenCalledWith('job-1');

    await wrapper.get('[data-testid="run-connector-conn-1"]').trigger('click');
    await flushPromises();
    expect(syncConnector).toHaveBeenCalledWith('conn-1', false);

    await wrapper.get('[data-testid="run-due-button"]').trigger('click');
    await flushPromises();
    expect(runDueConnectors).toHaveBeenCalledWith(10, false);

    expect(getKBOperations).toHaveBeenCalledTimes(4);
    expect(messageSuccess).toHaveBeenCalledTimes(3);
  });

  it('gates batch ingest and rebuild behind the current JSON dry-run signature', async () => {
    const wrapper = mount(KBOperationsView, { global: { stubs } });

    await flushPromises();

    const input = wrapper.get('[data-testid="kb-batch-json-input"]');
    const dryRunButton = () => wrapper.get('[data-testid="kb-batch-dry-run-button"]');
    const ingestButton = () => wrapper.get('[data-testid="kb-batch-ingest-button"]');
    const rebuildButton = () => wrapper.get('[data-testid="kb-batch-rebuild-button"]');

    expect(ingestButton().attributes('disabled')).toBeDefined();
    expect(rebuildButton().attributes('disabled')).toBeDefined();

    await input.setValue(JSON.stringify(batchPayload));
    await flushPromises();

    expect(dryRunButton().attributes('disabled')).toBeUndefined();
    expect(ingestButton().attributes('disabled')).toBeDefined();

    await dryRunButton().trigger('click');
    await flushPromises();

    expect(dryRunKnowledgeDocuments).toHaveBeenCalledWith(batchPayload);
    expect(ingestKnowledgeDocuments).not.toHaveBeenCalled();
    expect(ingestButton().attributes('disabled')).toBeUndefined();
    expect(wrapper.get('[data-testid="kb-batch-dry-run-summary"]').text()).toContain('policy.txt');

    await input.setValue(JSON.stringify(changedBatchPayload));
    await flushPromises();

    expect(ingestButton().attributes('disabled')).toBeDefined();
    expect(rebuildButton().attributes('disabled')).toBeDefined();

    await dryRunButton().trigger('click');
    await flushPromises();
    await ingestButton().trigger('click');
    await flushPromises();

    expect(ingestKnowledgeDocuments).toHaveBeenCalledWith(changedBatchPayload);
    expect(messageBoxConfirm).toHaveBeenCalledWith(
      expect.stringContaining('policy.txt'),
      '确认批量写入',
      expect.anything(),
    );
    expect(wrapper.get('[data-testid="kb-batch-ingest-summary"]').text()).toContain('generated-doc-1');
    expect(rebuildButton().attributes('disabled')).toBeUndefined();

    await input.setValue(JSON.stringify(batchPayload));
    await flushPromises();

    expect(rebuildButton().attributes('disabled')).toBeDefined();
    expect(rebuildKnowledgeDocuments).not.toHaveBeenCalled();

    await input.setValue(JSON.stringify(changedBatchPayload));
    await flushPromises();
    await rebuildButton().trigger('click');
    await flushPromises();

    expect(messageBoxConfirm).toHaveBeenLastCalledWith(
      expect.stringContaining('generated-doc-1'),
      '确认重建写入结果',
      expect.anything(),
    );
    expect(rebuildKnowledgeDocuments).toHaveBeenCalledWith({ document_ids: ['generated-doc-1'] });
    expect(wrapper.get('[data-testid="kb-batch-rebuild-summary"]').text()).toContain('generated-doc-1');
  });

  it('requires a matching rebuild dry-run signature before rebuilding one document', async () => {
    const wrapper = mount(KBOperationsView, { global: { stubs } });

    await flushPromises();

    const docInput = wrapper.get('[data-testid="kb-rebuild-doc-input"]');
    const dryRunButton = () => wrapper.get('[data-testid="kb-rebuild-dry-run-button"]');
    const rebuildButton = () => wrapper.get('[data-testid="kb-rebuild-button"]');

    expect(rebuildButton().attributes('disabled')).toBeDefined();

    await docInput.setValue('doc-1');
    await flushPromises();

    expect(rebuildButton().attributes('disabled')).toBeDefined();

    await dryRunButton().trigger('click');
    await flushPromises();

    expect(rebuildKnowledgeDocument).toHaveBeenCalledWith({
      doc_id: 'doc-1',
      dry_run: true,
      signature: 'sig:doc-1',
    });
    expect(rebuildButton().attributes('disabled')).toBeUndefined();

    await docInput.setValue('doc-2');
    await flushPromises();

    expect(rebuildButton().attributes('disabled')).toBeDefined();
    expect(rebuildKnowledgeDocument).toHaveBeenCalledTimes(1);

    await dryRunButton().trigger('click');
    await flushPromises();
    await rebuildButton().trigger('click');
    await flushPromises();

    expect(rebuildKnowledgeDocument).toHaveBeenLastCalledWith({
      doc_id: 'doc-2',
      dry_run: false,
      signature: 'sig:doc-2',
    });
    expect(messageBoxConfirm).toHaveBeenLastCalledWith(
      expect.stringContaining('doc-2'),
      '确认重建文档',
      expect.anything(),
    );

    const summary = wrapper.get('[data-testid="kb-rebuild-summary"]').text();
    expect(summary).toContain('doc-2');
    expect(summary).toContain('v3');
    expect(summary).toContain('12');
    expect(summary).toContain('8');
  });
});
