<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Prompt 模板库" subtitle="管理公共提示词及个人收藏夹">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">新建模板</el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载模板中...</span>
      </div>

      <EnhancedEmpty
        v-else-if="!templates.length"
        variant="document"
        title="暂无模板"
        description="沉淀您的第一个优质 Prompt 吧"
      />

      <div v-else class="template-grid">
        <div v-for="tpl in templates" :key="tpl.id" class="template-card">
          <div class="tpl-header">
            <div class="tpl-title">
              <h3>{{ tpl.name }}</h3>
              <el-tag size="small" :type="tpl.visibility === 'public' ? 'success' : 'info'" effect="plain">
                {{ tpl.visibility === 'public' ? '公共' : '个人' }}
              </el-tag>
            </div>
            <div class="tpl-actions">
              <el-button text type="primary" size="small" @click="openEditDialog(tpl)">编辑</el-button>
              <el-button text type="danger" size="small" @click="deleteTpl(tpl)">删除</el-button>
            </div>
          </div>
          <div class="tpl-body">
            <p>{{ tpl.content }}</p>
          </div>
          <div class="tpl-footer">
            <div class="tpl-tags">
              <el-tag v-for="tag in tpl.tags" :key="tag" size="small" type="info">{{ tag }}</el-tag>
            </div>
            <div class="tpl-fav">
              <el-icon :color="tpl.favorite ? '#e6a23c' : '#c0c4cc'" @click="toggleFav(tpl)" style="cursor: pointer; font-size: 18px;">
                <StarFilled v-if="tpl.favorite" />
                <Star v-else />
              </el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editingTemplate ? '编辑模板' : '新建模板'" width="550px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：英文翻译优化" />
        </el-form-item>
        
        <el-form-item label="Prompt 内容">
          <el-input v-model="form.content" type="textarea" :rows="6" placeholder="请在这里写下你的 Prompt..." />
        </el-form-item>

        <el-form-item label="可见性">
          <el-radio-group v-model="form.visibility">
            <el-radio value="private">个人私有</el-radio>
            <el-radio value="public">团队公开</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="标签 (Tags)">
          <el-select v-model="form.tags" multiple filterable allow-create default-first-option placeholder="输入或选择标签" style="width: 100%;">
            <el-option label="写作" value="writing" />
            <el-option label="编程" value="coding" />
            <el-option label="分析" value="analysis" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading, Star, StarFilled } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listPromptTemplates, createPromptTemplate, updatePromptTemplate, deletePromptTemplate } from '@/api/platform';

const templates = ref<any[]>([]);
const loading = ref(false);

const dialogVisible = ref(false);
const saving = ref(false);
const editingTemplate = ref<any>(null);

const form = ref({
  name: '',
  content: '',
  visibility: 'private',
  tags: [] as string[]
});

const loadData = async () => {
  loading.value = true;
  try {
    const res: any = await listPromptTemplates();
    templates.value = res.items || [];
  } finally {
    loading.value = false;
  }
};

const openCreateDialog = () => {
  editingTemplate.value = null;
  form.value = {
    name: '',
    content: '',
    visibility: 'private',
    tags: []
  };
  dialogVisible.value = true;
};

const openEditDialog = (tpl: any) => {
  editingTemplate.value = tpl;
  form.value = {
    name: tpl.name || '',
    content: tpl.content || '',
    visibility: tpl.visibility || 'private',
    tags: tpl.tags || []
  };
  dialogVisible.value = true;
};

const saveTemplate = async () => {
  if (!form.value.name.trim() || !form.value.content.trim()) {
    ElMessage.warning('名称和内容不能为空');
    return;
  }
  saving.value = true;
  try {
    if (editingTemplate.value) {
      await updatePromptTemplate(editingTemplate.value.id, form.value);
      ElMessage.success('更新成功');
    } else {
      await createPromptTemplate({ ...form.value, favorite: false });
      ElMessage.success('创建成功');
    }
    dialogVisible.value = false;
    loadData();
  } finally {
    saving.value = false;
  }
};

const toggleFav = async (tpl: any) => {
  try {
    await updatePromptTemplate(tpl.id, { favorite: !tpl.favorite });
    tpl.favorite = !tpl.favorite;
  } catch (e) {
    ElMessage.error('操作失败');
  }
};

const deleteTpl = async (tpl: any) => {
  try {
    await ElMessageBox.confirm('确定删除该模板吗？', '删除确认', { type: 'warning' });
  } catch {
    return;
  }
  await deletePromptTemplate(tpl.id);
  ElMessage.success('已删除');
  loadData();
};

onMounted(() => {
  loadData();
});
</script>

<style scoped>
.platform-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.platform-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: var(--bg-panel-muted);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.template-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tpl-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.tpl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tpl-title h3 {
  margin: 0;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.tpl-actions {
  display: flex;
}

.tpl-body {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-body);
  border-radius: var(--radius-sm);
  padding: 12px;
  white-space: pre-wrap;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tpl-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
}

.tpl-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
