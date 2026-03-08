<template>
  <div class="page">
    <section class="page-header kb-header">
      <div>
        <el-tag type="success" effect="dark">企业文档上传</el-tag>
        <h1>分块直传与异步索引</h1>
        <p>文件按 5MB 分块直传对象存储，上传完成立即返回，解析与增强在后台继续推进。</p>
      </div>
      <el-button plain @click="router.push('/workspace/chat')">前往统一 QA</el-button>
    </section>

    <section class="grid two-columns">
      <el-card shadow="hover" class="panel">
        <template #header>
          <div class="card-head">
            <div>
              <h2>知识库</h2>
              <p>先选择或创建知识库，再开始上传。</p>
            </div>
            <el-tag effect="plain">{{ bases.length }} 个知识库</el-tag>
          </div>
        </template>

        <el-form label-position="top">
          <el-form-item label="选择知识库">
            <el-select v-model="selectedBaseId" placeholder="请选择或先创建知识库">
              <el-option v-for="base in bases" :key="base.id" :label="base.name" :value="base.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="新建知识库名称">
            <el-input v-model="baseForm.name" placeholder="例如：运营制度库" />
          </el-form-item>
          <el-form-item label="分类">
            <el-input v-model="baseForm.category" placeholder="例如：制度 / FAQ / 合同" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="baseForm.description" type="textarea" :rows="3" placeholder="描述该知识库的用途" />
          </el-form-item>
          <el-button type="primary" :loading="creatingBase" @click="handleCreateBase">创建知识库</el-button>
        </el-form>
      </el-card>

      <el-card shadow="hover" class="panel">
        <template #header>
          <div class="card-head">
            <div>
              <h2>上传任务</h2>
              <p>浏览器直传 MinIO，支持断点续传与后台索引。</p>
            </div>
            <el-tag type="success" effect="plain">TXT / PDF / DOCX</el-tag>
          </div>
        </template>

        <el-form label-position="top">
          <el-form-item label="文档分类">
            <el-input v-model="uploadForm.category" placeholder="例如：人事制度 / 客服 FAQ" />
          </el-form-item>
          <el-form-item label="选择文件">
            <div class="file-picker">
              <el-button type="primary" plain @click="pickFiles">选择文件</el-button>
              <span class="file-name">{{ selectedFiles.length ? `${selectedFiles.length} 个文件待上传` : '尚未选择文件' }}</span>
            </div>
            <input ref="fileInputRef" class="hidden-input" type="file" accept=".txt,.pdf,.docx" multiple @change="handleFileChange" />
          </el-form-item>

          <div class="selected-files">
            <el-empty v-if="!selectedFiles.length" description="选择文件后会显示上传进度" />
            <div v-else class="file-progress-list">
              <div v-for="file in selectedFiles" :key="fileFingerprint(file)" class="file-progress-item">
                <div class="status-row">
                  <strong>{{ file.name }}</strong>
                  <span>{{ formatBytes(file.size) }}</span>
                </div>
                <el-progress :percentage="Math.round((uploadProgress[fileFingerprint(file)] || 0) * 100)" />
              </div>
            </div>
          </div>

          <el-button type="primary" :loading="uploading" @click="handleUpload">开始上传并索引</el-button>
        </el-form>
      </el-card>
    </section>

    <section class="grid two-columns">
      <el-card shadow="hover" class="panel">
        <template #header>
          <div class="card-head">
            <div>
              <h2>最近文档</h2>
              <p>上传完成后会立即出现，索引状态持续刷新。</p>
            </div>
          </div>
        </template>

        <el-empty v-if="!latestDocuments.length" description="当前没有文档记录" />
        <div v-else class="document-list">
          <el-card v-for="document in latestDocuments" :key="document.id" shadow="hover" class="document-card">
            <div class="status-row">
              <strong>{{ document.file_name }}</strong>
              <el-tag :type="statusMeta(document.status).type" effect="plain">{{ statusMeta(document.status).label }}</el-tag>
            </div>
            <p>类型：{{ document.file_type }}</p>
            <p>分段：{{ document.section_count || 0 }} 节，{{ document.chunk_count || 0 }} chunk</p>
            <div class="action-row">
              <el-button text @click="openDocument(document.id)">详情</el-button>
              <el-button text type="primary" @click="openInChat(document.id)">问答</el-button>
            </div>
          </el-card>
        </div>
      </el-card>

      <el-card shadow="hover" class="panel">
        <DocumentEvents
          :items="events"
          title="处理事件"
          description="记录上传、解析、快速可查、混合检索就绪与增强阶段。"
        />
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import DocumentEvents from '@/components/DocumentEvents.vue';
import {
  completeKBUpload,
  createKBUpload,
  createKnowledgeBase,
  getKBDocumentEvents,
  getKBIngestJob,
  getKBUpload,
  listKBDocuments,
  listKnowledgeBases,
  presignKBUploadParts
} from '@/api/kb';
import { uploadMultipartFile } from '@/utils/multipartUpload';
import { statusMeta } from '@/utils/status';

const router = useRouter();
const route = useRoute();

const bases = ref<any[]>([]);
const selectedBaseId = ref('');
const selectedFiles = ref<File[]>([]);
const latestDocuments = ref<any[]>([]);
const events = ref<any[]>([]);
const uploadProgress = ref<Record<string, number>>({});
const fileInputRef = ref<HTMLInputElement | null>(null);

const creatingBase = ref(false);
const uploading = ref(false);
let pollTimer: number | null = null;

const baseForm = reactive({
  name: '',
  description: '',
  category: ''
});

