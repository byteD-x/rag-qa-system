<template>
  <div class="page-shell">
    <PageHeaderCompact title="切片管理" :subtitle="document?.file_name || '加载中...'">
      <template #actions>
        <el-button plain @click="router.back()">返回</el-button>
        <el-switch v-model="showDisabled" active-text="显示已禁用" @change="loadChunks" />
      </template>
    </PageHeaderCompact>

    <div class="chunks-container">
      <LoadingState v-if="loading && !chunks.length" label="加载切片中…" />

      <EnhancedEmpty
        v-else-if="!chunks.length"
        variant="document"
        title="暂无切片"
        description="该文档暂时没有切片或切片正在生成中"
      />

      <div v-else class="chunk-list">
        <div
          v-for="(chunk, index) in chunks"
          :key="chunk.chunk_id"
          class="chunk-card"
          :class="{ 'is-disabled': chunk.disabled, 'is-updated': updatedChunkIds.includes(chunk.chunk_id) }"
        >
          <div class="chunk-header">
            <span class="chunk-id">#{{ index + 1 }}</span>
            <div class="chunk-actions">
              <el-button size="small" type="primary" plain @click="openEditDialog(chunk)">编辑</el-button>
              <el-button size="small" plain @click="openSplitDialog(chunk)">拆分</el-button>
              <el-button v-if="canMergeWithPrevious(chunk, index)" size="small" plain @click="mergeWithPrevious(chunk, chunks[index - 1], index)">向上合并</el-button>
              <el-button
                size="small"
                :type="chunk.disabled ? 'success' : 'danger'"
                plain
                @click="toggleDisable(chunk)"
              >
                {{ chunk.disabled ? '启用' : '禁用' }}
              </el-button>
            </div>
          </div>
          <div class="chunk-body">
            <p>{{ chunk.text_content }}</p>
          </div>
          <div v-if="chunk.manual_note || chunk.disabled_reason" class="chunk-footer">
            <el-tag v-if="chunk.disabled_reason" type="danger" size="small">禁用原因: {{ chunk.disabled_reason }}</el-tag>
            <el-tag v-if="chunk.manual_note" type="info" size="small">备注: {{ chunk.manual_note }}</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Dialog -->
    <el-dialog v-model="editDialogVisible" :title="editDialogTitle" width="600px">
      <el-form label-position="top">
        <el-form-item label="切片内容">
          <el-input v-model="editingChunk.text_content" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item label="人工备注">
          <el-input v-model="editingChunk.manual_note" placeholder="可在此记录修改原因..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveChunkEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Split Dialog -->
    <el-dialog v-model="splitDialogVisible" :title="splitDialogTitle" width="600px">
      <div class="split-intro">请在下方填入拆分后的文本片段，每段作为一个新切片。</div>
      <div v-if="splitTargetChunk?.disabled" class="split-note">该切片当前已停用：拆分后新切片会恢复启用，重新参与检索。</div>
      <div class="split-parts">
        <div v-for="(_, i) in splitParts" :key="i" class="split-part">
          <el-input v-model="splitParts[i]" type="textarea" :rows="3" />
          <el-button type="danger" plain :icon="Delete" aria-label="删除此片段" @click="splitParts.splice(i, 1)" />
        </div>
        <el-button type="primary" plain :icon="Plus" class="split-add" @click="splitParts.push('')">增加拆分片段</el-button>
      </div>
      <template #footer>
        <el-button @click="splitDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveChunkSplit">确认拆分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Delete, Plus } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { getKBDocument, getKBChunks, updateKBChunk, splitKBChunk, mergeKBChunks } from '@/api/kb';
import { isHandledRequestError } from '@/api/request';

const route = useRoute();
const router = useRouter();

const documentId = String(route.params.id);
const document = ref<any>(null);
const chunks = ref<any[]>([]);
const loading = ref(false);
const showDisabled = ref(false);

