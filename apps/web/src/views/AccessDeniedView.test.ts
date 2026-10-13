import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

const push = vi.fn();

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { permission: 'kb.manage', from: '/workspace/kb/operations' } }),
  useRouter: () => ({ push })
}));

import AccessDeniedView from './AccessDeniedView.vue';

describe('AccessDeniedView', () => {
  it('explains the missing permission and provides a workspace exit', async () => {
    const wrapper = mount(AccessDeniedView, {
      global: {
        stubs: {
          ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', emits: ['click'] }
        }
      }
    });

    expect(wrapper.text()).toContain('没有访问权限');
    expect(wrapper.text()).toContain('kb.manage');
    await wrapper.get('[data-testid="back-to-workspace"]').trigger('click');
    expect(push).toHaveBeenCalledWith('/workspace/entry');
  });
});