const uploadForm = reactive({
  category: ''
});

const fileFingerprint = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

const formatBytes = (value: number) => {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const clearPoller = () => {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
};

const loadBases = async () => {
  const res: any = await listKnowledgeBases();
  bases.value = res.items || [];
  if (!selectedBaseId.value && bases.value.length) {
    selectedBaseId.value = String(route.query.baseId || bases.value[0].id);
  }
};

const loadDocuments = async (baseId: string) => {
  const res: any = await listKBDocuments(baseId);
  latestDocuments.value = res.items || [];
};

const refreshEventFocus = async () => {
  if (!latestDocuments.value.length) {
    events.value = [];
    return;
  }
  const focus = latestDocuments.value[0];
  const result: any = await getKBDocumentEvents(focus.id);
  events.value = result.items || [];
};

const pickFiles = () => {
  fileInputRef.value?.click();
};

const handleFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  selectedFiles.value = Array.from(input.files || []);
};

const handleCreateBase = async () => {
  if (!baseForm.name.trim()) {
    ElMessage.warning('请先填写知识库名称');
    return;
  }
  creatingBase.value = true;
  try {
    const base: any = await createKnowledgeBase({
      name: baseForm.name.trim(),
      description: baseForm.description.trim(),
      category: baseForm.category.trim()
    });
    baseForm.name = '';
    baseForm.description = '';
    baseForm.category = '';
    await loadBases();
    selectedBaseId.value = base.id;
    ElMessage.success('知识库已创建');
  } finally {
    creatingBase.value = false;
  }
};

const pollJobs = async (jobIds: string[]) => {
  const snapshots = await Promise.all(jobIds.map((jobId) => getKBIngestJob(jobId)));
  const completed = snapshots.every((job: any) => ['ready', 'failed'].includes(String(job.document_status || job.status)));
  if (selectedBaseId.value) {
    await loadDocuments(selectedBaseId.value);
  }
  await refreshEventFocus();
  if (completed) {
    clearPoller();
    return;
  }
  pollTimer = window.setTimeout(() => {
    void pollJobs(jobIds);
  }, 2000);
};

const uploadSingleFile = async (file: File) => {
  const fingerprint = fileFingerprint(file);
  const result = await uploadMultipartFile({
    file,
    resumeKey: `kb-upload:${selectedBaseId.value}:${fingerprint}`,
    controller: {
      createUpload: () => createKBUpload({
        base_id: selectedBaseId.value,
        file_name: file.name,
        file_type: file.name.split('.').pop()?.toLowerCase() || 'txt',
        size_bytes: file.size,
        category: uploadForm.category.trim()
      }) as Promise<any>,
      getUpload: (uploadId: string) => getKBUpload(uploadId) as Promise<any>,
      presignParts: (uploadId: string, partNumbers: number[]) => presignKBUploadParts(uploadId, partNumbers) as Promise<any>,
      completeUpload: (uploadId: string, parts) => completeKBUpload(uploadId, parts) as Promise<any>
    },
    onProgress: ({ ratio }) => {
      uploadProgress.value = {
        ...uploadProgress.value,
        [fingerprint]: ratio
      };
    }
  });
  uploadProgress.value = {
    ...uploadProgress.value,
    [fingerprint]: 1
  };
  return result.result;
};

const handleUpload = async () => {
  if (!selectedBaseId.value) {
    ElMessage.warning('请先选择知识库');
    return;
  }
  if (!selectedFiles.value.length) {
    ElMessage.warning('请先选择文件');
    return;
  }
  uploading.value = true;
  try {
    const completed = [];
    for (const file of selectedFiles.value) {
      completed.push(await uploadSingleFile(file));
    }
    await loadDocuments(selectedBaseId.value);
    await refreshEventFocus();
    await pollJobs(completed.map((item: any) => String(item.job_id)));
    ElMessage.success('文件已接收，后台正在分阶段索引');
  } finally {
    uploading.value = false;
  }
};

const openDocument = (documentId: string) => {
  router.push(`/workspace/kb/documents/${documentId}`);
};

const openInChat = (documentId: string) => {
  router.push({
    path: '/workspace/chat',
    query: {
      preset: 'kb',
      baseId: selectedBaseId.value,
      documentId
    }
  });
};

watch(selectedBaseId, (baseId) => {
  if (!baseId) {
    latestDocuments.value = [];
    return;
  }
  void loadDocuments(baseId);
});

onMounted(async () => {
  await loadBases();
});

onBeforeUnmount(() => {
  clearPoller();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 30px;
  border-radius: 28px;
}

.kb-header {
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.2), transparent 30%),
    linear-gradient(135deg, #ffffff, #ecfdf5);
}

.page-header h1 {
  margin: 12px 0 8px;
  font-size: 34px;
}

.page-header p {
  margin: 0;
  color: var(--text-regular);
  line-height: 1.7;
}

.grid.two-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.panel {
  border-radius: 24px;
  border: none;
}

.panel :deep(.el-card__body) {
  padding: 24px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.card-head h2 {
  margin: 0;
}

.card-head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
}

.file-picker {
  display: flex;
  align-items: center;
  gap: 12px;
}

.file-name {
  color: var(--text-secondary);
}

.hidden-input {
  display: none;
}

.selected-files,
.file-progress-list,
.document-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.file-progress-item,
.document-card {
  border-radius: 18px;
}

.status-row,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

@media (max-width: 1200px) {
  .grid.two-columns {
    grid-template-columns: 1fr;
  }
}
</style>