const editDialogVisible = ref(false);
const saving = ref(false);
const editingChunk = ref<any>({});

const splitDialogVisible = ref(false);
const splitTargetChunk = ref<any>(null);
const splitParts = ref<string[]>([]);

// 写操作后只对受影响的切片做一次落点反馈，列表本身不重建（滚动位置保持）
const updatedChunkIds = ref<string[]>([]);
let updatedFlashTimer: number | undefined;

const flashUpdatedChunks = (chunkIds: string[]) => {
  const visibleIds = new Set(chunks.value.map((item) => item.chunk_id));
  updatedChunkIds.value = Array.from(new Set(chunkIds)).filter((id) => visibleIds.has(id));
  if (!updatedChunkIds.value.length) {
    return;
  }
  window.clearTimeout(updatedFlashTimer);
  updatedFlashTimer = window.setTimeout(() => {
    updatedChunkIds.value = [];
  }, 1200);
};

// split / merge 返回全量 items（含停用切片），按当前开关过滤后就地替换列表
const replaceChunks = (items: any[], focusIds: string[] = []) => {
  const nextItems = items.filter((item) => showDisabled.value || !item.disabled);
  const previousIds = new Set(chunks.value.map((item) => item.chunk_id));
  chunks.value = nextItems;
  const landedIds = focusIds.length
    ? focusIds
    : nextItems.filter((item) => !previousIds.has(item.chunk_id)).map((item) => item.chunk_id);
  flashUpdatedChunks(landedIds);
};

// PATCH 只返回单条切片，就地把这一条替换掉
const patchChunk = (updated: any) => {
  const chunkId = String(updated?.chunk_id || '');
  if (!chunkId) {
    loadChunks();
    return;
  }
  if (!showDisabled.value && updated.disabled) {
    chunks.value = chunks.value.filter((item) => item.chunk_id !== chunkId);
    return;
  }
  if (!chunks.value.some((item) => item.chunk_id === chunkId)) {
    loadChunks();
    return;
  }
  const next = { ...updated };
  delete next.vector_index;
  chunks.value = chunks.value.map((item) => (item.chunk_id === chunkId ? { ...item, ...next } : item));
  flashUpdatedChunks([chunkId]);
};

// 后端只接受同一小节内 chunk_index 相邻的合并，跨小节或中间隔着被隐藏的停用切片时不给入口
const canMergeWithPrevious = (chunk: any, index: number) => {
  if (index <= 0) {
    return false;
  }
  const previous = chunks.value[index - 1];
  if (!previous || previous.section_id !== chunk.section_id) {
    return false;
  }
  return Number(previous.chunk_index) + 1 === Number(chunk.chunk_index);
};

const describeChunk = (chunk: any) => {
  if (!chunk) {
    return '';
  }
  const index = chunks.value.findIndex((item) => item.chunk_id === chunk.chunk_id);
  return [index >= 0 ? `#${index + 1}` : '', chunk.section_title || ''].filter(Boolean).join(' · ');
};

const editDialogTitle = computed(() => {
  const label = describeChunk(editingChunk.value);
  return label ? `编辑切片 ${label}` : '编辑切片';
});

const splitDialogTitle = computed(() => {
  const label = describeChunk(splitTargetChunk.value);
  return label ? `拆分切片 ${label}` : '拆分切片';
});

const loadDoc = async () => {
  document.value = await getKBDocument(documentId);
};

const loadChunks = async () => {
  loading.value = true;
  try {
    const res: any = await getKBChunks(documentId, showDisabled.value);
    chunks.value = res.items || [];
  } finally {
    loading.value = false;
  }
};

const openEditDialog = (chunk: any) => {
  editingChunk.value = { ...chunk };
  editDialogVisible.value = true;
};

const saveChunkEdit = async () => {
  saving.value = true;
  try {
    const updated: any = await updateKBChunk(editingChunk.value.chunk_id, {
      text_content: editingChunk.value.text_content,
      manual_note: editingChunk.value.manual_note
    });
    patchChunk(updated);
    ElMessage.success('保存成功');
    editDialogVisible.value = false;
  } finally {
    saving.value = false;
  }
};

