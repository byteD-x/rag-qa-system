<template>
  <div class="chat-message-list">
    <div 
      v-for="(msg, index) in messages" 
      :key="index"
      :class="['message-row', msg.role]"
    >
      <div class="avatar">
        <el-icon v-if="msg.role === 'user'"><User /></el-icon>
        <el-icon v-else><Service /></el-icon>
      </div>
      <div class="content">
        <template v-if="msg.role === 'user'">
          {{ msg.content }}
        </template>
        <template v-else>
          <div v-if="msg.error" class="error-text">{{ msg.error }}</div>
          <RagMessageRenderer v-else-if="msg.data" :answer="msg.data" />
          <div v-else>思考中...</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { User, Service } from '@element-plus/icons-vue';
import RagMessageRenderer from './RagMessageRenderer.vue';

defineProps<{ messages: any[] }>();
</script>

<style scoped>
.chat-message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.message-row {
  display: flex;
  gap: 16px;
  animation: slideUpFade 0.3s ease-out;
}
.message-row.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--text-secondary);
  flex-shrink: 0;
  border: 1px solid var(--border-color-light);
}
.message-row.user .avatar {
  background: var(--el-color-primary);
  color: white;
  border-color: var(--el-color-primary);
}
.content {
  max-width: 75%;
  padding: 16px 20px;
  border-radius: 18px;
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  line-height: 1.6;
  font-size: 15px;
  color: var(--text-primary);
  border: 1px solid var(--border-color-light);
}
.message-row.user .content {
  background: var(--el-color-primary);
  color: white;
  border-color: var(--el-color-primary);
  border-bottom-right-radius: 4px;
  box-shadow: var(--shadow-blue);
}
.message-row:not(.user) .content {
  border-top-left-radius: 4px;
}
.error-text {
  color: var(--el-color-danger);
}
</style>
