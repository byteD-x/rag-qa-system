import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/store/chat', () => ({
  useChatStore: () => ({
    sessions: [
      { id: '1', title: '报销政策', updated_at: '2026-10-13T10:00:00Z', last_question: '审批需要哪些人' },
      { id: '2', title: '上线复盘', updated_at: '2026-10-12T10:00:00Z', last_question: '本周上线情况' }
    ],
    activeSessionId: '',
    startDraftSession: vi.fn(),
    selectSession: vi.fn(),
    renameActiveSession: vi.fn(),
    handleDeleteSession: vi.fn()
  })
}));

import ChatSidebar from './ChatSidebar.vue';

describe('ChatSidebar', () => {
  it('removes a closed mobile sidebar from the accessibility tree and tab order', () => {
    const wrapper = mount(ChatSidebar, {
      props: { open: false },
      global: {
        stubs: {
          ElIcon: { template: '<span><slot /></span>' },
          ElDropdown: { template: '<div><slot /><slot name="dropdown" /></div>' },
          ElDropdownMenu: { template: '<div><slot /></div>' },
          ElDropdownItem: { template: '<button><slot /></button>' }
        }
      }
    });

    const sidebar = wrapper.get('aside');
    expect(sidebar.attributes('aria-hidden')).toBe('true');
    expect(sidebar.attributes('inert')).toBeDefined();
  });

  it('filters sessions by title or last question', async () => {
    const wrapper = mount(ChatSidebar, {
      props: { open: true },
      global: { stubs: {
        ElIcon: { template: '<span><slot /></span>' },
        ElInput: { template: '<input v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />', props: ['modelValue'] }
      } }
    });

    await wrapper.get('[data-testid="session-search"]').setValue('审批');

    expect(wrapper.text()).toContain('报销政策');
    expect(wrapper.text()).not.toContain('上线复盘');
  });
});
