import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  routerPush,
  getKBOperations,
  retryKBIngestJob,
  syncConnector,
  runDueConnectors,
  messageSuccess,
  messageError,
} = vi.hoisted(() => ({
  routerPush: vi.fn(),
  getKBOperations: vi.fn(),
  retryKBIngestJob: vi.fn(),
  syncConnector: vi.fn(),
  runDueConnectors: vi.fn(),
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: messageSuccess,
    error: messageError,
  },
}));

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    isAdmin: () => true,
    hasPermission: (permission: string) => permission === 'kb.manage',
  }),
}));

vi.mock('@/api/kb', () => ({
  getKBOperations,
  retryKBIngestJob,
  syncConnector,
  runDueConnectors,
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

describe('KBOperationsView', () => {
  beforeEach(() => {
    routerPush.mockReset();
    getKBOperations.mockReset();
    retryKBIngestJob.mockReset();
    syncConnector.mockReset();
    runDueConnectors.mockReset();
    messageSuccess.mockReset();
    messageError.mockReset();
    getKBOperations.mockResolvedValue(payload);
    retryKBIngestJob.mockResolvedValue({});
    syncConnector.mockResolvedValue({});
    runDueConnectors.mockResolvedValue({});
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('renders operations data and triggers safe actions', async () => {
    const wrapper = mount(KBOperationsView, {
      global: {
        stubs: {
          PageHeaderCompact: {
            props: ['title'],
            template: '<div><h1>{{ title }}</h1><slot name="subtitle" /><slot name="actions" /></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('知识库运维总览');
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
});
