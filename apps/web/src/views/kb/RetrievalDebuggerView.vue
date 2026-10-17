<template>
  <div class="page-shell debugger-page">
    <PageHeaderCompact title="检索测试" />

    <div class="debugger-layout">
      <div class="debugger-sidebar">
        <el-form label-position="top">
          <el-form-item label="选择知识库">
            <el-select v-model="form.base_id" filterable placeholder="选择知识库" style="width: 100%;">
              <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="测试问题">
            <el-input
              v-model="form.question"
              data-testid="retrieval-question-input"
              type="textarea"
              :rows="4"
              placeholder="输入用户的查询问题..."
            />
          </el-form-item>
          <el-collapse v-model="advancedCollapse">
            <el-collapse-item name="advanced">
              <template #title>
                <span class="collapse-title">高级选项（文档 ID 范围 / 召回数量）</span>
              </template>
              <el-form-item label="文档 ID 范围（可选，每行一个）">
                <el-input
                  v-model="documentIdsText"
                  type="textarea"
                  :rows="3"
                  placeholder="留空表示使用当前知识库的默认检索范围"
                />
              </el-form-item>
              <el-form-item label="召回数量 Limit">
                <el-input-number v-model="form.limit" :min="1" :max="20" style="width: 100%;" />
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
          <el-form-item>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!form.base_id || !form.question"
              data-testid="run-retrieval-debug"
              style="width: 100%;"
              @click="runDebug"
            >
              {{ loading ? '检索中...' : '开始检索测试' }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="debugger-content" :class="{ 'is-loading': loading }">
        <EnhancedEmpty
          v-if="!hasRun"
          variant="search"
          title="等待测试"
          description="在左侧填写查询条件并运行测试"
        />

        <EnhancedEmpty
          v-else-if="!results.length"
          variant="document"
          title="未命中任何切片"
          description="尝试调整查询词或检查知识库内容"
        />

        <div v-else class="results-container">
          <div class="results-header">
            <div>
              <h3>召回结果 ({{ results.length }})</h3>
              <span class="trace-id" v-if="traceId">Trace ID: {{ traceId }}</span>
            </div>
            <div class="retrieval-stats" v-if="retrievalStats">
              <span
                v-for="stage in stageStats"
                :key="stage.key"
                :class="{ 'stat-degraded': stage.degraded }"
                :title="stage.degraded ? `${signalLabel(stage.key)}通道降级，该通道候选数可能不完整` : undefined"
              >
                {{ signalLabel(stage.key) }} {{ stage.degraded ? '降级' : (stage.count ?? 0) }}
              </span>
              <span>{{ formatNumber(retrievalStats.retrieval_ms) }} ms</span>
            </div>
          </div>

          <div class="query-summary" v-if="retrievalStats">
            <div><strong>原始问题</strong>{{ retrievalStats.original_query || '-' }}</div>
            <div v-if="retrievalStats.focus_query"><strong>聚焦查询</strong>{{ retrievalStats.focus_query }}</div>
            <div v-if="retrievalStats.rewritten_query"><strong>重写查询</strong>{{ retrievalStats.rewritten_query }}</div>
            <div v-if="retrievalStats.rerank_provider"><strong>重排方式</strong>{{ retrievalStats.rerank_provider }}</div>
          </div>

          <div class="result-list">
            <div v-for="(item, index) in results" :key="item.unit_id || index" class="result-card">
              <div class="result-header">
                <span class="result-rank">#{{ item.debug?.rank || item.evidence_path?.final_rank || (index + 1) }}</span>
                <div class="result-title">
                  <span class="result-doc">{{ item.document_title || '未知文档' }}</span>
                  <span class="result-section">{{ item.section_title || '未命名章节' }}</span>
                </div>
                <div class="result-scores">
                  <span class="result-score">总分 {{ formatNumber(item.debug?.score ?? item.evidence_path?.final_score) }}</span>
                  <span class="result-score" v-if="!hasSignal(item, 'rerank')">
                    重排 {{ formatNumber(item.debug?.rerank_score ?? item.signal_scores?.rerank) }}
                  </span>
                </div>
              </div>

              <div class="result-body">
                {{ item.quote || item.raw_text }}
              </div>

              <div class="signal-row" v-if="Object.keys(item.signal_scores || {}).length">
                <span v-for="(score, name) in item.signal_scores" :key="name" class="signal-chip">
                  {{ signalLabel(name) }} {{ formatNumber(score) }}
                </span>
              </div>

              <div class="result-footer">
                <span>Unit: {{ item.unit_id || '-' }}</span>
                <span>Doc: {{ item.document_id || '-' }}</span>
                <span v-if="item.evidence_path?.fts_rank">FTS #{{ item.evidence_path.fts_rank }}</span>
                <span v-if="item.evidence_path?.vector_rank">Vector #{{ item.evidence_path.vector_rank }}</span>
                <span v-if="item.evidence_path?.structure_hit">Structure hit</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listKnowledgeBases, retrieveDebugKB } from '@/api/kb';

