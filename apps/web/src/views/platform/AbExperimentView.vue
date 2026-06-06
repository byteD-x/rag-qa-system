<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="A/B 实验" subtitle="对比不同 Prompt / 模型的回答质量，数据驱动迭代">
      <template #actions>
        <el-button type="primary" @click="showCreate = true">
          <el-icon><Plus /></el-icon> 新建实验
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ experiments.length }}</div>
          <div class="stat-label">实验总数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ activeCount }}</div>
          <div class="stat-label">进行中</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ completedCount }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>

      <div v-if="!experiments.length" style="text-align:center; padding: 40px">
        <EnhancedEmpty variant="document" title="暂无实验" description="创建 A/B 实验来对比不同指令的效果" />
      </div>

      <div v-else class="experiment-list">
        <div v-for="exp in experiments" :key="exp.experiment_id" class="experiment-card">
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
          <div class="exp-meta">
            <span>创建于 {{ formatDate(exp.created_at) }}</span>
          </div>
          <div class="exp-actions">
            <el-button size="small" @click="viewReport(exp)">查看报告</el-button>
            <el-button v-if="exp.is_active" size="small" type="warning" @click="stopExperiment(exp)">停止</el-button>
          </div>
        </div>
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
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="startExperiment">启动实验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'
import EnhancedEmpty from '@/components/EnhancedEmpty.vue'

const experiments = ref<any[]>([])
const showCreate = ref(false)

const createForm = ref({
  name: '',
  control_prompt: '',
  variant_prompt: '',
  sample_size_target: 100,
  split_ratio: 0.5,
})

const activeCount = computed(() => experiments.value.filter(e => e.is_active).length)
const completedCount = computed(() => experiments.value.filter(e => !e.is_active).length)

function progressPct(exp: any) {
  return Math.min(Math.round((exp.sample_size || 0) / (exp.target || 100) * 100), 100)
}

async function loadData() {
  try {
    const res = await platformApi.listExperiments()
    experiments.value = res.data || []
  } catch { /* ignore */ }
}

async function startExperiment() {
  try {
    await platformApi.startExperiment({
      experiment_id: `exp_${Date.now()}`,
      ...createForm.value,
    })
    ElMessage.success('实验已启动')
    showCreate.value = false
    loadData()
  } catch { ElMessage.error('启动失败') }
}

async function stopExperiment(exp: any) {
  await platformApi.stopExperiment(exp.experiment_id)
  ElMessage.success('实验已停止')
  loadData()
}

function viewReport(exp: any) {
  void exp
  ElMessage.info('实验报告功能开发中')
}

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString()
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; text-align: center; padding: 16px; border-radius: 8px; background: var(--el-fill-color-light); }
.stat-value { font-size: 24px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.experiment-list { display: flex; flex-direction: column; gap: 16px; }
.experiment-card { border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 16px; }
.exp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.exp-header h3 { margin: 0; font-size: 15px; }
.exp-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.progress-text { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.exp-meta { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.exp-actions { display: flex; gap: 8px; }
</style>
