<template>
  <div class="page-shell debugger-page">
    <PageHeaderCompact title="检索测试工作台" subtitle="不触发 LLM 生成，专注诊断召回、融合与重排结果" />

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
          <el-form-item>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!form.base_id || !form.question"
              data-testid="run-retrieval-debug"
              style="width: 100%;"
              @click="runDebug"
            >
              开始检索测试
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="debugger-content">
        <div v-if="loading" class="loading-state">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <span>检索中...</span>
        </div>

        <EnhancedEmpty
          v-else-if="!hasRun"
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
              <span>结构 {{ retrievalStats.structure_candidates ?? 0 }}</span>
              <span>全文 {{ retrievalStats.fts_candidates ?? 0 }}</span>
              <span>向量 {{ retrievalStats.vector_candidates ?? 0 }}</span>
              <span>融合 {{ retrievalStats.fused_candidates ?? 0 }}</span>
              <span>重排 {{ retrievalStats.reranked_candidates ?? 0 }}</span>
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
                  <el-tag size="small" type="info">Score: {{ formatNumber(item.debug?.score ?? item.evidence_path?.final_score) }}</el-tag>
                  <el-tag size="small" type="success">Rerank: {{ formatNumber(item.debug?.rerank_score ?? item.signal_scores?.rerank) }}</el-tag>
                </div>
              </div>

              <div class="result-body">
                {{ item.quote || item.raw_text }}
              </div>

              <div class="signal-row" v-if="Object.keys(item.signal_scores || {}).length">
                <span v-for="(score, name) in item.signal_scores" :key="name" class="signal-chip">
                  {{ name }} {{ formatNumber(score) }}
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
import { ref, onMounted } from 'vue';
import { Loading } from '@element-plus/icons-vue';
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

const bases = ref<any[]>([]);
const form = ref({
  base_id: '',
  question: '',
  limit: 10
});
const documentIdsText = ref('');

const loading = ref(false);
const hasRun = ref(false);
const results = ref<RetrievalDebugItem[]>([]);
const retrievalStats = ref<RetrievalStats | null>(null);
const traceId = ref('');

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
  hasRun.value = true;
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
  } catch (e) {
    results.value = [];
    retrievalStats.value = null;
    traceId.value = '';
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

.debugger-content {
  flex: 1;
  background: var(--bg-panel-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1;
  color: var(--text-muted);
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
}

.trace-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.retrieval-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
}

.retrieval-stats span,
.signal-chip {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  padding: 4px 8px;
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
  font-size: 13px;
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
  font-size: 16px;
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
  font-size: 12px;
  color: var(--text-muted);
}

.result-scores,
.signal-row,
.result-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.result-body {
  font-size: 14px;
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
  font-size: 12px;
  color: var(--text-secondary);
}

.result-footer {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}
</style>
