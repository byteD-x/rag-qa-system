<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="场景模板">
    </PageHeaderCompact>

    <div class="platform-content">
      <LoadingState v-if="loading" label="加载场景模板..." />

      <div v-else class="scene-grid">
        <div v-for="scene in scenes" :key="scene.key" class="scene-card surface-card" :class="{ active: activeScene === scene.key }">
          <div class="scene-header">
            <div class="scene-icon">{{ scene.icon }}</div>
            <div class="scene-info">
              <h3>{{ scene.name }}</h3>
              <span class="scene-desc">{{ scene.description }}</span>
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
            <el-button
              size="small"
              type="primary"
              :loading="applyingKey === scene.key"
              :disabled="!!applyingKey && applyingKey !== scene.key"
              @click="applyScene(scene)"
            >
              创建/更新 Agent Profile
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import LoadingState from '@/components/LoadingState.vue';
import { listAgentProfiles, updateAgentProfile } from '@/api/platform';
import { isHandledRequestError } from '@/api/request';

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
}

const loading = ref(false);
const activeScene = ref('');
const applyingKey = ref('');

const scenes = ref<SceneItem[]>([]);

// 请求场景模板（从后端 API 或使用内置定义作为 fallback）
const builtinScenes: SceneItem[] = [
  { key: 'enterprise_qa', name: '企业知识问答', description: '基于企业知识库的精准问答', icon: '🏢', system_prompt: '你是一个企业级知识助手...', recommended_tools: ['search_scope','search_corpus'], model_routing: 'grounded', model_tier: 'standard' },
  { key: 'tech_support', name: '技术支持助手', description: '步骤化技术问题排查', icon: '🔧', system_prompt: '你是一个资深技术支持工程师...', recommended_tools: ['search_scope','search_corpus'], model_routing: 'grounded', model_tier: 'standard' },
  { key: 'compliance_review', name: '合规审查助手', description: '逐条对照政策法规审查', icon: '⚖️', system_prompt: '你是一个企业合规审查专家...', recommended_tools: ['search_scope','search_corpus','calculator'], model_routing: 'grounded', model_tier: 'premium' },
  { key: 'training_coach', name: '培训教练', description: '苏格拉底式引导教学', icon: '🎓', system_prompt: '你是一个耐心且善于引导的企业培训教练...', recommended_tools: ['search_scope','list_scope_documents'], model_routing: 'common_knowledge', model_tier: 'standard' },
  { key: 'data_analyst', name: '数据分析助手', description: 'SQL生成与数据解读', icon: '📊', system_prompt: '你是一个数据分析专家...', recommended_tools: ['search_scope','search_corpus','calculator'], model_routing: 'agent', model_tier: 'premium' },
  { key: 'code_reviewer', name: '代码审查助手', description: '代码质量与安全审查', icon: '💻', system_prompt: '你是一个资深代码审查工程师...', recommended_tools: ['search_scope','calculator'], model_routing: 'agent', model_tier: 'premium' },
];

const tierLabel = (t: string) => ({ economy: '经济', standard: '标准', premium: '高级' })[t] || t;
const retrievalLabel = (p?: string) => ({ structure: '结构优先', full_text: '全文优先', vector: '向量优先', balanced: '均衡' })[p || ''] || p || '均衡';

const loadScenes = async () => {
  loading.value = true;
  try {
    // 尝试从后端加载，失败则用内置
    await listAgentProfiles().catch(() => ({}));
    scenes.value = builtinScenes;
  } finally {
    loading.value = false;
  }
};

const applyScene = async (scene: SceneItem) => {
  if (applyingKey.value) return;
  applyingKey.value = scene.key;
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
    ElMessage.success(`已按「${scene.name}」创建/更新 Agent Profile`);
  } catch (error) {
    if (!isHandledRequestError(error)) ElMessage.error('创建 Agent Profile 失败，请稍后重试');
  } finally {
    applyingKey.value = '';
  }
};

onMounted(() => { loadScenes(); });
</script>

<style scoped>
.platform-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.platform-content { flex: 1; overflow-y: auto; padding: 20px; background: var(--bg-panel-muted); }

.scene-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 18px; }

.scene-card { display: flex; flex-direction: column; gap: 14px; transition: border-color var(--transition-fast); }
@media (hover: hover) and (pointer: fine) {
  .scene-card:hover { border-color: var(--blue-500); }
}
.scene-card.active { border-color: var(--blue-500); box-shadow: var(--shadow-md); }

.scene-header { display: flex; gap: 12px; }
.scene-icon { font-size: var(--text-h1); flex-shrink: 0; width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; background: var(--bg-panel-muted); border-radius: var(--radius-md); }
.scene-info { flex: 1; min-width: 0; }
.scene-info h3 { margin: 0 0 4px 0; font-size: var(--text-body); color: var(--text-primary); }
.scene-desc { font-size: var(--text-caption); color: var(--text-secondary); }

.scene-meta { display: flex; flex-direction: column; gap: 8px; }
.meta-row { display: flex; align-items: center; gap: 8px; }
.meta-label { font-size: var(--text-caption); color: var(--text-muted); width: 64px; flex-shrink: 0; }
.tool-chips, .meta-chips { display: flex; gap: 4px; flex-wrap: wrap; }

.scene-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 8px; border-top: 1px solid var(--border-color); }
</style>
