<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Agent 执行监控" subtitle="实时观测Agent任务拆解、工具调用链路与反思决策">
      <template #actions>
        <el-button @click="loadRuns" :loading="loadingRuns">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 统计概览 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ stats.total_runs }}</div>
          <div class="stat-label">总执行次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.avg_complexity }}</div>
          <div class="stat-label">平均复杂度</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.decomposition_rate }}%</div>
          <div class="stat-label">任务拆解率</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.avg_latency_ms }}ms</div>
          <div class="stat-label">平均延迟</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.reflection_pass_rate }}%</div>
          <div class="stat-label">自检通过率</div>
        </div>
      </div>

      <!-- 运行列表 -->
      <div class="section-header">
        <h3>Agent 运行记录</h3>
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable size="small" @change="loadRuns" style="width: 140px;">
          <el-option label="全部" value="" />
          <el-option label="已完成" value="completed" />
          <el-option label="已中断" value="interrupted" />
          <el-option label="失败" value="failed" />
        </el-select>
      </div>

      <div v-if="loadingRuns" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载运行记录...</span>
      </div>

      <EnhancedEmpty
        v-else-if="!runs.length"
        variant="document"
        title="暂无运行记录"
        description="发起一次Agent问答后，执行记录将显示在这里"
      />

      <div v-else class="run-list">
        <div
          v-for="run in runs"
          :key="run.id"
          class="run-card"
          :class="{ selected: selectedRun?.id === run.id }"
          @click="selectRun(run)"
        >
          <div class="run-header">
            <div class="run-status-col">
              <el-tag :type="statusTagType(run.status)" size="small" effect="dark">
                {{ statusLabel(run.status) }}
              </el-tag>
              <el-tag size="small" type="info" effect="plain" v-if="run.execution_mode">
                {{ run.execution_mode }}
              </el-tag>
            </div>
            <span class="run-time">{{ formatTime(run.created_at) }}</span>
          </div>
          <div class="run-question">{{ run.question }}</div>
          <div class="run-meta">
            <span>🔧 {{ run.tool_calls_used }}次工具调用</span>
            <span>⏱ {{ run.total_latency_ms }}ms</span>
            <span>📊 {{ run.answer_mode }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情面板 -->
    <el-drawer
      v-model="detailVisible"
      title="Agent 执行详情"
      size="720px"
      direction="rtl"
    >
      <div v-if="loadingDetail" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载详情...</span>
      </div>

      <div v-else-if="runDetail" class="detail-content">
        <!-- 任务拆解可视化 -->
        <div v-if="runDetail.requires_decomposition && runDetail.sub_tasks?.length" class="detail-section">
          <h4>📋 任务拆解 (复杂度: {{ runDetail.complexity_score }})</h4>
          <div class="dag-container">
            <div v-for="(group, gIdx) in runDetail.execution_order" :key="'g'+gIdx" class="dag-group">
              <div class="dag-group-label">并行组 {{ gIdx + 1 }}</div>
              <div class="dag-nodes">
                <div
                  v-for="taskId in group"
                  :key="taskId"
                  class="dag-node"
                  :class="getTaskStatus(taskId)"
                >
                  <div class="node-header">
                    <span class="node-id">{{ taskId }}</span>
                    <el-tag :type="taskStatusTag(taskId)" size="small">{{ getTaskStatus(taskId) }}</el-tag>
                  </div>
                  <div class="node-desc">{{ getTaskDesc(taskId) }}</div>
                  <div class="node-meta">
                    <span v-if="getTaskDeps(taskId).length">依赖: {{ getTaskDeps(taskId).join(', ') }}</span>
                    <span>类别: {{ getTaskCategory(taskId) }}</span>
                  </div>
                </div>
              </div>
              <div v-if="gIdx < runDetail.execution_order.length - 1" class="dag-arrow">↓</div>
            </div>
          </div>
        </div>

        <!-- 决策链路 -->
        <div class="detail-section">
          <h4>🧠 决策链路 (Agent Events)</h4>
          <el-timeline>
            <el-timeline-item
              v-for="(event, eIdx) in runDetail.agent_events"
              :key="'e'+eIdx"
              :timestamp="event.type"
              :type="eventTypeColor(event.type)"
              size="small"
              :hollow="event.type !== 'tool_request'"
            >
              <template v-if="event.type === 'agent_started'">
                问题: {{ event.question }}
              </template>
              <template v-else-if="event.type === 'assistant_turn'">
                第 {{ event.round }} 轮: 发起 {{ event.tool_call_count }} 个工具调用
                <div v-if="event.message_preview" class="event-preview">{{ event.message_preview }}</div>
              </template>
              <template v-else-if="event.type === 'tool_request'">
                调用工具 <strong>{{ event.tool }}</strong>
                <div class="event-args">{{ formatArgs(event.args) }}</div>
              </template>
              <template v-else-if="event.type === 'tool_result'">
                工具 <strong>{{ event.tool }}</strong> 返回 {{ event.result_count ?? event.selected_candidates }} 条结果
              </template>
            </el-timeline-item>
          </el-timeline>
        </div>

        <!-- 工具调用记录 -->
        <div class="detail-section">
          <h4>🔧 工具调用记录</h4>
          <el-table :data="runDetail.tool_calls" size="small" style="width: 100%">
            <el-table-column prop="tool" label="工具" width="140" />
            <el-table-column prop="question" label="参数" show-overflow-tooltip />
            <el-table-column prop="result_count" label="结果数" width="80" align="center" />
          </el-table>
        </div>

        <!-- 反思结果 -->
        <div v-if="runDetail.reflection" class="detail-section">
          <h4>🪞 反思自检</h4>
          <div class="reflection-card" :class="runDetail.reflection.passed ? 'passed' : 'failed'">
            <div class="reflection-scores">
              <div class="score-item">
                <span class="score-label">完整性</span>
                <el-progress :percentage="Math.round(runDetail.reflection.completeness_score * 100)" :color="scoreColor(runDetail.reflection.completeness_score)" />
              </div>
              <div class="score-item">
                <span class="score-label">准确性</span>
                <el-progress :percentage="Math.round(runDetail.reflection.accuracy_score * 100)" :color="scoreColor(runDetail.reflection.accuracy_score)" />
              </div>
              <div class="score-item">
                <span class="score-label">引用准确性</span>
                <el-progress :percentage="Math.round(runDetail.reflection.citation_score * 100)" :color="scoreColor(runDetail.reflection.citation_score)" />
              </div>
              <div class="score-item">
                <span class="score-label">置信度</span>
                <el-progress :percentage="Math.round(runDetail.reflection.confidence * 100)" :color="scoreColor(runDetail.reflection.confidence)" />
              </div>
            </div>
            <div v-if="runDetail.reflection.issues?.length" class="reflection-issues">
              <strong>发现的问题:</strong>
              <ul>
                <li v-for="(issue, i) in runDetail.reflection.issues" :key="i">{{ issue }}</li>
              </ul>
            </div>
            <div v-if="runDetail.reflection.suggestions?.length" class="reflection-suggestions">
              <strong>改进建议:</strong>
              <ul>
                <li v-for="(sug, i) in runDetail.reflection.suggestions" :key="i">{{ sug }}</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 性能指标 -->
        <div class="detail-section">
          <h4>⏱ 性能指标</h4>
          <div class="perf-metrics">
            <div class="perf-item">
              <span class="perf-label">总延迟</span>
              <span class="perf-value">{{ runDetail.total_latency_ms }}ms</span>
            </div>
            <div class="perf-item">
              <span class="perf-label">检索延迟</span>
              <span class="perf-value">{{ runDetail.retrieval_ms }}ms</span>
            </div>
            <div class="perf-item">
              <span class="perf-label">生成延迟</span>
              <span class="perf-value">{{ runDetail.generation_ms }}ms</span>
            </div>
            <div class="perf-item">
              <span class="perf-label">证据数</span>
              <span class="perf-value">{{ runDetail.evidence_count }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Loading, Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listAgentRuns, getAgentRunDetail, type AgentRunSummary, type AgentRunDetail, type AgentTaskNode } from '@/api/platform';

const runs = ref<AgentRunSummary[]>([]);
const runDetail = ref<AgentRunDetail | null>(null);
const selectedRun = ref<AgentRunSummary | null>(null);
const loadingRuns = ref(false);
const loadingDetail = ref(false);
const detailVisible = ref(false);
const statusFilter = ref('');

const stats = computed(() => {
  const completed = runs.value.filter(r => r.status === 'completed');
  const decomposed = runs.value.filter(r => 'complexity_score' in r);
  const reflected = completed.filter(r => (r as any).reflection_passed !== undefined);
  return {
    total_runs: runs.value.length,
    avg_complexity: runs.value.length ? (runs.value.reduce((s, r) => s + ((r as any).complexity_score || 1), 0) / runs.value.length).toFixed(1) : '0',
    decomposition_rate: runs.value.length ? Math.round((decomposed.length / runs.value.length) * 100) : 0,
    avg_latency_ms: completed.length ? Math.round(completed.reduce((s, r) => s + r.total_latency_ms, 0) / completed.length) : 0,
    reflection_pass_rate: reflected.length ? Math.round((reflected.filter(r => (r as any).reflection_passed).length / reflected.length) * 100) : 0,
  };
});

const statusTagType = (status: string) => {
  const map: Record<string, string> = { completed: 'success', interrupted: 'warning', failed: 'danger', running: 'primary' };
  return map[status] || 'info';
};

const statusLabel = (status: string) => {
  const map: Record<string, string> = { completed: '已完成', interrupted: '已中断', failed: '失败', running: '运行中' };
  return map[status] || status;
};

const formatTime = (ts: string) => {
  if (!ts) return '';
  return new Date(ts).toLocaleString('zh-CN');
};

const formatArgs = (args: Record<string, any>) => {
  return Object.entries(args || {}).map(([k, v]) => `${k}: ${typeof v === 'string' ? v.slice(0, 60) : JSON.stringify(v)}`).join(', ');
};

const scoreColor = (score: number) => {
  if (score >= 0.8) return '#67c23a';
  if (score >= 0.6) return '#e6a23c';
  return '#f56c6c';
};

const eventTypeColor = (type: string) => {
  const map: Record<string, string> = { agent_started: 'primary', assistant_turn: 'success', tool_request: 'warning', tool_result: 'info' };
  return map[type] || '';
};

const getTaskNode = (taskId: string): AgentTaskNode | undefined => {
  return runDetail.value?.sub_tasks?.find(t => t.id === taskId);
};

const getTaskStatus = (taskId: string) => {
  return getTaskNode(taskId)?.status || 'pending';
};

const getTaskDesc = (taskId: string) => {
  return getTaskNode(taskId)?.description || '';
};

const getTaskDeps = (taskId: string) => {
  return getTaskNode(taskId)?.depends_on || [];
};

const getTaskCategory = (taskId: string) => {
  return getTaskNode(taskId)?.category || 'unknown';
};

const taskStatusTag = (taskId: string) => {
  const map: Record<string, string> = { completed: 'success', running: 'warning', failed: 'danger', pending: 'info' };
  return map[getTaskStatus(taskId)] || 'info';
};

const loadRuns = async () => {
  loadingRuns.value = true;
  try {
    const params: any = { limit: 50 };
    if (statusFilter.value) params.status = statusFilter.value;
    const res: any = await listAgentRuns(params);
    runs.value = res.items || [];
  } finally {
    loadingRuns.value = false;
  }
};

const selectRun = async (run: AgentRunSummary) => {
  selectedRun.value = run;
  detailVisible.value = true;
  loadingDetail.value = true;
  try {
    const detail: any = await getAgentRunDetail(run.id);
    runDetail.value = detail;
  } finally {
    loadingDetail.value = false;
  }
};

onMounted(() => {
  loadRuns();
});
</script>

<style scoped>
.platform-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.platform-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: var(--bg-panel-muted);
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--blue-600);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
}

