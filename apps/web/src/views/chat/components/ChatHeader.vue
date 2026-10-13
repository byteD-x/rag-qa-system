<template>
  <header class="chat-header">
    <div class="header-title-area">
      <button
        ref="sidebarToggleButton"
        type="button"
        class="mobile-sidebar-toggle"
        aria-label="显示历史对话"
        @click="emit('toggle-sidebar')"
      >
        <el-icon><Grid /></el-icon>
      </button>
      <span class="chat-title">{{ chatStore.activeSessionTitle }}</span>
    </div>
    <div class="header-actions">
      <button
        v-if="chatStore.hasActiveFocusHint"
        type="button"
        class="action-chip action-chip--focus"
        @click="chatStore.clearFocusHint()"
      >
        <el-icon><Aim /></el-icon>
        <span>焦点: {{ chatStore.activeFocusLabel }}</span>
        <span class="focus-clear">清除</span>
      </button>

      <el-popover placement="bottom-end" :width="320" trigger="click">
        <template #reference>
          <button type="button" class="action-chip">
            <el-icon><Aim /></el-icon>
            <span>范围: {{ chatStore.scopeMode === 'all' ? '全局' : (chatStore.scopeMode === 'single' ? '单库' : '多库') }}</span>
          </button>
        </template>
        <div class="scope-popover">
          <div class="scope-popover-title">检索范围设置</div>
          <el-form label-position="top" size="default">
            <el-form-item label="范围模式">
              <el-radio-group v-model="chatStore.scopeMode" size="small" @change="chatStore.handleScopeModeChange" style="width: 100%">
                <el-radio-button value="single" style="flex: 1; text-align: center;">单库</el-radio-button>
                <el-radio-button value="multi" style="flex: 1; text-align: center;">多库</el-radio-button>
                <el-radio-button value="all" style="flex: 1; text-align: center;">全库</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="知识库">
              <el-select
                v-model="chatStore.selectedCorpusIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                filterable
                placeholder="选择知识库"
                size="small"
                style="width: 100%"
                @change="chatStore.handleCorpusChange"
              >
                <el-option
                  v-for="corpus in chatStore.kbCorpora"
                  :key="corpus.corpus_id"
                  :label="`${corpus.name} (${corpus.queryable_document_count}/${corpus.document_count})`"
                  :value="corpus.corpus_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="限定文档">
              <el-select
                v-model="chatStore.selectedDocumentIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                filterable
                :disabled="!chatStore.documentOptions.length"
                placeholder="可选"
                size="small"
                style="width: 100%"
              >
                <el-option
                  v-for="doc in chatStore.documentOptions"
                  :key="doc.document_id"
                  :label="`${doc.display_name} (${statusMeta(doc.status).label})`"
                  :value="doc.document_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="回答策略">
              <el-switch
                v-model="chatStore.allowCommonKnowledge"
                inline-prompt
                :active-value="true"
                :inactive-value="false"
                active-text="允许常识兜底"
                inactive-text="严格依据知识库"
                @change="chatStore.handleScopeModeChange"
              />
            </el-form-item>
          </el-form>
          <div class="scope-summary-box">
            <p>{{ selectedCorpusSummary }}</p>
          </div>
        </div>
      </el-popover>

      <el-popover placement="bottom-end" :width="280" trigger="click">
        <template #reference>
          <button type="button" class="action-chip" :class="{ 'is-agent': chatStore.executionMode === 'agent' }">
            <el-icon><Platform /></el-icon>
            <span>{{ chatStore.executionMode === 'agent' ? 'Agent 模式' : '标准 RAG' }}</span>
          </button>
        </template>
        <div class="scope-popover">
          <div class="scope-popover-title">执行模式</div>
          <el-radio-group v-model="chatStore.executionMode" size="small" @change="chatStore.handleExecutionModeChange" style="width: 100%;">
            <el-radio-button value="grounded" style="flex: 1;">标准 RAG</el-radio-button>
            <el-radio-button value="agent" style="flex: 1;">Agent 模式</el-radio-button>
          </el-radio-group>
          <p class="scope-summary" style="margin-top: 12px; font-size: 12px; color: var(--text-muted);">
            {{ chatStore.executionMode === 'agent' ? '允许助手多步思考、分解问题并多次检索，适合解决复杂问题。' : '基于检索到的片段直接生成回答，速度较快。' }}
          </p>
        </div>
      </el-popover>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { Aim, Grid, Platform } from '@element-plus/icons-vue';
import { useChatStore } from '@/store/chat';
import { statusMeta } from '@/utils/status';

const chatStore = useChatStore();
const emit = defineEmits<{ (e: 'toggle-sidebar'): void }>();
const sidebarToggleButton = ref<HTMLButtonElement | null>(null);

defineExpose({
  focusSidebarToggle: () => sidebarToggleButton.value?.focus()
});

const selectedCorpusSummary = computed(() => {
  if (chatStore.scopeMode === 'all' && !chatStore.selectedCorpusIds.length) {
    return '当前未手动限制知识库，默认在全部可用知识库内检索。';
  }

  const names = chatStore.selectedCorpusIds
    .map((id) => chatStore.kbCorpora.find((item: any) => item.corpus_id === id)?.name)
    .filter(Boolean)
    .join('、');

  if (!names) {
    return '尚未选择知识库。';
  }

  if (!chatStore.selectedDocumentIds.length) {
    return `已选择 ${names}，当前未缩圈到具体文档。`;
  }

  return `已选择 ${names}，并限制到 ${chatStore.selectedDocumentIds.length} 个具体文档。`;
});
</script>

<style scoped>
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-panel);
  z-index: 10;
}

.header-title-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.mobile-sidebar-toggle {
  display: none;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.action-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
  cursor: pointer;
}

@media (max-width: 768px) {
  .mobile-sidebar-toggle {
    display: inline-flex;
  }
}

.action-chip:hover {
  background: var(--bg-panel-muted);
  color: var(--text-primary);
}

.action-chip.is-agent {
  color: #059669;
  border-color: #a7f3d0;
  background: #ecfdf5;
}

.action-chip--focus {
  color: #275dad;
  border-color: #bfd7ff;
  background: #f5f9ff;
}

.focus-clear {
  color: var(--text-muted);
  font-size: 11px;
}

.scope-popover-title {
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.scope-summary-box {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-muted);
}
</style>
