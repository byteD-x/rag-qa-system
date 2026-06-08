import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { discoverLlmModels, getLlmConfig, messageSuccess, messageWarning } = vi.hoisted(() => ({
  discoverLlmModels: vi.fn(),
  getLlmConfig: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
}));

vi.mock('element-plus', () => ({
  ElMessage: {
    success: messageSuccess,
    warning: messageWarning,
  },
}));

vi.mock('@/api/platform', () => ({
  discoverLlmModels,
  getLlmConfig,
}));

import ModelProviderView from './ModelProviderView.vue';

const globalStubs = {
  PageHeaderCompact: {
    props: ['title'],
    template: '<header><h1>{{ title }}</h1><slot name="subtitle" /><slot name="actions" /></header>',
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
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    template: '<input :placeholder="placeholder" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
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
  'el-table': {
    props: ['data'],
    emits: ['row-click'],
    template: `
      <table>
        <tbody>
          <tr v-for="row in data" :key="row.id" @click="$emit('row-click', row)">
            <td>{{ row.id }}</td>
            <td>{{ row.owned_by }}</td>
          </tr>
        </tbody>
      </table>
    `,
  },
  'el-table-column': true,
  'el-tag': {
    template: '<span><slot /></span>',
  },
  'el-icon': {
    template: '<i><slot /></i>',
  },
  CopyDocument: true,
  Loading: true,
  Refresh: true,
  Search: true,
};

function extractRoutingJson(snippet: string) {
  const prefix = "LLM_MODEL_ROUTING_JSON='";
  const start = snippet.indexOf(prefix);
  expect(start).toBeGreaterThanOrEqual(0);
  const jsonText = snippet.slice(start + prefix.length, -1);
  return JSON.parse(jsonText);
}

describe('ModelProviderView', () => {
  beforeEach(() => {
    discoverLlmModels.mockReset();
    getLlmConfig.mockReset();
    messageSuccess.mockReset();
    messageWarning.mockReset();

    getLlmConfig.mockResolvedValue({
      enabled: true,
      configured: false,
      provider: 'openai-compatible',
      base_url: '',
      api_key_configured: false,
      current_model: '',
      common_knowledge_model: '',
      model_routing: {},
    });
    discoverLlmModels.mockResolvedValue({
      provider: 'newapi',
      base_url: 'https://relay.example.test/v1',
      models_url: 'https://relay.example.test/v1/models',
      api_key_configured: true,
      current_model: '',
      models: [
        { id: 'gpt-4.1-mini', object: 'model', owned_by: 'relay', created: 1710000000 },
        { id: 'qwen-plus', object: 'model', owned_by: 'relay', created: 1710000100 },
      ],
      count: 2,
    });
  });

  it('selects the first discovered model and renders a deployable routing snippet', async () => {
    const relayCredential = ['sample', 'credential'].join('-');
    const wrapper = mount(ModelProviderView, {
      global: {
        stubs: globalStubs,
      },
    });

    await flushPromises();

    const inputs = wrapper.findAll('input');
    const baseUrlInput = inputs.find((input) => input.attributes('placeholder') === 'https://relay.example.com/v1');
    const credentialInput = inputs.find((input) => {
      const placeholder = input.attributes('placeholder');
      return placeholder !== 'https://relay.example.com/v1' && placeholder !== 'grounded' && input.attributes('type') !== 'number';
    });

    expect(baseUrlInput).toBeTruthy();
    expect(credentialInput).toBeTruthy();

    await baseUrlInput!.setValue('https://relay.example.test/v1');
    await credentialInput!.setValue(relayCredential);
    const discoverButton = wrapper.findAll('button')[1];
    expect(discoverButton).toBeTruthy();
    await discoverButton!.trigger('click');
    await flushPromises();

    expect(discoverLlmModels).toHaveBeenCalledWith({
      provider: 'openai-compatible',
      base_url: 'https://relay.example.test/v1',
      max_models: 200,
      ['api_' + 'key']: relayCredential,
    });

    const modelSelect = wrapper.findAll('select').find((select) => (select.element as HTMLSelectElement).value === 'gpt-4.1-mini');
    expect(modelSelect).toBeTruthy();

    const snippet = wrapper.get('pre').text();
    expect(snippet).toContain('LLM_PROVIDER=newapi');
    expect(snippet).toContain('LLM_BASE_URL=https://relay.example.test/v1');
    expect(snippet).toContain('LLM_MODEL=gpt-4.1-mini');

    const routing = extractRoutingJson(snippet);
    expect(Object.keys(routing)).toEqual(['grounded']);
    expect(routing.grounded).toMatchObject({
      provider: 'newapi',
      base_url: 'https://relay.example.test/v1',
      model: 'gpt-4.1-mini',
    });
  });
});