.run-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.run-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  cursor: pointer;
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}

.run-card:hover {
  border-color: var(--blue-400);
}

.run-card.selected {
  border-color: var(--blue-500);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
}

.run-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.run-status-col {
  display: flex;
  gap: 8px;
}

.run-time {
  font-size: 12px;
  color: var(--text-muted);
}

.run-question {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.run-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

/* 详情面板 */
.detail-content {
  padding: 4px 0;
}

.detail-section {
  margin-bottom: 28px;
}

.detail-section h4 {
  margin: 0 0 14px 0;
  font-size: 15px;
  color: var(--text-primary);
}

/* DAG 可视化 */
.dag-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dag-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dag-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.dag-nodes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.dag-node {
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  border-left: 3px solid var(--blue-400);
}

.dag-node.completed { border-left-color: var(--green-400); }
.dag-node.running { border-left-color: var(--orange-400); }
.dag-node.failed { border-left-color: var(--red-400); }

.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.node-id {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}

.node-desc {
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.node-meta {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  gap: 10px;
}

.dag-arrow {
  text-align: center;
  font-size: 18px;
  color: var(--text-muted);
  padding: 2px 0;
}

.event-preview {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  font-style: italic;
}

.event-args {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
  word-break: break-all;
}

/* 反思卡片 */
.reflection-card {
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
}

.reflection-card.passed { border-left: 3px solid var(--green-400); }
.reflection-card.failed { border-left: 3px solid var(--red-400); }

.reflection-scores {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.score-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-label {
  font-size: 13px;
  color: var(--text-secondary);
  width: 80px;
  flex-shrink: 0;
}

.score-item :deep(.el-progress) {
  flex: 1;
}

.reflection-issues,
.reflection-suggestions {
  margin-top: 10px;
}

.reflection-issues strong { color: var(--red-500); font-size: 13px; }
.reflection-suggestions strong { color: var(--blue-500); font-size: 13px; }

.reflection-issues ul,
.reflection-suggestions ul {
  margin: 4px 0 0 16px;
  padding: 0;
}

.reflection-issues li { color: var(--red-600); font-size: 12px; }
.reflection-suggestions li { color: var(--blue-600); font-size: 12px; }

/* 性能指标 */
.perf-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.perf-item {
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px;
  text-align: center;
}

.perf-label {
  font-size: 12px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}

.perf-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
</style>
