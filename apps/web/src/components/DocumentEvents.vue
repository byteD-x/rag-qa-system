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
            <div class="event-title-group">
              <el-icon v-if="getStageIcon(item.stage)" :color="getTimelineNodeColor(item.stage)" class="stage-icon">
                <component :is="getStageIcon(item.stage)" />
              </el-icon>
              <strong>{{ stageLabel(item.stage) }}</strong>
            </div>
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
                <pre class="event-details"><code class="language-json">{{ pretty(item.details_json) }}</code></pre>
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
import { statusMeta } from '@/utils/status';
import { formatDateTime } from '@/utils/time';
import { 
  Monitor, 
  UploadFilled, 
  Document, 
  Cpu, 
  Connection, 
  CircleCheckFilled, 
  WarningFilled 
} from '@element-plus/icons-vue';

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

const STAGE_LABELS: Record<string, string> = {
  uploaded: '已接收',
  parsing_fast: '快速解析',
  parsing: '深度解析',
  fast_index_ready: '快速可查',
  enhancing: '增强处理中',
  hybrid_ready: '混合检索就绪',
  ready: '流程完成',
  failed: '处理失败'
};

const stageLabel = (stage: string) => STAGE_LABELS[stage] || stage;

const getTimelineNodeType = (stage: string) => {
  if (stage === 'ready') return 'success';
  if (stage === 'failed') return 'danger';
  if (stage === 'enhancing' || stage === 'parsing') return 'primary';
  return 'info';
};

const getTimelineNodeColor = (stage: string) => {
  if (stage === 'ready') return '#10b981';
  if (stage === 'failed') return '#ef4444';
  if (stage === 'enhancing' || stage === 'parsing') return 'var(--blue-600)';
  return 'var(--text-muted)';
};

const getStageIcon = (stage: string) => {
  if (stage === 'uploaded') return UploadFilled;
  if (stage === 'parsing_fast' || stage === 'parsing') return Document;
  if (stage === 'enhancing') return Cpu;
  if (stage.includes('ready') && stage !== 'ready') return Connection;
  if (stage === 'ready') return CircleCheckFilled;
  if (stage === 'failed') return WarningFilled;
  return null;
};

const pretty = (value: unknown) => JSON.stringify(value, null, 2);
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
  font-size: 14px;
  font-weight: 600;
}

.events-header p {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.events-count {
  font-size: 12px;
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
  font-size: 12px;
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

.event-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-icon {
  font-size: 18px;
}

.event-title-group strong {
  font-size: 1.05rem;
  color: var(--text-primary);
}

.event-message {
  margin-top: 12px;
  color: var(--text-regular);
  line-height: 1.7;
  font-size: 14px;
}

.error-text {
  color: #ef4444;
}

.event-details-wrapper {
  margin-top: 16px;
  border-radius: 12px;
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
  padding: 0;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}

.event-details {
  margin: 0;
  padding: 16px;
  overflow: auto;
  background: #0f172a;
  color: #e2e8f0;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  border-top: 1px dashed var(--border-color);
}

.event-details code {
  font-family: inherit;
}
</style>
