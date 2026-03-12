<template>
  <aside class="session-sidebar">
    <div class="sidebar-header">
      <button type="button" class="new-chat-btn" @click="chatStore.startDraftSession">
        <el-icon><Plus /></el-icon>
        <span>开启新对话</span>
      </button>
    </div>
    
    <div class="sidebar-content">
      <div v-if="!chatStore.sessions.length" class="session-empty">
        <span>暂无历史对话</span>
      </div>
      <div v-else class="session-list">
        <div class="session-group-title">最近对话</div>
        <button
          v-for="session in chatStore.sessions"
          :key="session.id"
          type="button"
          class="session-item"
          :class="{ active: session.id === chatStore.activeSessionId }"
          @click="chatStore.selectSession(session)"
        >
          <el-icon class="session-icon"><ChatLineRound /></el-icon>
          <span class="session-title" :title="session.title || '未命名对话'">
            {{ session.title || '未命名对话' }}
          </span>
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
import { useChatStore } from '@/store/chat';
import { Plus, ChatLineRound, Setting } from '@element-plus/icons-vue';

const chatStore = useChatStore();
</script>

<style scoped>
.session-sidebar {
  width: 280px;
  background: #f9f9fb;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.3s ease;
}

.sidebar-header {
  padding: 16px;
}

.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}

.new-chat-btn:hover {
  border-color: var(--blue-500);
  color: var(--blue-600);
  background: var(--blue-50);
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 16px;
}

.session-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 40px;
}

.session-group-title {
  font-size: 12px;
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
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.session-item:hover {
  background: #ececf1;
}

.session-item.active {
  background: #e5e7eb;
  color: var(--text-primary);
  font-weight: 500;
}

.session-icon {
  font-size: 16px;
  opacity: 0.6;
}

.session-title {
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  font-size: 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.session-more-btn:hover {
  background: #ececf1;
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .session-sidebar {
    position: absolute;
    z-index: 100;
    height: 100%;
    transform: translateX(-100%);
  }
  .chat-workspace.show-sidebar .session-sidebar {
    transform: translateX(0);
  }
}
</style>