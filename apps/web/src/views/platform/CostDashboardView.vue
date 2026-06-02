<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="成本可观测性" subtitle="实时追踪LLM调用成本、模型健康状态与Token消耗趋势">
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
      <div class="stats-row">
        <div class="stat-card primary">
          <div class="stat-value">{{ formatCost(costData?.total_cost || 0) }}</div>
          <div class="stat-label">总成本 ({{ costData?.currency || 'CNY' }})</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ formatNumber(costData?.total_tokens || 0) }}</div>
          <div class="stat-label">总 Token 消耗</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ costData?.total_calls || 0 }}</div>
          <div class="stat-label">总调用次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ costData?.total_calls ? (costData.total_cost / costData.total_calls * 1000).toFixed(2) : '0' }}</div>
          <div class="stat-label">千次调用平均成本</div>
        </div>
      </div>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载成本数据...</span>
      </div>

      <template v-else>
        <!-- 模型成本分布 -->
        <div class="section-header">
          <h3>按模型成本分布</h3>
        </div>
        <div class="model-cost-grid">
          <div v-for="m in costData?.by_model || []" :key="m.model" class="model-cost-card">
            <div class="mc-header">
              <strong>{{ m.model }}</strong>
              <el-tag size="small" effect="plain">{{ m.calls }} 次调用</el-tag>
            </div>
            <div class="mc-bar-wrapper">
              <div class="mc-bar" :style="{ width: maxModelCost ? (m.estimated_cost / maxModelCost * 100) + '%' : '0%' }" />
            </div>
            <div class="mc-meta">
              <span>{{ formatCost(m.estimated_cost) }}</span>
              <span>{{ formatNumber(m.input_tokens + m.output_tokens) }} tokens</span>
            </div>
          </div>
        </div>

        <!-- 模型健康状态 -->
        <div class="section-header" style="margin-top: 28px;">
          <h3>模型健康状态</h3>
          <div class="health-summary-text">
            健康 {{ modelHealth?.healthy_models || 0 }} / {{ modelHealth?.total_models || 0 }}
            <span v-if="modelHealth?.circuit_open_models" class="circuit-warn">
              | {{ modelHealth.circuit_open_models }} 个熔断中
            </span>
          </div>
        </div>
        <div class="model-health-grid">
          <div
            v-for="(health, name) in modelHealth?.models || {}"
            :key="name"
            class="health-card"
            :class="{ 'circuit-open': health.circuit_open }"
          >
            <div class="health-header">
              <strong>{{ name }}</strong>
              <el-tag :type="health.circuit_open ? 'danger' : health.health_score >= 0.8 ? 'success' : 'warning'" size="small" effect="dark">
                {{ health.circuit_open ? '熔断' : health.health_score >= 0.8 ? '健康' : '降级' }}
              </el-tag>
            </div>
            <div class="health-metrics">
              <div class="health-metric">
                <span class="hm-label">健康度</span>
                <el-progress :percentage="Math.round(health.health_score * 100)" :color="health.health_score >= 0.8 ? '#67c23a' : '#e6a23c'" :stroke-width="8" />
              </div>
              <div class="health-row">
                <div class="hm-item">
                  <span class="hm-val">{{ (health.success_rate * 100).toFixed(1) }}%</span>
                  <span class="hm-lbl">成功率</span>
                </div>
                <div class="hm-item">
                  <span class="hm-val">{{ health.p50_ms.toFixed(0) }}ms</span>
                  <span class="hm-lbl">P50</span>
                </div>
                <div class="hm-item">
                  <span class="hm-val">{{ health.p95_ms.toFixed(0) }}ms</span>
                  <span class="hm-lbl">P95</span>
                </div>
                <div class="hm-item">
                  <span class="hm-val">{{ health.total_calls }}</span>
                  <span class="hm-lbl">调用数</span>
                </div>
              </div>
            </div>
          </div>
        </div>

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

        <!-- 每日趋势 -->
        <div class="section-header" style="margin-top: 28px;">
          <h3>每日成本趋势</h3>
        </div>
        <div v-if="costData?.by_day?.length" class="daily-trend">
          <div v-for="d in costData.by_day.slice(-14)" :key="d.date" class="daily-bar-item">
            <div class="daily-bar" :style="{ height: maxDailyCost ? (d.cost / maxDailyCost * 100) + '%' : '0%' }" :title="formatCost(d.cost)" />
            <span class="daily-label">{{ d.date.slice(5) }}</span>
          </div>
        </div>
        <EnhancedEmpty v-else variant="document" title="暂无趋势数据" />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Loading, Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { getCostBreakdown, getModelHealth, type CostBreakdown, type ModelHealthSummary } from '@/api/platform';

