<template>
  <div class="corpus-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button :icon="Back" circle @click="$router.push('/dashboard/corpora')" />
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
        <el-table-column label="操作" width="320" fixed="right">
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
            <el-button
              type="danger"
              link
              @click="confirmDelete(scope.row)"
            >
              删除
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
          <div class="preview-info-bar">
            <el-tag type="info">文件大小：{{ formatSize(previewData.document.size_bytes ?? 0) }}</el-tag>
            <el-tag :type="getFileSizeTagType(fileSizeCategory)" style="margin-left: 8px;">
              {{ fileSizeCategoryText }}
            </el-tag>
          </div>

          <el-alert
            v-if="previewData.preview_mode === 'text' && fileSizeCategory === 'small'"
            type="success"
            :closable="false"
            show-icon
            title="小文件，已加载完整内容"
            class="preview-alert"
          />

          <el-alert
            v-if="fileSizeCategory === 'medium' && !fullContentLoaded"
            type="warning"
            :closable="false"
            show-icon
            title="中等大小文件，默认加载前 1000 行，可点击加载更多或加载完整按钮"
            class="preview-alert"
          />

          <el-alert
            v-if="fileSizeCategory === 'medium' && fullContentLoaded"
            type="success"
            :closable="false"
            show-icon
            title="已加载完整内容"
            class="preview-alert"
          />

          <el-alert
            v-if="fileSizeCategory === 'large'"
            type="error"
            :closable="false"
            show-icon
            title="大文件（> 10MB），默认使用 URL 预览模式，避免浏览器卡顿"
            class="preview-alert"
          />

          <template v-if="previewData.preview_mode === 'text'">
            <el-input
              :model-value="previewData.text ?? ''"
              type="textarea"
              :rows="22"
              readonly
              v-loading="previewLoading"
            />
            
            <div v-if="fileSizeCategory === 'medium' && !fullContentLoaded" class="preview-actions">
              <el-button type="primary" @click="loadMoreContent" :loading="loadingMore">
                加载更多 (已加载 {{ loadedLines }} 行)
              </el-button>
              <el-button type="success" @click="loadFullContent" :loading="loadingFull">
                加载完整内容 (约 {{ formatSize(previewData.document.size_bytes ?? 0) }})
              </el-button>
            </div>
          </template>

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

    <el-dialog v-model="deleteVisible" title="确认删除" width="500px" destroy-on-close>
      <el-alert
        type="error"
        show-icon
        :closable="false"
        title="删除后不可恢复"
        class="delete-alert"
      />
      <div class="delete-content">
        <p>确定要删除以下文档吗？</p>
        <p class="delete-filename"><strong>{{ deleteDocument?.file_name }}</strong></p>
        <p class="delete-warning">此操作将同时删除：</p>
        <ul class="delete-list">
          <li>文档文件本身</li>
          <li>关联的向量索引</li>
          <li>所有相关的元数据</li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="deleting"
          @click="executeDelete"
        >
          确认删除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Back } from '@element-plus/icons-vue';
import DocumentUploader from '@/components/DocumentUploader.vue';
import {
  getDocumentDetail,
  getDocumentPreview,
  listCorpusDocuments,
  updateDocumentContent,
  deleteDocument as deleteDocumentApi,
  type CorpusDocument,
  type DocumentPreviewResponse
} from '@/api/documents';

const SIZE_THRESHOLD_SMALL = 1024 * 1024;
const SIZE_THRESHOLD_LARGE = 10 * 1024 * 1024;

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
const fileSizeCategory = ref<'small' | 'medium' | 'large'>('small');
const fullContentLoaded = ref(false);
const loadedLines = ref(0);
const loadingMore = ref(false);
const loadingFull = ref(false);

const editVisible = ref(false);
const editLoading = ref(false);
const editSubmitting = ref(false);
const editDocument = ref<CorpusDocument | null>(null);
const editContent = ref('');

const deleteVisible = ref(false);
const deleting = ref(false);
const deleteDocument = ref<CorpusDocument | null>(null);

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

const fileSizeCategoryText = computed(() => {
  switch (fileSizeCategory.value) {
    case 'small':
      return '小文件 (< 1MB)';
    case 'medium':
      return '中等文件 (1MB - 10MB)';
    case 'large':
      return '大文件 (> 10MB)';
    default:
      return '';
  }
});

