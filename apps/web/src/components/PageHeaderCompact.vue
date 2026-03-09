<template>
  <header class="page-header-compact">
    <div class="page-header-compact__main">
      <h1 v-if="title" class="page-header-compact__title">{{ title }}</h1>
      <div v-if="$slots.subtitle" class="page-header-compact__subtitle">
        <slot name="subtitle" />
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header-compact__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
}>();
</script>

<style scoped>
.page-header-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--content-gap, 20px);
  flex-wrap: wrap;
  padding: 14px 0 16px;
  min-height: var(--page-header-compact, 56px);
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: -1px;
}

.page-header-compact__main {
  min-width: 0;
}

.page-header-compact__title {
  margin: 0;
  font-size: var(--text-h2, 1.125rem);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  letter-spacing: -0.02em;
}

.page-header-compact__subtitle {
  margin-top: 6px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-muted);
  font-weight: 500;
}

.page-header-compact__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
