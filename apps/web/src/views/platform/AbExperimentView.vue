<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="A/B 实验">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 新建实验
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <EnhancedEmpty
        v-if="!experiments.length"
        variant="document"
        title="暂无实验"
        description="创建 A/B 实验来对比不同指令的效果"
      />

      <div v-else class="experiment-list">
        <div v-for="exp in experiments" :key="exp.experiment_id" class="surface-card">
          <div class="exp-header">
            <h3>{{ exp.name }}</h3>
            <el-tag :type="exp.is_active ? 'success' : 'info'" size="small">
              {{ exp.is_active ? '进行中' : '已停止' }}
            </el-tag>
          </div>
          <div class="exp-progress">
            <el-progress
              :percentage="progressPct(exp)"
              :stroke-width="10"
              :status="exp.is_active ? '' : 'success'"
            />
            <span class="progress-text">{{ exp.sample_size || 0 }} / {{ exp.target }} 样本</span>
          </div>
          <div class="exp-actions">
            <el-button size="small" @click="viewReport(exp)">查看报告</el-button>
            <el-button v-if="exp.is_active" size="small" type="warning" @click="stopExperiment(exp)">停止</el-button>
          </div>
          <p v-if="stopErrorId === exp.experiment_id" class="inline-error">停止失败，实验仍在运行，请稍后重试</p>
        </div>

        <el-dialog v-model="reportVisible" title="实验报告" width="640px">
          <div v-if="report" class="report-content">
            <div class="report-summary">
              <span>样本 A：{{ report.sample_size?.A || 0 }}</span>
              <span>样本 B：{{ report.sample_size?.B || 0 }}</span>
              <el-tag :type="report.is_significant ? 'success' : 'info'">
                {{ report.is_significant ? '结果显著' : '尚无显著结论' }}
              </el-tag>
            </div>
            <p class="report-recommendation">建议：{{ recommendationLabel(report.recommendation) }}</p>
            <el-table :data="reportMetricRows" size="small">
              <el-table-column prop="metric" label="指标" />
              <el-table-column prop="aMean" label="A 均值" />
              <el-table-column prop="bMean" label="B 均值" />
              <el-table-column prop="diff" label="差异" />
              <el-table-column prop="pValue" label="p 值" />
            </el-table>
          </div>
          <EnhancedEmpty
            v-else-if="reportError"
            variant="question"
            title="报告加载失败"
            description="请关闭弹窗后重新点「查看报告」"
          />
          <LoadingState v-else label="正在加载报告..." />
        </el-dialog>
      </div>
    </div>

    <!-- 新建实验对话框 -->
    <el-dialog v-model="showCreate" title="新建 A/B 实验" width="560px">
      <el-form :model="createForm" label-position="top">
        <el-form-item label="实验名称" required>
          <el-input v-model="createForm.name" placeholder="如：Prompt v2.0 对比测试" />
        </el-form-item>
        <el-form-item label="对照组指令 (A)">
          <el-input v-model="createForm.control_prompt" type="textarea" :rows="3" placeholder="当前使用的指令版本" />
        </el-form-item>
        <el-form-item label="实验组指令 (B)">
          <el-input v-model="createForm.variant_prompt" type="textarea" :rows="3" placeholder="新指令版本" />
        </el-form-item>
        <el-form-item label="目标样本量">
          <el-input-number v-model="createForm.sample_size_target" :min="30" :max="1000" :step="50" />
        </el-form-item>
        <el-form-item label="流量分配 (B 比例)">
          <el-slider v-model="createForm.split_ratio" :min="0.1" :max="0.9" :step="0.1" show-input />
        </el-form-item>
      </el-form>
      <p v-if="createError" class="inline-error">启动失败，请稍后重试</p>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="startExperiment">启动实验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'
import EnhancedEmpty from '@/components/EnhancedEmpty.vue'
import LoadingState from '@/components/LoadingState.vue'

const experiments = ref<any[]>([])
const showCreate = ref(false)
const createError = ref(false)
const stopErrorId = ref('')
const reportVisible = ref(false)
const report = ref<any>(null)
const reportError = ref(false)

const createForm = ref({
  name: '',
  control_prompt: '',
  variant_prompt: '',
  sample_size_target: 100,
  split_ratio: 0.5,
})

function progressPct(exp: any) {
  return Math.min(Math.round((exp.sample_size || 0) / (exp.target || 100) * 100), 100)
}

async function loadData() {
  try {
    const res = await platformApi.listExperiments()
    experiments.value = res.data || []
  } catch { /* ignore */ }
}

function openCreateDialog() {
  createError.value = false
  showCreate.value = true
}

async function startExperiment() {
  createError.value = false
  try {
    await platformApi.startExperiment({
      experiment_id: `exp_${Date.now()}`,
      ...createForm.value,
    })
    ElMessage.success('实验已启动')
    showCreate.value = false
    loadData()
  } catch { createError.value = true }
}

async function stopExperiment(exp: any) {
  try {
    await ElMessageBox.confirm(`停止后将不再收集样本，确定停止「${exp.name}」吗？`, '确认停止')
  } catch { return }

  try {
    await platformApi.stopExperiment(exp.experiment_id)
    stopErrorId.value = ''
    ElMessage.success('实验已停止')
    loadData()
  } catch { stopErrorId.value = exp.experiment_id }
}

function viewReport(exp: any) {
  report.value = null
  reportError.value = false
  reportVisible.value = true
  platformApi.getExperimentReport(exp.experiment_id)
    .then((res) => { report.value = res.data })
    .catch(() => { reportError.value = true })
}

const reportMetricRows = computed(() => Object.entries(report.value?.metrics || {}).map(([metric, value]: [string, any]) => ({
  metric,
  aMean: value.A_mean,
  bMean: value.B_mean,
  diff: `${value.diff_pct}%`,
  pValue: value.p_value
})))

function recommendationLabel(value: string) {
  return ({ adopt_variant: '采用实验组 B', keep_control: '保留对照组 A', need_more_data: '继续收集数据' } as Record<string, string>)[value] || '继续收集数据'
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.experiment-list { display: flex; flex-direction: column; gap: 16px; }
.exp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.exp-header h3 { margin: 0; font-size: var(--text-body); }
.exp-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.progress-text { font-size: var(--text-caption); color: var(--el-text-color-secondary); white-space: nowrap; }
.exp-actions { display: flex; gap: 8px; }
.inline-error { margin: 8px 0 0; font-size: var(--text-caption); color: var(--el-color-danger); }
.report-content { display: grid; gap: 16px; }
.report-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; color: var(--el-text-color-secondary); }
.report-recommendation { margin: 0; color: var(--el-text-color-primary); }
</style>