const getFileSizeTagType = (category: 'small' | 'medium' | 'large') => {
  switch (category) {
    case 'small':
      return 'success';
    case 'medium':
      return 'warning';
    case 'large':
      return 'danger';
    default:
      return 'info';
  }
};

const categorizeFileSize = (sizeBytes: number): 'small' | 'medium' | 'large' => {
  if (sizeBytes < SIZE_THRESHOLD_SMALL) {
    return 'small';
  } else if (sizeBytes < SIZE_THRESHOLD_LARGE) {
    return 'medium';
  } else {
    return 'large';
  }
};

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
  fileSizeCategory.value = 'small';
  fullContentLoaded.value = false;
  loadedLines.value = 0;
  
  try {
    previewData.value = await getDocumentPreview(doc.id);
    
    const sizeBytes = previewData.value.document.size_bytes ?? doc.size_bytes ?? 0;
    fileSizeCategory.value = categorizeFileSize(sizeBytes);
    
    if (previewData.value.preview_mode === 'text' && previewData.value.text) {
      const lines = previewData.value.text.split('\n');
      loadedLines.value = lines.length;
      
      if (fileSizeCategory.value === 'small') {
        fullContentLoaded.value = true;
      } else if (fileSizeCategory.value === 'medium') {
        fullContentLoaded.value = false;
      } else {
        previewData.value.preview_mode = 'url';
      }
    } else {
      fileSizeCategory.value = 'large';
    }
  } catch (error) {
    ElMessage.error('获取预览失败');
    console.error(error);
  } finally {
    previewLoading.value = false;
  }
};

const loadMoreContent = async () => {
  if (!previewData.value || loadingMore.value) return;
  
  loadingMore.value = true;
  try {
    ElMessage.info('加载更多功能需要后端 API 支持，当前版本暂不支持');
  } finally {
    loadingMore.value = false;
  }
};

const loadFullContent = async () => {
  if (!previewData.value || loadingFull.value) return;
  
  loadingFull.value = true;
  try {
    previewLoading.value = true;
    previewData.value = await getDocumentPreview(previewData.value.document.id);
    fullContentLoaded.value = true;
    
    if (previewData.value.text) {
      const lines = previewData.value.text.split('\n');
      loadedLines.value = lines.length;
    }
    
    ElMessage.success('完整内容已加载');
  } catch (error) {
    ElMessage.error('加载完整内容失败');
    console.error(error);
  } finally {
    previewLoading.value = false;
    loadingFull.value = false;
  }
};

watch(previewVisible, (newVal) => {
  if (!newVal) {
    previewData.value = null;
    fileSizeCategory.value = 'small';
    fullContentLoaded.value = false;
    loadedLines.value = 0;
  }
});

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

const confirmDelete = (doc: CorpusDocument) => {
  deleteDocument.value = doc;
  deleteVisible.value = true;
};

const executeDelete = async () => {
  if (!deleteDocument.value) {
    return;
  }

  deleting.value = true;
  try {
    await deleteDocumentApi(deleteDocument.value.id);
    ElMessage.success('文档已删除');
    deleteVisible.value = false;
    await fetchDocuments();
  } catch (error) {
    ElMessage.error('删除失败，请稍后重试');
    console.error(error);
  } finally {
    deleting.value = false;
  }
};

watch(deleteVisible, (newVal) => {
  if (!newVal) {
    deleteDocument.value = null;
  }
});

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

.preview-info-bar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 8px;
}

.preview-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
  padding: 12px 0;
  border-top: 1px solid var(--border-color-light);
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

.delete-alert {
  margin-bottom: 16px;
  border-radius: 8px;
}

.delete-content {
  padding: 8px 0;
}

.delete-content p {
  margin: 8px 0;
  color: var(--text-primary);
}

.delete-filename {
  font-size: 16px;
  color: var(--text-primary);
  word-break: break-all;
}

.delete-warning {
  color: var(--text-secondary);
  font-size: 14px;
}

.delete-list {
  margin: 8px 0;
  padding-left: 20px;
  color: var(--text-secondary);
}

.delete-list li {
  margin: 4px 0;
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
