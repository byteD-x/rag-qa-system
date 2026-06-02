<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="API Key 管理" subtitle="创建、轮换、监控 API Key 的使用情况与配额">
      <template #actions>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon> 创建 Key
        </el-button>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ keys.length }}</div>
          <div class="stat-label">活跃 Key</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ revokedCount }}</div>
          <div class="stat-label">已撤销</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ quotaExhaustedCount }}</div>
          <div class="stat-label">配额耗尽</div>
        </div>
      </div>

      <el-table :data="keys" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="prefix" label="Key 前缀" min-width="160">
          <template #default="{ row }">
            <code class="key-prefix">{{ row.prefix }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="permissions" label="权限" width="180">
          <template #default="{ row }">
            <el-tag v-for="p in row.permissions" :key="p" size="small" style="margin-right: 4px">
              {{ p }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配额使用" width="160">
          <template #default="{ row }">
            <div v-if="row.quota_tokens > 0">
              <el-progress
                :percentage="row.tokens_used / row.quota_tokens * 100"
                :status="row.tokens_used / row.quota_tokens > 0.9 ? 'exception' : ''"
                :stroke-width="8"
              />
              <small>{{ formatTokens(row.tokens_used) }} / {{ formatTokens(row.quota_tokens) }}</small>
            </div>
            <el-tag v-else size="small" type="info">无限</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="rotateKey(row)">轮换</el-button>
            <el-button link type="danger" size="small" @click="revokeKey(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 创建对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建 API Key" width="520px" @closed="resetCreateForm">
      <el-form :model="createForm" label-position="top">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="用于标识此 Key 的用途" />
        </el-form-item>
        <el-form-item label="权限">
          <el-checkbox-group v-model="createForm.permissions">
            <el-checkbox label="chat.use">问答问答</el-checkbox>
            <el-checkbox label="kb.read">知识库查看</el-checkbox>
            <el-checkbox label="kb.write">知识库编辑</el-checkbox>
            <el-checkbox label="kb.manage">知识库管理</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="Token 配额（0=无限）">
          <el-input-number v-model="createForm.quota_tokens" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="速率限制（次/分钟）">
          <el-input-number v-model="createForm.rate_limit" :min="1" :max="600" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createKey">创建</el-button>
      </template>
    </el-dialog>

    <!-- 创建成功提示 -->
    <el-dialog v-model="showCreatedKey" title="Key 创建成功" width="520px">
      <el-alert type="warning" title="请立即复制并安全保存此 Key，关闭后将无法再次查看！" :closable="false" show-icon />
      <div class="created-key-box">
        <code>{{ createdRawKey }}</code>
        <el-button @click="copyKey" size="small" type="primary" style="margin-top: 8px">复制到剪贴板</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'

const loading = ref(false)
const keys = ref<any[]>([])
const showCreateDialog = ref(false)
const showCreatedKey = ref(false)
const createdRawKey = ref('')

const createForm = ref({
  name: '',
  permissions: ['chat.use'],
  quota_tokens: 100000,
  rate_limit: 60,
})

const revokedCount = computed(() => keys.value.filter(k => k.status === 'revoked').length)
const quotaExhaustedCount = computed(() => keys.value.filter(k => k.quota_tokens > 0 && k.tokens_used >= k.quota_tokens).length)

async function loadData() {
  loading.value = true
  try {
    const res = await platformApi.listApiKeys()
    keys.value = res.data || []
  } catch (e) {
    ElMessage.error('加载 API Key 列表失败')
  } finally {
    loading.value = false
  }
}

async function createKey() {
  try {
    const res = await platformApi.createApiKey(createForm.value)
    createdRawKey.value = res.data.raw_key
    showCreateDialog.value = false
    showCreatedKey.value = true
    loadData()
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

async function rotateKey(row: any) {
  try {
    await ElMessageBox.confirm('轮换后将创建新 Key，旧 Key 在 24 小时后自动失效。确定？', '确认轮换')
    await platformApi.rotateApiKey(row.id)
    ElMessage.success('Key 已轮换')
    loadData()
  } catch { /* 取消 */ }
}

async function revokeKey(row: any) {
  try {
    await ElMessageBox.confirm('撤销后该 Key 将立即失效，不可恢复。确定？', '确认撤销', { type: 'warning' })
    await platformApi.revokeApiKey(row.id)
    ElMessage.success('Key 已撤销')
    loadData()
  } catch { /* 取消 */ }
}

function copyKey() {
  navigator.clipboard.writeText(createdRawKey.value)
  ElMessage.success('已复制到剪贴板')
}

function resetCreateForm() {
  createForm.value = { name: '', permissions: ['chat.use'], quota_tokens: 100000, rate_limit: 60 }
}

function statusType(status: string) {
  const map: Record<string, string> = { active: 'success', rotating: 'warning', revoked: 'danger', expired: 'info' }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { active: '活跃', rotating: '轮换中', revoked: '已撤销', expired: '已过期' }
  return map[status] || status
}

function formatTokens(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K'
  return String(n)
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; text-align: center; padding: 16px; border-radius: 8px; background: var(--el-fill-color-light); }
.stat-value { font-size: 24px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.key-prefix { background: var(--el-fill-color); padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.created-key-box { margin-top: 16px; padding: 12px; background: var(--el-fill-color-light); border-radius: 8px; text-align: center; }
.created-key-box code { word-break: break-all; font-size: 13px; }
</style>
