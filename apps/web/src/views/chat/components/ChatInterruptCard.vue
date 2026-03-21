<template>
  <section class="interrupt-card">
    <div class="interrupt-card__head">
      <span class="interrupt-card__kind">{{ kindLabel }}</span>
      <strong>{{ interrupt.title }}</strong>
    </div>
    <div v-if="interrupt.subject?.summary" class="interrupt-card__subject">{{ interrupt.subject.summary }}</div>
    <p class="interrupt-card__detail">{{ interrupt.detail }}</p>

    <el-radio-group v-if="interrupt.options?.length" v-model="selectedOptionId" class="interrupt-card__options">
      <label
        v-for="option in interrupt.options"
        :key="option.id"
        class="interrupt-option"
        :class="{ 'interrupt-option--recommended': option.id === interrupt.recommended_option_id }"
      >
        <el-radio :label="option.id">
          <span class="interrupt-option__label">{{ option.label }}</span>
        </el-radio>
        <div v-if="option.badges?.length" class="interrupt-option__badges">
          <span v-for="badge in option.badges" :key="`${option.id}:${badge}`" class="interrupt-option__badge">{{ badge }}</span>
        </div>
        <span class="interrupt-option__desc">{{ option.description }}</span>
      </label>
    </el-radio-group>

    <el-input
      v-if="interrupt.allow_free_text"
      v-model="freeText"
      type="textarea"
      :rows="3"
      resize="none"
      :placeholder="interrupt.fallback_prompt || '补充更多上下文后继续'"
    />

    <div class="interrupt-card__actions">
      <el-button
        type="primary"
        size="small"
        :loading="Boolean(message.submitting)"
        :disabled="Boolean(message.resolved)"
        @click="handleSubmit"
      >
        {{ message.resolved ? '已处理' : '继续' }}
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useChatStore } from '@/store/chat';

const props = defineProps<{
  message: any;
}>();

const chatStore = useChatStore();
const interrupt = computed(() => props.message?.interrupt || {});
const selectedOptionId = ref(String(interrupt.value?.recommended_option_id || ''));
const freeText = ref('');

watch(interrupt, (value) => {
  selectedOptionId.value = String(value?.recommended_option_id || '');
  freeText.value = '';
});

const kindLabel = computed(() => {
  const kind = String(interrupt.value?.kind || '');
  if (kind === 'time_ambiguity') return '时间确认';
  if (kind === 'version_conflict') return '版本确认';
  if (kind === 'visual_ambiguity') return '截图确认';
  if (kind === 'scope_ambiguity') return '范围确认';
  if (kind === 'insufficient_evidence') return '补充信息';
  return '需要确认';
});

async function handleSubmit() {
  const payload: Record<string, any> = {};
  if (selectedOptionId.value) {
    payload.selected_option_ids = [selectedOptionId.value];
  }
  if (freeText.value.trim()) {
    payload.free_text = freeText.value.trim();
  }
  await chatStore.resumeInterrupt(props.message, payload);
}
</script>

<style scoped>
.interrupt-card {
  padding: 16px;
  border: 1px solid #dbe3f4;
  border-radius: 14px;
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
}

.interrupt-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.interrupt-card__kind {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #e0ecff;
  color: #275dad;
  font-size: 12px;
}

.interrupt-card__detail {
  margin: 0 0 14px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.interrupt-card__subject {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.interrupt-card__options {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.interrupt-option {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #dfe7f3;
  border-radius: 10px;
  background: #fff;
}

.interrupt-option--recommended {
  border-color: #8bb6ff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.interrupt-option__label {
  font-weight: 600;
  color: var(--text-primary);
}

.interrupt-option__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 24px;
}

.interrupt-option__badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4ff;
  color: #275dad;
  font-size: 11px;
}

.interrupt-option__desc {
  padding-left: 24px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.interrupt-card__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
