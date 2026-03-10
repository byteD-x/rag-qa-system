<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Agent 智能体市场" subtitle="管理您的智能体角色、能力插件及知识库挂载">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">创建智能体</el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载智能体中...</span>
      </div>

      <EnhancedEmpty
        v-else-if="!profiles.length"
        variant="document"
        title="暂无智能体"
        description="点击右上角创建您的第一个专属智能体"
      />

      <div v-else class="agent-grid">
        <div v-for="agent in profiles" :key="agent.id" class="agent-card">
          <div class="agent-header">
            <div class="agent-avatar">
              {{ agent.name.charAt(0).toUpperCase() }}
            </div>
            <div class="agent-title-col">
              <h3>{{ agent.name }}</h3>
              <span class="agent-desc">{{ agent.description || '暂无描述' }}</span>
            </div>
            <div class="agent-actions">
              <el-button plain size="small" @click="openEditDialog(agent)">编辑</el-button>
              <el-button plain size="small" type="danger" @click="deleteAgent(agent)">删除</el-button>
            </div>
          </div>
          <div class="agent-body">
            <div class="agent-tag-row">
              <el-tag size="small" effect="plain" v-if="agent.prompt_template_id">已绑定 Prompt</el-tag>
              <el-tag size="small" type="success" effect="plain" v-if="agent.default_corpus_ids?.length">已挂载知识库</el-tag>
            </div>
            <div class="agent-tools">
              <strong>启用插件:</strong>
              <div class="tool-list">
                <el-tag v-for="tool in agent.enabled_tools" :key="tool" size="small" type="info">{{ tool }}</el-tag>
                <span v-if="!agent.enabled_tools?.length" class="empty-text">未启用任何插件</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editingAgent ? '编辑智能体' : '创建智能体'" width="600px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：财报分析助手" />
        </el-form-item>
        
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="一句话介绍智能体..." />
        </el-form-item>

        <el-form-item label="系统设定 (Persona Prompt)">
          <el-input v-model="form.persona_prompt" type="textarea" :rows="4" placeholder="例如：你是一个资深财务分析师，请用专业的口吻解答问题..." />
        </el-form-item>

        <el-form-item label="插件列表 (Tools)">
          <el-select v-model="form.enabled_tools" multiple placeholder="选择启用的插件" style="width: 100%;">
            <el-option label="搜索作用域 (search_scope)" value="search_scope" />
            <el-option label="搜索语料库 (search_corpus)" value="search_corpus" />
            <el-option label="计算器 (calculator)" value="calculator" />
            <el-option label="列出文档 (list_scope_documents)" value="list_scope_documents" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="默认挂载知识库 (可选)">
          <el-select v-model="form.default_corpus_ids" multiple placeholder="请选择知识库" style="width: 100%;">
            <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="`kb:${b.id}`" />
          </el-select>
        </el-form-item>

        <el-form-item label="绑定 Prompt 模板 (可选)">
          <el-select v-model="form.prompt_template_id" clearable placeholder="选择公共 Prompt 模板" style="width: 100%;">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAgent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listAgentProfiles, createAgentProfile, updateAgentProfile, deleteAgentProfile, listPromptTemplates } from '@/api/platform';
import { listKnowledgeBases } from '@/api/kb';

const profiles = ref<any[]>([]);
const bases = ref<any[]>([]);
const templates = ref<any[]>([]);
const loading = ref(false);

const dialogVisible = ref(false);
const saving = ref(false);
const editingAgent = ref<any>(null);

const form = ref({
  name: '',
  description: '',
  persona_prompt: '',
  enabled_tools: [] as string[],
  default_corpus_ids: [] as string[],
  prompt_template_id: ''
});

const loadData = async () => {
  loading.value = true;
  try {
    const [profRes, basesRes, tempRes]: any = await Promise.all([
      listAgentProfiles(),
      listKnowledgeBases(),
      listPromptTemplates()
    ]);
    profiles.value = profRes.items || [];
    bases.value = basesRes.items || [];
    templates.value = tempRes.items || [];
  } finally {
    loading.value = false;
  }
};

const openCreateDialog = () => {
  editingAgent.value = null;
  form.value = {
    name: '',
    description: '',
    persona_prompt: '',
    enabled_tools: [],
    default_corpus_ids: [],
    prompt_template_id: ''
  };
  dialogVisible.value = true;
};

const openEditDialog = (agent: any) => {
  editingAgent.value = agent;
  form.value = {
    name: agent.name || '',
    description: agent.description || '',
    persona_prompt: agent.persona_prompt || '',
    enabled_tools: agent.enabled_tools || [],
    default_corpus_ids: agent.default_corpus_ids || [],
    prompt_template_id: agent.prompt_template_id || ''
  };
  dialogVisible.value = true;
};

const saveAgent = async () => {
  if (!form.value.name.trim()) {
    ElMessage.warning('名称不能为空');
    return;
  }
  saving.value = true;
  try {
    if (editingAgent.value) {
      await updateAgentProfile(editingAgent.value.id, form.value);
      ElMessage.success('更新成功');
    } else {
      await createAgentProfile(form.value);
      ElMessage.success('创建成功');
    }
    dialogVisible.value = false;
    loadData();
  } finally {
    saving.value = false;
  }
};

const deleteAgent = async (agent: any) => {
  try {
    await ElMessageBox.confirm('确定删除该智能体吗？', '删除确认', { type: 'warning' });
  } catch {
    return;
  }
  await deleteAgentProfile(agent.id);
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

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.agent-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: box-shadow var(--transition-base), border-color var(--transition-base);
}

.agent-card:hover {
  border-color: var(--blue-400);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

.agent-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.agent-avatar {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--blue-100);
  color: var(--blue-600);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
}

.agent-title-col {
  flex: 1;
  min-width: 0;
}

.agent-title-col h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-desc {
  font-size: 13px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.agent-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.agent-tag-row {
  display: flex;
  gap: 8px;
}

.agent-tools strong {
  font-size: 13px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 8px;
}

.tool-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.empty-text {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
