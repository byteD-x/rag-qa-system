<template>
  <div class="page-shell operations-page">
    <PageHeaderCompact title="知识库运维">
      <template #subtitle>
        <span v-if="operations">生成时间：{{ formatDateTime(operations.generated_at) }}</span>
      </template>
      <template #actions>
        <select v-if="authStore.isAdmin()" v-model="viewMode" class="toolbar-select" aria-label="数据范围" @change="reloadAll">
          <option value="personal">个人范围</option>
          <option value="admin">管理范围</option>
        </select>
        <select v-model.number="days" class="toolbar-select" aria-label="统计天数" @change="reloadAll">
          <option :value="7">最近 7 天</option>
          <option :value="14">最近 14 天</option>
          <option :value="30">最近 30 天</option>
        </select>
        <button type="button" class="toolbar-button" :disabled="loading" @click="reloadAll">
          {{ loading && operations ? '刷新中...' : '刷新' }}
        </button>
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

    <LoadingState v-if="!operations && loading" label="正在加载服务健康、ingest 与连接器状态…" />
    <EnhancedEmpty
      v-else-if="!operations"
      variant="question"
      title="未获取到运维数据"
      description="请点击工具栏「刷新」重新取数。"
    />
    <div v-else class="operations-content">
      <section class="operations-card">
        <div class="card-header">
          <div>
            <h3>服务健康</h3>
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
              <p data-testid="ingest-risk-summary">
                失败 {{ operations.ingest_ops.summary.failed_documents }} · Dead letter {{ operations.ingest_ops.summary.dead_letter_documents }} · 长时间卡住 {{ operations.ingest_ops.summary.stalled_documents }}
              </p>
            </div>
            <button type="button" class="link-button" @click="go('/workspace/kb/governance')">去治理页</button>
          </div>

          <div class="subsection">
            <div class="subsection__header">
              <strong>可重试任务</strong>
              <span>{{ operations.ingest_ops.retryable_jobs.length }} 条</span>
            </div>
            <EnhancedEmpty
              v-if="!operations.ingest_ops.retryable_jobs.length"
              variant="success"
              title="没有待重试任务"
              description="当前没有需要人工重试的 ingest job。"
            />
            <div v-else class="item-list">
              <div v-for="job in operations.ingest_ops.retryable_jobs" :key="job.job_id" class="item-card">
                <div class="item-card__main">
                  <div class="item-card__title">{{ job.file_name }}</div>
                  <div class="item-card__meta">
                    <span>{{ job.base_name }}</span>
                    <span>{{ statusLabel(job.job_status) }}</span>
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
            <EnhancedEmpty
              v-if="!operations.ingest_ops.stalled_documents.length"
              variant="success"
              title="没有卡住的文档"
              description="当前没有超过阈值仍未推进的文档。"
            />
            <div v-else class="item-list">
              <div v-for="document in operations.ingest_ops.stalled_documents" :key="document.document_id" class="item-card">
                <div class="item-card__main">
                  <div class="item-card__title">{{ document.file_name }}</div>
                  <div class="item-card__meta">
                    <span>{{ document.base_name }}</span>
                    <span>{{ statusLabel(document.document_status || 'unknown') }}</span>
                    <span>{{ statusLabel(document.job_status || 'no-job') }}</span>
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
              <p data-testid="connector-summary">
                连接器 {{ operations.connector_ops.summary.total_connectors }} · 启用调度 {{ operations.connector_ops.summary.scheduled_connectors }} · 当前到期 {{ operations.connector_ops.summary.due_connectors }} · 近期失败 {{ operations.connector_ops.summary.recent_failed_runs }}
              </p>
            </div>
            <button type="button" class="link-button" @click="go('/workspace/kb/connectors')">管理连接器</button>
          </div>

          <EnhancedEmpty
            v-if="!operations.connector_ops.items.length"
            variant="document"
            title="当前范围内没有连接器运行项"
            description="可在连接器页添加或启用数据源。"
          />
          <div v-else class="item-list">
            <div v-for="connector in operations.connector_ops.items" :key="connector.connector_id" class="item-card">
              <div class="item-card__main">
                <div class="item-card__title">{{ connector.name }}</div>
                <div class="item-card__meta">
                  <span>{{ connector.base_name }}</span>
                  <span>{{ connectorTypeLabel(connector.connector_type) }}</span>
                  <span>{{ connector.schedule_enabled ? '调度已启用' : '调度未启用' }}</span>
                  <span v-if="connector.last_run_outcome">{{ statusLabel(connector.last_run_outcome) }}</span>
                  <span>{{ connector.next_run_at ? `下次 ${formatDateTime(connector.next_run_at)}` : '无下次调度' }}</span>
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
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="operations-card surface-card">
        <div class="card-header">
          <div>
            <h3>知识灌入</h3>
            <p data-testid="kb-batch-gate">{{ batchGateHint }}</p>
          </div>
          <div class="item-card__actions">
            <button
              type="button"
              class="toolbar-button"
              :disabled="knowledgeBatchBusy"
              data-testid="kb-batch-reset-button"
              @click="resetKnowledgeBatch"
            >
              清空
            </button>
            <button
              type="button"
              class="toolbar-button"
              :disabled="!canRunKnowledgeBatchDryRun || knowledgeBatchDryRunLoading"
              data-testid="kb-batch-dry-run-button"
              @click="runKnowledgeBatchDryRun"
            >
              {{ knowledgeBatchDryRunLoading ? '预览中…' : '预览（dry-run）' }}
            </button>
            <button
              type="button"
              class="toolbar-button toolbar-button--primary"
              :disabled="!canRunKnowledgeBatchIngest || knowledgeBatchIngestLoading"
              data-testid="kb-batch-ingest-button"
              @click="runKnowledgeBatchIngest"
            >
              {{ knowledgeBatchIngestLoading ? '写入中…' : '批量写入' }}
            </button>
          </div>
        </div>

        <textarea
          v-model="knowledgeBatchJson"
          class="json-input"
          rows="6"
          aria-label="知识批量写入 JSON"
          data-testid="kb-batch-json-input"
          placeholder='{"documents":[{"base_id":"base-1","file_name":"policy.txt","content":"正文"}]}'
        ></textarea>

        <div v-if="lastKnowledgeBatchDryRunResult" class="operations-result" data-testid="kb-batch-dry-run-summary">
          <div class="metric-row">
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchDryRunResult.document_count }}</span>
              <span class="metric-label">文档</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchDryRunResult.total_content_chars }}</span>
              <span class="metric-label">字符</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchDryRunResult.total_sections }}</span>
              <span class="metric-label">section</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchDryRunResult.total_chunks }}</span>
              <span class="metric-label">chunk</span>
            </div>
          </div>
          <p class="operations-hint">预览只计算结果，未写入任何文档。</p>
          <div class="item-list">
            <div v-for="item in lastKnowledgeBatchDryRunResult.documents" :key="item.doc_id" class="item-card">
              <div class="item-card__main">
                <div class="item-card__title">{{ item.file_name }}</div>
                <div class="item-card__meta">
                  <span>{{ item.doc_id }}</span>
                  <span>字符 {{ item.content_chars }}</span>
                  <span>section {{ item.section_count }}</span>
                  <span>chunk {{ item.chunk_count }}</span>
                </div>
              </div>
            </div>
          </div>
          <JsonPreview :value="lastKnowledgeBatchDryRunResult" title="dry-run 原始返回" />
        </div>

        <div v-if="lastKnowledgeBatchIngestResult" class="operations-result" data-testid="kb-batch-ingest-summary">
          <div class="metric-row">
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchIngestResult.succeeded_documents }}</span>
              <span class="metric-label">写入成功</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchIngestResult.failed_documents }}</span>
              <span class="metric-label">写入失败</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ lastKnowledgeBatchIngestResult.chunk_count }}</span>
              <span class="metric-label">chunk</span>
            </div>
          </div>
          <p class="operations-hint">任务 {{ lastKnowledgeBatchIngestResult.batch.task_id }}</p>
          <div class="item-list">
            <div
              v-for="item in lastKnowledgeBatchIngestResult.documents"
              :key="`${item.index}-${item.document_id || item.input_doc_id || item.index}`"
              class="item-card"
            >
              <div class="item-card__main">
                <div class="item-card__title">{{ item.file_name || item.input_doc_id || item.document_id || '未命名文档' }}</div>
                <div class="item-card__meta">
                  <span>{{ item.ok ? '已写入' : item.code || '写入失败' }}</span>
                  <span v-if="item.document_id">{{ item.document_id }}</span>
                  <span v-if="item.chunk_count !== undefined">chunk {{ item.chunk_count }}</span>
                  <span v-if="item.detail">{{ item.detail }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <EnhancedEmpty
          v-if="!lastKnowledgeBatchDryRunResult && !lastKnowledgeBatchIngestResult"
          variant="search"
          title="尚未预览当前 JSON"
          description="粘贴包含 documents 数组的 JSON，先执行预览；预览通过后才会开放批量写入。"
        />

        <div class="subsection">
          <div class="subsection__header">
            <strong>重建写入结果</strong>
            <span>{{ knowledgeBatchRebuildDocumentIds.length }} 个可重建文档</span>
          </div>
          <p class="operations-hint">只重建上一次批量写入成功、并返回了 document_id 的文档；重建会替换这些文档现有的分块与向量。</p>
          <div class="item-card__actions">
            <button
              type="button"
              class="toolbar-button"
              :disabled="!canRunKnowledgeBatchRebuild || knowledgeBatchRebuildLoading"
              data-testid="kb-batch-rebuild-button"
              @click="runKnowledgeBatchRebuild"
            >
              {{ knowledgeBatchRebuildLoading ? '重建中…' : '重建写入结果' }}
            </button>
          </div>
          <div v-if="lastKnowledgeBatchRebuildResult" class="operations-result" data-testid="kb-batch-rebuild-summary">
            <div class="metric-row">
              <div class="metric-item">
                <span class="metric-value">{{ lastKnowledgeBatchRebuildResult.document_count }}</span>
                <span class="metric-label">文档</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">{{ lastKnowledgeBatchRebuildResult.succeeded_documents }}</span>
                <span class="metric-label">成功</span>
              </div>
              <div class="metric-item">
                <span class="metric-value">{{ lastKnowledgeBatchRebuildResult.failed_documents }}</span>
                <span class="metric-label">失败</span>
              </div>
            </div>
            <div class="item-list">
              <div v-for="item in lastKnowledgeBatchRebuildResult.documents" :key="item.doc_id" class="item-card">
                <div class="item-card__main">
                  <div class="item-card__title">{{ item.doc_id }}</div>
                  <div class="item-card__meta">
                    <span>{{ item.ok ? '已完成' : item.code || '重建失败' }}</span>
                    <span v-if="item.result?.chunk_count !== undefined">chunk {{ item.result.chunk_count }}</span>
                    <span v-if="item.detail">{{ item.detail }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="operations-card surface-card">
        <div class="card-header">
          <div>
            <h3>单文档重建</h3>
            <p data-testid="kb-rebuild-gate">{{ rebuildGateHint }}</p>
          </div>
        </div>

        <div class="item-card__actions">
          <input
            v-model="rebuildDocId"
            class="toolbar-select rebuild-input"
            type="text"
            aria-label="待重建文档 doc_id"
            data-testid="kb-rebuild-doc-input"
            placeholder="doc_id"
          />
          <button
            type="button"
            class="toolbar-button"
            :disabled="!canRunRebuildDryRun || rebuildDryRunLoading"
            data-testid="kb-rebuild-dry-run-button"
            @click="runRebuildDryRun"
          >
            {{ rebuildDryRunLoading ? '预览中…' : '预览 rebuild' }}
          </button>
          <button
            type="button"
            class="toolbar-button toolbar-button--primary"
            :disabled="!canRunRebuild || rebuildLoading"
            data-testid="kb-rebuild-button"
            @click="runRebuild"
          >
            {{ rebuildLoading ? '重建中…' : '执行 rebuild' }}
          </button>
        </div>

        <div v-if="lastRebuildResult" class="operations-result" data-testid="kb-rebuild-summary">
          <div class="metric-row">
            <div v-for="item in rebuildSummaryItems" :key="item.key" class="metric-item">
              <span class="metric-value">{{ item.value }}</span>
              <span class="metric-label">{{ item.label }}</span>
            </div>
          </div>
          <JsonPreview :value="lastRebuildResult" title="rebuild 原始返回" />
        </div>
        <EnhancedEmpty
          v-else
          variant="document"
          title="尚未执行 rebuild"
          description="输入 doc_id、通过预览后再执行，结果会显示在下方。"
        />
      </section>

      <section class="operations-card">
        <div class="card-header">
          <div>
            <h3>事故事件流</h3>
          </div>
        </div>
        <EnhancedEmpty
          v-if="!operations.incident_feed.items.length"
          variant="search"
          title="当前时间窗口内没有运维事故事件"
          description="失败、重试与降级事件将在此按时间倒序展示。"
        />
        <div v-else class="incident-list">
          <div v-for="item in operations.incident_feed.items" :key="item.id" class="incident-item">
            <div class="incident-item__header">
              <strong>{{ item.action }}</strong>
              <span class="status-pill status-pill--small" :class="statusClass(item.outcome)">{{ statusLabel(item.outcome) }}</span>
            </div>
            <div class="incident-item__meta">
              <span>{{ resourceTypeLabel(item.resource_type) }} / {{ item.resource_id || '-' }}</span>
              <span>trace: {{ item.trace_id || '-' }}</span>
              <span>{{ formatDateTime(item.created_at) }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import JsonPreview from '@/components/JsonPreview.vue';
import LoadingState from '@/components/LoadingState.vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import {
  buildKnowledgeBatchSignature,
  buildKnowledgeRebuildSignature,
  dryRunKnowledgeDocuments,
  getKBOperations,
  ingestKnowledgeDocuments,
  rebuildKnowledgeDocument,
  rebuildKnowledgeDocuments,
  retryKBIngestJob,
  runDueConnectors,
  syncConnector,
  type KnowledgeBatchDocumentsPayload,
  type KnowledgeBatchDryRunResponse,
  type KnowledgeBatchIngestResponse,
  type KBOperationsConnectorItem,
  type KBOperationsResponse,
  type KBOperationsRetryableJob,
  type RebuildKnowledgeDocumentResponse,
  type RebuildKnowledgeDocumentsResponse,
} from '@/api/kb';
import { isHandledRequestError } from '@/api/request';
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

const dueConnectorCount = computed(() => operations.value?.connector_ops.summary.due_connectors ?? 0);

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

const statusLabelMap: Record<string, string> = {
  ok: '健康',
  degraded: '降级',
  failed: '失败',
  success: '成功',
  retry: '重试',
  partial_success: '部分成功',
  denied: '拒绝',
  queued: '排队中',
  processing: '处理中',
  running: '执行中',
  stalled: '已停滞',
  dead_letter: '死信',
  ready: '已就绪',
  cancelled: '已取消',
  canceled: '已取消',
  paused: '已暂停',
  pending: '待处理',
  'no-job': '无任务',
  unknown: '未知',
};

const statusLabel = (status?: string) => statusLabelMap[status || ''] || status || '未知';

const healthLabel = (key: string) => ({
  database: '数据库',
  object_storage: '对象存储',
  vector_store: '向量库',
}[key] || key);

const connectorTypeLabel = (connectorType?: string) => ({
  local_directory: '本地目录',
  notion: 'Notion',
  web_crawler: 'Web 爬虫',
  feishu_document: '飞书文档',
  dingtalk_document: '钉钉文档',
  sql_query: '数据库 SQL',
}[connectorType || ''] || connectorType || '未知');

const resourceTypeLabel = (resourceType?: string) => ({
  connector: '连接器',
  document: '文档',
  ingest_job: 'ingest 任务',
  knowledge_base: '知识库',
  knowledge_base_type: '知识库类型',
  chunk: '分块',
  upload_session: '上传会话',
  document_batch: '批量文档',
  visual_asset: '视觉资产',
  audit_event: '审计事件',
}[resourceType || ''] || resourceType || '未知');

const buildErrorMessage = (error: unknown, actionLabel: string) => {
  const payload = (error as any)?.response?.data ?? {};
  const code = String(payload.code || '').trim();
  const traceId = String(payload.trace_id || '').trim();
  const detail = String(payload.detail || '').trim();
  const meta = [code ? `code=${code}` : '', traceId ? `trace=${traceId}` : ''].filter(Boolean).join(' / ');
  return [actionLabel, detail || '请求失败', meta].filter(Boolean).join(' | ');
};

const handleRetryJob = async (job: KBOperationsRetryableJob) => {
  try {
    await ElMessageBox.confirm(`确认重试文档“${job.file_name}”对应的 ingest 任务吗？`, '重试 ingest', { type: 'warning' });
  } catch {
    return;
  }
  retryingJobId.value = job.job_id;
  try {
    await retryKBIngestJob(job.job_id);
    ElMessage.success('已提交 ingest 重试');
    await fetchOperations(['ingest_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, 'ingest 重试失败'));
    }
  } finally {
    retryingJobId.value = '';
  }
};

const handleRunConnector = async (connector: KBOperationsConnectorItem) => {
  try {
    await ElMessageBox.confirm(`确认立即执行连接器“${connector.name}”吗？`, '立即同步', { type: 'warning' });
  } catch {
    return;
  }
  runningConnectorId.value = connector.connector_id;
  try {
    await syncConnector(connector.connector_id, false);
    ElMessage.success('连接器已触发执行');
    await fetchOperations(['connector_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, '连接器执行失败'));
    }
  } finally {
    runningConnectorId.value = '';
  }
};

const handleRunDueConnectors = async () => {
  const scopeLabel = viewMode.value === 'admin' ? '管理范围' : '个人范围';
  try {
    await ElMessageBox.confirm(
      `将执行 ${dueConnectorCount.value} 个当前到期连接器（单次上限 10 个，范围：${scopeLabel}）。是否继续？`,
      '执行到期连接器',
      { type: 'warning' },
    );
  } catch {
    return;
  }
  runDueLoading.value = true;
  try {
    await runDueConnectors(10, false);
    ElMessage.success('已触发到期连接器执行');
    await fetchOperations(['connector_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, '批量执行连接器失败'));
    }
  } finally {
    runDueLoading.value = false;
  }
};

const knowledgeBatchJson = ref('');
const lastKnowledgeBatchDryRunResult = ref<KnowledgeBatchDryRunResponse | null>(null);
const lastKnowledgeBatchDryRunSignature = ref('');
const lastKnowledgeBatchIngestResult = ref<KnowledgeBatchIngestResponse | null>(null);
const lastKnowledgeBatchIngestSignature = ref('');
const lastKnowledgeBatchRebuildResult = ref<RebuildKnowledgeDocumentsResponse | null>(null);
const knowledgeBatchDryRunLoading = ref(false);
const knowledgeBatchIngestLoading = ref(false);
const knowledgeBatchRebuildLoading = ref(false);

const rebuildDocId = ref('');
const lastRebuildDryRunResult = ref<RebuildKnowledgeDocumentResponse | null>(null);
const lastRebuildDryRunSignature = ref('');
const lastRebuildResult = ref<RebuildKnowledgeDocumentResponse | null>(null);
const rebuildDryRunLoading = ref(false);
const rebuildLoading = ref(false);

const canWrite = computed(() => authStore.hasPermission('kb.write'));

const knowledgeBatchBusy = computed(
  () => knowledgeBatchDryRunLoading.value || knowledgeBatchIngestLoading.value || knowledgeBatchRebuildLoading.value,
);

const rebuildBusy = computed(() => rebuildDryRunLoading.value || rebuildLoading.value);

const parsedKnowledgeBatchPayload = computed<KnowledgeBatchDocumentsPayload | null>(() => {
  const raw = knowledgeBatchJson.value.trim();
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as KnowledgeBatchDocumentsPayload;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !Array.isArray(parsed.documents)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
});

const knowledgeBatchPayloadSignature = computed(() => {
  const payload = parsedKnowledgeBatchPayload.value;
  return payload ? buildKnowledgeBatchSignature(payload) : '';
});

const rebuildPayloadSignature = computed(() => {
  const docId = rebuildDocId.value.trim();
  return docId ? buildKnowledgeRebuildSignature({ doc_id: docId }) : '';
});

const canRunKnowledgeBatchDryRun = computed(
  () => canWrite.value && !knowledgeBatchBusy.value && Boolean(knowledgeBatchPayloadSignature.value),
);

const canRunKnowledgeBatchIngest = computed(
  () =>
    canWrite.value &&
    !knowledgeBatchBusy.value &&
    Boolean(knowledgeBatchPayloadSignature.value) &&
    lastKnowledgeBatchDryRunSignature.value === knowledgeBatchPayloadSignature.value,
);

const knowledgeBatchRebuildDocumentIds = computed(() => {
  const documents = lastKnowledgeBatchIngestResult.value?.documents ?? [];
  return documents.filter((item) => item.ok && item.document_id).map((item) => item.document_id as string);
});

const canRunKnowledgeBatchRebuild = computed(
  () =>
    canWrite.value &&
    !knowledgeBatchBusy.value &&
    knowledgeBatchRebuildDocumentIds.value.length > 0 &&
    lastKnowledgeBatchIngestSignature.value === knowledgeBatchPayloadSignature.value,
);

const canRunRebuildDryRun = computed(
  () => canWrite.value && !rebuildBusy.value && Boolean(rebuildPayloadSignature.value),
);

const canRunRebuild = computed(
  () =>
    canWrite.value &&
    !rebuildBusy.value &&
    Boolean(rebuildPayloadSignature.value) &&
    lastRebuildDryRunSignature.value === rebuildPayloadSignature.value,
);

const batchGateHint = computed(() => {
  if (!canWrite.value) {
    return '当前账号缺少 kb.write 权限，无法预览或写入。';
  }
  if (canRunKnowledgeBatchIngest.value) {
    return '当前 JSON 已通过预览，可以写入。';
  }
  if (knowledgeBatchPayloadSignature.value) {
    return 'JSON 已改动，写入前需要重新预览。';
  }
  return '粘贴包含 documents 数组的 JSON 后再预览。';
});

const rebuildGateHint = computed(() => {
  if (!canWrite.value) {
    return '当前账号缺少 kb.write 权限，无法执行 rebuild。';
  }
  if (canRunRebuild.value) {
    return '当前 doc_id 已通过预览，可以执行 rebuild。';
  }
  if (rebuildPayloadSignature.value) {
    return 'doc_id 已改动或尚未预览，执行前需要重新预览。';
  }
  return '输入 doc_id 后再预览。';
});

const rebuildSummaryItems = computed(() => {
  const result = lastRebuildResult.value;
  const items: Array<{ key: string; label: string; value: string }> = [];
  if (!result) {
    return items;
  }
  const push = (label: string, value: unknown) => {
    if (value !== undefined && value !== null && value !== '') {
      items.push({ key: label, label, value: String(value) });
    }
  };
  push('doc_id', result.doc_id);
  push('version', result.version);
  push('chunk_count', result.chunk_count);
  push('indexed_chunks', result.indexed_chunks);
  push('deleted_previous', result.deleted_previous);
  return items;
});

const resetKnowledgeBatch = () => {
  knowledgeBatchJson.value = '';
  lastKnowledgeBatchDryRunResult.value = null;
  lastKnowledgeBatchDryRunSignature.value = '';
  lastKnowledgeBatchIngestResult.value = null;
  lastKnowledgeBatchIngestSignature.value = '';
  lastKnowledgeBatchRebuildResult.value = null;
};

const runKnowledgeBatchDryRun = async () => {
  const payload = parsedKnowledgeBatchPayload.value;
  const signature = knowledgeBatchPayloadSignature.value;
  if (!canWrite.value || !payload || !signature || knowledgeBatchBusy.value) {
    return;
  }
  lastKnowledgeBatchDryRunResult.value = null;
  lastKnowledgeBatchDryRunSignature.value = '';
  lastKnowledgeBatchIngestSignature.value = '';
  knowledgeBatchDryRunLoading.value = true;
  try {
    const response = await dryRunKnowledgeDocuments(payload);
    const result = ((response as any).data ?? response) as KnowledgeBatchDryRunResponse;
    lastKnowledgeBatchDryRunResult.value = result;
    lastKnowledgeBatchDryRunSignature.value = signature;
    if (!result.document_count) {
      ElMessage.warning('预览未解析出任何文档，请检查 documents 内容。');
    }
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error('知识批量预览失败。');
    }
  } finally {
    knowledgeBatchDryRunLoading.value = false;
  }
};

const runKnowledgeBatchIngest = async () => {
  const payload = parsedKnowledgeBatchPayload.value;
  const signature = knowledgeBatchPayloadSignature.value;
  const dryRunResult = lastKnowledgeBatchDryRunResult.value;
  if (!canWrite.value || !payload || !dryRunResult || knowledgeBatchBusy.value) {
    return;
  }
  if (lastKnowledgeBatchDryRunSignature.value !== signature) {
    ElMessage.warning('JSON 已改动，请重新预览后再写入。');
    return;
  }
  const fileNames = dryRunResult.documents.map((item) => item.file_name).filter(Boolean).join('、');
  try {
    await ElMessageBox.confirm(
      `将按当前 JSON 写入 ${dryRunResult.document_count} 个文档（共 ${dryRunResult.total_chunks} 个 chunk）：${fileNames || '未命名文档'}。写入会覆盖同名文档并记录新的 ingest 任务。`,
      '确认批量写入',
      { type: 'warning', confirmButtonText: '确认写入', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  knowledgeBatchIngestLoading.value = true;
  try {
    const response = await ingestKnowledgeDocuments(payload);
    const result = ((response as any).data ?? response) as KnowledgeBatchIngestResponse;
    lastKnowledgeBatchIngestResult.value = result;
    lastKnowledgeBatchIngestSignature.value = signature;
    lastKnowledgeBatchRebuildResult.value = null;
    if (result.failed_documents > 0 || result.succeeded_documents === 0) {
      ElMessage.error(`批量写入失败 ${result.failed_documents} 个文档。`);
    } else {
      ElMessage.success(`已写入 ${result.succeeded_documents} 个文档。`);
    }
    await fetchOperations(['ingest_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, '知识批量写入失败'));
    }
  } finally {
    knowledgeBatchIngestLoading.value = false;
  }
};

const runKnowledgeBatchRebuild = async () => {
  const documentIds = knowledgeBatchRebuildDocumentIds.value;
  if (!canWrite.value || !documentIds.length || knowledgeBatchBusy.value) {
    return;
  }
  if (lastKnowledgeBatchIngestSignature.value !== knowledgeBatchPayloadSignature.value) {
    ElMessage.warning('JSON 已改动，请重新写入后再重建。');
    return;
  }
  try {
    await ElMessageBox.confirm(
      `将重建 ${documentIds.length} 个文档：${documentIds.join('、')}。重建会重新生成分块与向量，并替换这些文档现有的分块。`,
      '确认重建写入结果',
      { type: 'warning', confirmButtonText: '确认重建', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  knowledgeBatchRebuildLoading.value = true;
  try {
    const result = await rebuildKnowledgeDocuments({ document_ids: documentIds });
    lastKnowledgeBatchRebuildResult.value = result;
    if (result.failed_documents > 0) {
      ElMessage.error(`重建失败 ${result.failed_documents} 个文档。`);
    } else {
      ElMessage.success(`已重建 ${result.succeeded_documents} 个文档。`);
    }
    await fetchOperations(['ingest_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, '批量重建失败'));
    }
  } finally {
    knowledgeBatchRebuildLoading.value = false;
  }
};

const runRebuildDryRun = async () => {
  const docId = rebuildDocId.value.trim();
  const signature = rebuildPayloadSignature.value;
  if (!canWrite.value || !docId || !signature || rebuildBusy.value) {
    return;
  }
  lastRebuildDryRunResult.value = null;
  lastRebuildDryRunSignature.value = '';
  rebuildDryRunLoading.value = true;
  try {
    const response = await rebuildKnowledgeDocument({ doc_id: docId, dry_run: true, signature });
    lastRebuildDryRunResult.value = ((response as any).data ?? response) as RebuildKnowledgeDocumentResponse;
    lastRebuildDryRunSignature.value = signature;
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, 'rebuild 预览失败'));
    }
  } finally {
    rebuildDryRunLoading.value = false;
  }
};

const runRebuild = async () => {
  const docId = rebuildDocId.value.trim();
  const signature = rebuildPayloadSignature.value;
  if (!canWrite.value || !docId || rebuildBusy.value) {
    return;
  }
  if (lastRebuildDryRunSignature.value !== signature) {
    ElMessage.warning('doc_id 已改动或尚未预览，请先预览 rebuild。');
    return;
  }
  try {
    await ElMessageBox.confirm(
      `将按 ${docId} 的当前内容重新生成分块与向量，并替换该文档现有的分块。`,
      '确认重建文档',
      { type: 'warning', confirmButtonText: '确认重建', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  rebuildLoading.value = true;
  try {
    const response = await rebuildKnowledgeDocument({ doc_id: docId, dry_run: false, signature });
    lastRebuildResult.value = ((response as any).data ?? response) as RebuildKnowledgeDocumentResponse;
    ElMessage.success(`已提交 ${docId} 的重建。`);
    await fetchOperations(['ingest_ops', 'incident_feed', 'data_quality']);
  } catch (error) {
    if (!isHandledRequestError(error)) {
      ElMessage.error(buildErrorMessage(error, '文档 rebuild 失败'));
    }
  } finally {
    rebuildLoading.value = false;
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
  font-size: var(--text-body);
  color: var(--text-primary);
}

.card-header p {
  margin: 0;
  font-size: var(--text-caption);
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
  font-size: var(--text-caption);
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
  color: var(--text-on-primary);
}

.link-button {
  background: transparent;
}

@media (hover: hover) and (pointer: fine) {
  .toolbar-button:not(:disabled):hover {
    opacity: 0.9;
  }

  .link-button:hover {
    color: var(--blue-600);
  }
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 72px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: var(--text-caption);
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
  color: var(--text-success-status);
}

.status-pill--warning {
  background: rgba(230, 162, 60, 0.12);
  color: var(--text-warning-status);
}

.status-pill--danger {
  background: rgba(245, 108, 108, 0.12);
  color: var(--text-danger-status);
}

.health-grid,
.item-list,
.incident-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 内层不再自成一个「框」：卡片(.operations-card)已经是表面，
   这里改用分隔线 + 列表 gap 表达条目边界，避免卡片套带底色的卡片。
   首项不画线，避免与卡头之间多出一条悬空分隔。 */
.health-item,
.item-card,
.incident-item {
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
}

.health-item:first-child,
.item-card:first-child,
.incident-item:first-child {
  padding-top: 0;
  border-top: none;
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
  font-size: var(--text-caption);
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
  color: var(--text-warning-banner);
  font-size: var(--text-caption);
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
  font-size: var(--text-caption);
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
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.item-card__meta,
.incident-item__meta {
  margin-top: 8px;
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.json-input {
  width: 100%;
  min-height: 132px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  line-height: 1.6;
  resize: vertical;
  transition: border-color var(--transition-fast);
}

.json-input:focus {
  border-color: var(--blue-600);
}

.rebuild-input {
  flex: 1 1 220px;
  min-width: 0;
}

.metric-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 28px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.operations-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.operations-hint {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--text-secondary);
  line-height: 1.5;
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
