import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

const { getWorkflowRun, retryWorkflowRun, selectSession } = vi.hoisted(() => ({
  getWorkflowRun: vi.fn(),
  retryWorkflowRun: vi.fn(),
  selectSession: vi.fn()
}));

vi.mock('@/api/chat', () => ({
  getWorkflowRun,
  retryWorkflowRun
}));

vi.mock('@/store/chat', () => ({
  useChatStore: () => ({
    activeSessionId: 'session-1',
    selectSession
  })
}));

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus');
  return {
    ...actual,
    ElMessage: {
      error: vi.fn(),
      success: vi.fn()
    }
  };
});

import ChatTraceDrawer from './ChatTraceDrawer.vue';

const globalStubs = {
  'el-drawer': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<section v-if="modelValue"><slot /></section>'
  },
  'el-tag': {
    template: '<span class="el-tag"><slot /></span>'
  },
  'el-timeline': {
    template: '<ol><slot /></ol>'
  },
  'el-timeline-item': {
    props: ['timestamp'],
    template: '<li><span>{{ timestamp }}</span><slot /></li>'
  },
  'el-collapse': {
    template: '<div><slot /></div>'
  },
  'el-collapse-item': {
    props: ['title'],
    template: '<section><h4>{{ title }}</h4><slot /></section>'
  },
  'el-table': {
    props: ['data'],
    template: '<table><tbody><tr v-for="(row, idx) in data" :key="idx"><td>{{ row.tool }}</td><td>{{ row.error || row.result_count }}</td></tr></tbody></table>'
  },
  'el-table-column': true,
  'el-button': {
    emits: ['click'],
    template: '<button @click="$emit(\'click\')"><slot /></button>'
  },
  'el-icon': {
    template: '<i><slot /></i>'
  },
  Loading: true
};

describe('ChatTraceDrawer', () => {
  it('renders workflow timeline, failure reasons and resume target', async () => {
    getWorkflowRun.mockResolvedValue({
      id: 'run-1',
      status: 'failed',
      execution_mode: 'agent',
      stage: 'failed',
      workflow_state: {
        stage: 'failed',
        can_resume: true,
        resume_target: 'persist_message',
        resume: { source_stage: 'generation_completed' },
        error: { type: 'RuntimeError', detail: 'answer generation failed' }
      },
      workflow_events: [
        { stage: 'retrieval_completed', status: 'running', evidence_count: 3, retrieval_ms: 12.5 },
        { stage: 'failed', status: 'failed', error: { type: 'RuntimeError', class: 'runtime' } }
      ],
      tool_calls: [
        { tool: 'search_scope', success: true, result_count: 2 },
        { tool: 'rerank', success: false, error: 'rerank unavailable' }
      ]
    });

    const wrapper = mount(ChatTraceDrawer, {
      global: { stubs: globalStubs }
    });

    await (wrapper.vm as any).show({ id: 'run-1' });
    await wrapper.vm.$nextTick();

    const text = wrapper.text();
    expect(text).toContain('事件时间线');
    expect(text).toContain('retrieval_completed');
    expect(text).toContain('失败与恢复');
    expect(text).toContain('persist_message');
    expect(text).toContain('RuntimeError: answer generation failed');
    expect(text).toContain('rerank: rerank unavailable');
    expect(text).toContain('工具调用摘要');
    expect(text).toContain('search_scope');
  });
});
