<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="PII 脱敏配置" subtitle="管理个人身份信息的检测规则与脱敏策略">
      <template #actions>
        <el-button type="primary" @click="saveConfig">
          <el-icon><Check /></el-icon> 保存配置
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 脱敏策略 -->
      <el-card header="全局脱敏策略" class="section-card">
        <el-form label-width="120px">
          <el-form-item label="默认策略">
            <el-radio-group v-model="config.strategy">
              <el-radio value="mask">部分遮盖 (138****8000)</el-radio>
              <el-radio value="hash">哈希替换</el-radio>
              <el-radio value="redact">完全删除</el-radio>
              <el-radio value="replace">替换为类型标签</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="遮盖字符">
            <el-input v-model="config.mask_char" style="width: 80px" maxlength="1" />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- PII 类型开关 -->
      <el-card header="检测类型" class="section-card" style="margin-top: 16px">
        <div class="pii-type-grid">
          <div v-for="pt in piiTypes" :key="pt.key" class="pii-type-row">
            <div class="pii-type-info">
              <el-switch v-model="pt.enabled" />
              <span class="pii-label">{{ pt.label }}</span>
              <el-tag size="small">{{ pt.key }}</el-tag>
            </div>
            <div class="pii-type-desc">{{ pt.description }}</div>
          </div>
        </div>
      </el-card>

      <!-- 测试区域 -->
      <el-card header="脱敏测试" class="section-card" style="margin-top: 16px">
        <el-input
          v-model="testInput"
          type="textarea"
          :rows="3"
          placeholder="输入包含敏感信息的测试文本..."
        />
        <el-button @click="runTest" type="primary" style="margin-top: 12px" :loading="testing">测试脱敏</el-button>
        <div v-if="testResult" class="test-result">
          <div class="result-row">
            <span class="result-label">检测到 {{ testResult.pii_count }} 处敏感信息</span>
            <span v-if="testResult.by_type" class="result-detail">
              <el-tag v-for="(count, type) in testResult.by_type" :key="type" size="small" style="margin-left: 6px">
                {{ type }}: {{ count }}
              </el-tag>
            </span>
          </div>
          <div class="result-output">
            <div class="output-label">脱敏后：</div>
            <div class="output-text">{{ testResult.sanitized }}</div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'

const config = reactive({
  strategy: 'mask',
  mask_char: '*',
})

const piiTypes = reactive([
  { key: 'phone', label: '手机号', description: '中国大陆手机号段 (13x-19x)', enabled: true },
  { key: 'email', label: '邮箱', description: '标准邮箱地址格式', enabled: true },
  { key: 'id_card', label: '身份证号', description: '18位身份证号（含校验位验证）', enabled: true },
  { key: 'bank_card', label: '银行卡号', description: '16-19位银行卡号', enabled: true },
  { key: 'ip_address', label: 'IP 地址', description: 'IPv4 地址', enabled: true },
  { key: 'credit_card', label: '信用卡号', description: 'Visa/MasterCard 格式', enabled: true },
  { key: 'license_plate', label: '车牌号', description: '中国车牌号格式', enabled: false },
  { key: 'passport', label: '护照号', description: '中国护照号格式', enabled: false },
])

const testInput = ref('')
const testResult = ref<any>(null)
const testing = ref(false)

async function saveConfig() {
  try {
    await platformApi.savePiiConfig({
      strategy: config.strategy,
      mask_char: config.mask_char,
      enabled_types: piiTypes.filter(t => t.enabled).map(t => t.key),
    })
    ElMessage.success('配置已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function runTest() {
  if (!testInput.value) return
  testing.value = true
  try {
    const res = await platformApi.testPiiDetection({ text: testInput.value, strategy: config.strategy })
    testResult.value = res.data
  } catch {
    ElMessage.error('检测失败')
  } finally {
    testing.value = false
  }
}

onMounted(async () => {
  try {
    const res = await platformApi.getPiiConfig()
    if (res.data) Object.assign(config, res.data)
  } catch { /* 使用默认配置 */ }
})
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.section-card { margin-bottom: 0; }
.pii-type-grid { display: flex; flex-direction: column; gap: 12px; }
.pii-type-row { display: flex; align-items: center; justify-content: space-between; }
.pii-type-info { display: flex; align-items: center; gap: 10px; }
.pii-label { font-weight: 500; min-width: 80px; }
.pii-type-desc { font-size: 12px; color: var(--el-text-color-secondary); }
.test-result { margin-top: 16px; padding: 12px; background: var(--el-fill-color-light); border-radius: 8px; }
.result-row { margin-bottom: 8px; }
.result-label { font-weight: 600; }
.output-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.output-text { font-family: monospace; font-size: 13px; white-space: pre-wrap; word-break: break-all; }
</style>
