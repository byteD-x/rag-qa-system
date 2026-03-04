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

    <!-- 进度展示区 -->
    <div v-if="isUploading || isPolling" class="progress-container">
      <div class="status-text">{{ currentStatus }}</div>
      <el-progress 
        v-if="isUploading" 
        :percentage="uploadProgress" 
        :status="uploadProgress === 100 ? 'success' : ''" 
      />
      <el-progress 
        v-if="isPolling" 
        :percentage="pollingProgress" 
        status="warning" 
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue';
import { useUploader } from '@/composables/useUploader';
import { ElMessage } from 'element-plus';

const props = defineProps<{ corpusId: string }>();
const emit = defineEmits(['uploaded']);

const handleSuccess = () => {
  emit('uploaded');
};

const { 
  uploadFile, 
  isUploading, 
  uploadProgress, 
  isPolling, 
  pollingProgress, 
  currentStatus 
} = useUploader(props.corpusId, handleSuccess);

const handleChange = async (uploadFileObj: any) => {
  if (uploadFileObj && uploadFileObj.raw) {
    const ext = uploadFileObj.name.split('.').pop()?.toLowerCase();
    if (!['txt', 'pdf', 'docx'].includes(ext)) {
      ElMessage.error('仅支持 txt, pdf, docx 格式');
      return;
    }
    await uploadFile(uploadFileObj.raw);
  }
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
.status-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-regular);
  margin-bottom: 12px;
}
</style>
