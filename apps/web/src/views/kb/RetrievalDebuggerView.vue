<template>
  <div class="page-shell debugger-page">
    <PageHeaderCompact title="检索测试工作台" subtitle="不触发LLM生成，纯检索与重排结果诊断" />
    
    <div class="debugger-layout">
      <div class="debugger-sidebar">
        <el-form label-position="top">
          <el-form-item label="选择知识库">
            <el-select v-model="form.base_id" filterable placeholder="选择知识库" style="width: 100%;">
              <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="测试 Query">
            <el-input v-model="form.query" type="textarea" :rows="4" placeholder="输入用户的查询问题..." />
          </el-form-item>
          <el-form-item label="召回数量 (Top K)">
            <el-input-number v-model="form.top_k" :min="1" :max="50" style="width: 100%;" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!form.base_id || !form.query" @click="runDebug" style="width: 100%;">
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
            <h3>召回结果 ({{ results.length }})</h3>
            <span class="trace-id" v-if="traceId">Trace ID: {{ traceId }}</span>
          </div>
          
          <div class="result-list">
            <div v-for="(item, index) in results" :key="index" class="result-card">
              <div class="result-header">
                <span class="result-rank">#{{ item.debug?.rank || (index + 1) }}</span>
                <span class="result-doc">{{ item.document_name || '未知文档' }}</span>
                <div class="result-scores">
                  <el-tag size="small" type="info">Score: {{ item.debug?.score?.toFixed(4) || '-' }}</el-tag>
                  <el-tag size="small" type="success">Rerank: {{ item.debug?.rerank_score?.toFixed(4) || '-' }}</el-tag>
                </div>
              </div>
              <div class="result-body">
                {{ item.text_content }}
              </div>
              <div class="result-footer">
                <span class="chunk-id">Chunk ID: {{ item.chunk_id }}</span>
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

const bases = ref<any[]>([]);
const form = ref({
  base_id: '',
  query: '',
  top_k: 10
});

const loading = ref(false);
const hasRun = ref(false);
const results = ref<any[]>([]);
const traceId = ref('');

const loadBases = async () => {
  const res: any = await listKnowledgeBases();
  bases.value = res.items || [];
  if (bases.value.length && !form.value.base_id) {
    form.value.base_id = bases.value[0].id;
  }
};

const runDebug = async () => {
  if (!form.value.base_id || !form.value.query) return;
  loading.value = true;
  hasRun.value = true;
  try {
    const res: any = await retrieveDebugKB({
      base_id: form.value.base_id,
      query: form.value.query,
      top_k: form.value.top_k
    });
    results.value = res.items || [];
    traceId.value = res.trace_id || '';
  } catch (e) {
    results.value = [];
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
  align-items: center;
  margin-bottom: 16px;
}

.trace-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
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

.result-doc {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.result-scores {
  display: flex;
  gap: 8px;
}

.result-body {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  margin-bottom: 12px;
}

.result-footer {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}
</style>
