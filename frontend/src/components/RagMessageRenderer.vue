<template>
  <div class="rag-renderer">
    <div v-if="answer.answer_sentences && answer.answer_sentences.length > 0">
      <p v-for="(sentence, i) in answer.answer_sentences" :key="i" class="sentence-line">
        {{ sentence.text }}
        <template v-if="sentence.evidence_type === 'common_knowledge'">
          <el-tag size="small" type="warning" class="knowledge-tag">非资料证据</el-tag>
        </template>
        <template v-else-if="sentence.evidence_type === 'source' && sentence.citation_ids">
          <el-popover
            v-for="cId in sentence.citation_ids"
            :key="cId"
            placement="top"
            title="引用来源"
            :width="300"
            trigger="click"
          >
            <template #reference>
              <sup class="citation-badge">[{{ citationLabel(cId) }}]</sup>
            </template>
            <div v-if="getCitation(cId)" class="citation-detail">
              <p><strong>文件:</strong> {{ getCitation(cId).file_name }}</p>
              <p v-if="getCitation(cId).page_or_loc"><strong>位置:</strong> {{ getCitation(cId).page_or_loc }}</p>
              <p><strong>原文:</strong> {{ getCitation(cId).snippet }}</p>
            </div>
            <div v-else class="citation-detail">
              <p>暂无详细来源信息</p>
            </div>
          </el-popover>
        </template>
      </p>
    </div>
    <div v-else class="raw-answer">
      {{ answer.content || answer }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ answer: any }>();

const getCitation = (id: string) => {
  if (!props.answer.citations) return null;
  return props.answer.citations.find((c: any) => c.citation_id === id) || null;
};

const citationIndexMap = computed(() => {
  const map = new Map<string, number>();
  const list = Array.isArray(props.answer?.citations) ? props.answer.citations : [];
  for (let idx = 0; idx < list.length; idx += 1) {
    const id = String(list[idx]?.citation_id || '');
    if (id) {
      map.set(id, idx + 1);
    }
  }
  return map;
});

const citationLabel = (id: string) => {
  return citationIndexMap.value.get(id) ?? id;
};
</script>

<style scoped>
.rag-renderer {
  font-size: 15px;
  line-height: 1.7;
  color: inherit;
}
.sentence-line {
  margin: 0 0 8px 0;
}
.knowledge-tag {
  margin-left: 4px;
  transform: scale(0.9);
  vertical-align: middle;
  border-radius: 12px;
}
.citation-badge {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  padding: 2px 6px;
  border-radius: 8px;
  cursor: pointer;
  margin-left: 4px;
  font-weight: 600;
  font-size: 11px;
  transition: all 0.2s ease;
}
.citation-badge:hover {
  background: var(--el-color-primary);
  color: white;
}
.citation-detail {
  font-size: 13px;
  color: var(--text-regular);
  max-height: 240px;
  overflow-y: auto;
  line-height: 1.6;
}
.citation-detail strong {
  color: var(--text-primary);
}
.citation-detail p {
  margin: 6px 0;
}
</style>
