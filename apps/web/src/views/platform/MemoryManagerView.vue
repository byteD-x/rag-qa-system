<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="记忆管理" subtitle="浏览和管理Agent从对话中提取的长期记忆与用户偏好">
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
          <div class="stat-value">{{ memoryStats?.total_entries || 0 }}</div>
          <div class="stat-label">总记忆条目</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ memoryStats?.active_entries || 0 }}</div>
          <div class="stat-label">活跃记忆</div>
        </div>
        <div class="stat-card" v-for="(count, type) in memoryStats?.by_type || {}" :key="type">
          <div class="stat-value">{{ count }}</div>
          <div class="stat-label">{{ typeLabel(type) }}</div>
        </div>
      </div>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="搜索记忆... (按主体/内容语义检索)"
          clearable
          @keyup.enter="doSearch"
          @clear="loadMemories"
          style="flex: 1;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="typeFilter" placeholder="记忆类型" clearable @change="loadMemories" style="width: 140px;">
          <el-option label="全部" value="" />
          <el-option label="偏好" value="preference" />
          <el-option label="事实" value="fact" />
          <el-option label="知识" value="knowledge" />
        </el-select>
        <el-button type="primary" @click="doSearch" :loading="searching">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载记忆...</span>
      </div>

      <EnhancedEmpty
        v-else-if="!memories.length"
        variant="document"
        title="暂无记忆"
        description="Agent将在对话中自动提取有价值的用户偏好和事实信息"
      />

      <div v-else class="memory-table-wrapper">
        <el-table :data="memories" size="small" style="width: 100%" stripe>
          <el-table-column prop="memory_type" label="类型" width="85">
            <template #default="{ row }">
              <el-tag :type="typeTag(row.memory_type)" size="small" effect="plain">
                {{ typeLabel(row.memory_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="subject" label="主体" width="140" show-overflow-tooltip />
          <el-table-column prop="predicate" label="关系" width="120" show-overflow-tooltip />
          <el-table-column prop="object" label="内容" show-overflow-tooltip>
            <template #default="{ row }">
              <span :class="{ 'inactive-text': !row.is_active }">{{ row.object }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="confidence" label="置信度" width="90" align="center">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.confidence * 100)"
                :color="row.confidence >= 0.8 ? '#67c23a' : row.confidence >= 0.5 ? '#e6a23c' : '#f56c6c'"
                :stroke-width="6"
                :show-text="false"
              />
              <span style="font-size: 11px; color: var(--text-muted);">{{ (row.confidence * 100).toFixed(0) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="75" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="dark">
                {{ row.is_active ? '活跃' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="155">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.is_active"
                text
                type="danger"
                size="small"
                @click="deactivate(row)"
              >
                停用
              </el-button>
              <span v-else class="inactive-text" style="font-size:12px;">已停用</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-row">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            @current-change="loadMemories"
            small
          />
        </div>
      </div>

      <!-- 高频主体 -->
      <div v-if="memoryStats?.top_subjects?.length" class="section-header" style="margin-top: 28px;">
        <h3>高频记忆主体</h3>
      </div>
      <div v-if="memoryStats?.top_subjects?.length" class="top-subjects">
        <div v-for="subj in memoryStats.top_subjects.slice(0, 10)" :key="subj.subject" class="subject-chip">
          <span class="subject-name">{{ subj.subject }}</span>
          <span class="subject-count">{{ subj.count }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading, Refresh, Search } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listMemoryEntries, searchMemoryEntries, deactivateMemory, getMemoryStats, type MemoryStats } from '@/api/platform';

interface MemoryRow {
  id: string;
  user_id: string;
  memory_type: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  source_session_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const memories = ref<MemoryRow[]>([]);
const memoryStats = ref<MemoryStats | null>(null);
const loading = ref(false);
const searching = ref(false);
const searchQuery = ref('');
const typeFilter = ref('');
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

const typeLabel = (type: string) => {
  const map: Record<string, string> = { preference: '偏好', fact: '事实', knowledge: '知识' };
  return map[type] || type;
};

const typeTag = (type: string) => {
  const map: Record<string, string> = { preference: 'warning', fact: 'primary', knowledge: 'success' };
  return map[type] || 'info';
};

const formatTime = (ts: string) => {
  if (!ts) return '-';
  return new Date(ts).toLocaleString('zh-CN');
};

const loadData = async () => {
  await Promise.all([loadMemories(), loadStats()]);
};

const loadMemories = async () => {
  loading.value = true;
  try {
    const params: any = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    };
    if (typeFilter.value) params.memory_type = typeFilter.value;
    const res: any = await listMemoryEntries(params);
    memories.value = res.items || [];
    total.value = res.total || 0;
  } finally {
    loading.value = false;
  }
};

const loadStats = async () => {
  try {
    const res: any = await getMemoryStats();
    memoryStats.value = res;
  } catch { /* 静默 */ }
};

const doSearch = async () => {
  if (!searchQuery.value.trim()) {
    await loadMemories();
    return;
  }
  searching.value = true;
  try {
    const params: any = { query: searchQuery.value.trim(), limit: 50 };
    if (typeFilter.value) params.memory_type = typeFilter.value;
    const res: any = await searchMemoryEntries(params);
    memories.value = res.items || [];
    total.value = res.total || 0;
  } finally {
    searching.value = false;
  }
};

const deactivate = async (memory: MemoryRow) => {
  try {
    await ElMessageBox.confirm(`确定停用这条记忆吗？\n"${memory.subject} ${memory.predicate} ${memory.object}"`, '停用确认', { type: 'warning' });
  } catch {
    return;
  }
  try {
    await deactivateMemory(memory.id);
    memory.is_active = false;
    ElMessage.success('已停用');
  } catch {
    ElMessage.error('停用失败');
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

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 14px;
  text-align: center;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--blue-600);
}

.stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
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

.memory-table-wrapper {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.inactive-text {
  color: var(--text-muted);
  font-style: italic;
}

.pagination-row {
  display: flex;
  justify-content: center;
  padding: 16px;
}

.section-header {
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
}

.top-subjects {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.subject-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 13px;
}

.subject-name {
  color: var(--text-primary);
}

.subject-count {
  background: var(--blue-100);
  color: var(--blue-600);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
}
</style>
