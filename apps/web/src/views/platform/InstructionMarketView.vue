<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="指令模板市场">
      <template #actions>
        <el-button @click="showImport = true"><el-icon><Upload /></el-icon> 导入</el-button>
        <el-button type="primary" @click="showCreate = true"><el-icon><Plus /></el-icon> 创建模板</el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div class="filter-bar">
        <el-input v-model="search" placeholder="搜索模板..." prefix-icon="Search" style="width: 300px" clearable />
      </div>

      <div class="template-grid">
        <div v-for="tmpl in filteredTemplates" :key="tmpl.id" class="template-card surface-card">
          <div class="template-header">
            <h3>{{ tmpl.name }}</h3>
            <el-tag size="small" :type="tmpl.visibility === 'public' ? 'success' : ''">
              {{ tmpl.visibility === 'public' ? '公共' : '私有' }}
            </el-tag>
          </div>
          <p class="template-desc">{{ tmpl.description || '暂无描述' }}</p>
          <div class="template-tags">
            <el-tag v-for="tag in tmpl.tags" :key="tag" size="small" effect="plain" style="margin-right: 4px">
              {{ tag }}
            </el-tag>
          </div>
          <div class="template-footer">
            <div class="template-stats">
              <span>⭐ {{ tmpl.stars || 0 }}</span>
              <span>📥 {{ tmpl.downloads || 0 }}</span>
              <span>v{{ tmpl.version }}</span>
            </div>
            <div class="template-actions">
              <el-button link size="small" @click="showTemplatePreview(tmpl)">预览</el-button>
              <el-button v-if="tmpl.visibility === 'public'" link size="small" @click="starTemplate(tmpl)">
                ⭐ 收藏
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <EnhancedEmpty v-if="!filteredTemplates.length" variant="document" title="暂无模板" description="创建或从市场导入 Prompt 模板" />
    </div>

    <!-- 预览对话框 -->
    <el-dialog v-model="showPreview" title="模板预览" width="640px">
      <div v-if="previewData" class="preview-box">
        <h4>{{ previewData.name }}</h4>
        <pre class="preview-content">{{ previewData.content }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import { platformApi } from '@/api/platform'
import PageHeaderCompact from '@/components/PageHeaderCompact.vue'
import EnhancedEmpty from '@/components/EnhancedEmpty.vue'

const search = ref('')
const showImport = ref(false)
const showCreate = ref(false)
const showPreview = ref(false)
const previewData = ref<any>(null)
const templates = ref<any[]>([])

const filteredTemplates = computed(() => {
  if (!search.value) return templates.value
  return templates.value.filter(t => t.name.includes(search.value) || !!t.description?.includes(search.value))
})

async function loadData() {
  try {
    const res = await platformApi.listPromptTemplates()
    templates.value = res.data || []
  } catch { /* ignore */ }
}

function showTemplatePreview(tmpl: any) {
  previewData.value = tmpl
  showPreview.value = true
}

async function starTemplate(tmpl: any) {
  tmpl.stars = (tmpl.stars || 0) + 1
  ElMessage.success('已收藏')
}

onMounted(loadData)
</script>

<style scoped>
.platform-content { padding: 16px 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; }
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.template-card { transition: border-color var(--transition-fast); }
@media (hover: hover) and (pointer: fine) {
  .template-card:hover { border-color: var(--blue-500); }
}
.template-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.template-header h3 { margin: 0; font-size: var(--text-body); }
.template-desc { font-size: var(--text-caption); color: var(--el-text-color-secondary); margin-bottom: 8px; }
.template-tags { margin-bottom: 12px; }
.template-footer { display: flex; justify-content: space-between; align-items: center; }
.template-stats { font-size: var(--text-caption); color: var(--el-text-color-secondary); display: flex; gap: 12px; }
.preview-box pre { background: var(--el-fill-color); padding: 12px; border-radius: var(--radius-xs); font-size: var(--text-caption); white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
</style>
