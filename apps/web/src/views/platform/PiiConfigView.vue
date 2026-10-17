<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="PII 脱敏配置">
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
        <div class="test-bar">
          <el-button @click="runTest" type="primary" :loading="testing">测试脱敏</el-button>
          <span class="test-hint" :class="{ 'test-hint-warn': dirty }">{{ testHint }}</span>
        </div>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import { platformApi } from '@/api/platform'
import { isHandledRequestError } from '@/api/request'
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

function currentState() {
  return {
    strategy: config.strategy,
    mask_char: config.mask_char,
    enabled_types: piiTypes.filter(t => t.enabled).map(t => t.key),
  }
}

const savedState = ref<any>(null)
const dirty = computed(() => {
  if (!savedState.value) return false
  const cur = currentState()
  const saved = savedState.value
  return cur.strategy !== saved.strategy
    || cur.mask_char !== saved.mask_char
    || cur.enabled_types.join() !== (saved.enabled_types || []).join()
})

const testHint = computed(() => dirty.value
  ? '有未保存的改动，测试仍按已保存的配置执行'
  : '测试使用已保存的配置（检测类型与遮盖字符）')

async function saveConfig() {
  if (!config.mask_char || [...config.mask_char].length !== 1) {
    ElMessage.error('遮盖字符必须填写一个字符')
    return
  }
  try {
    const res = await platformApi.savePiiConfig(currentState())
    savedState.value = res.data || currentState()
    ElMessage.success('配置已保存')
  } catch (error) {
    if (!isHandledRequestError(error)) ElMessage.error('保存失败')
  }
}

async function runTest() {
  if (!testInput.value.trim()) {
    ElMessage.warning('请输入要检测的文本')
    return
  }
  testing.value = true
  try {
    const res = await platformApi.testPiiDetection({ text: testInput.value, strategy: config.strategy })
    testResult.value = res.data
  } catch (error) {
    if (!isHandledRequestError(error)) ElMessage.error('检测失败')
  } finally {
    testing.value = false
  }
}

onMounted(async () => {
  try {
    const res = await platformApi.getPiiConfig()
    if (res.data) {
      Object.assign(config, res.data)
      const enabled = new Set(res.data.enabled_types || [])
      piiTypes.forEach(type => { type.enabled = enabled.has(type.key) })
      savedState.value = currentState()
    }
  } catch (error) {
    if (!isHandledRequestError(error)) ElMessage.error('加载 PII 配置失败，请重试')
  }
})
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.section-card { margin-bottom: 0; }
.pii-type-grid { display: flex; flex-direction: column; gap: 12px; }
.pii-type-row { display: flex; align-items: center; justify-content: space-between; }
.pii-type-info { display: flex; align-items: center; gap: 10px; }
.pii-label { font-weight: 500; min-width: 80px; }
.pii-type-desc { font-size: var(--text-caption); color: var(--el-text-color-secondary); }
.test-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.test-hint { font-size: var(--text-caption); color: var(--text-secondary); }
.test-hint-warn { color: var(--el-color-warning); }
.test-result { margin-top: 16px; padding: 12px; background: var(--el-fill-color-light); border-radius: var(--radius-sm); }
.result-row { margin-bottom: 8px; }
.result-label { font-weight: 600; }
.output-label { font-size: var(--text-caption); color: var(--el-text-color-secondary); margin-bottom: 4px; }
.output-text { font-family: monospace; font-size: var(--text-caption); white-space: pre-wrap; word-break: break-all; }
</style>
