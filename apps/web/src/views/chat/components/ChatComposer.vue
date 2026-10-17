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
        @keydown.enter.exact.prevent="handleAsk"
      />
      <button
        type="button"
        class="modern-send-btn"
        :class="{ 'is-active': question.trim().length > 0 || chatStore.asking }"
        :disabled="!chatStore.asking && !question.trim()"
        :aria-label="chatStore.asking ? '停止回答' : '发送问题'"
        @click="chatStore.asking ? chatStore.stopStreaming() : handleAsk()"
      >
        <el-icon v-if="chatStore.asking"><Close /></el-icon>
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
import { Position, Close } from '@element-plus/icons-vue';
import { useChatStore } from '@/store/chat';

const chatStore = useChatStore();
const question = ref('');

const emit = defineEmits<{
  (e: 'ask', q: string, done: (accepted: boolean) => void): void;
}>();

function handleAsk(event?: KeyboardEvent) {
  // 输入法组合过程中的 Enter（含 keyCode 229 的旧实现）不当作发送
  if (event?.isComposing || event?.keyCode === 229) {
    return;
  }
  if (!question.value.trim() || chatStore.asking) {
    return;
  }
  // 仅在 store 受理本次提问后清空输入，避免被拒绝时吞掉用户输入
  emit('ask', question.value, (accepted: boolean) => {
    if (accepted) {
      question.value = '';
    }
  });
}

// 供路由预设等外部来源回填问题
defineExpose({
  setQuestion: (val: string) => { question.value = val; }
});
</script>

<style scoped>
.composer-container {
  flex-shrink: 0;
  padding: 0 24px 24px;
  background: var(--bg-panel);
}

.composer-inner {
  max-width: 800px;
  margin: 0 auto;
  position: relative;
  background: var(--bg-panel);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  padding: 4px;
}

.modern-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 14px 48px 14px 16px;
  font-size: var(--text-body);
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
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  color: var(--el-color-white);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-body);
  transition: background-color var(--transition-fast), color var(--transition-fast), transform 120ms var(--ease-enter);
}

.modern-send-btn.is-active {
  background: var(--blue-600);
  cursor: pointer;
}

.modern-send-btn.is-active:active {
  transform: scale(0.94);
}

.modern-send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.composer-footer {
  text-align: center;
  font-size: var(--text-caption);
  color: var(--text-muted);
  margin-top: 12px;
}

@media (max-width: 768px) {
  .composer-container {
    padding: 8px 12px calc(8px + env(safe-area-inset-bottom));
  }
}
</style>
