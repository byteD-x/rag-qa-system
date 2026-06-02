<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="工具注册中心" subtitle="管理Agent工具注册、启停、MCP服务接入与执行统计">
      <template #actions>
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeaderCompact>

    <div class="platform-content">
      <!-- 统计概览 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value">{{ summary?.registered_tools || 0 }}</div>
          <div class="stat-label">已注册工具</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary?.categories || 0 }}</div>
          <div class="stat-label">工具类别</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary?.mcp_servers || 0 }}</div>
          <div class="stat-label">MCP服务</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary?.cache_entries || 0 }}</div>
          <div class="stat-label">缓存条目</div>
        </div>
      </div>

      <!-- 分类 Tab -->
      <el-tabs v-model="activeCategory" @tab-change="handleCategoryChange">
        <el-tab-pane label="全部" name="" />
        <el-tab-pane v-for="cat in categories" :key="cat" :label="cat" :name="cat" />
      </el-tabs>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载工具列表...</span>
      </div>

      <EnhancedEmpty
        v-else-if="!tools.length"
        variant="document"
        title="暂无工具"
        description="Agent工具将在首次使用时自动注册"
      />

      <div v-else class="tool-grid">
        <div v-for="tool in tools" :key="tool.name" class="tool-card">
          <div class="tool-header">
            <div class="tool-icon" :style="{ background: categoryColor(tool.category) }">
              {{ toolIcon(tool.category) }}
            </div>
            <div class="tool-info">
              <div class="tool-name-row">
                <h3>{{ tool.name }}</h3>
                <el-tag :type="tool.enabled ? 'success' : 'danger'" size="small" effect="dark">
                  {{ tool.enabled ? '已启用' : '已停用' }}
                </el-tag>
              </div>
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
import { Loading, Refresh } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { getToolRegistrySummary, listAgentTools, toggleAgentTool, type ToolRegistrySummary } from '@/api/platform';

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
const summary = ref<ToolRegistrySummary | null>(null);
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
    summary.value = summaryRes;
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
    search: '#e6f4ff', compute: '#f0f5ff', external: '#fff7e6',
    system: '#f6ffed', general: '#f5f5f5',
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

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--blue-600);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
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
  transition: border-color var(--transition-base);
}

.tool-card:hover {
  border-color: var(--blue-400);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tool-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-name-row h3 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-cat {
  font-size: 11px;
  color: var(--text-muted);
}

.tool-body {
  flex: 1;
}

.tool-desc {
  font-size: 13px;
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
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-lbl {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
