<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="场景模板库" subtitle="预制的多场景Agent行为配置，一键切换回答模式">
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 标签筛选 -->
      <div class="tag-bar">
        <el-tag
          v-for="tag in allTags"
          :key="tag"
          :type="activeTag === tag ? 'primary' : 'info'"
          :effect="activeTag === tag ? 'dark' : 'plain'"
          @click="activeTag = activeTag === tag ? '' : tag"
          style="cursor: pointer; margin-right: 8px;"
        >
          {{ tag }}
        </el-tag>
        <el-button text size="small" v-if="activeTag" @click="activeTag = ''">清除筛选</el-button>
      </div>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载场景模板...</span>
      </div>

      <div v-else class="scene-grid">
        <div v-for="scene in filteredScenes" :key="scene.key" class="scene-card" :class="{ active: activeScene === scene.key }">
          <div class="scene-header">
            <div class="scene-icon">{{ scene.icon }}</div>
            <div class="scene-info">
              <h3>{{ scene.name }}</h3>
              <span class="scene-desc">{{ scene.description }}</span>
            </div>
          </div>

          <div class="scene-body">
            <div class="scene-prompt-preview">
              {{ truncate(scene.system_prompt, 180) }}
            </div>
          </div>

          <div class="scene-meta">
            <div class="meta-row">
              <span class="meta-label">推荐工具</span>
              <div class="tool-chips">
                <el-tag v-for="t in scene.recommended_tools" :key="t" size="small" type="info">{{ t }}</el-tag>
              </div>
            </div>
            <div class="meta-row">
              <span class="meta-label">模型策略</span>
              <div class="meta-chips">
                <el-tag size="small" effect="plain">{{ scene.model_routing }}</el-tag>
                <el-tag size="small" :type="scene.model_tier === 'premium' ? 'warning' : scene.model_tier === 'economy' ? 'success' : 'info'" effect="plain">
                  {{ tierLabel(scene.model_tier) }}
                </el-tag>
              </div>
            </div>
            <div class="meta-row">
              <span class="meta-label">检索偏好</span>
              <el-tag size="small" effect="plain">{{ retrievalLabel(scene.retrieval_preference) }}</el-tag>
            </div>
          </div>

          <div class="scene-footer">
            <el-button size="small" @click="previewScene(scene)">预览 Prompt</el-button>
            <el-button size="small" type="primary" @click="applyScene(scene)">
              应用此场景
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 预览对话框 -->
    <el-dialog v-model="previewVisible" title="场景 Prompt 预览" width="600px">
      <div class="preview-content">
        <div class="preview-header">
          <span class="preview-icon">{{ previewSceneData?.icon }}</span>
          <strong>{{ previewSceneData?.name }}</strong>
        </div>
        <pre class="preview-text">{{ previewSceneData?.system_prompt }}</pre>
        <div class="preview-meta" v-if="previewSceneData">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="模型路由">{{ previewSceneData.model_routing }}</el-descriptions-item>
            <el-descriptions-item label="模型层级">{{ tierLabel(previewSceneData.model_tier) }}</el-descriptions-item>
            <el-descriptions-item label="检索偏好">{{ retrievalLabel(previewSceneData.retrieval_preference) }}</el-descriptions-item>
            <el-descriptions-item label="推荐工具">{{ previewSceneData.recommended_tools.join(', ') }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listAgentProfiles, updateAgentProfile } from '@/api/platform';

interface SceneItem {
  key: string;
  name: string;
  description: string;
  icon: string;
  system_prompt: string;
  recommended_tools: string[];
  retrieval_preference?: string;
  model_routing: string;
  model_tier: string;
  tags: string[];
}

const loading = ref(false);
const activeTag = ref('');
const activeScene = ref('');
const previewVisible = ref(false);
const previewSceneData = ref<SceneItem | null>(null);

const scenes = ref<SceneItem[]>([]);

