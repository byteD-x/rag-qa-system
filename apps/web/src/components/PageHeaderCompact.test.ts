import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import PageHeaderCompact from './PageHeaderCompact.vue';

describe('PageHeaderCompact', () => {
  it('renders the subtitle prop when no subtitle slot is provided', () => {
    const wrapper = mount(PageHeaderCompact, {
      props: {
        title: '知识库',
        subtitle: '管理文档与检索状态'
      }
    });

    expect(wrapper.find('.page-header-compact__subtitle').text()).toBe('管理文档与检索状态');
  });
});