const toggleDisable = async (chunk: any) => {
  let disabledReason = '';
  if (!chunk.disabled) {
    try {
      const { value } = await ElMessageBox.prompt('请输入禁用原因（选填）', '禁用切片', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      });
      disabledReason = value || '';
    } catch {
      return;
    }
  }

  try {
    const updated: any = await updateKBChunk(chunk.chunk_id, {
      disabled: !chunk.disabled,
      disabled_reason: disabledReason
    });
    patchChunk(updated);
    ElMessage.success(chunk.disabled ? '已启用' : '已禁用');
  } catch (e) {
    if (!isHandledRequestError(e)) ElMessage.error('操作失败');
  }
};

const openSplitDialog = (chunk: any) => {
  splitTargetChunk.value = chunk;
  // Initialize with the original content as one part, or rough split by newlines
  const parts = chunk.text_content.split('\n\n').filter((s: string) => s.trim() !== '');
  splitParts.value = parts.length > 0 ? parts : [chunk.text_content];
  splitDialogVisible.value = true;
};

const saveChunkSplit = async () => {
  const validParts = splitParts.value.filter(p => p.trim());
  if (validParts.length < 2) {
    ElMessage.warning('至少需要拆分为2段有效内容');
    return;
  }
  saving.value = true;
  try {
    const res: any = await splitKBChunk(splitTargetChunk.value.chunk_id, validParts);
    if (Array.isArray(res?.items)) {
      replaceChunks(res.items);
    } else {
      loadChunks();
    }
    ElMessage.success('拆分成功');
    splitDialogVisible.value = false;
  } finally {
    saving.value = false;
  }
};

const mergeWithPrevious = async (currentChunk: any, prevChunk: any, index: number) => {
  try {
    await ElMessageBox.confirm(
      `将保留上一段（#${index}）：本段（#${index + 1}）的正文会并入上一段后删除，本段的人工备注不会带入。`,
      '合并切片',
      {
        type: 'warning',
        confirmButtonText: '确认合并',
        cancelButtonText: '取消'
      }
    );
  } catch {
    return;
  }
  try {
    const res: any = await mergeKBChunks([prevChunk.chunk_id, currentChunk.chunk_id], '\n\n');
    if (Array.isArray(res?.items)) {
      replaceChunks(res.items, [prevChunk.chunk_id]);
    } else {
      loadChunks();
    }
    ElMessage.success('合并成功');
  } catch (e) {
    if (!isHandledRequestError(e)) ElMessage.error('合并失败');
  }
};

onMounted(() => {
  loadDoc();
  loadChunks();
});

onUnmounted(() => {
  window.clearTimeout(updatedFlashTimer);
});
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.chunks-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--content-gap);
  background: var(--bg-panel-muted);
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1000px;
  margin: 0 auto;
}

.chunk-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
}

.chunk-card.is-disabled {
  opacity: 0.6;
  background: var(--bg-panel-muted);
}

.chunk-card.is-updated {
  border-color: var(--blue-600);
}

@media (prefers-reduced-motion: no-preference) {
  .chunk-card.is-updated {
    animation: chunk-landed 260ms var(--ease-enter);
  }
}

@keyframes chunk-landed {
  from {
    opacity: 0.4;
    transform: translateY(4px);
  }
}

.chunk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 12px;
}

.chunk-id {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.chunk-actions {
  display: flex;
  gap: 8px;
}

.chunk-body {
  font-size: var(--text-body);
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.chunk-footer {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.split-intro {
  margin-bottom: var(--content-gap);
}

.split-note {
  margin-bottom: var(--content-gap);
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.split-parts {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.split-part {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.split-part :deep(.el-input) {
  flex: 1;
}

.split-add {
  width: 100%;
}
</style>
