import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getKBGovernance, getKBGovernanceBatchEvents } = vi.hoisted(() => ({
  getKBGovernance: vi.fn(),
  getKBGovernanceBatchEvents: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
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
  getKBDocument: vi.fn(),
  getKBDocumentVisualAssets: vi.fn(),
  getKBGovernance,
  getKBGovernanceBatchEventDetail: vi.fn(),
  getKBGovernanceBatchEvents,
  getKBVisualAssetRegions: vi.fn(),
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
  ElInput: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<textarea v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
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

// 满页 payload：让「下一页」按钮可用（canGoNextPage 依赖某区段已加载条数达到 limit）
const fullPagePayload = (() => {
  const items = Array.from({ length: 50 }, (_, index) => documentItem(`doc-${index + 1}`, `ops-policy-${index + 1}.pdf`));
  return {
    ...governancePayload,
    summary: { ...governancePayload.summary, pending_review: 120 },
    queues: { ...governancePayload.queues, pending_review: items },
  };
})();

const findButton = (wrapper: any, label: string) =>
  wrapper.findAll('button').find((node: any) => node.text().trim() === label);

describe('KBGovernanceView governance queues', () => {
  beforeEach(() => {
    getKBGovernance.mockReset();
    getKBGovernanceBatchEvents.mockReset();
    getKBGovernance.mockResolvedValue(governancePayload);
    getKBGovernanceBatchEvents.mockResolvedValue({ items: [] });
  });

  it('renders governance queues without any write affordance', async () => {
    const wrapper = mount(KBGovernanceView, { global: { stubs } });

    await flushPromises();

    expect(getKBGovernance).toHaveBeenCalled();
    expect(wrapper.text()).toContain('ops-policy-v1.pdf');
    expect(wrapper.text()).toContain('ops-policy-v2.pdf');
    expect(wrapper.html()).not.toContain('kb-batch-');
    expect(wrapper.html()).not.toContain('kb-rebuild-');
  });

  it('requests the first page with no owner filter by default', async () => {
    mount(KBGovernanceView, { global: { stubs } });

    await flushPromises();

    expect(getKBGovernance).toHaveBeenCalledWith({
      view: 'admin',
      limit: 50,
      offset: 0,
      owner_user_id: '',
    });
  });

  it('advances and rewinds the offset through the pager', async () => {
    getKBGovernance.mockResolvedValue(fullPagePayload);
    const wrapper = mount(KBGovernanceView, { global: { stubs } });

    await flushPromises();

    const next = findButton(wrapper, '下一页');
    expect(next).toBeTruthy();
    expect(next!.attributes('disabled')).toBeUndefined();

    await next!.trigger('click');
    await flushPromises();

    expect(getKBGovernance).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 }));
    expect(wrapper.text()).toContain('第 2 页');

    const prev = findButton(wrapper, '上一页');
    expect(prev!.attributes('disabled')).toBeUndefined();

    await prev!.trigger('click');
    await flushPromises();

    expect(getKBGovernance).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 }));
    expect(wrapper.text()).toContain('第 1 页');
  });
});
