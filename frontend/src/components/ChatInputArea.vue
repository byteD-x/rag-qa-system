<template>
  <div class="chat-input-area">
    <div class="config-toolbar">
      <el-switch v-model="scope.allow_common_knowledge" active-text="允许常识兜底" />
      <el-select v-model="allCorpusMode" class="toolbar-select">
        <el-option label="全库检索" value="all" />
        <el-option label="单库检索" value="single" />
        <el-option label="多库跨搜" value="multi" />
      </el-select>

      <el-select
        v-if="allCorpusMode === 'single'"
        v-model="selectedSingleCorpus"
        placeholder="请选择知识库"
        class="corpus-select"
      >
        <el-option
          v-for="item in corpora"
          :key="item.id"
          :label="item.name"
          :value="item.id"
        />
      </el-select>

      <el-select
        v-if="allCorpusMode === 'multi'"
        v-model="selectedMultiCorpora"
        multiple
        collapse-tags
        placeholder="请选择多个知识库"
        class="corpus-select multi"
      >
        <el-option
          v-for="item in corpora"
          :key="item.id"
          :label="item.name"
          :value="item.id"
        />
      </el-select>
    </div>
    <div class="input-wrapper">
      <el-input
        v-model="question"
        type="textarea"
        resize="none"
        :rows="3"
        placeholder="Ctrl+Enter 发送 / 请选择知识库域..."
        :disabled="disabled"
        @keydown.ctrl.enter="handleSend"
        class="chat-textarea"
      />
      <div class="input-actions">
        <el-button 
          type="primary" 
          class="send-btn"
          :disabled="disabled || !question.trim()" 
          @click="handleSend"
        >
          <el-icon :size="20"><Position /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import type { ChatScope } from '@/api/chat';
import { getCorpora } from '@/api/corpora';
import { ElMessage } from 'element-plus';
import { Position } from '@element-plus/icons-vue';

const props = defineProps<{ disabled: boolean }>();
const emit = defineEmits(['send']);

const question = ref('');
const scope = reactive<ChatScope>({
  mode: 'single',
  corpus_ids: [],
  allow_common_knowledge: false
});

const corpora = ref<any[]>([]);
const allCorpusMode = ref<'all' | 'single' | 'multi'>('single');
const selectedSingleCorpus = ref<string>('');
const selectedMultiCorpora = ref<string[]>([]);

const loadCorpora = async () => {
  try {
    const res: any = await getCorpora();
    corpora.value = res.items || res || [];
    if (corpora.value.length > 0) {
      selectedSingleCorpus.value = corpora.value[0].id;
    }
  } catch (err) {
    console.error('Failed to load corpora', err);
  }
};

onMounted(() => {
  loadCorpora();
});

const handleSend = () => {
  if (!question.value.trim() || props.disabled) return;
  
  const targetScope: ChatScope = {
    mode: 'single',
    corpus_ids: [],
    document_ids: [],
    allow_common_knowledge: scope.allow_common_knowledge
  };
  
  if (allCorpusMode.value === 'all') {
    targetScope.corpus_ids = corpora.value.map(c => c.id);
  } else if (allCorpusMode.value === 'single') {
    if (selectedSingleCorpus.value) {
      targetScope.corpus_ids = [selectedSingleCorpus.value];
    }
  } else if (allCorpusMode.value === 'multi') {
    targetScope.corpus_ids = [...selectedMultiCorpora.value];
  }
  
  if (targetScope.corpus_ids.length === 0) {
    ElMessage.warning('知识库选择为空，无法发送对话');
    return;
  }
  if (allCorpusMode.value === 'multi' && targetScope.corpus_ids.length < 2) {
    ElMessage.warning('多库跨搜模式下此至少需要选择两个知识库');
    return;
  }
  
  targetScope.mode = targetScope.corpus_ids.length >= 2 ? 'multi' : 'single';
  
  emit('send', question.value.trim(), targetScope);
  question.value = '';
};
</script>

<style scoped>
.chat-input-area {
  padding: 20px 40px 30px;
  background: transparent;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.config-toolbar {
  display: flex;
  align-items: center;
  padding: 0 10px;
}
.toolbar-select {
  width: 120px;
  margin-left: 15px;
}
.corpus-select {
  width: 200px;
  margin-left: 15px;
}
.corpus-select.multi {
  width: 240px;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border-radius: 16px;
  padding: 12px;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-color-light);
  transition: box-shadow var(--el-transition-duration) ease;
}
.input-wrapper:focus-within {
  box-shadow: var(--shadow-lg);
  border-color: var(--el-color-primary-light-5);
}

:deep(.chat-textarea .el-textarea__inner) {
  box-shadow: none !important;
  background: transparent !important;
  padding: 8px !important;
  font-size: 15px;
  color: var(--text-primary);
  line-height: 1.6;
}
:deep(.chat-textarea .el-textarea__inner::placeholder) {
  color: var(--text-placeholder);
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding-right: 8px;
}
.send-btn {
  height: 40px;
  width: 48px;
  border-radius: 12px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
  transition: all 0.2s ease;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--shadow-blue);
}
</style>