interface RetrievalStats {
  original_query?: string;
  rewritten_query?: string;
  focus_query?: string;
  structure_candidates?: number;
  fts_candidates?: number;
  vector_candidates?: number;
  fused_candidates?: number;
  reranked_candidates?: number;
  selected_candidates?: number;
  retrieval_ms?: number;
  rerank_provider?: string;
  degraded_signals?: string[];
}

interface RetrievalDebugItem {
  unit_id?: string;
  document_id?: string;
  document_title?: string;
  section_title?: string;
  quote?: string;
  raw_text?: string;
  signal_scores?: Record<string, number>;
  evidence_path?: {
    structure_hit?: boolean;
    fts_rank?: number | null;
    vector_rank?: number | null;
    final_rank?: number | null;
    final_score?: number;
  };
  debug?: {
    rank?: number;
    score?: number;
    signal_scores?: Record<string, number>;
    rerank_score?: number;
  };
}

// 后端信号键是动态给出的（packages/python/shared/retrieval.py:53），未知键保留原样
const CHANNEL_LABELS: Record<string, string> = {
  structure: '结构',
  fts: '全文',
  vector: '向量',
  fused: '融合',
  rerank: '重排'
};

const bases = ref<any[]>([]);
const form = ref({
  base_id: '',
  question: '',
  limit: 10
});
const documentIdsText = ref('');
const advancedCollapse = ref<string[]>([]);

const loading = ref(false);
const hasRun = ref(false);
const results = ref<RetrievalDebugItem[]>([]);
const retrievalStats = ref<RetrievalStats | null>(null);
const traceId = ref('');

const signalLabel = (name: string) => CHANNEL_LABELS[name] || name;

const stageStats = computed(() => {
  const stats = retrievalStats.value;
  if (!stats) return [];
  const degraded = new Set(stats.degraded_signals || []);
  return [
    { key: 'structure', count: stats.structure_candidates },
    { key: 'fts', count: stats.fts_candidates },
    { key: 'vector', count: stats.vector_candidates },
    { key: 'fused', count: stats.fused_candidates },
    { key: 'rerank', count: stats.reranked_candidates }
  ].map((stage) => ({ ...stage, degraded: degraded.has(stage.key) }));
});

const hasSignal = (item: RetrievalDebugItem, name: string) =>
  Object.prototype.hasOwnProperty.call(item.signal_scores || {}, name);

const loadBases = async () => {
  const res: any = await listKnowledgeBases();
  bases.value = res.items || [];
  if (bases.value.length && !form.value.base_id) {
    form.value.base_id = bases.value[0].id;
  }
};

const parseDocumentIds = () => documentIdsText.value
  .split(/\r?\n|,/)
  .map((item) => item.trim())
  .filter(Boolean);

const formatNumber = (value: unknown) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(4) : '-';
};

const runDebug = async () => {
  if (!form.value.base_id || !form.value.question) return;
  loading.value = true;
  try {
    const res: any = await retrieveDebugKB({
      base_id: form.value.base_id,
      question: form.value.question,
      document_ids: parseDocumentIds(),
      limit: form.value.limit
    });
    results.value = res.items || [];
    retrievalStats.value = res.retrieval || null;
    traceId.value = res.trace_id || '';
    hasRun.value = true;
  } catch {
    // 请求层已统一提示失败；保留上一次结果，避免失败被渲染成「未命中」
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadBases();
});
</script>

<style scoped>
.debugger-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.debugger-layout {
  flex: 1;
  display: flex;
  gap: 20px;
  min-height: 0;
}

.debugger-sidebar {
  width: 320px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px;
  overflow-y: auto;
}

.collapse-title {
  font-size: var(--text-body);
  color: var(--text-secondary);
  font-weight: 500;
}

.debugger-content {
  flex: 1;
  background: var(--bg-panel-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.debugger-content.is-loading > * {
  opacity: 0.6;
}

:deep(.el-icon.is-loading) {
  animation-duration: 0.9s;
}

.results-container {
  padding: 20px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.results-header h3 {
  margin: 0 0 4px;
  font-size: var(--text-h2);
}

.trace-id {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.retrieval-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.retrieval-stats span,
.signal-chip {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  padding: 4px 8px;
}

.retrieval-stats .stat-degraded {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
}

.query-summary {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-body);
}

.query-summary div {
  display: flex;
  gap: 10px;
}

.query-summary strong {
  flex: 0 0 72px;
  color: var(--text-primary);
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 16px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.result-rank {
  font-weight: bold;
  font-size: var(--text-body);
  color: var(--blue-600);
}

.result-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-doc {
  font-weight: 600;
  color: var(--text-primary);
}

.result-section {
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.result-scores,
.signal-row,
.result-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.result-score {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.result-body {
  font-size: var(--text-body);
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  margin-bottom: 12px;
}

.signal-row {
  margin-bottom: 12px;
}

.signal-chip {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.result-footer {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-muted);
}
</style>
