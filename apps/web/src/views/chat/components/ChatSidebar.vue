<template>
  <aside class="session-sidebar" :aria-hidden="!props.open" :inert="!props.open">
    <div class="sidebar-header">
      <button type="button" class="new-chat-btn" @click="startNewChat">
        <el-icon><Plus /></el-icon>
        <span>开启新对话</span>
      </button>
      <button ref="closeButton" type="button" class="sidebar-close-btn" aria-label="关闭历史对话" @click="emit('close')">
        <el-icon><Close /></el-icon>
      </button>
    </div>
    
    <div class="sidebar-content">
      <el-input v-if="chatStore.sessions.length" v-model="search" data-testid="session-search" clearable placeholder="搜索标题或最近问题" />
      <div v-if="!chatStore.sessions.length" class="session-empty">
        <span>暂无历史对话</span>
      </div>
      <div v-else-if="!filteredSessions.length" class="session-empty">
        <span>没有匹配的历史对话</span>
      </div>
      <div v-else class="session-list">
        <div class="session-group-title">最近对话</div>
        <button
          v-for="session in filteredSessions"
          :key="session.id"
          type="button"
          class="session-item"
          :class="{ active: session.id === chatStore.activeSessionId }"
          @click="selectSession(session)"
        >
          <el-icon class="session-icon"><ChatLineRound /></el-icon>
          <span class="session-title" :title="session.title || '未命名对话'">
            {{ session.title || '未命名对话' }}
          </span>
          <span v-if="formatUpdatedAt(session.updated_at)" class="session-date">{{ formatUpdatedAt(session.updated_at) }}</span>
        </button>
      </div>
    </div>

    <div class="sidebar-footer" v-if="chatStore.activeSessionId">
      <el-dropdown placement="top" trigger="click">
        <button class="session-more-btn">
          <el-icon><Setting /></el-icon> 会话选项
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="chatStore.renameActiveSession">
              重命名会话
            </el-dropdown-item>
            <el-dropdown-item divided type="danger" @click="chatStore.handleDeleteSession">
              删除会话
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useChatStore } from '@/store/chat';
import { Close, Plus, ChatLineRound, Setting } from '@element-plus/icons-vue';

const chatStore = useChatStore();
const props = withDefaults(defineProps<{ open?: boolean }>(), { open: true });
const emit = defineEmits<{ (e: 'close'): void }>();
const closeButton = ref<HTMLButtonElement | null>(null);
const search = ref('');
const filteredSessions = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return chatStore.sessions;
  return chatStore.sessions.filter((session: any) =>
    [session.title, session.last_question, session.last_user_question]
      .some((value) => String(value || '').toLowerCase().includes(query))
  );
});
const formatUpdatedAt = (value: unknown) => {
  if (!value) return '';
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('zh-CN');
};

defineExpose({
  focusCloseButton: () => closeButton.value?.focus()
});

function startNewChat() {
  chatStore.startDraftSession();
  emit('close');
}

function selectSession(session: any) {
  void chatStore.selectSession(session);
  emit('close');
}
</script>

<style scoped>
.session-sidebar {
  width: 280px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 16px;
  display: flex;
  gap: 8px;
}

.new-chat-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-weight: 500;
  font-size: var(--text-body);
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background-color var(--transition-fast);
}

.sidebar-close-btn {
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

@media (hover: hover) and (pointer: fine) {
  .new-chat-btn:hover {
    border-color: var(--blue-500);
    color: var(--blue-600);
    background: var(--blue-50);
  }
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 16px;
}

.session-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-caption);
  margin-top: 40px;
}

.session-group-title {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-muted);
  margin: 12px 0 8px 4px;
  text-transform: uppercase;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--text-regular);
  font-size: var(--text-body);
  cursor: pointer;
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

@media (hover: hover) and (pointer: fine) {
  .session-item:hover {
    background: var(--bg-panel-muted);
  }
}

.session-item.active {
  background: var(--blue-50);
  color: var(--text-primary);
  font-weight: 500;
}

.session-icon {
  font-size: var(--text-body);
  opacity: 0.6;
}

.session-title {
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-date {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: var(--text-caption);
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(0,0,0,0.05);
}

.session-more-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: var(--text-caption);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

@media (hover: hover) and (pointer: fine) {
  .session-more-btn:hover {
    background: var(--bg-panel-muted);
    color: var(--text-primary);
  }
}

@media (max-width: 768px) {
  .session-sidebar {
    position: absolute;
    z-index: 100;
    height: 100%;
    transform: translateX(-100%);
    transition: transform var(--transition-fast);
  }
  .sidebar-close-btn {
    display: inline-flex;
  }
  .chat-workspace.show-sidebar .session-sidebar {
    transform: translateX(0);
    transition: transform 200ms var(--ease-enter);
  }
}
</style>
