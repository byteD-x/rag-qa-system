<template>
  <el-container class="chat-view">
    <el-aside width="260px" class="chat-sidebar">
      <ChatSidebar @select-session="handleSessionSelect" />
    </el-aside>
    <el-main class="chat-main">
      <div v-if="!currentSessionId" class="empty-state">
        <el-empty description="请选择或新建一个会话开始对话" />
      </div>
      <div v-else class="chat-box">
        <ChatMessageList :messages="messages" />
        <ChatInputArea @send="handleSend" :disabled="loading" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ChatSidebar from '@/components/ChatSidebar.vue';
import ChatMessageList from '@/components/ChatMessageList.vue';
import ChatInputArea from '@/components/ChatInputArea.vue';
import { sendMessage } from '@/api/chat';
import type { ChatScope } from '@/api/chat';

const currentSessionId = ref<string>('');
const messages = ref<any[]>([]);
const loading = ref(false);

const buildChatErrorMessage = (error: any) => {
  const status = error?.response?.status;
  const detail =
    error?.response?.data?.error ||
    error?.response?.data?.message ||
    error?.response?.data?.detail;

  if (status === 400) {
    return detail || '请求参数或检索范围不合法，请检查后重试。';
  }
  if (status === 401) {
    return '登录已失效，请重新登录后再试。';
  }
  if (status === 404) {
    return detail || '会话或资源不存在，请刷新页面后重试。';
  }
  if (status === 405) {
    return '接口方法不匹配，请检查前后端路由配置。';
  }
  if (detail) {
    return String(detail);
  }
  return error?.message || '请求失败，请稍后重试。';
};

const handleSessionSelect = (id: string) => {
  currentSessionId.value = id;
  messages.value = []; // TBD: History support
};

const handleSend = async (question: string, scope: ChatScope) => {
  if (!currentSessionId.value) return;
  messages.value.push({ role: 'user', content: question });
  loading.value = true;
  try {
    const res = await sendMessage(currentSessionId.value, { question, scope });
    messages.value.push({ role: 'assistant', data: res });
  } catch (err: any) {
    messages.value.push({ role: 'assistant', error: buildChatErrorMessage(err) });
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.chat-view {
  height: 100%;
}
.chat-sidebar {
  border-right: 1px solid #ebeef5;
  background: #fafafa;
}
.chat-main {
  display: flex;
  flex-direction: column;
  padding: 0;
  height: 100%;
}
.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chat-box {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>
