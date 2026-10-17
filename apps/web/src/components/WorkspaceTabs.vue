<template>
  <div v-if="tabs.length > 1 && tabs.some((tab) => tab.key === activeKey)" class="workspace-tabs" role="navigation" aria-label="已打开页面">
    <el-tabs
      :model-value="activeKey"
      type="card"
      closable
      @tab-change="handleTabChange"
      @tab-remove="handleTabRemove"
    >
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :name="tab.key"
        :closable="!tab.pinned"
      >
        <template #label>
          <span class="workspace-tab-label" :title="tab.title">
            <el-icon v-if="tab.icon" :size="14"><component :is="tab.icon" /></el-icon>
            <span>{{ tab.title }}</span>
          </span>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
export interface WorkspaceTab {
  key: string;
  title: string;
  pinned?: boolean;
  icon?: unknown;
}

defineProps<{
  tabs: WorkspaceTab[];
  activeKey: string;
}>();

const emit = defineEmits<{
  (event: 'select', key: string): void;
  (event: 'remove', key: string): void;
}>();

const handleTabChange = (key: string | number) => emit('select', String(key));
const handleTabRemove = (key: string | number) => emit('remove', String(key));
</script>

<style scoped>
.workspace-tabs {
  flex: 0 0 auto;
  min-width: 0;
  padding: 0 4px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.workspace-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: 0;
}

.workspace-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.workspace-tabs :deep(.el-tabs__nav) {
  border: 0;
  gap: 4px;
}

.workspace-tabs :deep(.el-tabs__item) {
  height: 38px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  color: var(--text-secondary);
  font-size: var(--text-caption);
  font-weight: 600;
  transition: color var(--transition-fast), background-color var(--transition-fast), border-color var(--transition-fast);
}

.workspace-tabs :deep(.el-tabs__item:hover) {
  color: var(--text-primary);
  background: var(--bg-panel-muted);
}

.workspace-tabs :deep(.el-tabs__item.is-active) {
  border-color: var(--border-color) var(--border-color) var(--bg-panel);
  background: var(--bg-panel);
  color: var(--blue-700);
}

.workspace-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.workspace-tab-label {
  display: inline-flex;
  align-items: center;
  max-width: 180px;
  gap: 6px;
  white-space: nowrap;
}

.workspace-tab-label > span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 768px) {
  .workspace-tabs {
    padding-inline: 0;
    overflow-x: auto;
  }

  .workspace-tabs :deep(.el-tabs__nav) {
    min-width: max-content;
  }
}
</style>
