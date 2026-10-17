<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="Agent 工作台">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">创建智能体</el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <LoadingState v-if="loading" label="加载智能体中..." />

      <EnhancedEmpty
        v-else-if="loadError"
        variant="question"
        title="加载失败"
        description="智能体列表加载失败，请稍后重试"
      >
        <template #actions>
          <el-button type="primary" @click="loadData()">重试</el-button>
        </template>
      </EnhancedEmpty>

      <EnhancedEmpty
        v-else-if="!profiles.length"
        variant="document"
        title="暂无智能体"
      >
        <template #actions>
          <el-button type="primary" @click="openCreateDialog">创建智能体</el-button>
        </template>
      </EnhancedEmpty>

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
              <el-button plain size="small" type="danger" :loading="deletingId === agent.id" @click="deleteAgent(agent)">删除</el-button>
            </div>
          </div>
          <div class="agent-body" v-if="hasFacts(agent)">
            <div class="agent-tag-row">
              <el-tag v-for="tool in agent.enabled_tools" :key="tool" size="small" type="info">{{ toolLabel(tool) }}</el-tag>
              <el-tag v-for="corpusId in agent.default_corpus_ids" :key="corpusId" size="small" type="success" effect="plain">{{ kbLabel(corpusId) }}</el-tag>
              <el-tag v-if="promptLabel(agent)" size="small" effect="plain">{{ promptLabel(agent) }}</el-tag>
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
            <el-option v-for="tool in TOOL_OPTIONS" :key="tool.value" :label="`${tool.label} (${tool.value})`" :value="tool.value" />
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
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { listAgentProfiles, createAgentProfile, updateAgentProfile, deleteAgentProfile, listPromptTemplates } from '@/api/platform';
import { listKnowledgeBases } from '@/api/kb';

const profiles = ref<any[]>([]);
const bases = ref<any[]>([]);
const templates = ref<any[]>([]);
const loading = ref(false);
const loadError = ref(false);

const dialogVisible = ref(false);
const saving = ref(false);
const deletingId = ref('');
const editingAgent = ref<any>(null);

const TOOL_OPTIONS = [
  { value: 'search_scope', label: '搜索作用域' },
  { value: 'search_corpus', label: '搜索语料库' },
  { value: 'calculator', label: '计算器' },
  { value: 'list_scope_documents', label: '列出文档' }
];

const toolLabel = (tool: string) => TOOL_OPTIONS.find((item) => item.value === tool)?.label || tool;

const kbLabel = (corpusId: string) =>
  bases.value.find((base: any) => base.id === corpusId || `kb:${base.id}` === corpusId)?.name || corpusId;

const promptLabel = (agent: any) =>
  agent.prompt_template?.name || templates.value.find((tpl: any) => tpl.id === agent.prompt_template_id)?.name || '';

const hasFacts = (agent: any) =>
  Boolean(agent.enabled_tools?.length || agent.default_corpus_ids?.length || promptLabel(agent));

const form = ref({
  name: '',
  description: '',
  persona_prompt: '',
  enabled_tools: [] as string[],
  default_corpus_ids: [] as string[],
  prompt_template_id: ''
});

const loadData = async (silent = false) => {
  if (!silent) {
    loading.value = true;
    loadError.value = false;
  }
  try {
    const [profRes, basesRes, tempRes]: any = await Promise.all([
      listAgentProfiles(),
      listKnowledgeBases(),
      listPromptTemplates()
    ]);
    profiles.value = profRes.items || [];
    bases.value = basesRes.items || [];
    templates.value = tempRes.items || [];
  } catch {
    if (!silent) loadError.value = true;
  } finally {
    if (!silent) loading.value = false;
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
    loadData(true);
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
  deletingId.value = agent.id;
  try {
    await deleteAgentProfile(agent.id);
    ElMessage.success('已删除');
    await loadData(true);
  } finally {
    deletingId.value = '';
  }
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
}

.agent-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.agent-avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--blue-50);
  color: var(--blue-600);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-h2);
  font-weight: bold;
}

.agent-title-col {
  flex: 1;
  min-width: 0;
}

.agent-title-col h3 {
  margin: 0 0 4px 0;
  font-size: var(--text-body);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-desc {
  font-size: var(--text-caption);
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
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.agent-tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

</style>
