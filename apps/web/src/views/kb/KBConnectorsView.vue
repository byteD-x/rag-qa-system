<template>
  <div class="page-shell connectors-page">
    <PageHeaderCompact title="多源同步">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">添加数据源</el-button>
      </template>
    </PageHeaderCompact>

    <div class="connectors-content">
      <LoadingState v-if="loading" label="加载数据源..." />

      <div v-else-if="loadError" class="error-state" role="alert">
        <strong>加载数据源失败</strong>
        <span>暂时无法获取数据源，请检查网络后重试。</span>
        <el-button type="primary" plain data-testid="retry-connectors" @click="loadData(true)">重新加载</el-button>
      </div>

      <EnhancedEmpty
        v-else-if="!connectors.length"
        variant="document"
        title="暂无数据源"
        description="点击右上角添加您的第一个数据源"
      />

      <div v-else class="connector-list">
        <div v-for="conn in connectors" :key="connector_id(conn)" class="connector-card">
          <div class="conn-header">
            <div class="conn-title">
              <el-icon :size="20" :class="getConnectorIconClass(conn.connector_type)">
                <component :is="getConnectorIcon(conn.connector_type)" />
              </el-icon>
              <strong>{{ conn.name }}</strong>
              <span v-if="busyId === connector_id(conn)" class="conn-busy">
                <el-icon class="is-loading" :size="14"><Loading /></el-icon>
                刷新中...
              </span>
            </div>
            <div class="conn-actions">
              <el-button
                size="small"
                plain
                :loading="syncingId === connector_id(conn)"
                :disabled="syncingId === connector_id(conn)"
                @click="runSync(conn)"
              >
                立即同步
              </el-button>
              <el-button size="small" plain @click="openEditDialog(conn)">配置</el-button>
              <el-button size="small" type="danger" plain @click="deleteConn(conn)">删除</el-button>
            </div>
          </div>
          
          <div class="conn-details">
            <span
              v-for="item in connectorMeta(conn)"
              :key="item.key"
              :class="{ 'conn-details__error': item.error }"
            >
              {{ item.text }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editingConnector ? '编辑数据源' : '添加数据源'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="数据源名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：飞书技术文档同步" />
        </el-form-item>
        
        <el-form-item label="目标知识库" prop="base_id">
          <el-select v-model="form.base_id" style="width: 100%;">
            <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="数据源类型">
          <el-select v-model="form.connector_type" :disabled="!!editingConnector" style="width: 100%;">
            <el-option label="本地目录 (Local Directory)" value="local_directory" />
            <el-option label="Notion" value="notion" />
            <el-option label="Web 爬虫" value="web_crawler" />
            <el-option label="飞书文档" value="feishu_document" />
            <el-option label="钉钉文档" value="dingtalk_document" />
            <el-option label="数据库 (Text-to-SQL)" value="sql_query" />
          </el-select>
        </el-form-item>

        <!-- Config JSON mapping for simplicity in this MVP -->
        <el-form-item :label="configJsonLabel">
          <el-input v-model="configJson" type="textarea" :rows="6" placeholder="{}" />
        </el-form-item>

        <el-form-item label="源中文件消失时">
          <el-switch v-model="form.delete_missing" active-text="软删除知识库中的对应文档" inactive-text="保留不删除" />
        </el-form-item>

        <el-form-item label="定时同步">
          <div style="display: flex; gap: 12px; align-items: center;">
            <el-switch v-model="form.schedule_enabled" />
            <el-input-number v-if="form.schedule_enabled" v-model="form.schedule_interval" :min="15" placeholder="分钟" />
            <span v-if="form.schedule_enabled">分钟</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConnector">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="syncResultVisible" title="同步结果" width="720px">
      <div v-if="syncResult" class="sync-result">
        <div class="sync-result__summary">
          <span>新增 {{ syncResult.counts?.create || 0 }}</span>
          <span>更新 {{ syncResult.counts?.update || 0 }}</span>
          <span>跳过 {{ syncResult.counts?.skip || 0 }}</span>
          <span>软删除 {{ syncResult.counts?.soft_delete || 0 }}</span>
        </div>
        <div v-if="syncResult.items?.length" class="sync-result__list">
          <div
            v-for="item in syncResult.items"
            :key="`${item.action}-${item.document_id || item.relative_path || item.file_name}`"
            class="sync-result__item"
          >
            <div class="sync-result__row">
              <strong>{{ item.file_name || item.relative_path || item.document_id || '未命名文档' }}</strong>
              <el-tag size="small" effect="plain">{{ item.action }}</el-tag>
            </div>
            <div v-if="item.reason" class="sync-result__reason">{{ item.reason }}</div>
          </div>
        </div>
        <EnhancedEmpty
          v-else
          variant="document"
          title="暂无同步项"
          description="本次同步没有产生新增、更新或删除项。"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading, Document, Position, Coin } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { formatDateTime } from '@/utils/time';
