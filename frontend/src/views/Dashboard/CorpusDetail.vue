<template>
  <div class="corpus-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button icon="Back" circle @click="$router.push('/dashboard/corpora')" />
        <h2>知识库文档管理 {{ corpusId }}</h2>
      </div>
    </div>

    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span>上传新文档</span>
        </div>
      </template>
      <DocumentUploader :corpusId="corpusId" @uploaded="fetchDocuments" />
    </el-card>

    <el-card class="list-card">
      <template #header>
        <div class="card-header">
          <span>文档列表</span>
          <el-button link type="primary" @click="fetchDocuments">刷新</el-button>
        </div>
      </template>

      <el-table :data="documents" v-loading="loading" border style="width: 100%">
        <el-table-column prop="id" label="ID" min-width="280" />
        <el-table-column prop="file_name" label="文件名" min-width="220" />
        <el-table-column prop="file_type" label="类型" width="100">
          <template #default="scope">
            <el-tag>{{ scope.row.file_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="120">
          <template #default="scope">
            {{ formatSize(scope.row.size_bytes) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="scope">
            <el-button type="primary" link @click="openDetail(scope.row)">详情</el-button>
            <el-button type="success" link @click="openPreview(scope.row)">在线查看</el-button>
            <el-button
              type="warning"
              link
              :disabled="!canEdit(scope.row)"
              @click="openEdit(scope.row)"
            >
              在线修改
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="文档详情" width="680px">
      <div v-loading="detailLoading">
        <el-descriptions v-if="detailData" :column="1" border>
          <el-descriptions-item label="文档 ID">{{ detailData.id }}</el-descriptions-item>
          <el-descriptions-item label="知识库 ID">{{ detailData.corpus_id }}</el-descriptions-item>
          <el-descriptions-item label="文件名">{{ detailData.file_name }}</el-descriptions-item>
          <el-descriptions-item label="文件类型">{{ detailData.file_type }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatSize(detailData.size_bytes) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detailData.status }}</el-descriptions-item>
          <el-descriptions-item label="创建者">{{ detailData.created_by ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(detailData.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="在线查看" width="980px" destroy-on-close>
      <div v-loading="previewLoading">
        <template v-if="previewData">
          <el-alert
            v-if="previewData.preview_mode === 'text'"
            type="info"
            :closable="false"
            title="文本预览用于快速确认内容；如需改写请使用“在线修改”。"
            class="preview-alert"
          />
          <el-input
            v-if="previewData.preview_mode === 'text'"
            :model-value="previewData.text ?? ''"
            type="textarea"
            :rows="22"
            readonly
          />

          <div v-else class="preview-url-mode">
            <div class="preview-toolbar">
              <el-button type="primary" @click="openPreviewInNewTab">新窗口打开</el-button>
              <span class="preview-expire-text">
                预览链接有效期 {{ previewData.expires_in_seconds ?? 0 }} 秒
              </span>
            </div>
            <iframe
              v-if="previewData.view_url"
              :src="previewData.view_url"
              class="preview-frame"
              title="文档预览"
            />
            <el-empty v-else description="预览链接不可用" />
          </div>
        </template>
      </div>
    </el-dialog>

    <el-dialog v-model="editVisible" title="在线修改（仅 TXT）" width="980px" destroy-on-close>
      <div v-loading="editLoading">
        <template v-if="editDocument">
          <el-alert
            type="warning"
            show-icon
            :closable="false"
            title="保存后将自动触发文档重新入库与向量索引重建。"
            class="preview-alert"
          />
          <el-input
            v-model="editContent"
            type="textarea"
            :rows="22"
            maxlength="1048576"
            show-word-limit
            placeholder="请输入文档内容"
          />
        </template>
      </div>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="editSubmitting"
          :disabled="!editContent.trim()"
          @click="submitEdit"
        >
          保存并重建索引
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import DocumentUploader from '@/components/DocumentUploader.vue';
import {
  getDocumentDetail,
  getDocumentPreview,
  listCorpusDocuments,
  updateDocumentContent,
  type CorpusDocument,
  type DocumentPreviewResponse
} from '@/api/documents';

const route = useRoute();
const corpusId = computed(() => String(route.params.id ?? ''));
const loading = ref(false);
const documents = ref<CorpusDocument[]>([]);

const detailVisible = ref(false);
const detailLoading = ref(false);
const detailData = ref<CorpusDocument | null>(null);

const previewVisible = ref(false);
const previewLoading = ref(false);
const previewData = ref<DocumentPreviewResponse | null>(null);

const editVisible = ref(false);
const editLoading = ref(false);
const editSubmitting = ref(false);
const editDocument = ref<CorpusDocument | null>(null);
const editContent = ref('');

const fetchDocuments = async () => {
  loading.value = true;
  try {
    const res = await listCorpusDocuments(corpusId.value);
    documents.value = res.items ?? [];
  } finally {
    loading.value = false;
  }
};

const formatDateTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

const formatSize = (sizeBytes: number) => {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return '0 B';
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
};

const getStatusType = (status: CorpusDocument['status']) => {
  switch (status) {
    case 'ready':
      return 'success';
    case 'failed':
      return 'danger';
    case 'indexing':
      return 'warning';
    case 'uploaded':
      return 'info';
    default:
      return '';
  }
};

const canEdit = (doc: CorpusDocument) => doc.file_type === 'txt';

const openDetail = async (doc: CorpusDocument) => {
  detailVisible.value = true;
  detailLoading.value = true;
  detailData.value = null;
  try {
    detailData.value = await getDocumentDetail(doc.id);
  } finally {
    detailLoading.value = false;
  }
};

const openPreview = async (doc: CorpusDocument) => {
  previewVisible.value = true;
  previewLoading.value = true;
  previewData.value = null;
  try {
    previewData.value = await getDocumentPreview(doc.id);
  } finally {
    previewLoading.value = false;
  }
};

const openPreviewInNewTab = () => {
  const url = previewData.value?.view_url;
  if (!url) {
    ElMessage.warning('预览链接不可用');
    return;
  }
  window.open(url, '_blank', 'noopener');
};

const openEdit = async (doc: CorpusDocument) => {
  if (!canEdit(doc)) {
    ElMessage.warning('仅 txt 文档支持在线修改');
    return;
  }

  editVisible.value = true;
  editLoading.value = true;
  editDocument.value = null;
  editContent.value = '';

  try {
    const [detail, preview] = await Promise.all([
      getDocumentDetail(doc.id),
      getDocumentPreview(doc.id)
    ]);
    if (preview.preview_mode !== 'text') {
      ElMessage.error('当前文档不支持在线编辑');
      editVisible.value = false;
      return;
    }

    editDocument.value = detail;
    editContent.value = preview.text ?? '';
  } finally {
    editLoading.value = false;
  }
};

const submitEdit = async () => {
  if (!editDocument.value) {
    return;
  }

  const nextContent = editContent.value;
  if (!nextContent.trim()) {
    ElMessage.warning('内容不能为空');
    return;
  }

  editSubmitting.value = true;
  try {
    await updateDocumentContent(editDocument.value.id, nextContent);
    ElMessage.success('内容已更新，已提交重建索引任务');
    editVisible.value = false;
    await fetchDocuments();
  } finally {
    editSubmitting.value = false;
  }
};

onMounted(() => {
  fetchDocuments();
});
</script>

<style scoped>
.corpus-detail {
  padding: 24px;
  margin: 16px;
  background-color: var(--bg-surface);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
  min-height: calc(100vh - 32px);
}

.page-header {
  margin-bottom: 28px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.upload-card {
  margin-bottom: 24px;
  border-radius: 16px;
  border: 1px solid var(--border-color-light);
  box-shadow: var(--shadow-sm);
}

.list-card {
  border-radius: 16px;
  border: 1px solid var(--border-color-light);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: var(--text-primary);
}

.preview-alert {
  margin-bottom: 12px;
  border-radius: 8px;
}

.preview-url-mode {
  width: 100%;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.preview-expire-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.preview-frame {
  width: 100%;
  height: 620px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

:deep(.el-table) {
  border-radius: 8px;
}
:deep(.el-table th.el-table__cell) {
  background-color: var(--bg-base);
  color: var(--text-secondary);
  font-weight: 600;
}
</style>
