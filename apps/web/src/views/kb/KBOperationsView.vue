<template>
  <div class="page-shell operations-page">
    <PageHeaderCompact title="知识库运维总览">
      <template #subtitle>
        <span>面向知识库管理员的值班视图，聚合健康检查、ingest 风险、连接器运行和近期事故流。</span>
        <span v-if="operations">生成时间：{{ formatDateTime(operations.generated_at) }}</span>
      </template>
      <template #actions>
        <select v-if="authStore.isAdmin()" v-model="viewMode" class="toolbar-select" @change="reloadAll">
          <option value="personal">个人范围</option>
          <option value="admin">管理范围</option>
        </select>
        <select v-model.number="days" class="toolbar-select" @change="reloadAll">
          <option :value="7">最近 7 天</option>
          <option :value="14">最近 14 天</option>
          <option :value="30">最近 30 天</option>
        </select>
        <button type="button" class="toolbar-button" :disabled="loading" @click="reloadAll">刷新</button>
        <button
          type="button"
          class="toolbar-button toolbar-button--primary"
          :disabled="runDueLoading"
          data-testid="run-due-button"
          @click="handleRunDueConnectors"
        >
          {{ runDueLoading ? '执行中...' : '执行到期连接器' }}
        </button>
      </template>
    </PageHeaderCompact>

    <div v-if="loading" class="operations-loading">正在加载运维数据...</div>
    <div v-else-if="!operations" class="operations-empty">未获取到运维数据，请稍后重试。</div>
    <div v-else class="operations-content">
      <section class="operations-card">
        <div class="card-header">
          <div>
            <h3>服务健康</h3>
            <p>直接复用 KB `readyz` 依赖检查，并结合区块降级状态给出聚合结论。</p>
          </div>
          <span class="status-pill" :class="statusClass(operations.service_health.status)">
            {{ statusLabel(operations.service_health.status) }}
          </span>
        </div>
        <div class="health-grid">
          <div v-for="(check, key) in operations.service_health.checks" :key="key" class="health-item">
            <div class="health-item__header">
              <strong>{{ healthLabel(key) }}</strong>
              <span class="status-pill status-pill--small" :class="statusClass(check.status)">{{ statusLabel(check.status) }}</span>
            </div>
            <p v-if="check.detail" class="health-item__detail">{{ check.detail }}</p>
          </div>
        </div>
        <div v-if="operations.data_quality.degraded_sections.length" class="degraded-banner">
          <strong>当前部分区块已降级：</strong>
          <span v-for="item in operations.data_quality.degraded_sections" :key="item.key">{{ item.key }}</span>
        </div>
      </section>

      <section class="operations-grid">
        <article class="operations-card">
          <div class="card-header">
            <div>
              <h3>Ingest 风险队列</h3>
              <p>优先处理可重试任务和长时间无推进的文档。</p>
            </div>
            <button type="button" class="link-button" @click="go('/workspace/kb/governance')">去治理页</button>
          </div>

          <div class="metric-row">
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.ingest_ops.summary.failed_documents }}</span>
              <span class="metric-box__label">失败文档</span>
            </div>
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.ingest_ops.summary.dead_letter_documents }}</span>
              <span class="metric-box__label">Dead letter</span>
            </div>
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.ingest_ops.summary.stalled_documents }}</span>
              <span class="metric-box__label">长时间卡住</span>
            </div>
          </div>

          <div class="subsection">
            <div class="subsection__header">
              <strong>可重试任务</strong>
              <span>{{ operations.ingest_ops.retryable_jobs.length }} 条</span>
            </div>
            <div v-if="!operations.ingest_ops.retryable_jobs.length" class="empty-inline">当前没有需要人工重试的 ingest job。</div>
            <div v-else class="item-list">
              <div v-for="job in operations.ingest_ops.retryable_jobs" :key="job.job_id" class="item-card">
                <div class="item-card__main">
                  <div class="item-card__title">{{ job.file_name }}</div>
                  <div class="item-card__meta">
                    <span>{{ job.base_name }}</span>
                    <span>{{ job.job_status }}</span>
                    <span v-if="job.last_error_code">{{ job.last_error_code }}</span>
                    <span>{{ formatDateTime(job.updated_at) }}</span>
                  </div>
                  <p v-if="job.error_message" class="item-card__detail">{{ job.error_message }}</p>
                </div>
                <div class="item-card__actions">
                  <button
                    type="button"
                    class="toolbar-button toolbar-button--primary"
                    :disabled="retryingJobId === job.job_id"
                    :data-testid="`retry-job-${job.job_id}`"
                    @click="handleRetryJob(job)"
                  >
                    {{ retryingJobId === job.job_id ? '重试中...' : '重试 ingest' }}
                  </button>
                  <button type="button" class="toolbar-button" @click="go(`/workspace/kb/documents/${job.document_id}`)">文档详情</button>
                </div>
              </div>
            </div>
          </div>

          <div class="subsection">
            <div class="subsection__header">
              <strong>卡住文档</strong>
              <span>阈值 {{ operations.ingest_ops.summary.stalled_threshold_hours }} 小时</span>
            </div>
            <div v-if="!operations.ingest_ops.stalled_documents.length" class="empty-inline">当前没有超过阈值仍未推进的文档。</div>
            <div v-else class="item-list">
              <div v-for="document in operations.ingest_ops.stalled_documents" :key="document.document_id" class="item-card">
                <div class="item-card__main">
                  <div class="item-card__title">{{ document.file_name }}</div>
                  <div class="item-card__meta">
                    <span>{{ document.base_name }}</span>
                    <span>{{ document.document_status || 'unknown' }}</span>
                    <span>{{ document.job_status || 'no-job' }}</span>
                    <span>{{ formatDateTime(document.last_activity_at) }}</span>
                  </div>
                  <p v-if="document.error_message" class="item-card__detail">{{ document.error_message }}</p>
                </div>
                <div class="item-card__actions">
                  <button type="button" class="toolbar-button" @click="go(`/workspace/kb/documents/${document.document_id}`)">文档详情</button>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="operations-card">
          <div class="card-header">
            <div>
              <h3>Connector 运行看板</h3>
              <p>优先关注到期调度和最近失败运行。</p>
            </div>
            <button type="button" class="link-button" @click="go('/workspace/kb/connectors')">管理连接器</button>
          </div>

          <div class="metric-row">
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.connector_ops.summary.total_connectors }}</span>
              <span class="metric-box__label">连接器总数</span>
            </div>
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.connector_ops.summary.scheduled_connectors }}</span>
              <span class="metric-box__label">启用调度</span>
            </div>
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.connector_ops.summary.due_connectors }}</span>
              <span class="metric-box__label">当前到期</span>
            </div>
            <div class="metric-box">
              <span class="metric-box__value">{{ operations.connector_ops.summary.recent_failed_runs }}</span>
              <span class="metric-box__label">近期失败</span>
            </div>
          </div>

          <div v-if="!operations.connector_ops.items.length" class="empty-inline">当前范围内没有连接器运行项。</div>
          <div v-else class="item-list">
            <div v-for="connector in operations.connector_ops.items" :key="connector.connector_id" class="item-card">
              <div class="item-card__main">
                <div class="item-card__title">{{ connector.name }}</div>
                <div class="item-card__meta">
                  <span>{{ connector.base_name }}</span>
                  <span>{{ connector.connector_type }}</span>
                  <span>{{ connector.schedule_enabled ? 'schedule:on' : 'schedule:off' }}</span>
                  <span v-if="connector.last_run_outcome">{{ connector.last_run_outcome }}</span>
                  <span>{{ connector.next_run_at ? `next ${formatDateTime(connector.next_run_at)}` : '无下次调度' }}</span>
                </div>
                <p v-if="connector.last_error" class="item-card__detail">{{ connector.last_error }}</p>
              </div>
              <div class="item-card__actions">
                <button
                  type="button"
                  class="toolbar-button toolbar-button--primary"
                  :disabled="runningConnectorId === connector.connector_id"
                  :data-testid="`run-connector-${connector.connector_id}`"
                  @click="handleRunConnector(connector)"
                >
                  {{ runningConnectorId === connector.connector_id ? '执行中...' : '立即同步' }}
                </button>
                <button type="button" class="toolbar-button" @click="go('/workspace/kb/connectors')">连接器页</button>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="operations-card">
        <div class="card-header">
          <div>
            <h3>事故事件流</h3>
            <p>仅展示 ingest / connector 相关的失败、重试和降级事件。</p>
          </div>
        </div>
        <div v-if="!operations.incident_feed.items.length" class="empty-inline">当前时间窗口内没有新的运维事故事件。</div>
        <div v-else class="incident-list">
          <div v-for="item in operations.incident_feed.items" :key="item.id" class="incident-item">
            <div class="incident-item__header">
              <strong>{{ item.action }}</strong>
              <span class="status-pill status-pill--small" :class="statusClass(item.outcome)">{{ item.outcome }}</span>
            </div>
            <div class="incident-item__meta">
              <span>{{ item.resource_type }} / {{ item.resource_id || '-' }}</span>
              <span>trace: {{ item.trace_id || '-' }}</span>
              <span>{{ formatDateTime(item.created_at) }}</span>
            </div>
            <pre class="incident-item__details">{{ stringifyDetails(item.details) }}</pre>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import {
  getKBOperations,
  retryKBIngestJob,
  runDueConnectors,
  syncConnector,
  type KBOperationsConnectorItem,
  type KBOperationsResponse,
  type KBOperationsRetryableJob,
} from '@/api/kb';
import { useAuthStore } from '@/store/auth';
import { formatDateTime } from '@/utils/time';

