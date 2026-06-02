import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listKnowledgeBases, retrieveDebugKB } = vi.hoisted(() => ({
  listKnowledgeBases: vi.fn(),
  retrieveDebugKB: vi.fn(),
}));

vi.mock('@/api/kb', () => ({
  listKnowledgeBases,
  retrieveDebugKB,
}));

import RetrievalDebuggerView from './RetrievalDebuggerView.vue';

const globalStubs = {
  PageHeaderCompact: {
    props: ['title', 'subtitle'],
    template: '<header><h1>{{ title }}</h1><p>{{ subtitle }}</p></header>',
  },
  EnhancedEmpty: {
    props: ['title', 'description'],
    template: '<div><h2>{{ title }}</h2><p>{{ description }}</p></div>',
  },
  'el-form': {
    template: '<form><slot /></form>',
  },
  'el-form-item': {
    template: '<label><slot /></label>',
  },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  'el-option': {
    props: ['label', 'value'],
    template: '<option :value="value">{{ label }}</option>',
  },
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<textarea v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-input-number': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
  },
  'el-button': {
    props: ['disabled', 'loading'],
    emits: ['click'],
    template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': {
    template: '<span><slot /></span>',
  },
  'el-icon': {
    template: '<i><slot /></i>',
  },
  Loading: true,
};

describe('RetrievalDebuggerView', () => {
  beforeEach(() => {
    listKnowledgeBases.mockReset();
    retrieveDebugKB.mockReset();
    listKnowledgeBases.mockResolvedValue({
      items: [{ id: 'base-1', name: 'Finance KB' }],
    });
    retrieveDebugKB.mockResolvedValue({
      query: 'Who signs expense approvals?',
      trace_id: 'kb-trace-1',
      retrieval: {
        original_query: 'Who signs expense approvals?',
        focus_query: 'expense approvals signs',
        structure_candidates: 1,
        fts_candidates: 2,
        vector_candidates: 3,
        fused_candidates: 3,
        reranked_candidates: 2,
        selected_candidates: 2,
        retrieval_ms: 12.3456,
        rerank_provider: 'heuristic',
      },
      items: [
        {
          unit_id: 'unit-approval',
          document_id: 'doc-policy',
          document_title: 'Expense Policy',
          section_title: 'Approval Signatures',
          quote: 'Department owner and finance reviewer signatures are required.',
          raw_text: 'raw approval text',
          signal_scores: { structure: 1.2, fts: 0.8, vector: 0.6, rerank: 9.5 },
          evidence_path: { structure_hit: true, fts_rank: 1, vector_rank: 2, final_rank: 1, final_score: 0.91 },
          debug: { rank: 1, score: 0.91, signal_scores: { fts: 0.8 }, rerank_score: 9.5 },
        },
        {
          unit_id: 'unit-raw',
          document_id: 'doc-policy',
          document_title: 'Expense Policy',
          section_title: 'Fallback Note',
          quote: '',
          raw_text: 'Render raw_text when quote is empty.',
          signal_scores: { fts: 0.5 },
          evidence_path: { fts_rank: 2, final_rank: 2, final_score: 0.42 },
          debug: { rank: 2, score: 0.42, signal_scores: { fts: 0.5 }, rerank_score: 0 },
        },
      ],
    });
  });

  it('sends backend-compatible debug payload and renders evidence diagnostics', async () => {
    const wrapper = mount(RetrievalDebuggerView, {
      global: {
        stubs: globalStubs,
      },
    });

    await flushPromises();
    await wrapper.get('[data-testid="retrieval-question-input"]').setValue('Who signs expense approvals?');
    await wrapper.get('[data-testid="run-retrieval-debug"]').trigger('click');
    await flushPromises();

    expect(retrieveDebugKB).toHaveBeenCalledWith({
      base_id: 'base-1',
      question: 'Who signs expense approvals?',
      document_ids: [],
      limit: 10,
    });
    expect(wrapper.text()).toContain('Expense Policy');
    expect(wrapper.text()).toContain('Approval Signatures');
    expect(wrapper.text()).toContain('unit-approval');
    expect(wrapper.text()).toContain('Department owner and finance reviewer signatures are required.');
    expect(wrapper.text()).toContain('Render raw_text when quote is empty.');
    expect(wrapper.text()).toContain('structure 1.2000');
    expect(wrapper.text()).toContain('fts 0.8000');
    expect(wrapper.text()).toContain('FTS #1');
    expect(wrapper.text()).toContain('Vector #2');
    expect(wrapper.text()).toContain('12.3456 ms');
    expect(wrapper.text()).toContain('heuristic');
    expect(wrapper.text()).toContain('kb-trace-1');
  });
});
