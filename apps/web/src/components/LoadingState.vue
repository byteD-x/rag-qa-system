<template>
  <div class="loading-state" role="status" aria-live="polite">
    <el-icon class="is-loading" :size="iconSize"><Loading /></el-icon>
    <span>{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue';

withDefaults(defineProps<{ label?: string; iconSize?: number }>(), {
  label: '加载中…',
  iconSize: 32
});
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--text-secondary);
  font-size: var(--text-body, 0.9375rem);
}
</style>