const router = useRouter();
const authStore = useAuthStore();

const loading = ref(true);
const runDueLoading = ref(false);
const retryingJobId = ref('');
const runningConnectorId = ref('');
const viewMode = ref<'personal' | 'admin'>(authStore.isAdmin() ? 'admin' : 'personal');
const days = ref(14);
const operations = ref<KBOperationsResponse | null>(null);

const reloadParams = computed(() => ({
  view: viewMode.value,
  days: days.value,
}));

const applyOperationsPayload = (payload: KBOperationsResponse, sections: Array<'service_health' | 'ingest_ops' | 'connector_ops' | 'incident_feed' | 'data_quality'> | 'all' = 'all') => {
  if (sections === 'all' || !operations.value) {
    operations.value = payload;
    return;
  }
  operations.value = {
    ...operations.value,
    generated_at: payload.generated_at,
    data_quality: payload.data_quality,
    ...(sections.includes('service_health') ? { service_health: payload.service_health } : {}),
    ...(sections.includes('ingest_ops') ? { ingest_ops: payload.ingest_ops } : {}),
    ...(sections.includes('connector_ops') ? { connector_ops: payload.connector_ops } : {}),
    ...(sections.includes('incident_feed') ? { incident_feed: payload.incident_feed } : {}),
  };
};

