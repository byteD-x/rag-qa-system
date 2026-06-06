<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="缓存管理" subtitle="管理语义缓存、精确缓存与Prompt Cache策略">
      <template #actions>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 统计概览 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ cacheStats?.total_entries || 0 }}</div>
          <div class="stat-label">缓存条目</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ cacheStats?.total_hits || 0 }}</div>
          <div class="stat-label">累计命中</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ ((cacheStats?.hit_rate_estimate || 0) * 100).toFixed(1) }}%</div>
          <div class="stat-label">预估命中率</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ ((cacheStats?.memory_usage_estimate || 0) / 1024).toFixed(0) }}KB</div>
          <div class="stat-label">内存占用</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ (cacheStats?.avg_age_seconds || 0).toFixed(0) }}s</div>
          <div class="stat-label">平均缓存年龄</div>
        </div>
      </div>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载缓存数据...</span>
      </div>

      <template v-else>
        <!-- 缓存配置 -->
        <div class="section-header">
          <h3>缓存配置</h3>
          <el-button size="small" type="primary" @click="saveConfig" :loading="saving">保存配置</el-button>
        </div>
        <div class="config-panel">
          <div class="config-row">
            <div class="config-item">
              <label>语义相似度阈值</label>
              <el-slider
                v-model="configForm.semantic_threshold"
                :min="0.7"
                :max="0.99"
                :step="0.01"
                :marks="{ 0.7: '0.7', 0.85: '0.85', 0.92: '0.92', 0.99: '0.99' }"
                show-input
              />
              <span class="config-hint">越高越严格，越高缓存命中率越低但准确率越高</span>
            </div>
          </div>
          <div class="config-row">
            <div class="config-item">
              <label>默认 TTL (秒)</label>
              <el-input-number v-model="configForm.default_ttl" :min="60" :max="86400" :step="600" />
              <span class="config-hint">缓存过期时间，默认 3600 秒（1小时）</span>
            </div>
            <div class="config-item">
              <label>最大条目数</label>
              <el-input-number v-model="configForm.max_entries" :min="100" :max="100000" :step="1000" />
              <span class="config-hint">超过此数量自动 LRU 淘汰</span>
            </div>
          </div>
        </div>

        <!-- 缓存失效 -->
        <div class="section-header" style="margin-top: 28px;">
          <h3>缓存失效</h3>
        </div>
        <div class="invalidate-panel">
          <div class="invalidate-row">
            <div class="invalidate-item">
              <label>按知识库失效</label>
              <el-input v-model="invalidateForm.corpus_id" placeholder="输入 corpus_id（如 kb:xxx）" clearable />
              <el-button type="warning" @click="doInvalidate('corpus')" :loading="invalidating">
                失效该知识库缓存
              </el-button>
            </div>
          </div>
          <div class="invalidate-row">
            <div class="invalidate-item">
              <label>按问题失效</label>
              <el-input v-model="invalidateForm.question" placeholder="输入完整问题文本" clearable />
              <el-button type="warning" @click="doInvalidate('question')" :loading="invalidating">
                失效该问题缓存
              </el-button>
            </div>
          </div>
          <div class="invalidate-row danger">
            <el-button type="danger" @click="doInvalidate('all')" :loading="invalidatingAll">
              <el-icon><Delete /></el-icon>
              清空全部缓存
            </el-button>
            <span class="danger-hint">高危操作：将清空所有缓存条目，下次请求将重新调用 LLM</span>
          </div>
        </div>

        <!-- 缓存层级说明 -->
        <div class="section-header" style="margin-top: 28px;">
          <h3>三层缓存架构</h3>
        </div>
        <div class="cache-layers">
          <div class="layer-card">
            <div class="layer-icon">🎯</div>
            <div class="layer-info">
              <strong>L1 精确缓存</strong>
              <p>完全相同的「问题+知识库+模型」直接复用答案，0 Token 消耗</p>
              <el-tag size="small" type="success">命中率最高</el-tag>
            </div>
          </div>
          <div class="layer-card">
            <div class="layer-icon">🔍</div>
            <div class="layer-info">
              <strong>L2 语义缓存</strong>
              <p>基于问题 embedding 相似度匹配（余弦相似度 ≥ 阈值），自动判断语义等价</p>
              <el-tag size="small" type="warning">命中率中等</el-tag>
            </div>
          </div>
          <div class="layer-card">
            <div class="layer-icon">⚡</div>
            <div class="layer-info">
              <strong>L3 Prompt Cache</strong>
              <p>利用 LLM API 的内置缓存能力，缓存 system prompt 前缀避免重复计算</p>
              <el-tag size="small" type="info">节省输入 Token</el-tag>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading, Refresh, Delete } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import { getCacheStats, invalidateCache, getCacheConfig, updateCacheConfig, type CacheStats } from '@/api/platform';

