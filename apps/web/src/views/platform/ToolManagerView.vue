<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="工具管理">
      <template #actions>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 分类 Tab -->
      <el-tabs v-model="activeCategory" @tab-change="handleCategoryChange">
        <el-tab-pane label="全部" name="" />
        <el-tab-pane v-for="cat in categories" :key="cat" :label="cat" :name="cat" />
      </el-tabs>

      <LoadingState v-if="loading && !tools.length" label="加载工具列表..." />

      <EnhancedEmpty
        v-else-if="!tools.length"
        variant="document"
        title="暂无工具"
        description="Agent工具将在首次使用时自动注册"
      />

      <div v-else class="tool-grid" v-loading="loading">
        <div v-for="tool in tools" :key="tool.name" class="tool-card">
          <div class="tool-header">
            <div class="tool-icon" :style="{ background: categoryColor(tool.category) }">
              {{ toolIcon(tool.category) }}
            </div>
            <div class="tool-info">
              <h3>{{ tool.name }}</h3>
              <span class="tool-cat">{{ tool.category }}</span>
            </div>
            <el-switch
              v-model="tool.enabled"
              @change="toggleTool(tool)"
              :loading="tool._toggling"
              size="small"
            />
          </div>
          <div class="tool-body">
            <p class="tool-desc">{{ tool.description }}</p>
          </div>
          <div class="tool-footer">
            <div class="tool-stats">
              <div class="tool-stat">
                <span class="stat-num">{{ tool.total_calls }}</span>
                <span class="stat-lbl">调用次数</span>
              </div>
              <div class="tool-stat">
                <span class="stat-num">{{ (tool.success_rate * 100).toFixed(0) }}%</span>
                <span class="stat-lbl">成功率</span>
              </div>
              <div class="tool-stat">
                <span class="stat-num">{{ tool.avg_duration_ms.toFixed(0) }}ms</span>
                <span class="stat-lbl">平均耗时</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { getToolRegistrySummary, listAgentTools, toggleAgentTool } from '@/api/platform';

interface ToolItem {
  name: string;
  category: string;
  description: string;
  enabled: boolean;
  total_calls: number;
  success_rate: number;
  avg_duration_ms: number;
  _toggling?: boolean;
}

const tools = ref<ToolItem[]>([]);
const loading = ref(false);
const activeCategory = ref('');
const categories = ref<string[]>([]);

const loadData = async () => {
  loading.value = true;
  try {
    const [summaryRes, toolsRes]: any = await Promise.all([
      getToolRegistrySummary(),
      listAgentTools(activeCategory.value ? { category: activeCategory.value } : undefined),
    ]);
    tools.value = (toolsRes.items || []).map((t: any) => ({ ...t, _toggling: false }));
    categories.value = Object.keys(summaryRes?.tools
      ? [...new Set(Object.values(summaryRes.tools).map((t: any) => t.category))]
      : []);
  } finally {
    loading.value = false;
  }
};

const handleCategoryChange = () => {
  loadData();
};

const toggleTool = async (tool: ToolItem) => {
  tool._toggling = true;
  try {
    await toggleAgentTool(tool.name, tool.enabled);
    ElMessage.success(`${tool.name} 已${tool.enabled ? '启用' : '停用'}`);
  } catch {
    tool.enabled = !tool.enabled;
  } finally {
    tool._toggling = false;
  }
};

const categoryColor = (cat: string) => {
  const colors: Record<string, string> = {
    search: 'var(--blue-50)', compute: 'var(--blue-50)', external: 'var(--el-color-warning-light-9)',
    system: 'var(--el-color-success-light-9)', general: 'var(--bg-panel-muted)',
  };
  return colors[cat] || colors.general;
};

const toolIcon = (cat: string) => {
  const icons: Record<string, string> = {
    search: '🔍', compute: '🧮', external: '🔗', system: '⚙️', general: '🔧',
  };
  return icons[cat] || '🔧';
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

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.tool-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tool-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-h2);
  flex-shrink: 0;
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-info h3 {
  margin: 0;
  font-size: var(--text-body);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-cat {
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.tool-body {
  flex: 1;
}

.tool-desc {
  font-size: var(--text-caption);
  color: var(--text-secondary);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tool-footer {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.tool-stats {
  display: flex;
  gap: 16px;
}

.tool-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-num {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.stat-lbl {
  font-size: var(--text-caption);
  color: var(--text-muted);
}
</style>
