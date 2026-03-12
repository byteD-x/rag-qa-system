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
        <div class="trace-kv" v-if="workflowRunDetail.llm_trace?.duration_ms"><span>耗时:</span> <strong>{{ workflowRunDetail.llm_trace.duration_ms }} ms</strong></div>
        <div class="trace-kv" v-if="workflowRunDetail.llm_trace?.route_key"><span>路由:</span> <strong>{{ workflowRunDetail.llm_trace.route_key }}</strong></div>
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
import { ref } from 'vue';
import { Loading } from '@element-plus/icons-vue';
import { getWorkflowRun, retryWorkflowRun } from '@/api/chat';
import { ElMessage } from 'element-plus';
import { useChatStore } from '@/store/chat';

const chatStore = useChatStore();
const visible = ref(false);
const workflowRunDetail = ref<any>(null);
const loadingWorkflow = ref(false);
const retrying = ref(false);

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
.trace-collapse { border: none; }
.json-viewer { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: var(--font-mono); font-size: 12px; max-height: 400px; overflow: auto; }
.trace-actions { margin-top: 24px; }
.trace-loading { display: flex; align-items: center; justify-content: center; gap: 8px; height: 100px; color: var(--text-muted); }
</style>