<template>
  <div class="page-shell connectors-page">
    <PageHeaderCompact title="多源数据同步" subtitle="连接内部系统，实现增量知识自动同步">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">添加数据源</el-button>
      </template>
    </PageHeaderCompact>

    <div class="connectors-content">
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载数据源...</span>
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
            </div>
            <div class="conn-actions">
              <el-button size="small" plain @click="runSync(conn)">立即同步</el-button>
              <el-button size="small" plain @click="openEditDialog(conn)">配置</el-button>
              <el-button size="small" type="danger" plain @click="deleteConn(conn)">删除</el-button>
            </div>
          </div>
          
          <div class="conn-details">
            <div class="detail-item">
              <span class="label">知识库:</span>
              <span>{{ getBaseName(conn.base_id) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">类型:</span>
              <span>{{ getConnectorTypeName(conn.connector_type) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">定时任务:</span>
              <span>{{ conn.schedule?.enabled ? `每 ${conn.schedule.interval_minutes} 分钟` : '已禁用' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editingConnector ? '编辑数据源' : '添加数据源'" width="500px">
      <el-form label-position="top">
        <el-form-item label="数据源名称">
          <el-input v-model="form.name" placeholder="例如：飞书技术文档同步" />
        </el-form-item>
        
        <el-form-item label="目标知识库">
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
        <el-form-item label="配置 JSON">
          <el-input v-model="configJson" type="textarea" :rows="6" placeholder="{}" />
        </el-form-item>

        <el-form-item label="定时同步">
          <div style="display: flex; gap: 12px; align-items: center;">
            <el-switch v-model="form.schedule_enabled" />
            <el-input-number v-if="form.schedule_enabled" v-model="form.schedule_interval" :min="10" placeholder="分钟" />
            <span v-if="form.schedule_enabled">分钟</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConnector">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading, Document, Position, Coin } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listConnectors, createConnector, updateConnector, deleteConnector, syncConnector, listKnowledgeBases } from '@/api/kb';

const connectors = ref<any[]>([]);
const bases = ref<any[]>([]);
const loading = ref(false);

const dialogVisible = ref(false);
const saving = ref(false);
const editingConnector = ref<any>(null);

const form = ref({
  name: '',
  base_id: '',
  connector_type: 'web_crawler',
  schedule_enabled: false,
  schedule_interval: 60
});
const configJson = ref('{}');

const connector_id = (conn: any) => conn.id || conn.connector_id;

const loadData = async () => {
  loading.value = true;
  try {
    const [basesRes, connsRes]: any = await Promise.all([
      listKnowledgeBases(),
      listConnectors()
    ]);
    bases.value = basesRes.items || [];
    connectors.value = connsRes.items || [];
  } finally {
    loading.value = false;
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

const openCreateDialog = () => {
  editingConnector.value = null;
  form.value = {
    name: '',
    base_id: bases.value[0]?.id || '',
    connector_type: 'web_crawler',
    schedule_enabled: false,
    schedule_interval: 60
  };
  configJson.value = '{\n  "urls": ["https://example.com"]\n}';
  dialogVisible.value = true;
};

const openEditDialog = (conn: any) => {
  editingConnector.value = conn;
  form.value = {
    name: conn.name,
    base_id: conn.base_id,
    connector_type: conn.connector_type,
    schedule_enabled: conn.schedule?.enabled || false,
    schedule_interval: conn.schedule?.interval_minutes || 60
  };
  configJson.value = JSON.stringify(conn.config || {}, null, 2);
  dialogVisible.value = true;
};

const saveConnector = async () => {
  let parsedConfig = {};
  try {
    parsedConfig = JSON.parse(configJson.value);
  } catch (e) {
    ElMessage.error('配置 JSON 格式错误');
    return;
  }

  saving.value = true;
  const payload = {
    name: form.value.name,
    base_id: form.value.base_id,
    connector_type: form.value.connector_type,
    config: parsedConfig,
    schedule: {
      enabled: form.value.schedule_enabled,
      interval_minutes: form.value.schedule_interval
    }
  };

  try {
    if (editingConnector.value) {
      await updateConnector(connector_id(editingConnector.value), payload);
      ElMessage.success('更新成功');
    } else {
      await createConnector(payload as any);
      ElMessage.success('创建成功');
    }
    dialogVisible.value = false;
    loadData();
  } finally {
    saving.value = false;
  }
};

const deleteConn = async (conn: any) => {
  try {
    await ElMessageBox.confirm('确定删除该数据源吗？', '删除数据源', { type: 'warning' });
  } catch {
    return;
  }
  await deleteConnector(connector_id(conn));
  ElMessage.success('已删除');
  loadData();
};

const runSync = async (conn: any) => {
  try {
    await syncConnector(connector_id(conn), false);
    ElMessage.success('同步任务已提交');
  } catch (e) {
    ElMessage.error('同步提交失败');
  }
};

onMounted(() => {
  loadData();
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

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
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
  font-size: 16px;
  color: var(--text-primary);
}

.conn-actions {
  display: flex;
  gap: 8px;
}

.conn-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
}

.detail-item .label {
  color: var(--text-secondary);
}
</style>
