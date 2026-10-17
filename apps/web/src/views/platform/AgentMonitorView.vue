<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Agent 监控">
      <template #actions>
        <el-button @click="loadRuns" :loading="loadingRuns">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
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

      <LoadingState v-if="loadingRuns" label="加载运行记录..." />

      <EnhancedEmpty
        v-else-if="loadError"
        variant="question"
        title="运行记录加载失败"
        description="后端暂时不可用，请点右上角「刷新」重试"
      />

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
      <LoadingState v-if="loadingDetail" label="加载详情..." />

      <EnhancedEmpty
        v-else-if="detailError"
        variant="question"
        title="执行详情加载失败"
        description="请关闭抽屉后重新选择该运行"
      />

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
import { ref, onMounted } from 'vue';
import { Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { listAgentRuns, getAgentRunDetail, type AgentRunSummary, type AgentRunDetail, type AgentTaskNode } from '@/api/platform';

const runs = ref<AgentRunSummary[]>([]);
const runDetail = ref<AgentRunDetail | null>(null);
const selectedRun = ref<AgentRunSummary | null>(null);
const loadingRuns = ref(false);
const loadingDetail = ref(false);
const detailVisible = ref(false);
const statusFilter = ref('');
const loadError = ref(false);
const detailError = ref(false);

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
  if (score >= 0.8) return 'var(--el-color-success)';
  if (score >= 0.6) return 'var(--el-color-warning)';
  return 'var(--el-color-danger)';
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
  loadError.value = false;
  try {
    const params: any = { limit: 50 };
    if (statusFilter.value) params.status = statusFilter.value;
    const res: any = await listAgentRuns(params);
    runs.value = res.items || [];
  } catch {
    loadError.value = true;
    runs.value = [];
  } finally {
    loadingRuns.value = false;
  }
};

const selectRun = async (run: AgentRunSummary) => {
  selectedRun.value = run;
  detailVisible.value = true;
  loadingDetail.value = true;
  detailError.value = false;
  runDetail.value = null;
  try {
    const detail: any = await getAgentRunDetail(run.id);
    runDetail.value = detail;
  } catch {
    detailError.value = true;
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

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: var(--text-body);
  color: var(--text-primary);
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
  transition: border-color var(--transition-base);
}

@media (hover: hover) and (pointer: fine) {
  .run-card:hover {
    border-color: var(--blue-500);
  }
}

.run-card.selected {
  border-color: var(--blue-500);
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
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.run-question {
  font-size: var(--text-body);
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
  font-size: var(--text-caption);
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
  font-size: var(--text-body);
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
  font-size: var(--text-caption);
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
  border-left: 3px solid var(--blue-500);
}

.dag-node.completed { border-left-color: var(--el-color-success); }
.dag-node.running { border-left-color: var(--el-color-warning); }
.dag-node.failed { border-left-color: var(--el-color-danger); }

.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.node-id {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-muted);
}

.node-desc {
  font-size: var(--text-caption);
  color: var(--text-primary);
  margin-bottom: 4px;
}

.node-meta {
  font-size: var(--text-caption);
  color: var(--text-muted);
  display: flex;
  gap: 10px;
}

.dag-arrow {
  text-align: center;
  font-size: var(--text-h2);
  color: var(--text-muted);
  padding: 2px 0;
}

.event-preview {
  font-size: var(--text-caption);
  color: var(--text-muted);
  margin-top: 4px;
  font-style: italic;
}

.event-args {
  font-size: var(--text-caption);
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

.reflection-card.passed { border-left: 3px solid var(--el-color-success); }
.reflection-card.failed { border-left: 3px solid var(--el-color-danger); }

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
  font-size: var(--text-caption);
  color: var(--text-secondary);
  width: 80px;
  flex-shrink: 0;
}

.score-item :deep(.el-progress) {
  flex: 1;
}

/* Element Plus 默认给进度条宽度 600ms 的过渡（且动的是 width），这里改为瞬时 */
:deep(.el-progress-bar__inner) { transition: none; }

.reflection-issues,
.reflection-suggestions {
  margin-top: 10px;
}

.reflection-issues strong { color: var(--el-color-danger); font-size: var(--text-caption); }
.reflection-suggestions strong { color: var(--blue-500); font-size: var(--text-caption); }

.reflection-issues ul,
.reflection-suggestions ul {
  margin: 4px 0 0 16px;
  padding: 0;
}

.reflection-issues li { color: var(--el-color-danger); font-size: var(--text-caption); }
.reflection-suggestions li { color: var(--blue-600); font-size: var(--text-caption); }

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
  font-size: var(--text-caption);
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}

.perf-value {
  font-size: var(--text-h2);
  font-weight: 600;
  color: var(--text-primary);
}
</style>