import { listConnectors, createConnector, updateConnector, deleteConnector, syncConnector, listKnowledgeBases } from '@/api/kb';
import { isHandledRequestError } from '@/api/request';

const connectors = ref<any[]>([]);
const bases = ref<any[]>([]);
const loading = ref(false);
const loadError = ref('');
const syncResultVisible = ref(false);
const syncResult = ref<any | null>(null);
const syncingId = ref('');
const busyId = ref('');

const dialogVisible = ref(false);
const saving = ref(false);
const editingConnector = ref<any>(null);

const formRef = ref<any>();
const form = ref({
  name: '',
  base_id: '',
  connector_type: 'web_crawler',
  delete_missing: true,
  schedule_enabled: false,
  schedule_interval: 60
});
const rules = {
  name: [{ required: true, message: '请输入数据源名称', trigger: 'blur' }],
  base_id: [{ required: true, message: '请选择目标知识库', trigger: 'change' }]
};
const configJson = ref('{}');

// 每种连接器类型在后端读取的必填配置键（apps/services/knowledge-base/src/app/kb_connector_routes.py:149-181）
const CONNECTOR_CONFIG_KEYS: Record<string, string> = {
  local_directory: 'source_path',
  notion: 'page_ids',
  web_crawler: 'urls',
  feishu_document: 'urls',
  dingtalk_document: 'urls',
  sql_query: 'dsn_env、query'
};

const configJsonLabel = computed(() => {
  const keys = CONNECTOR_CONFIG_KEYS[form.value.connector_type];
  return keys ? `配置 JSON（必填 ${keys}）` : '配置 JSON';
});

const connector_id = (conn: any) => conn.id || conn.connector_id;

// 首屏加载才整段替换列表；保存/删除后的刷新保留旧数据渲染，避免滚动位置与视觉锚点丢失
const loadData = async (first = false) => {
  if (first) {
    loading.value = true;
  }
  loadError.value = '';
  try {
    const [basesRes, connsRes]: any = await Promise.all([
      listKnowledgeBases({ skipErrorHandler: true }),
      listConnectors(undefined, { skipErrorHandler: true })
    ]);
    bases.value = basesRes.items || [];
    connectors.value = connsRes.items || [];
  } catch (error) {
    const message = error instanceof Error ? error.message : 'request_failed';
    // 刷新失败时若已有列表，保留渲染（否则整段卸载会丢滚动位置与视觉锚点）
    if (first || !connectors.value.length) {
      loadError.value = message;
    } else {
      if (!isHandledRequestError(error)) ElMessage.error('刷新数据源失败，已保留当前列表');
    }
  } finally {
    if (first) {
      loading.value = false;
    }
  }
};

const getBaseName = (baseId: string) => {
  const b = bases.value.find(x => x.id === baseId);
  return b ? b.name : '未知';
};

const getConnectorTypeName = (type: string) => {
  const map: any = {
    local_directory: '本地目录',
    notion: 'Notion',
    web_crawler: 'Web 爬虫',
    feishu_document: '飞书文档',
    dingtalk_document: '钉钉文档',
    sql_query: '数据库 SQL'
  };
  return map[type] || type;
};

const getConnectorIcon = (type: string) => {
  if (type === 'sql_query') return Coin;
  if (type === 'web_crawler') return Position;
  return Document;
};

const getConnectorIconClass = (type: string) => {
  return `icon-${type.replace('_', '-')}`;
};

const countText = (counts: any) =>
  `新增 ${counts?.create || 0} 更新 ${counts?.update || 0} 跳过 ${counts?.skip || 0} 软删除 ${counts?.soft_delete || 0}`;

// 后端列表接口已返回 schedule.last_run_at / schedule.next_run_at / last_result（kb_connector_routes.py:27-46）
const connectorMeta = (conn: any) => {
  const schedule = conn.schedule || {};
  const result = conn.last_result || {};
  const items: Array<{ key: string; text: string; error?: boolean }> = [
    { key: 'base', text: `知识库 ${getBaseName(conn.base_id)}` },
    { key: 'type', text: `类型 ${getConnectorTypeName(conn.connector_type)}` },
    { key: 'schedule', text: `定时同步 ${schedule.enabled ? `每 ${schedule.interval_minutes} 分钟` : '已禁用'}` },
    { key: 'last_run', text: schedule.last_run_at ? `上次同步 ${formatDateTime(schedule.last_run_at)}` : '尚未同步' }
  ];
  if (result.error_message) {
    items.push({ key: 'last_result', text: `上次同步失败：${result.error_message}`, error: true });
  } else if (result.counts) {
    items.push({ key: 'last_result', text: `上次结果 ${countText(result.counts)}` });
  }
  if (schedule.next_run_at) {
    items.push({ key: 'next_run', text: `下次运行 ${formatDateTime(schedule.next_run_at)}` });
  }
  return items;
};

