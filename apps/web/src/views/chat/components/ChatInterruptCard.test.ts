import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { resumeInterrupt } = vi.hoisted(() => ({
  resumeInterrupt: vi.fn()
}));

vi.mock('@/store/chat', () => ({
  useChatStore: () => ({
    resumeInterrupt
  })
}));

import ChatInterruptCard from './ChatInterruptCard.vue';

const globalStubs = {
  'el-radio-group': {
    template: '<div><slot /></div>'
  },
  'el-radio': {
    props: ['label'],
    template: '<label :data-label="label"><slot /></label>'
  },
  'el-input': {
    props: ['placeholder'],
    template: '<textarea :placeholder="placeholder"></textarea>'
  },
  'el-button': {
    emits: ['click'],
    template: '<button @click="$emit(\'click\')"><slot /></button>'
  }
};

describe('ChatInterruptCard', () => {
  beforeEach(() => {
    resumeInterrupt.mockReset();
    resumeInterrupt.mockResolvedValue(undefined);
  });

  it('renders subject, badges, fallback input and submits the recommended option', async () => {
    const wrapper = mount(ChatInterruptCard, {
      props: {
        message: {
          submitting: false,
          resolved: false,
          interrupt: {
            kind: 'version_conflict',
            title: '版本确认',
            detail: '存在多个版本',
            recommended_option_id: 'document:doc-v2',
            allow_free_text: true,
            fallback_prompt: '请补充上下文',
            subject: {
              type: 'version_family',
              summary: '2 个候选版本'
            },
            options: [
              {
                id: 'document:doc-v2',
                label: '按 v2 回答',
                description: '当前生效版本',
                badges: ['v2', 'current']
              }
            ]
          }
        }
      },
      global: {
        stubs: globalStubs
      }
    });

    expect(wrapper.text()).toContain('2 个候选版本');
    expect(wrapper.text()).toContain('v2');
    expect(wrapper.find('textarea').attributes('placeholder')).toBe('请补充上下文');

    await wrapper.get('button').trigger('click');

    expect(resumeInterrupt).toHaveBeenCalledWith(
      expect.objectContaining({ interrupt: expect.any(Object) }),
      { selected_option_ids: ['document:doc-v2'] }
    );
  });
});
