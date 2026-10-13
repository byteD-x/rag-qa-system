import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, fullPath: '/workspace/chat' })
}));

vi.mock('@/router', () => ({ default: { push: vi.fn() } }));

vi.mock('@/store/chat', () => ({
  useChatStore: () => ({
    messages: [],
    asking: false,
    hasStreamingAssistant: false,
    sessions: [],
    activeSessionId: '',
    loadCorpora: vi.fn(),
    loadSessions: vi.fn(),
    startDraftSession: vi.fn(),
    applyScope: vi.fn(),
    setFocusHint: vi.fn(),
    handleScopeModeChange: vi.fn(),
    selectSession: vi.fn(),
    stopStreaming: vi.fn(),
    ask: vi.fn()
  })
}));

import UnifiedChatView from './UnifiedChatView.vue';

describe('UnifiedChatView', () => {
  it('exposes query progress through a polite status live region', () => {
    const wrapper = mount(UnifiedChatView, {
      global: {
        stubs: {
          ChatSidebar: true,
          ChatHeader: true,
          ChatMessageItem: true,
          ChatComposer: true,
          ChatTraceDrawer: true,
          ElIcon: { template: '<span><slot /></span>' }
        }
      }
    });

    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite');
  });
});