const fetchOperations = async (sections: Array<'service_health' | 'ingest_ops' | 'connector_ops' | 'incident_feed' | 'data_quality'> | 'all' = 'all') => {
  const response = await getKBOperations(reloadParams.value);
  const payload = ((response as any).data ?? response) as KBOperationsResponse;
  applyOperationsPayload(payload, sections);
};

const reloadAll = async () => {
  loading.value = true;
  try {
    await fetchOperations('all');
  } finally {
    loading.value = false;
  }
};

const go = (path: string) => {
  router.push(path);
};

const statusClass = (status?: string) => ({
  'status-pill--ok': status === 'ok' || status === 'success',
  'status-pill--warning': status === 'degraded' || status === 'retry' || status === 'partial_success',
  'status-pill--danger': status === 'failed' || status === 'denied',
});

const statusLabel = (status?: string) => {
  if (status === 'ok') return '健康';
  if (status === 'degraded') return '降级';
  if (status === 'failed') return '失败';
  if (status === 'success') return '成功';
  if (status === 'retry') return '重试';
  if (status === 'partial_success') return '部分成功';
  if (status === 'denied') return '拒绝';
  return status || 'unknown';
};

const healthLabel = (key: string) => ({
  database: '数据库',
  object_storage: '对象存储',
  vector_store: '向量库',
}[key] || key);

