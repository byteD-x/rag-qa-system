<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Agent 协作编排" subtitle="可视化多 Agent 协作的执行计划、DAG 依赖与结果聚合">
      <template #actions>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 统计 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ stats.totalPlans }}</div>
          <div class="stat-label">编排计划</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.successRate }}%</div>
          <div class="stat-label">执行成功率</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.avgWorkers }}</div>
          <div class="stat-label">平均 Worker 数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.avgTimeMs }}ms</div>
          <div class="stat-label">平均执行时间</div>
        </div>
      </div>

      <!-- 编排记录列表 -->
      <el-table :data="runs" v-loading="loading" stripe @row-click="showRunDetail">
        <el-table-column prop="plan_id" label="计划 ID" width="100" />
        <el-table-column prop="question" label="问题" min-width="180" show-overflow-tooltip />
        <el-table-column label="子任务" width="80">
          <template #default="{ row }">{{ row.sub_tasks?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="成功/失败" width="100">
          <template #default="{ row }">
            <span style="color: var(--el-color-success)">{{ row.success_count }}</span>
            <span style="margin: 0 4px">/</span>
            <span style="color: var(--el-color-danger)">{{ row.failure_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ row.total_time_ms }}ms</template>
        </el-table-column>
        <el-table-column label="Worker 类型" width="140">
          <template #default="{ row }">
            <el-tag
              v-for="wt in row.worker_types"
              :key="wt"
              size="small"
              effect="plain"
              style="margin-right: 4px"
            >{{ wt }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 执行详情抽屉 -->
      <el-drawer v-model="showDetail" title="编排执行详情" size="560px">
        <template v-if="selectedRun">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="计划 ID">{{ selectedRun.plan_id }}</el-descriptions-item>
            <el-descriptions-item label="问题">{{ selectedRun.question }}</el-descriptions-item>
            <el-descriptions-item label="总耗时">{{ selectedRun.total_time_ms }}ms</el-descriptions-item>
          </el-descriptions>

          <!-- DAG 执行顺序 -->
          <h4 style="margin-top: 20px">执行顺序（拓扑排序）</h4>
          <div v-for="(group, idx) in selectedRun.execution_order || []" :key="idx" class="exec-group">
            <el-tag type="warning" size="small">并行组 {{ idx + 1 }}</el-tag>
            <div class="group-tasks">
              <el-tag v-for="tid in group" :key="tid" size="small" effect="dark" style="margin: 2px 4px">
                {{ tid }}
              </el-tag>
            </div>
          </div>

          <!-- Worker 结果 -->
          <h4 style="margin-top: 20px">Worker 执行结果</h4>
          <div v-for="wr in selectedRun.worker_results || []" :key="wr.task_id" class="worker-result">
            <div class="wr-header">
              <el-tag :type="wr.success ? 'success' : 'danger'" size="small">
                {{ wr.worker_type }}
              </el-tag>
              <span class="wr-id">{{ wr.task_id }}</span>
              <span class="wr-time">{{ wr.execution_time_ms }}ms</span>
            </div>
            <div v-if="wr.error" class="wr-error">{{ wr.error }}</div>
            <div class="wr-evidence">
              证据数: {{ wr.evidence?.length || 0 }}
            </div>
          </div>
        </template>
      </el-drawer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'

const loading = ref(false)
const runs = ref<any[]>([])
const showDetail = ref(false)
const selectedRun = ref<any>(null)

const stats = reactive({
  totalPlans: 0,
  successRate: 0,
  avgWorkers: 0,
  avgTimeMs: 0,
})

async function loadData() {
  loading.value = true
  try {
    const res = await platformApi.listOrchestrationRuns()
    const data = res.data || []
    runs.value = data.map((r: any) => ({
      ...r,
      worker_types: [...new Set((r.worker_results || []).map((w: any) => w.worker_type))],
    }))

    stats.totalPlans = data.length
    const successes = data.filter((r: any) => r.failure_count === 0).length
    stats.successRate = data.length ? Math.round(successes / data.length * 100) : 0
    stats.avgWorkers = data.length
      ? Math.round(data.reduce((s: number, r: any) => s + (r.sub_tasks?.length || 0), 0) / data.length)
      : 0
    stats.avgTimeMs = data.length
      ? Math.round(data.reduce((s: number, r: any) => s + (r.total_time_ms || 0), 0) / data.length)
      : 0
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function showRunDetail(row: any) {
  selectedRun.value = row
  showDetail.value = true
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; text-align: center; padding: 16px; border-radius: 8px; background: var(--el-fill-color-light); }
.stat-value { font-size: 24px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.exec-group { margin: 8px 0; }
.group-tasks { display: inline-flex; flex-wrap: wrap; margin-left: 8px; }
.worker-result { margin: 8px 0; padding: 8px; border: 1px solid var(--el-border-color-light); border-radius: 6px; }
.wr-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.wr-id { font-size: 12px; color: var(--el-text-color-secondary); }
.wr-time { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.wr-error { font-size: 12px; color: var(--el-color-danger); padding: 4px 0; }
.wr-evidence { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
