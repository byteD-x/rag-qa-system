import { shallowMount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { handleFeedback } = vi.hoisted(() => ({
  handleFeedback: vi.fn()
}));

vi.mock('@/store/chat', () => ({
  useChatStore: () => ({
    handleFeedback
  })
}));

import ChatMessageItem from './ChatMessageItem.vue';

const globalStubs = {
  ChatInterruptCard: true,
  CitationList: true,
  'el-icon': {
    template: '<i><slot /></i>'
  },
  'el-popover': {
    template: '<div><slot name="reference" /><slot /></div>'
  },
  'el-select': true,
  'el-option': true,
  'el-input': true,
  Platform: true,
  User: true,
  Connection: true
};

describe('ChatMessageItem', () => {
  beforeEach(() => {
    handleFeedback.mockReset();
  });

  it('renders answer basis for assistant messages', () => {
    const wrapper = shallowMount(ChatMessageItem, {
      props: {
        message: {
          id: 'msg-1',
          role: 'assistant',
          content: '最终答案',
          message_kind: 'answer',
          answer_basis: {
            label: 'v2 / 第 3 页 / terminal config'
          },
          citations: []
        }
      },
      global: {
        stubs: globalStubs
      }
    });

    expect(wrapper.find('.answer-basis').exists()).toBe(true);
    expect(wrapper.find('.answer-basis__text').text()).toContain('v2 / 第 3 页 / terminal config');
  });
});
