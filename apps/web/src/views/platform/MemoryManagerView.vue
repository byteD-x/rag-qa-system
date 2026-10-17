<template>
  <div class="page-shell platform-page">
    <PageHeaderCompact title="记忆管理">
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
        <div class="stat-card surface-card">
          <div class="stat-value metric-value">{{ memoryStats?.total_entries || 0 }}</div>
          <div class="stat-label metric-label">总记忆条目</div>
        </div>
        <div class="stat-card surface-card">
          <div class="stat-value metric-value">{{ memoryStats?.active_entries || 0 }}</div>
          <div class="stat-label metric-label">活跃记忆</div>
        </div>
        <div class="stat-card surface-card" v-for="(count, type) in memoryStats?.by_type || {}" :key="type">
          <div class="stat-value metric-value">{{ count }}</div>
          <div class="stat-label metric-label">{{ typeLabel(type) }}</div>
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

      <LoadingState v-if="loading && !memories.length" label="加载记忆..." />

      <EnhancedEmpty
        v-else-if="!memories.length"
        variant="document"
        title="暂无记忆"
        description="Agent将在对话中自动提取有价值的用户偏好和事实信息"
      />

      <div v-else class="memory-table-wrapper">
        <el-table :data="memories" v-loading="loading" size="small" style="width: 100%" stripe>
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
              <span class="confidence-text">{{ (row.confidence * 100).toFixed(0) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="75" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.is_active ? 'success' : 'info'"
                :class="{ 'state-flash': flashId === row.id }"
                size="small"
                effect="dark"
              >
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
            </template>
          </el-table-column>
        </el-table>

        <!-- 搜索结果上限 50 条且 total 为返回行数，搜索态翻页会落到未过滤数据，故隐藏 -->
        <div v-if="!searchActive" class="pagination-row">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Refresh, Search } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { listMemoryEntries, searchMemoryEntries, deactivateMemory, getMemoryStats, type MemoryStats } from '@/api/platform';
import { isHandledRequestError } from '@/api/request';

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
const searchActive = ref(false);
const flashId = ref('');
let flashTimer: number | undefined;

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
  searchActive.value = false;
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
    searchActive.value = true;
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
    flashId.value = memory.id;
    window.clearTimeout(flashTimer);
    flashTimer = window.setTimeout(() => { flashId.value = ''; }, 200);
    ElMessage.success('已停用');
  } catch (error) {
    if (!isHandledRequestError(error)) ElMessage.error('停用失败');
  }
};

onMounted(() => {
  loadData();
});

onUnmounted(() => {
  window.clearTimeout(flashTimer);
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

/* 容器/数字/标签统一走 style.css 的 .surface-card / .metric-value / .metric-label，
   这里只保留本页差异项：居中、紧凑内边距、数字主色、标签上间距。 */
.stat-card {
  padding: 14px;
  text-align: center;
}

.stat-value {
  color: var(--blue-600);
}

.stat-label {
  margin-top: 2px;
}

.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
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

.confidence-text {
  color: var(--text-muted);
  font-size: var(--text-caption);
}

/* 停用成功后就地强调该行状态一次（可被下一次操作打断） */
.state-flash {
  opacity: 0.45;
  transition: opacity var(--transition-fast);
}

.pagination-row {
  display: flex;
  justify-content: center;
  padding: 16px;
}
</style>