const stringifyDetails = (value: Record<string, unknown>) => JSON.stringify(value || {}, null, 2);

const buildErrorMessage = (error: unknown, actionLabel: string) => {
  const payload = (error as any)?.response?.data ?? {};
  const code = String(payload.code || '').trim();
  const traceId = String(payload.trace_id || '').trim();
  const detail = String(payload.detail || '').trim();
  const meta = [code ? `code=${code}` : '', traceId ? `trace=${traceId}` : ''].filter(Boolean).join(' / ');
  return [actionLabel, detail || '请求失败', meta].filter(Boolean).join(' | ');
};

const handleRetryJob = async (job: KBOperationsRetryableJob) => {
  if (!window.confirm(`确认重试文档“${job.file_name}”对应的 ingest 任务吗？`)) {
    return;
  }
  retryingJobId.value = job.job_id;
  try {
    await retryKBIngestJob(job.job_id);
    ElMessage.success('已提交 ingest 重试');
    await fetchOperations(['ingest_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    ElMessage.error(buildErrorMessage(error, 'ingest 重试失败'));
  } finally {
    retryingJobId.value = '';
  }
};

const handleRunConnector = async (connector: KBOperationsConnectorItem) => {
  if (!window.confirm(`确认立即执行连接器“${connector.name}”吗？`)) {
    return;
  }
  runningConnectorId.value = connector.connector_id;
  try {
    await syncConnector(connector.connector_id, false);
    ElMessage.success('连接器已触发执行');
    await fetchOperations(['connector_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    ElMessage.error(buildErrorMessage(error, '连接器执行失败'));
  } finally {
    runningConnectorId.value = '';
  }
};

const handleRunDueConnectors = async () => {
  if (!window.confirm('确认执行当前所有到期连接器吗？')) {
    return;
  }
  runDueLoading.value = true;
  try {
    await runDueConnectors(10, false);
    ElMessage.success('已触发到期连接器执行');
    await fetchOperations(['connector_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    ElMessage.error(buildErrorMessage(error, '批量执行连接器失败'));
  } finally {
    runDueLoading.value = false;
  }
};

onMounted(async () => {
  await reloadAll();
});
</script>

<style scoped>
.operations-page {
  gap: 20px;
}

.operations-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-top: 16px;
}

.operations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
}

.operations-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.card-header h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--text-primary);
}

.card-header p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.toolbar-select,
.toolbar-button,
.link-button {
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 12px;
}

.toolbar-button,
.link-button {
  cursor: pointer;
}

.toolbar-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.toolbar-button--primary {
  background: var(--blue-600);
  border-color: var(--blue-600);
  color: #fff;
}

.link-button {
  background: transparent;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 72px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: var(--bg-panel-muted);
  color: var(--text-secondary);
}

.status-pill--small {
  min-width: 0;
  padding: 4px 8px;
}

.status-pill--ok {
  background: rgba(103, 194, 58, 0.12);
  color: #2f7d1f;
}

.status-pill--warning {
  background: rgba(230, 162, 60, 0.12);
  color: #b26a07;
}

.status-pill--danger {
  background: rgba(245, 108, 108, 0.12);
  color: #c03838;
}

.health-grid,
.item-list,
.incident-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.health-item,
.item-card,
.incident-item {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  padding: 14px;
}

.health-item__header,
.incident-item__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.health-item__detail,
.item-card__detail {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.degraded-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: rgba(230, 162, 60, 0.12);
  color: #8a5800;
  font-size: 12px;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 12px;
}

.metric-box {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  padding: 12px;
  text-align: center;
}

.metric-box__value {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-box__label {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.subsection {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.subsection__header,
.item-card__actions,
.incident-item__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.subsection__header {
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-secondary);
}

.item-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.item-card__main {
  min-width: 0;
  flex: 1;
}

.item-card__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.item-card__meta,
.incident-item__meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.incident-item__details {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  color: var(--text-secondary);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.operations-loading,
.operations-empty,
.empty-inline {
  padding: 20px;
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: var(--bg-panel);
}

@media (max-width: 768px) {
  .item-card,
  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .item-card__actions {
    justify-content: flex-start;
  }
}
</style>
