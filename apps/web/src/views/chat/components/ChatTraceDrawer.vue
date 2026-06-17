<template>
  <el-drawer v-model="visible" title="执行轨迹 (Trace)" size="450px" :destroy-on-close="true">
    <div v-if="workflowRunDetail" class="trace-panel">
      <div class="trace-status-bar">
        <el-tag :type="workflowRunDetail.status === 'completed' ? 'success' : (workflowRunDetail.status === 'failed' ? 'danger' : 'info')">
          {{ workflowRunDetail.status.toUpperCase() }}
        </el-tag>
        <span class="trace-id">{{ workflowRunDetail.id }}</span>
      </div>

      <div class="trace-section">
        <div class="trace-section-title">基本信息</div>
        <div class="trace-kv"><span>模式:</span> <strong>{{ workflowRunDetail.execution_mode }}</strong></div>
        <div class="trace-kv"><span>阶段:</span> <strong>{{ workflowRunDetail.stage || workflowRunDetail.workflow_state?.stage || '-' }}</strong></div>
        <div class="trace-kv" v-if="workflowRunDetail.llm_trace?.duration_ms"><span>耗时:</span> <strong>{{ workflowRunDetail.llm_trace.duration_ms }} ms</strong></div>
        <div class="trace-kv" v-if="workflowRunDetail.llm_trace?.route_key"><span>路由:</span> <strong>{{ workflowRunDetail.llm_trace.route_key }}</strong></div>
        <div class="trace-kv" v-if="workflowRunDetail.workflow_state?.can_resume"><span>可恢复:</span> <strong>{{ workflowRunDetail.workflow_state.resume_target || 'yes' }}</strong></div>
      </div>

      <div class="trace-section" v-if="eventTimeline.length">
        <div class="trace-section-title">事件时间线</div>
        <el-timeline class="trace-timeline">
          <el-timeline-item
            v-for="event in eventTimeline"
            :key="`${event.index}-${event.stage}`"
            :type="timelineItemType(event.status)"
            :timestamp="event.stage"
            size="small"
          >
            <div class="timeline-item">
              <div class="timeline-item__row">
                <strong>{{ event.status }}</strong>
                <span v-if="event.evidence_count !== undefined" class="timeline-item__meta">证据 {{ event.evidence_count }}</span>
                <span v-if="event.tool_call_count !== undefined" class="timeline-item__meta">工具 {{ event.tool_call_count }}</span>
                <span v-if="event.retrieval_ms !== undefined" class="timeline-item__meta">{{ event.retrieval_ms }} ms</span>
              </div>
              <div v-if="event.error_type" class="timeline-item__error">{{ event.error_type }}{{ event.error_class ? ` / ${event.error_class}` : '' }}</div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>

      <div class="trace-section" v-if="workflowRunDetail.workflow_state?.error || failureReasons.length || workflowRunDetail.status === 'failed'">
        <div class="trace-section-title">失败与恢复</div>
        <div class="trace-empty" v-if="!failureReasons.length && !workflowRunDetail.workflow_state?.error">暂无失败摘要</div>
        <div v-else class="trace-summary-grid">
          <div class="trace-summary-card" v-if="workflowRunDetail.workflow_state?.error">
            <span class="trace-summary-label">当前错误</span>
            <strong>{{ workflowRunDetail.workflow_state.error.type || '-' }}</strong>
            <p>{{ workflowRunDetail.workflow_state.error.detail || '-' }}</p>
          </div>
          <div class="trace-summary-card" v-if="workflowRunDetail.workflow_state?.resume_target">
            <span class="trace-summary-label">恢复目标</span>
            <strong>{{ workflowRunDetail.workflow_state.resume_target }}</strong>
            <p v-if="workflowRunDetail.workflow_state?.resume?.source_stage">来自 {{ workflowRunDetail.workflow_state.resume.source_stage }}</p>
          </div>
          <div class="trace-summary-card" v-if="failureReasons.length">
            <span class="trace-summary-label">失败原因</span>
            <ul>
              <li v-for="reason in failureReasons" :key="reason">{{ reason }}</li>
            </ul>
          </div>
        </div>
      </div>

      <div class="trace-section" v-if="workflowRunDetail.tool_calls?.length">
        <div class="trace-section-title">工具调用摘要</div>
        <el-table :data="workflowRunDetail.tool_calls.slice(0, 8)" size="small" style="width: 100%">
          <el-table-column prop="tool" label="工具" width="140" />
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="toolCallTag(row)" size="small">{{ toolCallStatus(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="result_count" label="结果数" width="78" align="center" />
        </el-table>
      </div>

      <el-collapse class="trace-collapse">
        <el-collapse-item title="LLM Trace" name="1" v-if="workflowRunDetail.llm_trace">
          <pre class="json-viewer">{{ JSON.stringify(workflowRunDetail.llm_trace, null, 2) }}</pre>
        </el-collapse-item>
        <el-collapse-item title="Tool Calls" name="2" v-if="workflowRunDetail.tool_calls?.length">
          <pre class="json-viewer">{{ JSON.stringify(workflowRunDetail.tool_calls, null, 2) }}</pre>
        </el-collapse-item>
        <el-collapse-item title="State" name="3">
          <pre class="json-viewer">{{ JSON.stringify(workflowRunDetail.workflow_state, null, 2) }}</pre>
        </el-collapse-item>
      </el-collapse>

      <div class="trace-actions" v-if="workflowRunDetail.status === 'failed'">
        <el-button type="primary" style="width: 100%" :loading="retrying" @click="handleRetry">
          重新执行
        </el-button>
      </div>
    </div>
    <div v-else class="trace-loading">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { Loading } from '@element-plus/icons-vue';
import { getWorkflowRun, retryWorkflowRun } from '@/api/chat';
import { ElMessage } from 'element-plus';
import { useChatStore } from '@/store/chat';

const chatStore = useChatStore();
const visible = ref(false);
const workflowRunDetail = ref<any>(null);
const loadingWorkflow = ref(false);
const retrying = ref(false);

const eventTimeline = computed(() => {
  const events = Array.isArray(workflowRunDetail.value?.workflow_events) ? workflowRunDetail.value.workflow_events : [];
  return events.map((event: any, index: number) => ({
    index: index + 1,
    stage: String(event?.stage || event?.status || `event-${index + 1}`),
    status: String(event?.status || 'unknown'),
    evidence_count: event?.evidence_count,
    retrieval_ms: event?.retrieval_ms,
    error_type: event?.error?.type,
    error_class: event?.error?.class
  }));
});

const failureReasons = computed(() => {
  const reasons = new Set<string>();
  const workflowError = workflowRunDetail.value?.workflow_state?.error;
  if (workflowError) {
    reasons.add([workflowError.type, workflowError.detail].filter(Boolean).join(': ') || 'workflow_error');
  }
  for (const event of eventTimeline.value) {
    if (event.error_type) {
      reasons.add([event.error_type, event.error_class].filter(Boolean).join(' / '));
    }
  }
  for (const call of Array.isArray(workflowRunDetail.value?.tool_calls) ? workflowRunDetail.value.tool_calls : []) {
    if (call?.error) {
      reasons.add(`${call.tool || 'tool'}: ${String(call.error)}`);
    }
  }
  return Array.from(reasons).slice(0, 6);
});

async function show(workflowInfo: any) {
  if (!workflowInfo || !workflowInfo.id) return;
  workflowRunDetail.value = null;
  visible.value = true;
  loadingWorkflow.value = true;
  try {
    const res: any = await getWorkflowRun(workflowInfo.id);
    workflowRunDetail.value = res;
  } catch (e) {
    ElMessage.error('获取执行轨迹失败');
    visible.value = false;
  } finally {
    loadingWorkflow.value = false;
  }
}

async function handleRetry() {
  if (!workflowRunDetail.value?.id) return;
  try {
    retrying.value = true;
    await retryWorkflowRun(workflowRunDetail.value.id);
    ElMessage.success('已发起重试');
    visible.value = false;
    if (chatStore.activeSessionId) {
      await chatStore.selectSession({ id: chatStore.activeSessionId });
    }
  } catch (e) {
    ElMessage.error('重试失败');
  } finally {
    retrying.value = false;
  }
}

function timelineItemType(status: string) {
  const map: Record<string, string> = { completed: 'success', failed: 'danger', running: 'primary', interrupted: 'warning' };
  return map[status] || 'info';
}

function toolCallStatus(row: any) {
  if (row?.error) return 'failed';
  if (row?.success === false) return 'failed';
  return 'success';
}

function toolCallTag(row: any) {
  return toolCallStatus(row) === 'failed' ? 'danger' : 'success';
}

defineExpose({ show });
</script>

<style scoped>
.trace-panel { padding: 0 16px 16px; }
.trace-status-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.trace-id { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }
.trace-section { margin-bottom: 20px; background: #f9f9fb; padding: 12px; border-radius: 8px; }
.trace-section-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.trace-kv { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.trace-kv span { color: var(--text-muted); }
.trace-empty { font-size: 12px; color: var(--text-muted); }
.trace-timeline { margin-top: 8px; }
.timeline-item { display: flex; flex-direction: column; gap: 4px; }
.timeline-item__row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 13px; }
.timeline-item__meta { color: var(--text-muted); font-size: 12px; }
.timeline-item__error { color: var(--el-color-danger); font-size: 12px; }
.trace-summary-grid { display: flex; flex-direction: column; gap: 8px; }
.trace-summary-card { background: #fff; border: 1px solid var(--border-color); border-radius: 6px; padding: 10px 12px; }
.trace-summary-label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.trace-summary-card p, .trace-summary-card ul { margin: 4px 0 0; font-size: 12px; color: var(--text-secondary); padding-left: 16px; }
.trace-collapse { border: none; }
.json-viewer { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: var(--font-mono); font-size: 12px; max-height: 400px; overflow: auto; }
.trace-actions { margin-top: 24px; }
.trace-loading { display: flex; align-items: center; justify-content: center; gap: 8px; height: 100px; color: var(--text-muted); }
</style>
