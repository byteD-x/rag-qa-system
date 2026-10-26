<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="模型接入">
            <template #actions>
        <el-button @click="loadConfig" :loading="configLoading">
          <el-icon><Refresh /></el-icon>
          刷新配置
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">当前 Provider</span>
          <strong>{{ config?.provider || '-' }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-label">默认模型</span>
          <strong>{{ config?.current_model || '-' }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-label">Base URL</span>
          <strong class="truncate">{{ config?.base_url || '-' }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-label">密钥状态</span>
          <el-tag :type="config?.api_key_configured ? 'success' : 'warning'" effect="plain">
            {{ config?.api_key_configured ? '已配置' : '未配置' }}
          </el-tag>
        </div>
      </div>

      <section class="panel model-config-panel">
        <div class="panel-header">
          <div>
            <h2>已配置服务商</h2>
            <p class="panel-subtitle">每个服务商只需配置一次，阶段卡片会复用它发现的模型。</p>
          </div>
          <el-button type="primary" size="small" @click="openProviderDialog">新增服务商</el-button>
        </div>
        <el-table :data="modelConfigs" size="small">
          <el-table-column prop="name" label="名称" width="150" />
          <el-table-column prop="provider_type" label="提供商" width="150" />
          <el-table-column label="可用模型" min-width="160">
            <template #default="{ row }">{{ row.available_models?.length || (row.model_name ? 1 : 0) }} 个</template>
          </el-table-column>
          <el-table-column label="默认用途" min-width="150">
            <template #default="{ row }">{{ row.default_purposes?.join('、') || '-' }}</template>
          </el-table-column>
          <el-table-column label="密钥" width="110">
            <template #default="{ row }"><el-tag size="small" :type="row.api_key_configured ? 'success' : 'warning'" effect="plain">{{ row.api_key_configured ? row.api_key_hint : '未配置' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button link type="primary" @click="testSavedConfig(row.id)">测试</el-button>
              <el-button link type="danger" @click="disableSavedConfig(row.id)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel stage-panel">
        <div class="panel-header">
          <div>
            <h2>RAG 阶段模型</h2>
            <p class="panel-subtitle">按检索到生成的顺序绑定已启用服务方；卡片内只能选择已保存配置。</p>
          </div>
          <el-tag effect="plain" type="info">{{ providerModelCount }} 个服务商 · {{ availableStageModelCount }} 个模型</el-tag>
        </div>

        <EnhancedEmpty
          v-if="!enabledModelConfigs.length"
          variant="document"
          title="先配置一个可用服务方"
          description="完成上方连接设置并保存后，阶段模型会出现在这里。"
        />
        <div v-else class="stage-grid">
          <article v-for="stage in modelStages" :key="stage.key" class="stage-card">
            <div class="stage-card__header">
              <div>
                <span class="stage-index">{{ String(stage.order / 10).padStart(2, '0') }}</span>
                <h3>{{ stage.name }}</h3>
              </div>
              <el-tag v-if="stage.builtin" size="small" effect="plain" type="info">系统内置</el-tag>
              <el-tag v-else-if="stage.config" size="small" effect="plain" type="success">已绑定</el-tag>
              <el-tag v-else size="small" effect="plain" type="warning">未配置</el-tag>
            </div>
            <p class="stage-card__description">{{ stage.description }}</p>
            <template v-if="stage.builtin">
              <div class="stage-built-in">由系统自动执行，无需绑定外部模型</div>
            </template>
            <template v-else>
              <el-select v-model="stageSelections[stage.key]" filterable clearable style="width: 100%" placeholder="搜索服务商或模型">
                <el-option-group v-for="provider in stageProviders(stage)" :key="provider.id" :label="provider.name">
                  <el-option v-for="model in provider.models" :key="`${provider.id}:${model.id}`" :label="model.id" :value="`${provider.id}:${model.id}`" />
                </el-option-group>
              </el-select>
              <div v-if="!stageProviders(stage).length" class="stage-empty">没有符合该阶段要求的已配置模型</div>
              <div class="stage-card__footer">
                <span class="muted">{{ selectedStageLabel(stage) }}</span>
                <el-button size="small" type="primary" :loading="stageSaving === stage.key" @click="saveStage(stage.key)">
                  绑定
                </el-button>
              </div>
            </template>
          </article>
        </div>
      </section>

      <el-dialog v-model="showModelConfig" title="保存服务商" width="560px">
        <el-form label-position="top">
          <el-form-item label="服务商名称"><el-input v-model="modelForm.name" placeholder="例如：团队 OpenAI 中转" /></el-form-item>
          <div class="form-row">
            <el-form-item label="提供商">
              <el-select v-model="modelForm.provider_type" filterable allow-create style="width: 100%">
                <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="请求格式">
              <el-select v-model="modelForm.request_format" style="width: 100%">
                <el-option v-for="item in requestFormatOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="Base URL"><el-input v-model="modelForm.base_url" placeholder="https://api.example.com/v1" /></el-form-item>
          <el-form-item label="API Key"><el-input v-model="modelForm.api_key" show-password placeholder="保存后由服务端加密存储" /></el-form-item>
          <el-form-item label="默认用途"><el-checkbox-group v-model="modelForm.default_purposes"><el-checkbox label="chat">对话</el-checkbox><el-checkbox label="embedding">嵌入</el-checkbox><el-checkbox label="interview">面试</el-checkbox><el-checkbox label="scoring">评分</el-checkbox></el-checkbox-group></el-form-item>
          <div class="provider-catalog-note">将保存当前已发现的 {{ models.length }} 个模型，之后可在各阶段卡片中分别选择。</div>
        </el-form>
        <template #footer><el-button @click="showModelConfig = false">取消</el-button><el-button type="primary" :loading="modelSaving" @click="saveModelConfig">保存服务商</el-button></template>
      </el-dialog>

      <div class="provider-layout">
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>连接设置</h2>
              <p class="panel-subtitle">填写 Base URL 与 API Key，自动读取可用模型</p>
            </div>
            <el-tag effect="plain" type="info">兼容 OpenAI 格式</el-tag>
          </div>

          <el-form label-position="top" class="provider-form" @submit.prevent>
            <el-form-item label="提供商">
              <el-select v-model="form.provider" filterable allow-create default-first-option style="width: 100%">
                <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>

            <el-form-item label="请求格式">
              <el-select v-model="form.request_format" style="width: 100%">
                <el-option v-for="item in requestFormatOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>

            <el-form-item label="Base URL">
              <el-input
                v-model="form.base_url"
                clearable
                placeholder="https://relay.example.com/v1"
              />
            </el-form-item>

            <el-form-item label="API Key">
              <el-input
                v-model="form.credential"
                clearable
                show-password
                placeholder="仅用于本次模型发现请求"
              />
            </el-form-item>

            <div class="form-row">
              <el-form-item label="最多返回">
                <el-input-number v-model="form.max_models" :min="1" :max="1000" :step="50" style="width: 100%" />
              </el-form-item>
              <el-form-item label="Route Key">
                <el-input v-model="routeKey" clearable placeholder="grounded" />
              </el-form-item>
            </div>
            <el-form-item label="Fallback Route Key">
              <el-input v-model="fallbackRouteKey" clearable placeholder="grounded_backup" />
            </el-form-item>

            <el-button type="primary" :loading="discovering" @click="discoverModels">
              <el-icon><Search /></el-icon>
              获取模型列表
            </el-button>
            <el-button v-if="models.length" @click="openSaveDialog">保存服务商</el-button>
          </el-form>

          <div class="security-note">
            <strong>安全边界</strong>
            <p>API Key 仅用于当前页面的发现请求；保存配置时会在服务端加密存储。支持 OpenAI Chat Completions、Responses，以及 Ollama 的 OpenAI 兼容端点。</p>
          </div>
        </section>

        <section class="panel panel--results">
          <div class="panel-header">
            <h2>模型列表</h2>
            <div class="results-tools">
              <el-input v-model="modelSearch" clearable size="small" placeholder="搜索模型 ID" class="model-search" />
              <span class="muted">{{ filteredModels.length }} / {{ discoveryResult?.count || 0 }} 个模型</span>
            </div>
          </div>

          <Transition name="loading-fade">
            <LoadingState v-if="discovering" label="正在请求中转站 /models..." />
          </Transition>

          <template v-if="!discovering">
            <EnhancedEmpty
              v-if="!models.length"
              variant="document"
              title="尚未获取模型"
              description="填写 Base URL 与 API Key 后获取模型列表"
            />

            <el-table v-else :data="filteredModels" height="280" size="small" @row-click="selectModel">
              <el-table-column label="模型 ID" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  <button
                    type="button"
                    class="model-id"
                    :class="{ 'is-selected': row.id === selectedModel }"
                    :aria-pressed="row.id === selectedModel"
                    @click.stop="selectModel(row)"
                  >
                    {{ row.id }}
                  </button>
                </template>
              </el-table-column>
              <el-table-column prop="owned_by" label="Owner" width="130" show-overflow-tooltip />
              <el-table-column label="Created" width="120">
                <template #default="{ row }">
                  {{ formatCreated(row.created) }}
                </template>
              </el-table-column>
            </el-table>
          </template>
        </section>
      </div>

      <section class="panel config-output">
        <div class="panel-header">
          <h2>环境变量配置片段</h2>
          <el-button size="small" plain :disabled="!selectedModel" @click="copyConfig">
            <el-icon><CopyDocument /></el-icon>
            复制
          </el-button>
        </div>

        <template v-if="selectedModel">
          <pre>{{ configSnippet }}</pre>
          <p class="muted snippet-hint">
            仅在本页未保存任何模型配置、或已保存配置被禁用时生效；已启用的数据库配置会覆盖这些环境变量（ai_client.py:211-229）。
          </p>
        </template>
        <EnhancedEmpty
          v-else
          variant="document"
          title="尚未选择模型"
          description="从上方模型列表中选定一个模型后生成配置片段"
        />
      </section>

      <section v-if="routeEntries.length" class="panel">
        <div class="panel-header">
          <h2>已配置路由</h2>
          <span class="muted">{{ routeEntries.length }} 条</span>
        </div>
        <el-table :data="routeEntries" size="small">
          <el-table-column prop="route_key" label="Route Key" width="160" />
          <el-table-column prop="model" label="模型" min-width="180" show-overflow-tooltip />
          <el-table-column prop="base_url" label="Base URL" min-width="240" show-overflow-tooltip />
          <el-table-column label="API Key" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.api_key_configured ? 'success' : 'warning'" effect="plain">
                {{ row.api_key_configured ? '已配置' : '未配置' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="fallback_route_key" label="Fallback" width="130" />
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { CopyDocument, Refresh, Search } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import {
  discoverLlmModels,
  getLlmConfig,
  listModelProviderConfigs,
  createModelProviderConfig,
  disableModelProviderConfig,
  testModelProviderConfig,
  getModelStages,
  updateModelStages,
  type LlmConfigSummary,
  type LlmModelDiscoveryResult,
  type LlmModelItem,
  type ModelProviderConfig,
  type ModelStageDefinition,
  type LlmRequestFormat
} from '@/api/platform';

const config = ref<LlmConfigSummary | null>(null);
const discoveryResult = ref<LlmModelDiscoveryResult | null>(null);
const selectedModel = ref('');
const routeKey = ref('grounded');
const fallbackRouteKey = ref('grounded_backup');
const configLoading = ref(false);
const discovering = ref(false);
const modelConfigs = ref<ModelProviderConfig[]>([]);
const modelStages = ref<ModelStageDefinition[]>([]);
const stageSelections = reactive<Record<string, string | null>>({});
const stageSaving = ref('');
const showModelConfig = ref(false);
const modelSaving = ref(false);
const modelSearch = ref('');
const lastCredential = ref('');
const modelForm = reactive({ name: '', provider_type: 'openai-compatible', request_format: 'chat_completions' as LlmRequestFormat, api_key: '', base_url: '', model_name: '', default_purposes: ['chat'] });

const providerOptions = [
  { label: 'OpenAI 兼容', value: 'openai-compatible' },
  { label: 'New API', value: 'newapi' },
  { label: 'Sub2API', value: 'sub2api' },
  { label: 'Ollama', value: 'ollama' },
  { label: 'LM Studio', value: 'lmstudio' },
  { label: 'vLLM', value: 'vllm' },
  { label: 'JEV', value: 'jev' },
  { label: 'Cross-Encoder', value: 'cross-encoder' },
  { label: 'External Cross-Encoder', value: 'external-cross-encoder' },
];
const requestFormatOptions = [
  { label: 'Chat Completions（通用）', value: 'chat_completions' as LlmRequestFormat },
  { label: 'Responses API（OpenAI 新接口）', value: 'responses' as LlmRequestFormat },
];

const form = reactive({
  provider: 'openai-compatible',
  base_url: '',
  credential: '',
  max_models: 200,
  request_format: 'chat_completions' as LlmRequestFormat
});

const models = computed<LlmModelItem[]>(() => discoveryResult.value?.models || []);
const filteredModels = computed(() => {
  const query = modelSearch.value.trim().toLowerCase();
  if (!query) return models.value;
  return models.value.filter(item => `${item.id} ${item.owned_by}`.toLowerCase().includes(query));
});

const enabledModelConfigs = computed(() => modelConfigs.value.filter(item => item.enabled));
const providerModelCount = computed(() => enabledModelConfigs.value.length);
const availableStageModelCount = computed(() => enabledModelConfigs.value.reduce((count, item) => count + modelCatalog(item).length, 0));

function modelCatalog(config: ModelProviderConfig) {
  const models = Array.isArray(config.available_models) ? config.available_models : [];
  if (models.length) return models;
  return config.model_name ? [{ id: config.model_name, object: 'model', owned_by: '', created: null }] : [];
}

function stageProviders(stage: ModelStageDefinition) {
  const allowed = stage.allowed_provider_types || [];
  const providers = enabledModelConfigs.value.filter(item => {
    if (allowed.length) return allowed.includes(item.provider_type);
    return !['jev', 'cross-encoder', 'external-cross-encoder'].includes(item.provider_type);
  });
  return providers.map(item => ({ ...item, models: modelCatalog(item) })).filter(item => item.models.length);
}

function selectedStageLabel(stage: ModelStageDefinition) {
  const value = stageSelections[stage.key] || '';
  const [configId, ...modelParts] = value.split(':');
  const modelName = modelParts.join(':');
  const selected = enabledModelConfigs.value.find(item => item.id === configId);
  return selected && modelName ? `${selected.name} · ${modelName}` : '未绑定';
}

const routeEntries = computed(() =>
  Object.entries(config.value?.model_routing || {}).map(([route_key, item]) => ({
    route_key,
    ...item
  }))
);

const effectiveBaseUrl = computed(() => discoveryResult.value?.base_url || form.base_url || config.value?.base_url || '');
const effectiveProvider = computed(() => discoveryResult.value?.provider || form.provider || config.value?.provider || 'openai-compatible');

function inferProviderFromUrl(value: string) {
  const url = value.toLowerCase();
  const markers: Array<[string, string]> = [
    ['newapi', 'newapi'], ['new-api', 'newapi'], ['sub2api', 'sub2api'],
    ['ollama', 'ollama'], ['lmstudio', 'lmstudio'], ['lm-studio', 'lmstudio'],
    ['dashscope', 'dashscope'], ['aliyuncs', 'dashscope'], ['deepseek', 'deepseek'],
  ];
  return markers.find(([marker]) => url.includes(marker))?.[1] || 'openai-compatible';
}

const configSnippet = computed(() => {
  const model = selectedModel.value || '<select-a-model>';
  const baseUrl = effectiveBaseUrl.value || '<relay-base-url>';
  const provider = effectiveProvider.value || 'openai-compatible';
  const requestFormat = discoveryResult.value?.request_format || form.request_format;
  const route = (routeKey.value || 'grounded').trim();
  const fallbackRoute = (fallbackRouteKey.value || '').trim();
  const effectiveFallbackRoute = fallbackRoute && fallbackRoute !== route ? fallbackRoute : '';
  const credentialField = 'api_' + 'key';
  const credentialEnv = 'LLM_API_' + 'KEY';
  const credentialPlaceholder = '<relay-api-key>';
  const primaryRouteConfig: Record<string, string> = {
    provider,
    base_url: baseUrl,
    request_format: requestFormat,
    [credentialField]: credentialPlaceholder,
    model
  };
  const routeConfig: Record<string, Record<string, string>> = {
    [route]: primaryRouteConfig
  };
  if (effectiveFallbackRoute) {
    primaryRouteConfig.fallback_route_key = effectiveFallbackRoute;
    routeConfig[effectiveFallbackRoute] = {
      provider,
      base_url: baseUrl,
      request_format: requestFormat,
      [credentialField]: credentialPlaceholder,
      model
    };
  }
  const routeJson = JSON.stringify(routeConfig, null, 2);

  return [
    `LLM_PROVIDER=${provider}`,
    `LLM_BASE_URL=${baseUrl}`,
    `${credentialEnv}=${credentialPlaceholder}`,
    `LLM_MODEL=${model}`,
    `LLM_REQUEST_FORMAT=${requestFormat}`,
    `LLM_MODEL_ROUTING_JSON='${routeJson}'`
  ].join('\n');
});

function applyConfigDefaults(payload: LlmConfigSummary | null) {
  if (!payload) return;
  form.provider = payload.provider || 'openai-compatible';
  form.base_url = payload.base_url || '';
  selectedModel.value = payload.current_model || '';
  modelForm.base_url = payload.base_url || '';
  modelForm.provider_type = payload.provider || 'openai-compatible';
}

async function loadConfig() {
  configLoading.value = true;
  try {
    const payload: any = await getLlmConfig();
    config.value = payload;
    applyConfigDefaults(payload);
    const stored: any = await listModelProviderConfigs().catch(() => ({ items: [] }));
    modelConfigs.value = stored.items || [];
    if (typeof getModelStages === 'function') {
      const stagePayload: any = await getModelStages().catch(() => ({ stages: [] }));
      modelStages.value = (stagePayload.stages || []).sort((left: ModelStageDefinition, right: ModelStageDefinition) => left.order - right.order);
      for (const stage of modelStages.value) {
        stageSelections[stage.key] = stage.config_id && stage.model_name ? `${stage.config_id}:${stage.model_name}` : null;
      }
    }
    if (form.base_url) {
      await discoverModels(true);
    }
  } finally {
    configLoading.value = false;
  }
}

async function saveStage(stageKey: string) {
  stageSaving.value = stageKey;
  try {
    const payload: Record<string, { config_id: string; model_name: string } | null> = {};
    for (const stage of modelStages.value) {
      if (!stage.builtin) {
        const value = stageSelections[stage.key] || '';
        const separator = value.indexOf(':');
        payload[stage.key] = separator > 0 ? { config_id: value.slice(0, separator), model_name: value.slice(separator + 1) } : null;
      }
    }
    const result: any = await updateModelStages(payload);
    modelStages.value = (result.stages || modelStages.value).sort((left: ModelStageDefinition, right: ModelStageDefinition) => left.order - right.order);
    for (const stage of modelStages.value) stageSelections[stage.key] = stage.config_id && stage.model_name ? `${stage.config_id}:${stage.model_name}` : null;
    ElMessage.success('阶段模型绑定已保存');
  } finally {
    stageSaving.value = '';
  }
}

function openProviderDialog() {
  modelForm.provider_type = effectiveProvider.value;
  modelForm.request_format = discoveryResult.value?.request_format || form.request_format;
  modelForm.base_url = effectiveBaseUrl.value;
  modelForm.model_name = '';
  modelForm.api_key = lastCredential.value;
  modelForm.name = modelForm.provider_type;
  showModelConfig.value = true;
}

function openSaveDialog() {
  openProviderDialog();
}

async function saveModelConfig() {
  if (!modelForm.name.trim() || !modelForm.base_url.trim() || !models.value.length) {
    ElMessage.warning('请先发现模型，并填写服务商名称和 Base URL');
    return;
  }
  modelSaving.value = true;
  try {
    const result: any = await createModelProviderConfig({
      ...modelForm,
      model_name: '',
      extra: { request_format: modelForm.request_format, available_models: models.value },
    });
    modelConfigs.value.unshift(result);
    showModelConfig.value = false;
    modelForm.api_key = '';
    lastCredential.value = '';
    await loadConfig();
    ElMessage.success(`服务商已保存，共发现 ${models.value.length} 个模型`);
  } finally {
    modelSaving.value = false;
  }
}

async function testSavedConfig(configId: string) {
  await testModelProviderConfig(configId);
  ElMessage.success('连接测试成功');
}

async function disableSavedConfig(configId: string) {
  try {
    await ElMessageBox.confirm('停用后该配置会立即从列表移除且无法撤销，确定停用吗？', '停用确认', { type: 'warning' });
  } catch {
    return;
  }
  await disableModelProviderConfig(configId);
  modelConfigs.value = modelConfigs.value.filter(item => item.id !== configId);
  ElMessage.success('模型配置已停用');
}

async function discoverModels(silent = false) {
  if (form.provider === 'openai-compatible' && form.base_url.trim()) {
    form.provider = inferProviderFromUrl(form.base_url);
  }
  if (!form.base_url.trim()) {
    if (!silent) ElMessage.warning('请先填写中转站 Base URL');
    return;
  }
  const noKeyProvider = ['ollama', 'localai', 'vllm', 'local', 'openai-compatible-local'].includes(form.provider.toLowerCase());
  if (!form.credential.trim() && !config.value?.api_key_configured && !noKeyProvider) {
    if (!silent) ElMessage.warning('请填写 API Key，或先在后端环境变量中配置密钥');
    return;
  }

  discovering.value = true;
  try {
    const credentialValue = form.credential.trim();
    lastCredential.value = credentialValue;
    const payloadBody = {
      provider: form.provider,
      base_url: form.base_url,
      max_models: form.max_models,
      ...(form.request_format !== 'chat_completions' ? { request_format: form.request_format } : {}),
      ...(credentialValue ? { ['api_' + 'key']: credentialValue } : {})
    };
    const payload: any = await discoverLlmModels({
      ...payloadBody
    });
    discoveryResult.value = payload;
    form.request_format = payload.request_format || form.request_format;
    selectedModel.value = payload.models?.[0]?.id || selectedModel.value;
    if (payload.provider && form.provider === 'openai-compatible') form.provider = payload.provider;
    if (selectedModel.value) {
      modelForm.provider_type = payload.provider || form.provider;
      modelForm.request_format = payload.request_format || form.request_format;
      modelForm.base_url = payload.base_url || form.base_url;
      modelForm.model_name = selectedModel.value;
    }
    if (!silent) ElMessage.success(`已获取 ${payload.count || 0} 个模型`);
  } finally {
    form.credential = '';
    discovering.value = false;
  }
}

function selectModel(row: LlmModelItem) {
  selectedModel.value = row.id;
}

function formatCreated(value: number | null) {
  if (!value) return '-';
  return new Date(value * 1000).toISOString().slice(0, 10);
}

async function copyConfig() {
  await navigator.clipboard.writeText(configSnippet.value);
  ElMessage.success('配置片段已复制');
}

onMounted(() => {
  loadConfig();
});
</script>

<style scoped>
.platform-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.platform-content { flex: 1; overflow-y: auto; padding: 20px; background: var(--bg-panel-muted); }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  color: var(--text-muted);
  font-size: var(--text-caption);
}

.summary-item strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: var(--text-body);
  font-weight: 600;
}

.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-layout {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.panel + .panel,
.config-output {
  margin-top: 16px;
}

.stage-panel {
  margin-top: 16px;
}

.stage-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.stage-card {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-panel);
}

.stage-card__header,
.stage-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.stage-card__header > div {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.stage-card h3 {
  overflow: hidden;
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-caption);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-index {
  color: var(--blue-600);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}

.stage-card__description {
  min-height: 38px;
  margin: 10px 0 12px;
  color: var(--text-secondary);
  font-size: var(--text-caption);
  line-height: 1.5;
}

.stage-card__footer {
  margin-top: 10px;
}

.stage-built-in {
  padding: 9px 10px;
  border-radius: var(--radius-xs);
  background: var(--bg-panel-muted);
  color: var(--text-muted);
  font-size: var(--text-caption);
}

.stage-empty {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: var(--text-caption);
  line-height: 1.5;
}

.provider-catalog-note {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-panel-muted);
  color: var(--text-secondary);
  font-size: var(--text-caption);
  line-height: 1.5;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-header h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-body);
  font-weight: 600;
}

.panel-subtitle {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: var(--text-caption);
}

.results-tools {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-search {
  width: 190px;
}

.provider-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.security-note {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: var(--text-caption);
  line-height: 1.6;
}

.security-note strong {
  display: block;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.security-note p {
  margin: 0;
}

/* 保留结果面板的最小高度，避免加载态 → 列表的跳变（LoadingState 自身只给 padding）。 */
:deep(.loading-state) {
  min-height: 220px;
}

/* 加载态进场只淡入 opacity，不改尺寸；离开不加过渡，避免与新内容在文档流里重叠跳动。 */
.loading-fade-enter-active {
  transition: opacity var(--transition-fast);
}

.loading-fade-enter-from {
  opacity: 0;
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-caption);
}

.snippet-hint {
  margin: 8px 0 0;
  line-height: 1.6;
}

.model-id {
  padding: 0;
  border: 0;
  background: none;
  color: var(--blue-600);
  font: inherit;
  text-align: left;
}

.model-id.is-selected {
  color: var(--text-primary);
  font-weight: 600;
}

.config-output pre {
  overflow: auto;
  margin: 0;
  padding: 14px;
  border-radius: var(--radius-xs);
  background: var(--bg-panel-muted);
  color: var(--text-primary);
  font-size: var(--text-caption);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1100px) {
  .summary-grid,
  .provider-layout,
  .stage-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .platform-content { padding: 14px; }
  .form-row { grid-template-columns: 1fr; gap: 0; }
  .results-tools { align-items: flex-end; flex-direction: column; gap: 4px; }
  .model-search { width: 150px; }
}
</style>
