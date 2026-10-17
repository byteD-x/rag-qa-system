<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="成本分析">
      <template #actions>
        <el-select v-model="periodDays" @change="loadData" size="small" style="width: 120px;">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
        </el-select>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 总览卡片 -->
      <div v-if="costData" class="stats-row">
        <div class="stat-card primary surface-card">
          <div class="stat-value metric-value">{{ formatCost(costData?.total_cost || 0) }}</div>
          <div class="stat-label metric-label">总成本 ({{ costData?.currency || 'CNY' }})</div>
        </div>
        <div class="stat-card surface-card">
          <div class="stat-value metric-value">{{ formatNumber(costData?.total_tokens || 0) }}</div>
          <div class="stat-label metric-label">总 Token 消耗</div>
        </div>
        <div class="stat-card surface-card">
          <div class="stat-value metric-value">{{ costData?.total_calls || 0 }}</div>
          <div class="stat-label metric-label">总调用次数</div>
        </div>
        <div class="stat-card surface-card">
          <div class="stat-value metric-value">{{ costData?.total_calls ? (costData.total_cost / costData.total_calls * 1000).toFixed(2) : '0' }}</div>
          <div class="stat-label metric-label">千次调用平均成本</div>
        </div>
      </div>

      <LoadingState v-if="loading" label="加载成本数据..." />

      <EnhancedEmpty
        v-else-if="loadError"
        variant="question"
        title="成本数据加载失败"
        description="后端暂时不可用，请点右上角「刷新」重试"
      />

      <template v-else>
        <!-- 模型成本与健康：同一模型的成本与健康状态同卡呈现，免去按模型名两处肉眼对齐 -->
        <div class="section-header">
          <h3>模型成本与健康</h3>
          <div class="health-summary-text">
            健康 {{ modelHealth?.healthy_models || 0 }} / {{ modelHealth?.total_models || 0 }}
            <span v-if="modelHealth?.circuit_open_models" class="circuit-warn">
              | {{ modelHealth.circuit_open_models }} 个熔断中
            </span>
          </div>
        </div>
        <div v-if="modelRows.length" class="model-row-list">
          <div
            v-for="row in modelRows"
            :key="row.name"
            class="model-row"
            :class="{ 'circuit-open': row.health?.circuit_open }"
          >
            <div class="mr-head">
              <strong>{{ row.name }}</strong>
              <el-tag v-if="row.health" :type="healthTagType(row.health)" size="small" effect="dark">
                {{ healthTagLabel(row.health) }}
              </el-tag>
              <el-tag v-else size="small" effect="plain" type="info">无健康数据</el-tag>
            </div>
            <div class="mc-bar-wrapper">
              <div class="mc-bar" :style="{ width: maxModelCost ? (row.cost / maxModelCost * 100) + '%' : '0%' }" />
            </div>
            <div class="mr-meta">
              <span>{{ formatCost(row.cost) }}</span>
              <span>{{ row.calls }} 次调用</span>
              <span>{{ formatNumber(row.tokens) }} tokens</span>
              <template v-if="row.health">
                <span>{{ (row.health.success_rate * 100).toFixed(1) }}% 成功率</span>
                <span>P50 {{ row.health.p50_ms.toFixed(0) }}ms</span>
                <span>P95 {{ row.health.p95_ms.toFixed(0) }}ms</span>
                <span class="mr-health">健康度 {{ Math.round(row.health.health_score * 100) }}%</span>
              </template>
            </div>
          </div>
        </div>
        <EnhancedEmpty v-else variant="document" title="暂无模型数据" description="本区间内没有模型调用记录" />

        <!-- 按场景成本分布 -->
        <div class="section-header" style="margin-top: 28px;">
          <h3>按场景成本分布</h3>
        </div>
        <div v-if="costData?.by_scene?.length" class="scene-cost-list">
          <div v-for="s in costData.by_scene" :key="s.scene" class="scene-cost-item">
            <div class="scene-info">
              <span class="scene-name">{{ s.scene }}</span>
              <span class="scene-pct">{{ s.percentage.toFixed(1) }}%</span>
            </div>
            <div class="scene-bar-bg">
              <div class="scene-bar" :style="{ width: s.percentage + '%' }" />
            </div>
            <span class="scene-cost">{{ formatCost(s.cost) }}</span>
          </div>
        </div>
        <EnhancedEmpty v-else variant="document" title="暂无场景数据" description="使用不同场景后数据将自动聚合" />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { getCostBreakdown, getModelHealth, type CostBreakdown, type ModelHealthItem, type ModelHealthSummary } from '@/api/platform';

