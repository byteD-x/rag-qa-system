<template>
  <div class="enhanced-empty" :class="variant">
    <div class="empty-illustration">
      <slot name="illustration">
        <div class="default-illustration">
          <el-icon :size="iconSize" :color="iconColor">
            <component :is="iconComponent" />
          </el-icon>
        </div>
      </slot>
    </div>

    <div class="empty-content">
      <h3 v-if="title" class="empty-title">{{ title }}</h3>
      <p v-if="description" class="empty-description">{{ description }}</p>

      <div v-if="$slots.actions" class="empty-actions">
        <slot name="actions"></slot>
      </div>

      <div v-if="$slots.tips" class="empty-tips">
        <slot name="tips"></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  Document,
  Folder,
  ChatDotRound,
  Connection,
  Search,
  Upload,
  QuestionFilled,
  CircleCheck
} from '@element-plus/icons-vue';

interface Props {
  variant?: 'document' | 'folder' | 'chat' | 'search' | 'upload' | 'question' | 'success' | 'default';
  title?: string;
  description?: string;
  imageSize?: number;
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default'
});

const iconMap: Record<string, any> = {
  document: Document,
  folder: Folder,
  chat: ChatDotRound,
  search: Search,
  upload: Upload,
  question: QuestionFilled,
  success: CircleCheck,
  default: Connection
};

const iconComponent = computed(() => iconMap[props.variant] || iconMap.default);

const iconSize = computed(() => props.imageSize || 48);

const iconColor = computed(() => {
  const colorMap: Record<string, string> = {
    document: 'var(--blue-600)',
    folder: 'var(--blue-600)',
    chat: 'var(--blue-600)',
    search: 'var(--text-secondary)',
    upload: 'var(--blue-600)',
    question: 'var(--text-secondary)',
    success: 'var(--blue-600)',
    default: 'var(--text-secondary)'
  };
  return colorMap[props.variant] || colorMap.default;
});
</script>

<style scoped>
.enhanced-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 28px;
  text-align: center;
}

.empty-illustration {
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.default-illustration {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: var(--radius-md);
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
}

.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.empty-title {
  font-size: var(--text-h2, 1.125rem);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}

.empty-description {
  font-size: var(--text-body, 0.9375rem);
  color: var(--text-secondary);
  margin: 0;
  max-width: 380px;
  line-height: 1.6;
}

.empty-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.empty-tips {
  margin-top: 24px;
  padding: 18px 22px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-panel-muted);
  max-width: 420px;
  text-align: left;
}

.empty-tips :deep(strong) {
  display: block;
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: var(--text-body, 0.9375rem);
  font-weight: 600;
}

.empty-tips :deep(ul) {
  margin: 0;
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: var(--text-body, 0.9375rem);
  line-height: 1.7;
}

.empty-tips :deep(li) {
  margin-bottom: 6px;
}

@media (max-width: 768px) {
  .enhanced-empty {
    padding: 40px 20px;
  }

  .default-illustration {
    width: 64px;
    height: 64px;
  }

  .empty-title {
    font-size: 1.0625rem;
  }

  .empty-description {
    font-size: 0.875rem;
  }
}
</style>
