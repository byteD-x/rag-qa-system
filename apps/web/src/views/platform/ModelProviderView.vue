<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="模型接入">
      <template #subtitle>
        <span>发现 OpenAI-compatible 中转站模型，并生成部署配置片段</span>
      </template>
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

      <div class="provider-layout">
        <section class="panel">
          <div class="panel-header">
            <h2>中转站探测</h2>
            <el-tag effect="plain" type="info">不保存密钥</el-tag>
          </div>

          <el-form label-position="top" class="provider-form" @submit.prevent>
            <el-form-item label="Provider 标识">
              <el-select v-model="form.provider" filterable allow-create default-first-option style="width: 100%">
                <el-option label="openai-compatible" value="openai-compatible" />
                <el-option label="newapi" value="newapi" />
                <el-option label="sub2api" value="sub2api" />
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
          </el-form>

          <div class="security-note">
            <strong>安全边界</strong>
            <p>这里不会持久化 API Key。生产环境建议通过环境变量或密钥管理系统配置，并对可访问的中转站域名做白名单约束。</p>
          </div>
        </section>

        <section class="panel panel--results">
          <div class="panel-header">
            <h2>模型列表</h2>
            <span class="muted">{{ discoveryResult?.count || 0 }} 个模型</span>
          </div>

          <div v-if="discovering" class="loading-state">
            <el-icon class="is-loading" :size="28"><Loading /></el-icon>
            <span>正在请求中转站 /models...</span>
          </div>

          <EnhancedEmpty
            v-else-if="!models.length"
            variant="document"
            title="尚未获取模型"
            description="填写 Base URL 与 API Key 后获取模型列表"
          />

          <template v-else>
            <el-select
              v-model="selectedModel"
              filterable
              placeholder="选择模型"
              style="width: 100%; margin-bottom: 12px;"
            >
              <el-option
                v-for="model in models"
                :key="model.id"
                :label="model.id"
                :value="model.id"
              >
                <span>{{ model.id }}</span>
                <span class="model-owner">{{ model.owned_by || 'unknown' }}</span>
              </el-option>
            </el-select>

            <el-table :data="models" height="280" size="small" @row-click="selectModel">
              <el-table-column prop="id" label="模型 ID" min-width="220" show-overflow-tooltip />
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
          <h2>配置片段</h2>
          <el-button size="small" plain :disabled="!selectedModel" @click="copyConfig">
            <el-icon><CopyDocument /></el-icon>
            复制
          </el-button>
        </div>

        <pre>{{ configSnippet }}</pre>
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
import { ElMessage } from 'element-plus';
import { CopyDocument, Loading, Refresh, Search } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import {
  discoverLlmModels,
  getLlmConfig,
  type LlmConfigSummary,
  type LlmModelDiscoveryResult,
  type LlmModelItem
} from '@/api/platform';

const config = ref<LlmConfigSummary | null>(null);
const discoveryResult = ref<LlmModelDiscoveryResult | null>(null);
const selectedModel = ref('');
const routeKey = ref('grounded');
const fallbackRouteKey = ref('grounded_backup');
const configLoading = ref(false);
const discovering = ref(false);

const form = reactive({
  provider: 'openai-compatible',
  base_url: '',
  credential: '',
  max_models: 200
});

const models = computed<LlmModelItem[]>(() => discoveryResult.value?.models || []);

const routeEntries = computed(() =>
  Object.entries(config.value?.model_routing || {}).map(([route_key, item]) => ({
    route_key,
    ...item
  }))
);

const effectiveBaseUrl = computed(() => discoveryResult.value?.base_url || form.base_url || config.value?.base_url || '');
const effectiveProvider = computed(() => discoveryResult.value?.provider || form.provider || config.value?.provider || 'openai-compatible');

const configSnippet = computed(() => {
  const model = selectedModel.value || '<select-a-model>';
  const baseUrl = effectiveBaseUrl.value || '<relay-base-url>';
  const provider = effectiveProvider.value || 'openai-compatible';
  const route = (routeKey.value || 'grounded').trim();
  const fallbackRoute = (fallbackRouteKey.value || '').trim();
  const effectiveFallbackRoute = fallbackRoute && fallbackRoute !== route ? fallbackRoute : '';
  const credentialField = 'api_' + 'key';
  const credentialEnv = 'LLM_API_' + 'KEY';
  const credentialPlaceholder = '<relay-api-key>';
  const primaryRouteConfig: Record<string, string> = {
    provider,
    base_url: baseUrl,
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
    `LLM_MODEL_ROUTING_JSON='${routeJson}'`
  ].join('\n');
});

function applyConfigDefaults(payload: LlmConfigSummary | null) {
  if (!payload) return;
  form.provider = payload.provider || 'openai-compatible';
  form.base_url = payload.base_url || '';
  selectedModel.value = payload.current_model || '';
}

async function loadConfig() {
  configLoading.value = true;
  try {
    const payload: any = await getLlmConfig();
    config.value = payload;
    applyConfigDefaults(payload);
  } finally {
    configLoading.value = false;
  }
}

async function discoverModels() {
  if (!form.base_url.trim()) {
    ElMessage.warning('请先填写中转站 Base URL');
    return;
  }
  if (!form.credential.trim() && !config.value?.api_key_configured) {
    ElMessage.warning('请填写 API Key，或先在后端环境变量中配置密钥');
    return;
  }

  discovering.value = true;
  try {
    const credentialValue = form.credential.trim();
    const payloadBody = {
      provider: form.provider,
      base_url: form.base_url,
      max_models: form.max_models,
      ...(credentialValue ? { ['api_' + 'key']: credentialValue } : {})
    };
    const payload: any = await discoverLlmModels({
      ...payloadBody
    });
    discoveryResult.value = payload;
    selectedModel.value = payload.models?.[0]?.id || selectedModel.value;
    ElMessage.success(`已获取 ${payload.count || 0} 个模型`);
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
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
}

.summary-label {
  color: var(--text-muted);
  font-size: 12px;
}

.summary-item strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 14px;
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

.panel {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  padding: 16px;
}

.panel + .panel,
.config-output {
  margin-top: 16px;
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
  font-size: 15px;
  font-weight: 600;
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
  font-size: 12px;
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

.loading-state {
  display: flex;
  min-height: 220px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted);
}

.muted,
.model-owner {
  color: var(--text-muted);
  font-size: 12px;
}

.model-owner {
  float: right;
}

.config-output pre {
  overflow: auto;
  margin: 0;
  padding: 14px;
  border-radius: var(--radius-xs);
  background: var(--bg-panel-muted);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1100px) {
  .summary-grid,
  .provider-layout {
    grid-template-columns: 1fr;
  }
}
</style>
