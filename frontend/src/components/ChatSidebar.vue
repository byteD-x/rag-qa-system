<template>
  <div class="chat-sidebar-inner">
    <div class="sidebar-header">
      <el-button type="primary" class="new-session-btn" @click="handleCreate">
        <el-icon class="el-icon--left"><Plus /></el-icon>
        新建会话 / New Chat
      </el-button>
    </div>
    <div class="session-list-wrapper">
      <ul class="session-list" v-loading="loading">
        <li 
          v-for="session in sessions" 
          :key="session.id" 
          class="session-item"
          :class="{ active: currentId === session.id }"
          @click="select(session.id)"
        >
          <el-icon class="session-icon" :size="16"><ChatLineRound /></el-icon>
          <span class="title">{{ session.title || '新对话' }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { createSession, getSessions } from '@/api/chat';
import type { ChatSession } from '@/api/chat';
import { ChatLineRound, Plus } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

const emit = defineEmits(['select-session']);
const sessions = ref<ChatSession[]>([]);
const currentId = ref<string>('');
const loading = ref(false);

const loadSessions = async () => {
  loading.value = true;
  try {
    const res: any = await getSessions();
    sessions.value = res.items || res || [];
  } catch (err) {
    // 忽略预检加载失败
  } finally {
    loading.value = false;
  }
};

const handleCreate = async () => {
  try {
    const res: any = await createSession('新对话 / New Chat');
    sessions.value.unshift(res);
    select(res.id);
  } catch (err) {
    ElMessage.error('创建会话失败');
  }
};

const select = (id: string) => {
  currentId.value = id;
  emit('select-session', id);
};

onMounted(() => {
  loadSessions();
});
</script>

<style scoped>
.chat-sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border-color-light);
}
.sidebar-header {
  padding: 16px;
}
.new-session-btn {
  width: 100%;
  border-radius: 12px;
  height: 44px;
  font-weight: 500;
  transition: all var(--el-transition-duration);
  box-shadow: var(--shadow-sm);
}
.new-session-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-blue);
}
.session-list-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 16px;
}
/* hide scrollbar for clean look */
.session-list-wrapper::-webkit-scrollbar {
  width: 4px;
}
.session-list-wrapper::-webkit-scrollbar-thumb {
  background-color: transparent;
  border-radius: 4px;
}
.session-list-wrapper:hover::-webkit-scrollbar-thumb {
  background-color: var(--border-color);
}
.session-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.session-item {
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-regular);
  transition: all 0.2s ease;
  font-size: 14px;
}
.session-item:hover {
  background-color: var(--bg-base);
  color: var(--text-primary);
}
.session-item.active {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 500;
}
.session-icon {
  flex-shrink: 0;
  opacity: 0.7;
}
.session-item.active .session-icon {
  opacity: 1;
}
.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
