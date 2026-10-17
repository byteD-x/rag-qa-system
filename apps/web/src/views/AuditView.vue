<template>
  <div class="page-shell audit-page">
    <PageHeaderCompact title="审计日志">
      <template #subtitle>
        <span class="audit-stats">{{ events.length }} 条</span>
        <span class="audit-stats muted">{{ deniedCount }} 拒绝</span>
        <span class="audit-stats muted">{{ failureCount }} 失败</span>
      </template>
    </PageHeaderCompact>

    <FilterBarSticky>
      <div class="filter-row">
        <el-select v-model="filters.service" clearable placeholder="服务" size="default" style="width: 140px">
          <el-option label="全部" value="" />
          <el-option label="网关" value="gateway" />
          <el-option label="知识库服务" value="kb-service" />
        </el-select>
        <el-select v-model="filters.outcome" clearable placeholder="结果" size="default" style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="成功" value="success" />
          <el-option label="拒绝" value="denied" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button
          text
          type="primary"
          size="default"
          :aria-expanded="showAdvancedFilters"
          @click="showAdvancedFilters = !showAdvancedFilters"
        >
          {{ advancedToggleLabel }}
        </el-button>
        <el-button type="primary" :loading="loading" size="default" @click="loadAuditEvents">查询</el-button>
        <el-button plain size="default" @click="resetFilters">重置</el-button>
      </div>
      <div v-if="showAdvancedFilters" class="filter-row">
        <el-input v-model="filters.actor_user_id" placeholder="用户 ID" clearable size="default" style="width: 140px" />
        <el-input v-model="filters.action" placeholder="动作" clearable size="default" style="width: 160px" />
        <el-input v-model="filters.resource_type" placeholder="资源类型" clearable size="default" style="width: 120px" />
        <el-input v-model="filters.resource_id" placeholder="资源 ID" clearable size="default" style="width: 140px" />
      </div>
    </FilterBarSticky>

    <p v-if="rangeHint" class="audit-range-hint">{{ rangeHint }}</p>

    <div class="table-wrapper">
      <EnhancedEmpty
        v-if="loadError"
        variant="question"
        title="审计日志加载失败"
        description="后端暂时不可用，请点「查询」重试"
        class="audit-empty"
      />
      <EnhancedEmpty
        v-else-if="!events.length && !loading"
        variant="search"
        title="暂无审计事件"
        description="符合条件的审计记录将在此展示"
        class="audit-empty"
      />
      <el-table v-else :data="events" stripe size="default" class="audit-table">
        <el-table-column prop="created_at" label="时间" min-width="160" />
        <el-table-column prop="service" label="服务" min-width="100">
          <template #default="{ row }">
            {{ row.service === 'gateway' ? '网关' : row.service === 'kb-service' ? '知识库服务' : row.service || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" min-width="150" show-overflow-tooltip />
        <el-table-column prop="resource_type" label="资源类型" min-width="100" />
        <el-table-column prop="resource_id" label="资源 ID" min-width="140" show-overflow-tooltip />
        <el-table-column prop="actor_email" label="操作者" min-width="150" show-overflow-tooltip />
        <el-table-column prop="actor_role" label="角色" min-width="100" />
        <el-table-column prop="outcome" label="结果" min-width="80">
          <template #default="{ row }">
            <el-tag :type="outcomeTagType(row.outcome)" effect="plain" size="small">{{ outcomeLabel(row.outcome) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trace_id" label="追踪 ID" min-width="140" show-overflow-tooltip />
        <el-table-column label="" width="70" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openDetailDrawer(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer
      v-model="detailDrawerVisible"
      title="事件详情"
      size="420px"
      destroy-on-close
    >
      <JsonPreview v-if="selectedEvent" :value="selectedEvent.details" empty="该事件没有附加详情" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { listAuditEvents } from '@/api/audit';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import FilterBarSticky from '@/components/FilterBarSticky.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import JsonPreview from '@/components/JsonPreview.vue';

const PAGE_LIMIT = 50;

const loading = ref(false);
const loadError = ref(false);
const rangeHint = ref('');
const events = ref<any[]>([]);
const showAdvancedFilters = ref(false);
const detailDrawerVisible = ref(false);
const selectedEvent = ref<any | null>(null);

const filters = reactive({
  service: '',
  actor_user_id: '',
  resource_type: '',
  resource_id: '',
  action: '',
  outcome: ''
});

const advancedFilterCount = computed(() => [
  filters.actor_user_id,
  filters.action,
  filters.resource_type,
  filters.resource_id
].filter(Boolean).length);

const advancedToggleLabel = computed(() => {
  if (showAdvancedFilters.value) return '收起高级筛选';
  return advancedFilterCount.value ? `高级筛选 (${advancedFilterCount.value})` : '高级筛选';
});

const deniedCount = computed(() => events.value.filter((e) => e.outcome === 'denied').length);
const failureCount = computed(() => events.value.filter((e) => e.outcome === 'failed').length);

const loadAuditEvents = async () => {
  loading.value = true;
  loadError.value = false;
  try {
    const result: any = await listAuditEvents({
      ...filters,
      limit: PAGE_LIMIT,
      offset: 0
    });
    const items = Array.isArray(result.items) ? result.items : [];
    const limit = Number(result.pagination?.limit) || PAGE_LIMIT;
    events.value = items;
    rangeHint.value = items.length >= limit
      ? `已加载 ${items.length} 条（单次上限 ${limit} 条），可能还有更多记录，请用筛选条件缩小范围`
      : '';
  } catch {
    events.value = [];
    rangeHint.value = '';
    loadError.value = true;
  } finally {
    loading.value = false;
  }
};

const resetFilters = async () => {
  filters.service = '';
  filters.actor_user_id = '';
  filters.resource_type = '';
  filters.resource_id = '';
  filters.action = '';
  filters.outcome = '';
  await loadAuditEvents();
};

const outcomeTagType = (outcome: string) => {
  if (outcome === 'success') return 'success';
  if (outcome === 'denied') return 'warning';
  if (outcome === 'failed') return 'danger';
  return 'info';
};

const outcomeLabel = (outcome: string) => {
  if (outcome === 'success') return '成功';
  if (outcome === 'denied') return '拒绝';
  if (outcome === 'failed') return '失败';
  return outcome || '—';
};

const openDetailDrawer = (row: any) => {
  selectedEvent.value = row;
  detailDrawerVisible.value = true;
};

onMounted(() => void loadAuditEvents());
</script>

<style scoped>
.audit-page {
  gap: var(--content-gap, 20px);
  overflow: hidden;
}

.audit-stats {
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-secondary);
  margin-right: 14px;
  font-weight: 500;
}

.audit-stats.muted {
  color: var(--text-muted);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.filter-row + .filter-row {
  margin-top: 12px;
}

.audit-range-hint {
  margin: 0;
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-secondary);
}

.table-wrapper {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.audit-empty {
  padding: 48px 24px !important;
}

.audit-table {
  border-radius: var(--radius-sm);
}

@media (max-width: 640px) {
  .audit-stats {
    margin-right: 8px;
  }

  :deep(.page-header-compact__main) {
    flex-wrap: wrap;
  }

  :deep(.page-header-compact__subtitle) {
    width: 100%;
  }
}
</style>