const loading = ref(false);
const periodDays = ref(7);
const costData = ref<CostBreakdown | null>(null);
const modelHealth = ref<ModelHealthSummary | null>(null);

const maxModelCost = computed(() => {
  if (!costData.value?.by_model?.length) return 1;
  return Math.max(...costData.value.by_model.map(m => m.estimated_cost));
});

const maxDailyCost = computed(() => {
  if (!costData.value?.by_day?.length) return 1;
  return Math.max(...costData.value.by_day.map(d => d.cost));
});

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
  try {
    const [costRes, healthRes]: any = await Promise.all([
      getCostBreakdown({ period_days: periodDays.value }),
      getModelHealth(),
    ]);
    costData.value = costRes;
    modelHealth.value = healthRes;
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
.stat-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; text-align: center; }
.stat-card.primary { border-color: var(--blue-400); background: #f0f7ff; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--blue-600); }
.stat-card.primary .stat-value { font-size: 26px; }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 48px; color: var(--text-muted); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.section-header h3 { margin: 0; font-size: 15px; color: var(--text-primary); }
.health-summary-text { font-size: 13px; color: var(--text-secondary); }
.circuit-warn { color: var(--red-500); font-weight: 600; }

/* 模型成本 */
.model-cost-grid { display: flex; flex-direction: column; gap: 10px; }
.model-cost-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px 16px; }
.mc-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.mc-header strong { font-size: 13px; }
.mc-bar-wrapper { height: 6px; background: var(--bg-panel-muted); border-radius: 3px; margin-bottom: 6px; overflow: hidden; }
.mc-bar { height: 100%; background: linear-gradient(90deg, var(--blue-400), var(--blue-600)); border-radius: 3px; transition: width 0.5s; }
.mc-meta { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

/* 模型健康 */
.model-health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.health-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 14px; }
.health-card.circuit-open { border-color: var(--red-400); background: #fff5f5; }
.health-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.health-header strong { font-size: 13px; }
.health-metric { margin-bottom: 8px; }
.hm-label { font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 2px; }
.health-row { display: flex; gap: 12px; }
.hm-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.hm-val { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.hm-lbl { font-size: 10px; color: var(--text-muted); }

/* 场景成本 */
.scene-cost-list { display: flex; flex-direction: column; gap: 8px; }
.scene-cost-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
.scene-info { width: 140px; display: flex; justify-content: space-between; align-items: center; }
.scene-name { font-size: 13px; color: var(--text-primary); }
.scene-pct { font-size: 11px; color: var(--text-muted); }
.scene-bar-bg { flex: 1; height: 20px; background: var(--bg-panel-muted); border-radius: 4px; overflow: hidden; }
.scene-bar { height: 100%; background: var(--blue-400); border-radius: 4px; transition: width 0.5s; }
.scene-cost { width: 80px; text-align: right; font-size: 12px; color: var(--text-secondary); font-variant-numeric: tabular-nums; }

/* 每日趋势 */
.daily-trend { display: flex; align-items: flex-end; gap: 4px; height: 120px; padding: 8px 0; }
.daily-bar-item { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.daily-bar { width: 100%; max-width: 32px; background: var(--blue-400); border-radius: 3px 3px 0 0; min-height: 2px; transition: height 0.3s; cursor: pointer; }
.daily-bar:hover { background: var(--blue-600); }
.daily-label { font-size: 9px; color: var(--text-muted); margin-top: 4px; transform: rotate(-45deg); transform-origin: top left; }
</style>
