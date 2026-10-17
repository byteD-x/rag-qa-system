<template>
  <div class="events-block">
    <div v-if="title || description || items.length" class="events-header">
      <h3 v-if="title">{{ title }}</h3>
      <p v-if="description">{{ description }}</p>
      <span v-if="items.length" class="events-count">{{ items.length }} 条</span>
    </div>

    <EnhancedEmpty
      v-if="!items.length"
      variant="default"
      title="暂无事件"
      description="处理完成后将在此展示"
      class="events-empty"
    />

    <el-timeline v-else class="events-timeline">
      <el-timeline-item
        v-for="item in items"
        :key="`${item.created_at}-${item.stage}`"
        :timestamp="formatDateTime(item.created_at)"
        placement="top"
        :type="getTimelineNodeType(item.stage)"
        :color="getTimelineNodeColor(item.stage)"
        :hollow="item.stage !== 'ready' && item.stage !== 'failed'"
      >
        <div class="event-card">
          <div class="event-head">
            <el-tag :type="statusMeta(item.stage).type" effect="plain" size="small">{{ statusMeta(item.stage).label }}</el-tag>
          </div>
          <p class="event-message" :class="{'error-text': item.stage === 'failed'}">{{ item.message }}</p>
          
          <div v-if="item.details_json" class="event-details-wrapper">
            <el-collapse class="custom-collapse">
              <el-collapse-item name="1">
                <template #title>
                  <div class="collapse-title">
                    <el-icon><Monitor /></el-icon> 详情
                  </div>
                </template>
                <JsonPreview :value="item.details_json" />
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import JsonPreview from '@/components/JsonPreview.vue';
import { statusMeta } from '@/utils/status';
import { formatDateTime } from '@/utils/time';
import { Monitor } from '@element-plus/icons-vue';

interface EventItem {
  stage: string;
  message: string;
  created_at: string;
  details_json?: unknown;
}

defineProps<{
  items: EventItem[];
  title?: string;
  description?: string;
}>();

const getTimelineNodeType = (stage: string) => {
  if (stage === 'ready') return 'success';
  if (stage === 'failed') return 'danger';
  if (stage === 'enhancing' || stage === 'parsing') return 'primary';
  return 'info';
};

const getTimelineNodeColor = (stage: string) => {
  if (stage === 'ready') return 'var(--el-color-success)';
  if (stage === 'failed') return 'var(--el-color-danger)';
  if (stage === 'enhancing' || stage === 'parsing') return 'var(--blue-600)';
  return 'var(--text-muted)';
};
</script>

<style scoped>
.events-block {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.events-empty {
  padding: 32px 20px !important;
}

.events-empty :deep(.default-illustration) {
  width: 56px;
  height: 56px;
}

.events-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.events-header h3 {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
}

.events-header p {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.events-count {
  font-size: var(--text-caption);
  color: var(--text-muted);
  margin-left: auto;
}

.events-timeline {
  padding-left: 4px;
  margin-top: 8px;
}

.events-timeline :deep(.el-timeline-item__node) {
  background-color: var(--bg-page);
  border: 2px solid currentColor;
}

.events-timeline :deep(.el-timeline-item__tail) {
  border-left: 2px solid var(--border-color);
}

.events-timeline :deep(.el-timeline-item__timestamp) {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  margin-bottom: 6px;
}

.event-card {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.event-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.event-message {
  margin-top: 12px;
  color: var(--text-regular);
  line-height: 1.7;
  font-size: var(--text-body);
}

.error-text {
  color: var(--el-color-danger);
}

.event-details-wrapper {
  margin-top: 16px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.custom-collapse {
  border-top: none;
  border-bottom: none;
}

.custom-collapse :deep(.el-collapse-item__header) {
  background: var(--bg-panel-muted);
  border-bottom: none;
  height: 40px;
  line-height: 40px;
  padding: 0 16px;
  color: var(--text-secondary);
}

.custom-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}

.custom-collapse :deep(.el-collapse-item__content) {
  padding: 12px;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-caption);
  font-weight: 600;
}
</style>
