<template>
  <div class="error-boundary">
    <div v-if="hasError" class="error-fallback">
      <div class="error-panel">
        <el-icon :size="40" color="#ef4444" class="error-icon">
          <WarningFilled />
        </el-icon>
        <h3 class="error-title">{{ title || '出错了' }}</h3>
        <p class="error-message">{{ errorMessage }}</p>

        <div v-if="errorDetails && showDetails" class="error-details">
          <pre class="error-code"><code>{{ errorDetails }}</code></pre>
        </div>

        <div class="error-actions">
          <el-button
            v-if="showRetry"
            type="primary"
            :loading="isRetrying"
            @click="handleRetry"
          >
            {{ retryText || '重试' }}
          </el-button>
          <el-button plain @click="handleReset">
            {{ resetText || '返回' }}
          </el-button>
          <slot name="actions"></slot>
        </div>
      </div>
    </div>

    <slot v-else></slot>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { WarningFilled } from '@element-plus/icons-vue';

interface Props {
  title?: string;
  errorMessage?: string;
  errorDetails?: string;
  showRetry?: boolean;
  retryText?: string;
  resetText?: string;
  showDetails?: boolean;
  retryDelay?: number;
  maxRetries?: number;
}

const props = withDefaults(defineProps<Props>(), {
  errorMessage: '发生意外错误，请稍后重试。',
  showRetry: true,
  retryText: '重试',
  resetText: '返回',
  showDetails: true,
  retryDelay: 1000,
  maxRetries: 3
});

const emit = defineEmits<{
  (e: 'retry', attempt: number): void;
  (e: 'reset'): void;
  (e: 'error', error: Error): void;
}>();

const hasError = ref(false);
const isRetrying = ref(false);
const retryCount = ref(0);

const handleError = (error: Error) => {
  hasError.value = true;
  emit('error', error);
};

const handleRetry = async () => {
  if (retryCount.value >= props.maxRetries) {
    return;
  }

  isRetrying.value = true;
  retryCount.value++;

  try {
    await new Promise((resolve) => setTimeout(resolve, props.retryDelay));
    emit('retry', retryCount.value);
  } finally {
    isRetrying.value = false;
  }
};

const handleReset = () => {
  hasError.value = false;
  retryCount.value = 0;
  emit('reset');
};

const resetError = () => {
  hasError.value = false;
  retryCount.value = 0;
};

defineExpose({
  handleError,
  resetError
});

watch(
  () => props.errorDetails,
  (newDetails) => {
    if (newDetails && !hasError.value) {
      hasError.value = true;
    }
  }
);

onMounted(() => {
  window.addEventListener('error', (event) => {
    if (event.target instanceof Element) {
      handleError(new Error(event.message || 'Resource load failed'));
    }
  });
});
</script>

<style scoped>
.error-boundary {
  min-height: inherit;
}

.error-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  padding: 24px;
  background: var(--bg-panel);
}

.error-panel {
  max-width: 480px;
  text-align: center;
  padding: 24px;
}

.error-icon {
  margin-bottom: 16px;
}

.error-title {
  margin: 0 0 8px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.error-message {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.error-details {
  text-align: left;
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  margin-bottom: 20px;
  overflow-x: auto;
}

.error-code {
  font-family: var(--font-mono);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}

.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .error-actions {
    flex-direction: column;
  }

  .error-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
