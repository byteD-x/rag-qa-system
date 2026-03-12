<template>
  <div class="composer-container">
    <div class="composer-inner">
      <el-input
        v-model="question"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 6 }"
        placeholder="输入您的问题，Enter 发送，Shift + Enter 换行"
        resize="none"
        class="modern-input"
        @keydown.ctrl.enter.prevent="handleAsk"
        @keydown.enter.exact.prevent="handleAsk"
      />
      <button class="modern-send-btn" :class="{ 'is-active': question.trim().length > 0 }" :disabled="chatStore.asking" @click="handleAsk">
        <el-icon v-if="chatStore.asking" class="is-loading"><Loading /></el-icon>
        <el-icon v-else><Position /></el-icon>
      </button>
    </div>
    <div class="composer-footer">
      内容由 AI 生成，可能存在错误，请核实重要信息。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Position, Loading } from '@element-plus/icons-vue';
import { useChatStore } from '@/store/chat';

const chatStore = useChatStore();
const question = ref('');

const emit = defineEmits<{
  (e: 'ask', q: string): void;
}>();

function handleAsk() {
  if (question.value.trim() && !chatStore.asking) {
    emit('ask', question.value);
    question.value = '';
  }
}

// Expose setQuestion for suggested prompts
defineExpose({
  setQuestion: (val: string) => { question.value = val; }
});
</script>

<style scoped>
.composer-container {
  padding: 0 24px 24px;
  background: linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,1) 20%);
}

.composer-inner {
  max-width: 800px;
  margin: 0 auto;
  position: relative;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  border: 1px solid var(--border-color);
  padding: 4px;
}

.modern-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 14px 48px 14px 16px;
  font-size: 15px;
  line-height: 1.5;
  resize: none;
}

.modern-input :deep(.el-textarea__inner:focus) {
  box-shadow: none !important;
}

.modern-send-btn {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #e5e5e5;
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.2s;
}

.modern-send-btn.is-active {
  background: var(--blue-600);
  cursor: pointer;
}

.modern-send-btn.is-active:hover {
  background: var(--blue-700);
}

.composer-footer {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 12px;
}
</style>