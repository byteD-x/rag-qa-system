import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listConnectors, listKnowledgeBases, messageError } = vi.hoisted(() => ({
  listConnectors: vi.fn(),
  listKnowledgeBases: vi.fn(),
  messageError: vi.fn()
}));

vi.mock('element-plus', () => ({
  ElMessage: { error: messageError, success: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}));

vi.mock('@/api/kb', () => ({
  listConnectors,
  listKnowledgeBases,
  createConnector: vi.fn(),
  updateConnector: vi.fn(),
  deleteConnector: vi.fn(),
  syncConnector: vi.fn()
}));

import KBConnectorsView from './KBConnectorsView.vue';

describe('KBConnectorsView error state', () => {
  beforeEach(() => {
    listConnectors.mockReset();
    listKnowledgeBases.mockReset();
    messageError.mockReset();
    listKnowledgeBases.mockResolvedValue({ items: [] });
    listConnectors.mockRejectedValue(new Error('gateway unavailable'));
  });

  it('shows an actionable error instead of the empty state when loading fails', async () => {
    const wrapper = mount(KBConnectorsView, {
      global: {
        stubs: {
          PageHeaderCompact: { template: '<header><slot name="actions" /></header>' },
          EnhancedEmpty: { template: '<div class="empty-state"><slot /></div>' },
          ElButton: { template: '<button v-bind="$attrs"><slot /></button>' },
          ElIcon: { template: '<span><slot /></span>' },
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElForm: { template: '<form><slot /></form>' },
          ElFormItem: { template: '<div><slot /></div>' },
          ElInput: { template: '<input />' },
          ElSelect: { template: '<select><slot /></select>' },
          ElOption: { template: '<option />' },
          ElSwitch: { template: '<input type="checkbox" />' },
          ElInputNumber: { template: '<input type="number" />' },
          ElTag: { template: '<span><slot /></span>' }
        }
      }
    });

    await flushPromises();

    expect(wrapper.find('.error-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('加载数据源失败');
    expect(wrapper.find('[data-testid="retry-connectors"]').exists()).toBe(true);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
  });

  it('does not show a duplicate global error toast for list failures', async () => {
    const wrapper = mount(KBConnectorsView, {
      global: {
        stubs: {
          PageHeaderCompact: { template: '<header><slot name="actions" /></header>' },
          EnhancedEmpty: { template: '<div class="empty-state"><slot /></div>' },
          ElButton: { template: '<button v-bind="$attrs"><slot /></button>' },
          ElIcon: { template: '<span><slot /></span>' },
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElForm: { template: '<form><slot /></form>' }, ElFormItem: { template: '<div><slot /></div>' },
          ElInput: { template: '<input />' }, ElSelect: { template: '<select><slot /></select>' },
          ElOption: { template: '<option />' }, ElSwitch: { template: '<input type="checkbox" />' },
          ElInputNumber: { template: '<input type="number" />' }, ElTag: { template: '<span><slot /></span>' }
        }
      }
    });

    await flushPromises();
    expect(messageError).not.toHaveBeenCalled();
    expect(wrapper.find('.error-state').exists()).toBe(true);
  });
});
