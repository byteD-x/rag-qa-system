import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listKnowledgeBases } = vi.hoisted(() => ({
  listKnowledgeBases: vi.fn()
}));

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() })
}));

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}));

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'user-1', role: 'admin' },
    isAdmin: () => true,
    hasPermission: () => true
  })
}));

vi.mock('@/api/kb', () => ({
  completeKBUpload: vi.fn(),
  createKBUpload: vi.fn(),
  createKnowledgeBase: vi.fn(),
  deleteKBDocument: vi.fn(),
  deleteKnowledgeBase: vi.fn(),
  getKBDocumentEvents: vi.fn().mockResolvedValue({ items: [] }),
  getKBIngestJob: vi.fn(),
  getKBUpload: vi.fn(),
  listKBJobPositions: vi.fn().mockResolvedValue({ items: [] }),
  listKBTypes: vi.fn().mockResolvedValue({ items: [] }),
  listKBDocuments: vi.fn().mockResolvedValue({ items: [] }),
  listKnowledgeBases,
  presignKBUploadParts: vi.fn(),
  updateKnowledgeBase: vi.fn()
}));

vi.mock('@/api/request', () => ({
  createIdempotencyKey: (value: string) => value
}));

vi.mock('@/utils/multipartUpload', () => ({
  uploadMultipartFile: vi.fn()
}));

vi.mock('@/utils/status', () => ({
  statusMeta: () => ({ type: 'info', label: '待处理' })
}));

import KBUploadView from './KBUploadView.vue';

describe('KBUploadView layout', () => {
  beforeEach(() => {
    listKnowledgeBases.mockReset();
    listKnowledgeBases.mockResolvedValue({ items: [] });
  });

  it('exposes the long upload form as a keyboard-focusable scroll region', () => {
    const wrapper = mount(KBUploadView, {
      global: {
        stubs: {
          PageHeaderCompact: { template: '<header><slot name="actions" /></header>' },
          DocumentEvents: { template: '<div />' },
          EnhancedEmpty: { template: '<div />' },
          ElButton: { template: '<button><slot /></button>' },
          ElCollapse: { template: '<div><slot /></div>' },
          ElCollapseItem: { template: '<div><slot /><slot name="title" /></div>' },
          ElDatePicker: { template: '<input />' },
          ElDivider: { template: '<div><slot /></div>' },
          ElForm: { template: '<form><slot /></form>' },
          ElFormItem: { template: '<div><slot /></div>' },
          ElIcon: { template: '<span><slot /></span>' },
          ElInput: { template: '<input />' },
          ElInputNumber: { template: '<input type="number" />' },
          ElOption: { template: '<option />' },
          ElProgress: { template: '<progress />' },
          ElSelect: { template: '<select><slot /></select>' },
          ElSwitch: { template: '<input type="checkbox" />' },
          ElTag: { template: '<span><slot /></span>' }
        }
      }
    });

    const region = wrapper.get('.upload-left');
    expect(region.attributes('data-testid')).toBe('kb-upload-scroll-region');
    expect(region.attributes('role')).toBe('region');
    expect(region.attributes('tabindex')).toBe('0');
    expect(region.attributes('aria-label')).toBe('上传与版本设置');
  });
});
