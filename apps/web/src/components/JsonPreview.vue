<template>
  <div class="json-preview">
    <div v-if="title" class="json-preview__title">{{ title }}</div>
    <pre class="json-preview__body">{{ text }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{ value: unknown; title?: string; empty?: string }>(), {
  empty: '无数据'
});

const text = computed(() => {
  const value = props.value;
  if (value === null || value === undefined || value === '') {
    return props.empty;
  }
  if (typeof value === 'string') {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return props.empty;
  }
});
</script>

<style scoped>
.json-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.json-preview__title {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
}

.json-preview__body {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  color: var(--text-regular);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow: auto;
}
</style>