const loading = ref(false);
const saving = ref(false);
const invalidating = ref(false);
const invalidatingAll = ref(false);
const cacheStats = ref<CacheStats | null>(null);

const configForm = reactive({
  semantic_threshold: 0.92,
  default_ttl: 3600,
  max_entries: 10000,
});

const invalidateForm = reactive({
  corpus_id: '',
  question: '',
});

const loadData = async () => {
  loading.value = true;
  try {
    const [stats, cfg]: any = await Promise.all([
      getCacheStats(),
      getCacheConfig().catch(() => ({})),
    ]);
    cacheStats.value = stats;
    if (cfg.semantic_threshold) configForm.semantic_threshold = cfg.semantic_threshold;
    if (cfg.default_ttl) configForm.default_ttl = cfg.default_ttl;
    if (cfg.max_entries) configForm.max_entries = cfg.max_entries;
  } finally {
    loading.value = false;
  }
};

const saveConfig = async () => {
  saving.value = true;
  try {
    await updateCacheConfig({
      semantic_threshold: configForm.semantic_threshold,
      default_ttl: configForm.default_ttl,
      max_entries: configForm.max_entries,
    });
    ElMessage.success('缓存配置已保存');
  } catch {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

const doInvalidate = async (scope: string) => {
  if (scope === 'all') {
    try {
      await ElMessageBox.confirm('确定要清空全部缓存吗？所有后续请求将重新调用 LLM。', '高危操作确认', {
        type: 'warning',
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      });
    } catch { return; }
  }

  const setLoading = (v: boolean) => {
    if (scope === 'all') invalidatingAll.value = v;
    else invalidating.value = v;
  };

  setLoading(true);
  try {
    const params: any = {};
    if (scope === 'corpus' && invalidateForm.corpus_id) params.corpus_id = invalidateForm.corpus_id;
    if (scope === 'question' && invalidateForm.question) params.question = invalidateForm.question;
    const res: any = await invalidateCache(params);
    ElMessage.success(`已失效 ${res?.invalidated_count || 'N'} 条缓存`);
    loadData();
  } catch {
    ElMessage.error('操作失败');
  } finally {
    setLoading(false);
  }
};

onMounted(() => { loadData(); });
</script>

<style scoped>
.platform-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.platform-content { flex: 1; overflow-y: auto; padding: 20px; background: var(--bg-panel-muted); }

.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 24px; }
.stat-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 14px; text-align: center; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--blue-600); }
.stat-label { font-size: 11px; color: var(--text-secondary); margin-top: 3px; }

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 48px; color: var(--text-muted); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.section-header h3 { margin: 0; font-size: 15px; color: var(--text-primary); }

/* 配置面板 */
.config-panel { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 20px; }
.config-row { display: flex; gap: 24px; margin-bottom: 16px; }
.config-item { flex: 1; }
.config-item label { font-size: 13px; color: var(--text-primary); display: block; margin-bottom: 8px; font-weight: 500; }
.config-hint { font-size: 11px; color: var(--text-muted); display: block; margin-top: 4px; }
.config-item :deep(.el-slider) { margin-top: 8px; }

/* 失效面板 */
.invalidate-panel { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 20px; }
.invalidate-row { margin-bottom: 14px; }
.invalidate-row.danger { padding-top: 14px; border-top: 1px solid var(--border-color); display: flex; align-items: center; gap: 12px; }
.invalidate-item { display: flex; align-items: center; gap: 12px; }
.invalidate-item label { font-size: 13px; color: var(--text-primary); white-space: nowrap; flex-shrink: 0; width: 100px; }
.invalidate-item .el-input { flex: 1; max-width: 300px; }
.danger-hint { font-size: 12px; color: var(--red-500); }

/* 缓存层级说明 */
.cache-layers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.layer-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; display: flex; gap: 14px; }
.layer-icon { font-size: 28px; flex-shrink: 0; }
.layer-info { flex: 1; }
.layer-info strong { font-size: 14px; color: var(--text-primary); display: block; margin-bottom: 6px; }
.layer-info p { font-size: 12px; color: var(--text-secondary); margin: 0 0 8px 0; line-height: 1.5; }
</style>