const openCreateDialog = () => {
  editingConnector.value = null;
  form.value = {
    name: '',
    base_id: bases.value[0]?.id || '',
    connector_type: 'web_crawler',
    delete_missing: true,
    schedule_enabled: false,
    schedule_interval: 60
  };
  configJson.value = '{}';
  dialogVisible.value = true;
};

const openEditDialog = (conn: any) => {
  editingConnector.value = conn;
  const storedConfig = { ...(conn.config || {}) };
  const deleteMissing = storedConfig.delete_missing;
  delete storedConfig.delete_missing;
  form.value = {
    name: conn.name,
    base_id: conn.base_id,
    connector_type: conn.connector_type,
    delete_missing: deleteMissing !== false,
    schedule_enabled: conn.schedule?.enabled || false,
    schedule_interval: conn.schedule?.interval_minutes || 60
  };
  configJson.value = JSON.stringify(storedConfig, null, 2);
  dialogVisible.value = true;
};

const saveConnector = async () => {
  if (!(await formRef.value?.validate())) {
    return;
  }
  let parsedConfig = {};
  try {
    parsedConfig = JSON.parse(configJson.value);
  } catch (e) {
    ElMessage.error('配置 JSON 格式错误');
    return;
  }
  if (!parsedConfig || typeof parsedConfig !== 'object' || Array.isArray(parsedConfig)) {
    ElMessage.error('配置 JSON 必须是对象');
    return;
  }

  saving.value = true;
  const payload = {
    name: form.value.name,
    base_id: form.value.base_id,
    connector_type: form.value.connector_type,
    config: { ...parsedConfig, delete_missing: form.value.delete_missing },
    schedule: {
      enabled: form.value.schedule_enabled,
      interval_minutes: form.value.schedule_interval
    }
  };

  try {
    if (editingConnector.value) {
      await updateConnector(connector_id(editingConnector.value), payload);
      ElMessage.success('更新成功');
      busyId.value = connector_id(editingConnector.value);
    } else {
      const created: any = await createConnector(payload as any);
      ElMessage.success('创建成功');
      busyId.value = connector_id(created || {});
    }
    dialogVisible.value = false;
    await loadData();
  } finally {
    saving.value = false;
    busyId.value = '';
  }
};

const deleteConn = async (conn: any) => {
  try {
    await ElMessageBox.confirm('确定删除该数据源吗？', '删除数据源', { type: 'warning' });
  } catch {
    return;
  }
  busyId.value = connector_id(conn);
  try {
    await deleteConnector(connector_id(conn));
    ElMessage.success('已删除');
    await loadData();
  } finally {
    busyId.value = '';
  }
};

const runSync = async (conn: any) => {
  syncingId.value = connector_id(conn);
  try {
    const response: any = await syncConnector(syncingId.value, false);
    syncResult.value = response?.result || response || null;
    syncResultVisible.value = Boolean(syncResult.value);
    await loadData();
  } catch {
    // 请求层已统一提示失败，这里不再重复弹窗
  } finally {
    syncingId.value = '';
  }
};

onMounted(() => {
  loadData(true);
});
</script>

<style scoped>
.connectors-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.connectors-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: var(--bg-panel-muted);
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 220px;
  padding: 32px;
  color: var(--text-secondary);
  text-align: center;
}

.error-state strong {
  color: var(--text-primary);
  font-size: var(--text-body);
}

.connector-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}

.connector-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conn-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.conn-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-body);
  color: var(--text-primary);
}

.conn-actions {
  display: flex;
  gap: 8px;
}

.conn-busy {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
  font-size: var(--text-caption, 0.75rem);
  font-weight: 400;
}

.conn-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: var(--text-secondary);
  font-size: var(--text-caption);
}

.conn-details__error {
  color: var(--el-color-danger);
}

.sync-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sync-result__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--text-secondary);
  font-size: var(--text-caption);
}

.sync-result__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sync-result__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sync-result__reason {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: var(--text-caption);
}
</style>
