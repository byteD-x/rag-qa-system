import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getKBGovernance,
  getKBGovernanceBatchEvents,
  rebuildKnowledgeDocument,
  messageSuccess,
  messageWarning,
} = vi.hoisted(() => ({
  getKBGovernance: vi.fn(),
  getKBGovernanceBatchEvents: vi.fn(),
  rebuildKnowledgeDocument: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: messageSuccess,
    warning: messageWarning,
    error: vi.fn(),
  },
}));

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'user-1' },
    isAdmin: () => true,
    hasPermission: (permission: string) => permission === 'kb.write',
  }),
}));

vi.mock('@/api/kb', () => ({
  batchUpdateKBDocuments: vi.fn(),
  buildKnowledgeRebuildSignature: ({ doc_id }: { doc_id: string }) => `sig:${String(doc_id || '').trim()}`,
  getKBDocument: vi.fn(),
  getKBDocumentVisualAssets: vi.fn(),
  getKBGovernance,
  getKBGovernanceBatchEventDetail: vi.fn(),
  getKBGovernanceBatchEvents,
  getKBVisualAssetRegions: vi.fn(),
  rebuildKnowledgeDocument,
  updateKBDocument: vi.fn(),
}));

import KBGovernanceView from './KBGovernanceView.vue';

const documentItem = (documentId: string, fileName: string) => ({
  document_id: documentId,
  base_id: 'base-1',
  base_name: '运营制度库',
  file_name: fileName,
  status: 'ready',
  enhancement_status: 'chunk_vectors_ready',
  version_family_key: 'ops-policy',
  version_label: 'v1',
  version_number: 1,
  version_status: 'active',
  is_current_version: true,
  effective_from: null,
  effective_to: null,
  effective_now: true,
  visual_asset_count: 0,
  low_confidence_region_count: 0,
  low_confidence_asset_id: '',
  low_confidence_region_id: '',
  low_confidence_region_label: '',
  low_confidence_region_confidence: null,
  low_confidence_region_bbox: [],
  created_at: null,
  updated_at: null,
  owner_user_id: 'user-1',
  review_status: 'review_pending',
  reviewer_note: '',
  reviewed_at: null,
  reviewed_by_user_id: '',
  reviewed_by_email: '',
  reason: 'review_pending',
});

const governancePayload = {
  view: 'admin',
  limit: 8,
  generated_at: '2026-06-08T00:00:00Z',
  summary: {
    pending_review: 2,
    approved_ready: 0,
    rejected_documents: 0,
    expired_documents: 0,
    visual_attention: 0,
    visual_low_confidence: 0,
    missing_version_family: 0,
    version_conflicts: 0,
  },
  queues: {
    pending_review: [
      documentItem('doc-1', 'ops-policy-v1.pdf'),
      documentItem('doc-2', 'ops-policy-v2.pdf'),
    ],
    approved_ready: [],
    rejected_documents: [],
    expired_documents: [],
    visual_attention: [],
    visual_low_confidence: [],
    missing_version_family: [],
    version_conflicts: [],
  },
  data_quality: {
    unsupported_fields: [],
    degraded_sections: [],
  },
};

const stubs = {
  PageHeaderCompact: {
    props: ['title'],
    template: '<div><h1>{{ title }}</h1><slot name="actions" /></div>',
  },
  ElButton: {
    props: ['disabled', 'loading'],
    emits: ['click'],
    template: '<button v-bind="$attrs" :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  ElCheckbox: {
    props: ['modelValue'],
    emits: ['change'],
    template: '<input v-bind="$attrs" type="checkbox" :checked="modelValue" @change="$emit(\'change\', $event.target.checked)" />',
  },
  ElInput: { template: '<textarea v-bind="$attrs" />' },
  ElRadioGroup: { template: '<div><slot /></div>' },
  ElRadioButton: { template: '<button><slot /></button>' },
  ElTag: { template: '<span><slot /></span>' },
  ElSkeleton: { template: '<div />' },
  ElDrawer: { template: '<div><slot /></div>' },
  ElForm: { template: '<form><slot /></form>' },
  ElFormItem: { template: '<div><slot /></div>' },
  ElSelect: { template: '<select><slot /></select>' },
  ElOption: { template: '<option />' },
  ElInputNumber: { template: '<input type="number" />' },
  ElDatePicker: { template: '<input />' },
  ElSwitch: { template: '<input type="checkbox" />' },
};

describe('KBGovernanceView rebuild action', () => {
  beforeEach(() => {
    getKBGovernance.mockReset();
    getKBGovernanceBatchEvents.mockReset();
    rebuildKnowledgeDocument.mockReset();
    messageSuccess.mockReset();
    messageWarning.mockReset();
    getKBGovernance.mockResolvedValue(governancePayload);
    getKBGovernanceBatchEvents.mockResolvedValue({ items: [] });
    rebuildKnowledgeDocument.mockImplementation((payload: any) => {
      if (payload.dry_run) {
        return Promise.resolve({ dry_run: true, signature: payload.signature });
      }
      return Promise.resolve({
        doc_id: payload.doc_id,
        version: 'v3',
        chunk_count: 12,
        indexed_chunks: 12,
        deleted_previous: 8,
      });
    });
  });

  it('requires matching dry-run signature before rebuild and renders summary', async () => {
    const wrapper = mount(KBGovernanceView, { global: { stubs } });

    await flushPromises();

    const rebuildButton = () => wrapper.get('[data-testid="kb-rebuild-button"]');
    const dryRunButton = () => wrapper.get('[data-testid="kb-rebuild-dry-run-button"]');

    await wrapper.get('[data-testid="select-document-doc-1"]').setValue(true);
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

    await wrapper.get('[data-testid="select-document-doc-1"]').setValue(false);
    await wrapper.get('[data-testid="select-document-doc-2"]').setValue(true);
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
    expect(wrapper.get('[data-testid="kb-rebuild-summary"]').text()).toContain('doc_id doc-2');
    expect(wrapper.get('[data-testid="kb-rebuild-summary"]').text()).toContain('version v3');
    expect(wrapper.get('[data-testid="kb-rebuild-summary"]').text()).toContain('chunk_count 12');
    expect(wrapper.get('[data-testid="kb-rebuild-summary"]').text()).toContain('indexed_chunks 12');
    expect(wrapper.get('[data-testid="kb-rebuild-summary"]').text()).toContain('deleted_previous 8');
  });
});