// 请求场景模板（从后端 API 或使用内置定义作为 fallback）
const builtinScenes: SceneItem[] = [
  { key: 'enterprise_qa', name: '企业知识问答', description: '基于企业知识库的精准问答', icon: '🏢', system_prompt: '你是一个企业级知识助手...', recommended_tools: ['search_scope','search_corpus'], model_routing: 'grounded', model_tier: 'standard', tags: ['qa','enterprise'] },
  { key: 'tech_support', name: '技术支持助手', description: '步骤化技术问题排查', icon: '🔧', system_prompt: '你是一个资深技术支持工程师...', recommended_tools: ['search_scope','search_corpus'], model_routing: 'grounded', model_tier: 'standard', tags: ['tech','support'] },
  { key: 'compliance_review', name: '合规审查助手', description: '逐条对照政策法规审查', icon: '⚖️', system_prompt: '你是一个企业合规审查专家...', recommended_tools: ['search_scope','search_corpus','calculator'], model_routing: 'grounded', model_tier: 'premium', tags: ['compliance','legal'] },
  { key: 'training_coach', name: '培训教练', description: '苏格拉底式引导教学', icon: '🎓', system_prompt: '你是一个耐心且善于引导的企业培训教练...', recommended_tools: ['search_scope','list_scope_documents'], model_routing: 'common_knowledge', model_tier: 'standard', tags: ['training','education'] },
  { key: 'data_analyst', name: '数据分析助手', description: 'SQL生成与数据解读', icon: '📊', system_prompt: '你是一个数据分析专家...', recommended_tools: ['search_scope','search_corpus','calculator'], model_routing: 'agent', model_tier: 'premium', tags: ['data','analytics'] },
  { key: 'code_reviewer', name: '代码审查助手', description: '代码质量与安全审查', icon: '💻', system_prompt: '你是一个资深代码审查工程师...', recommended_tools: ['search_scope','calculator'], model_routing: 'agent', model_tier: 'premium', tags: ['code','review'] },
];

const allTags = computed(() => {
  const tags = new Set<string>();
  scenes.value.forEach(s => s.tags.forEach(t => tags.add(t)));
  return Array.from(tags).sort();
});

const filteredScenes = computed(() => {
  if (!activeTag.value) return scenes.value;
  return scenes.value.filter(s => s.tags.includes(activeTag.value));
});

const tierLabel = (t: string) => ({ economy: '经济', standard: '标准', premium: '高级' })[t] || t;
const retrievalLabel = (p: string) => ({ structure: '结构优先', full_text: '全文优先', vector: '向量优先', balanced: '均衡' })[p] || p;
const truncate = (text: string, max: number) => text.length > max ? text.slice(0, max) + '...' : text;

const loadScenes = async () => {
  loading.value = true;
  try {
    // 尝试从后端加载，失败则用内置
    const res: any = await listAgentProfiles().catch(() => ({}));
    scenes.value = builtinScenes;
  } finally {
    loading.value = false;
  }
};

const previewScene = (scene: SceneItem) => {
  previewSceneData.value = scene;
  previewVisible.value = true;
};

const applyScene = async (scene: SceneItem) => {
  try {
    // 创建或更新 Agent Profile 以应用场景
    await updateAgentProfile('default', {
      scene_template_key: scene.key,
      name: scene.name,
    }).catch(async () => {
      const { createAgentProfile } = await import('@/api/platform');
      await createAgentProfile({
        name: scene.name,
        persona_prompt: scene.system_prompt,
        enabled_tools: scene.recommended_tools,
      });
    });
    activeScene.value = scene.key;
    ElMessage.success(`已应用场景「${scene.name}」`);
  } catch {
    ElMessage.warning('请先创建 Agent Profile 后再绑定场景');
  }
};

onMounted(() => { loadScenes(); });
</script>

<style scoped>
.platform-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.platform-content { flex: 1; overflow-y: auto; padding: 20px; background: var(--bg-panel-muted); }

.tag-bar { margin-bottom: 18px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 48px; color: var(--text-muted); }

.scene-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 18px; }

.scene-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 20px; display: flex; flex-direction: column; gap: 14px; transition: border-color var(--transition-base), box-shadow var(--transition-base); }
.scene-card:hover { border-color: var(--blue-400); box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
.scene-card.active { border-color: var(--blue-500); box-shadow: 0 2px 12px rgba(59,130,246,0.2); }

.scene-header { display: flex; gap: 12px; }
.scene-icon { font-size: 32px; flex-shrink: 0; width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; background: var(--bg-panel-muted); border-radius: 12px; }
.scene-info { flex: 1; min-width: 0; }
.scene-info h3 { margin: 0 0 4px 0; font-size: 16px; color: var(--text-primary); }
.scene-desc { font-size: 13px; color: var(--text-secondary); }

.scene-prompt-preview { font-size: 12px; color: var(--text-muted); background: var(--bg-panel-muted); border-radius: var(--radius-sm); padding: 10px 12px; line-height: 1.5; font-style: italic; }

.scene-meta { display: flex; flex-direction: column; gap: 8px; }
.meta-row { display: flex; align-items: center; gap: 8px; }
.meta-label { font-size: 12px; color: var(--text-muted); width: 64px; flex-shrink: 0; }
.tool-chips, .meta-chips { display: flex; gap: 4px; flex-wrap: wrap; }

.scene-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 8px; border-top: 1px solid var(--border-color); }

.preview-content { display: flex; flex-direction: column; gap: 14px; }
.preview-header { display: flex; align-items: center; gap: 8px; font-size: 16px; }
.preview-icon { font-size: 28px; }
.preview-text { background: var(--bg-panel-muted); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; margin: 0; max-height: 300px; overflow-y: auto; }
</style>