const loading = ref(false);
const periodDays = ref(7);
const costData = ref<CostBreakdown | null>(null);
const modelHealth = ref<ModelHealthSummary | null>(null);
const loadError = ref(false);

const maxModelCost = computed(() => {
  if (!costData.value?.by_model?.length) return 1;
  return Math.max(...costData.value.by_model.map(m => m.estimated_cost));
});

// 行集合＝区间内有成本的模型（按成本降序，保持后端顺序），按模型名与健康表 join；
// 额外补上「当期无调用但正在熔断」的模型，避免熔断状态被区间过滤掉。
const modelRows = computed(() => {
  const health = modelHealth.value?.models || {};
  const rows = (costData.value?.by_model || []).map(m => ({
    name: m.model,
    cost: m.estimated_cost,
    calls: m.calls,
    tokens: m.input_tokens + m.output_tokens,
    health: (health[m.model] || null) as ModelHealthItem | null,
  }));
  const known = new Set(rows.map(r => r.name));
  for (const [name, item] of Object.entries(health)) {
    if (!known.has(name) && item.circuit_open) {
      rows.push({ name, cost: 0, calls: 0, tokens: 0, health: item });
    }
  }
  return rows;
});

type HealthTagType = 'success' | 'warning' | 'danger';
const healthTagType = (h: ModelHealthItem): HealthTagType => (h.circuit_open ? 'danger' : h.health_score >= 0.8 ? 'success' : 'warning');
const healthTagLabel = (h: ModelHealthItem) => (h.circuit_open ? '熔断' : h.health_score >= 0.8 ? '健康' : '降级');

const formatCost = (v: number) => {
  if (v >= 1) return '¥' + v.toFixed(2);
  if (v >= 0.01) return '¥' + v.toFixed(4);
  return '¥' + v.toFixed(6);
};

const formatNumber = (v: number) => {
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
  return v.toString();
};

const loadData = async () => {
  loading.value = true;
  loadError.value = false;
  try {
    const [costRes, healthRes]: any = await Promise.all([
      getCostBreakdown({ period_days: periodDays.value }),
      getModelHealth(),
    ]);
    costData.value = costRes;
    modelHealth.value = healthRes;
  } catch {
    loadError.value = true;
    costData.value = null;
    modelHealth.value = null;
  } finally {
    loading.value = false;
  }
};

onMounted(() => { loadData(); });
</script>

<style scoped>
.platform-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.platform-content { flex: 1; overflow-y: auto; padding: 20px; background: var(--bg-panel-muted); }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.stat-card.primary { border-color: var(--blue-500); background: var(--blue-50); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.section-header h3 { margin: 0; font-size: var(--text-body); color: var(--text-primary); }
.health-summary-text { font-size: var(--text-caption); color: var(--text-secondary); }
.circuit-warn { color: var(--el-color-danger); font-weight: 600; }

/* 模型成本与健康（单列堆叠，窄屏不横向滚动） */
.model-row-list { display: flex; flex-direction: column; gap: 10px; }
.model-row { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px 16px; }
.model-row.circuit-open { border-color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.mr-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.mr-head strong { font-size: var(--text-caption); }
.mc-bar-wrapper { height: 6px; background: var(--bg-panel-muted); border-radius: var(--radius-xs); margin-bottom: 6px; overflow: hidden; }
.mc-bar { height: 100%; background: var(--blue-500); border-radius: var(--radius-xs); }
.mr-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: var(--text-caption); color: var(--text-muted); }
.mr-health { color: var(--text-secondary); font-weight: 600; }

/* 场景成本 */
.scene-cost-list { display: flex; flex-direction: column; gap: 8px; }
.scene-cost-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
.scene-info { width: 140px; display: flex; justify-content: space-between; align-items: center; }
.scene-name { font-size: var(--text-caption); color: var(--text-primary); }
.scene-pct { font-size: var(--text-caption); color: var(--text-muted); }
.scene-bar-bg { flex: 1; height: 20px; background: var(--bg-panel-muted); border-radius: var(--radius-xs); overflow: hidden; }
.scene-bar { height: 100%; background: var(--blue-500); border-radius: var(--radius-xs); }
.scene-cost { width: 80px; text-align: right; font-size: var(--text-caption); color: var(--text-secondary); font-variant-numeric: tabular-nums; }
</style>
