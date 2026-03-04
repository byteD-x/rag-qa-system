<template>
  <div class="corpora-list-view">
    <div class="page-header">
      <h2>知识库管理</h2>
      <div class="toolbar-actions">
        <el-button icon="Refresh" @click="fetchData" class="action-btn">刷新</el-button>
        <el-button
          type="danger"
          icon="Delete"
          :disabled="selectedRows.length === 0"
          @click="handleBatchDelete"
          class="action-btn"
        >
          批量删除
        </el-button>
        <el-button type="primary" icon="Plus" @click="handleCreate" class="new-corpus-btn">
          新建知识库
        </el-button>
      </div>
    </div>

    <el-table
      ref="tableRef"
      :data="tableData"
      v-loading="loading"
      style="width: 100%; margin-top: 20px;"
      row-key="id"
      class="custom-table"
      @selection-change="handleSelectionChange"
      @row-click="handleRowClick"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column prop="id" label="ID" width="300" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" />
      <el-table-column prop="created_at" label="创建时间" width="200" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="scope">
          <el-button type="primary" link @click="goDetail(scope.row.id)" size="small">管理文档</el-button>
          <el-button type="danger" link @click="handleDelete(scope.row)" size="small">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <CreateCorpusModal ref="createModalRef" @success="fetchData" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getCorpora, deleteCorpus, batchDeleteCorpora } from '@/api/corpora';
import type { Corpus } from '@/api/types';
import CreateCorpusModal from '@/components/CreateCorpusModal.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const router = useRouter();
const loading = ref(false);
const tableData = ref<Corpus[]>([]);
const selectedRows = ref<Corpus[]>([]);
const createModalRef = ref();
const tableRef = ref();

const fetchData = async () => {
  loading.value = true;
  try {
    const res: any = await getCorpora();
    if (res.items) {
      tableData.value = res.items;
    } else {
      tableData.value = res; 
    }
    selectedRows.value = [];
  } finally {
    loading.value = false;
  }
};

const handleCreate = () => {
  if (createModalRef.value) {
    createModalRef.value.open();
  }
};

const goDetail = (id: string) => {
  router.push(`/dashboard/corpus/${id}`);
};

const handleSelectionChange = (rows: Corpus[]) => {
  selectedRows.value = rows;
};

const handleRowClick = (row: Corpus, _column: any, event: MouseEvent) => {
  const target = event.target as HTMLElement | null;
  if (target?.closest('button') || target?.closest('a')) {
    return;
  }
  tableRef.value?.toggleRowSelection(row);
};

const handleDelete = async (row: Corpus) => {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${row.name}」吗？该操作会删除其文档与索引关联记录。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    );
  } catch {
    return;
  }

  await deleteCorpus(row.id);
  ElMessage.success('删除成功');
  await fetchData();
};

const handleBatchDelete = async () => {
  const ids = selectedRows.value.map((item) => item.id);
  if (ids.length === 0) {
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定批量删除已选中的 ${ids.length} 个知识库吗？该操作不可撤销。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    );
  } catch {
    return;
  }

  const result: any = await batchDeleteCorpora(ids);
  ElMessage.success(`批量删除成功，共删除 ${result.deleted_count ?? ids.length} 个知识库`);
  await fetchData();
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.corpora-list-view {
  padding: 24px;
  background-color: var(--bg-surface);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
  margin: 16px;
  min-height: calc(100vh - 32px);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.action-btn {
  border-radius: 8px;
}
.new-corpus-btn {
  border-radius: 8px;
  box-shadow: var(--shadow-blue);
}
:deep(.custom-table) {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border-color-light);
}
:deep(.custom-table th.el-table__cell) {
  background-color: var(--bg-base);
  color: var(--text-secondary);
  font-weight: 600;
}
</style>
