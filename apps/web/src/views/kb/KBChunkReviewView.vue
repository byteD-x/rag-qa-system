<template>
  <div class="page-shell">
    <PageHeaderCompact title="知识切片管理" :subtitle="document?.file_name || '加载中...'">
      <template #actions>
        <el-button plain @click="router.back()">返回</el-button>
        <el-switch v-model="showDisabled" active-text="显示已禁用" @change="loadChunks" style="margin-left: 16px;" />
      </template>
    </PageHeaderCompact>

    <div class="chunks-container">
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>加载切片中...</span>
      </div>

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
          :class="{ 'is-disabled': chunk.disabled }"
        >
          <div class="chunk-header">
            <span class="chunk-id">#{{ index + 1 }} (ID: {{ chunk.chunk_id.slice(0,8) }}...)</span>
            <div class="chunk-actions">
              <el-button size="small" type="primary" plain @click="openEditDialog(chunk)">编辑</el-button>
              <el-button size="small" type="warning" plain @click="openSplitDialog(chunk)">拆分</el-button>
              <el-button v-if="index > 0" size="small" plain @click="mergeWithPrevious(chunk, chunks[index-1])">向上合并</el-button>
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
    <el-dialog v-model="editDialogVisible" title="编辑切片" width="600px">
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
    <el-dialog v-model="splitDialogVisible" title="拆分切片" width="600px">
      <div style="margin-bottom: 16px;">请在下方填入拆分后的文本片段，每段作为一个新切片。</div>
      <div v-for="(_, i) in splitParts" :key="i" style="margin-bottom: 10px; display: flex; gap: 8px;">
        <el-input v-model="splitParts[i]" type="textarea" :rows="3" style="flex: 1;" />
        <el-button type="danger" plain icon="Delete" @click="splitParts.splice(i, 1)" />
      </div>
      <el-button type="primary" plain icon="Plus" style="width: 100%; margin-bottom: 16px;" @click="splitParts.push('')">增加拆分片段</el-button>
      <template #footer>
        <el-button @click="splitDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveChunkSplit">确认拆分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { getKBDocument, getKBChunks, updateKBChunk, splitKBChunk, mergeKBChunks } from '@/api/kb';

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
    await updateKBChunk(editingChunk.value.chunk_id, {
      text_content: editingChunk.value.text_content,
      manual_note: editingChunk.value.manual_note
    });
    ElMessage.success('保存成功');
    editDialogVisible.value = false;
    loadChunks();
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
    await updateKBChunk(chunk.chunk_id, {
      disabled: !chunk.disabled,
      disabled_reason: disabledReason
    });
    ElMessage.success(chunk.disabled ? '已启用' : '已禁用');
    loadChunks();
  } catch (e) {
    ElMessage.error('操作失败');
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
    await splitKBChunk(splitTargetChunk.value.chunk_id, validParts);
    ElMessage.success('拆分成功');
    splitDialogVisible.value = false;
    loadChunks();
  } finally {
    saving.value = false;
  }
};

const mergeWithPrevious = async (currentChunk: any, prevChunk: any) => {
  try {
    await ElMessageBox.confirm('确定要将此切片与上一个切片合并吗？', '合并切片', {
      type: 'warning'
    });
  } catch {
    return;
  }
  try {
    await mergeKBChunks([prevChunk.chunk_id, currentChunk.chunk_id], '\n\n');
    ElMessage.success('合并成功');
    loadChunks();
  } catch (e) {
    ElMessage.error('合并失败');
  }
};

onMounted(() => {
  loadDoc();
  loadChunks();
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
  padding: 16px;
  background: var(--bg-panel-muted);
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
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
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.chunk-card.is-disabled {
  opacity: 0.6;
  background: var(--bg-body);
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
  font-size: 13px;
  color: var(--text-secondary);
}

.chunk-actions {
  display: flex;
  gap: 8px;
}

.chunk-body {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.chunk-footer {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
</style>
