<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Webhook 管理" subtitle="注册回调地址，在事件发生时自动通知外部系统">
      <template #actions>
        <el-button type="primary" @click="showRegister = true">
          <el-icon><Plus /></el-icon> 注册 Webhook
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <el-table :data="hooks" v-loading="loading" stripe>
        <el-table-column prop="url" label="回调 URL" min-width="200" show-overflow-tooltip />
        <el-table-column label="监听事件" width="180">
          <template #default="{ row }">
            <el-tag v-for="ev in row.events" :key="ev" size="small" style="margin-right: 4px">{{ ev }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '活跃' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="重试" width="70">
          <template #default="{ row }">{{ row.retry_count }}次</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link size="small" @click="testHook(row)">测试</el-button>
            <el-button link size="small" @click="toggleHook(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" size="small" @click="deleteHook(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 投递历史 -->
      <el-card header="最近投递记录" style="margin-top: 20px">
        <el-table :data="deliveries" size="small">
          <el-table-column prop="event" label="事件" width="140" />
          <el-table-column prop="url" label="URL" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                {{ row.status === 'success' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="http_status" label="HTTP" width="60" />
          <el-table-column prop="duration_ms" label="耗时" width="80">
            <template #default="{ row }">{{ row.duration_ms }}ms</template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-dialog v-model="showRegister" title="注册 Webhook" width="500px">
      <el-form :model="form" label-position="top">
        <el-form-item label="回调 URL" required>
          <el-input v-model="form.url" placeholder="https://your-server.com/webhook" />
        </el-form-item>
        <el-form-item label="监听事件">
          <el-select v-model="form.events" multiple placeholder="选择事件类型" style="width:100%">
            <el-option label="问答完成 (chat.completed)" value="chat.completed" />
            <el-option label="会话创建 (session.created)" value="session.created" />
            <el-option label="知识库更新 (kb.updated)" value="kb.updated" />
            <el-option label="Agent 执行完成 (agent.completed)" value="agent.completed" />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥（可选）">
          <el-input v-model="form.secret" placeholder="HMAC 签名密钥" show-password />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" placeholder="可选说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRegister = false">取消</el-button>
        <el-button type="primary" @click="register">注册</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'

const loading = ref(false)
const hooks = ref<any[]>([])
const deliveries = ref<any[]>([])
const showRegister = ref(false)

const form = ref({ url: '', events: ['chat.completed'], secret: '', description: '' })

async function loadData() {
  loading.value = true
  try {
    const [hRes, dRes] = await Promise.all([
      platformApi.listWebhooks(),
      platformApi.webhookDeliveries(),
    ])
    hooks.value = hRes.data || []
    deliveries.value = dRes.data || []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

async function register() {
  try {
    await platformApi.registerWebhook(form.value)
    ElMessage.success('Webhook 已注册')
    showRegister.value = false
    form.value = { url: '', events: ['chat.completed'], secret: '', description: '' }
    loadData()
  } catch { ElMessage.error('注册失败') }
}

async function testHook(row: any) {
  try {
    await platformApi.testWebhook(row.id)
    ElMessage.success('测试请求已发送')
  } catch { ElMessage.error('测试失败') }
}

async function toggleHook(row: any) {
  await platformApi.updateWebhook(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '已停用' : '已启用')
  loadData()
}

async function deleteHook(row: any) {
  await platformApi.deleteWebhook(row.id)
  ElMessage.success('已删除')
  loadData()
}

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleString()
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
</style>
