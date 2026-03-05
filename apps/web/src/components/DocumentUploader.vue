<template>
  <div class="document-uploader">
    <el-upload
      class="upload-demo"
      drag
      action="#"
      :auto-upload="false"
      :show-file-list="false"
      :on-change="handleChange"
      :disabled="isUploading || isPolling"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">
        拖拽文件到此处，或 <em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          支持 txt / pdf / docx，大小不超过 500MB
        </div>
      </template>
    </el-upload>

    <div v-if="isUploading || isPolling || uploadError" class="progress-container">
      <div class="status-header">
        <el-icon v-if="uploadError" class="status-icon error"><circle-close /></el-icon>
        <el-icon v-else-if="isPolling && pollingProgress === 100" class="status-icon success"><circle-check /></el-icon>
        <el-icon v-else class="status-icon loading"><loading /></el-icon>
        <span class="status-text">{{ currentStatus }}</span>
      </div>

      <el-progress 
        v-if="isUploading" 
        :percentage="uploadProgress" 
        :status="uploadError ? 'exception' : (uploadProgress === 100 ? 'success' : undefined)"
        :format="getProgressText"
        :stroke-width="20"
      />
      
      <el-progress 
        v-if="isPolling" 
        :percentage="pollingProgress" 
        :status="pollingProgress === 100 ? 'success' : 'warning'"
        :stroke-width="20"
      />

      <div v-if="uploadError" class="error-details">
        <el-alert
          :title="uploadError.message"
          :description="uploadError.details"
          type="error"
          :closable="true"
          @close="handleErrorClose"
          show-icon
        />
        <el-button 
          type="primary" 
          size="small" 
          @click="handleRetry"
          :loading="isUploading"
        >
          <el-icon><refresh /></el-icon>
          重试上传
        </el-button>
      </div>

      <div v-if="isUploading && progressInfo?.estimatedRemaining" class="time-remaining">
        预计剩余时间：{{ formatTime(progressInfo.estimatedRemaining) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { UploadFilled, CircleClose, CircleCheck, Loading, Refresh } from '@element-plus/icons-vue';
import { useUploader } from '@/composables/useUploader';
import { ElMessage } from 'element-plus';

const props = defineProps<{ corpusId: string }>();
const emit = defineEmits(['uploaded']);

const handleSuccess = () => {
  emit('uploaded');
};

const { 
  uploadFile, 
  retryUpload,
  isUploading, 
  uploadProgress, 
  isPolling, 
  pollingProgress, 
  currentStatus,
  uploadError,
  progressInfo,
  getProgressText
} = useUploader(props.corpusId, handleSuccess);

let currentFile: File | null = null;

const handleChange = async (uploadFileObj: any) => {
  if (uploadFileObj && uploadFileObj.raw) {
    currentFile = uploadFileObj.raw;
    const ext = uploadFileObj.name.split('.').pop()?.toLowerCase();
    if (!['txt', 'pdf', 'docx'].includes(ext)) {
      ElMessage.error('仅支持 txt, pdf, docx 格式');
      return;
    }
    await uploadFile(uploadFileObj.raw);
  }
};

const handleErrorClose = () => {
  uploadError.value = null;
};

const handleRetry = () => {
  if (currentFile) {
    retryUpload(currentFile);
  }
};

const formatTime = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
  return `${Math.round(seconds / 3600)}小时`;
};
</script>

<style scoped>
.document-uploader {
  margin-bottom: 16px;
}

:deep(.el-upload-dragger) {
  border-radius: 12px;
  background-color: var(--bg-base);
  border: 2px dashed var(--border-color);
  transition: all var(--el-transition-duration);
}

:deep(.el-upload-dragger:hover) {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.progress-container {
  margin-top: 20px;
  padding: 20px;
  background-color: var(--bg-base);
  border: 1px solid var(--border-color-light);
  border-radius: 12px;
}

.status-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 8px;
}

.status-icon {
  font-size: 18px;
}

.status-icon.loading {
  color: var(--el-color-primary);
  animation: rotate 1.5s linear infinite;
}

.status-icon.success {
  color: var(--el-color-success);
}

.status-icon.error {
  color: var(--el-color-danger);
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.status-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-regular);
  flex: 1;
}

.error-details {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:deep(.el-alert) {
  padding: 12px 16px;
}

:deep(.el-alert__title) {
  font-size: 14px;
}

:deep(.el-alert__description) {
  font-size: 13px;
  margin-top: 4px;
}

.time-remaining {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
}

:deep(.el-progress-bar) {
  border-radius: 4px;
}

:deep(.el-progress__text) {
  font-size: 12px !important;
}
</style>
