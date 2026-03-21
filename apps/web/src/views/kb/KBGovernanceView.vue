<template>
  <div class="page-shell governance-page">
    <PageHeaderCompact title="知识治理工作台">
      <template #actions>
        <el-radio-group v-if="authStore.isAdmin()" v-model="viewMode" size="small" @change="loadAllData">
          <el-radio-button value="personal">个人范围</el-radio-button>
          <el-radio-button value="admin">全局范围</el-radio-button>
        </el-radio-group>
        <el-button plain :loading="loading || batchEventsLoading" @click="loadAllData">刷新</el-button>
        <el-button plain @click="router.push('/workspace/kb/upload')">知识库管理</el-button>
      </template>
    </PageHeaderCompact>

    <div class="summary-grid">
      <section v-for="card in summaryCards" :key="card.key" class="summary-card">
        <span class="summary-label">{{ card.label }}</span>
        <strong class="summary-value">{{ card.value }}</strong>
        <span class="summary-hint">{{ card.hint }}</span>
      </section>
    </div>

    <section class="toolbar-row">
      <div class="toolbar-group">
        <span class="toolbar-label">工作集</span>
        <el-radio-group v-model="workset" size="small">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="pending_me">待我处理</el-radio-button>
          <el-radio-button label="reviewed_by_me">我已处理</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-meta">
        <span>生成时间：{{ formatTime(governance?.generated_at) }}</span>
        <span v-if="hasDegradedSections" class="degraded-text">当前治理数据存在降级字段。</span>
      </div>
    </section>

    <section v-if="selectedDocumentIds.length" class="panel">
      <div class="panel-head">
        <strong>已选 {{ selectedDocumentIds.length }} 项</strong>
        <el-button text size="small" @click="clearSelection">清空选择</el-button>
      </div>
      <el-input v-model="batchReviewerNote" type="textarea" :rows="2" placeholder="批量驳回或审核时可填写统一备注" />
      <div class="actions">
        <el-button :loading="bulkLoading" :disabled="!canWrite || !currentUserId" @click="runBulkAction('assign_to_me')">批量指派给我</el-button>
        <el-button :loading="bulkLoading" :disabled="!canWrite" @click="runBulkAction('review_pending')">批量提交审核</el-button>
        <el-button type="success" plain :loading="bulkLoading" :disabled="!canWrite" @click="runBulkAction('approved')">批量通过</el-button>
        <el-button type="danger" plain :loading="bulkLoading" :disabled="!canWrite" @click="runBulkAction('rejected')">批量驳回</el-button>
      </div>
    </section>

    <section v-if="lastBatchResult" class="panel">
      <div class="panel-head">
        <strong>最近一次批量治理结果</strong>
        <el-button v-if="canRetryFailedBatch" text size="small" :loading="bulkLoading" @click="retryFailedBatchItems">仅重试失败项</el-button>
      </div>
      <div class="toolbar-meta">
        <span>总数 {{ lastBatchResult.summary.total }}</span>
        <span>成功 {{ lastBatchResult.summary.succeeded }}</span>
        <span>失败 {{ lastBatchResult.summary.failed }}</span>
        <span>动作 {{ batchActionLabel(lastBatchRequest?.patch) }}</span>
      </div>
      <div v-if="failedBatchItems.length" class="list">
        <article v-for="item in failedBatchItems" :key="item.document_id" class="list-item">
          <strong>{{ item.document_id }}</strong>
          <span>{{ item.code || 'unknown_error' }}</span>
          <span>{{ item.detail || '请求失败' }}</span>
        </article>
      </div>
      <div v-else class="empty">最近一次批量治理没有失败项。</div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <strong>批量治理审计记录</strong>
        <el-button text size="small" :loading="batchEventsLoading" @click="loadBatchEvents">刷新</el-button>
      </div>
      <div v-if="batchEventsLoading" class="loading-panel"><el-skeleton :rows="3" animated /></div>
      <div v-else-if="!batchEvents.length" class="empty">当前范围内暂无批量治理记录。</div>
      <div v-else class="list">
        <article v-for="event in batchEvents" :key="event.id" class="list-item">
          <strong>{{ batchActionLabel(event.details?.patch) }}</strong>
          <span>{{ event.actor_email || event.actor_user_id || '-' }}</span>
          <span>{{ formatTime(event.created_at) }}</span>
          <span>成功 {{ Number(event.details?.succeeded || 0) }} / 失败 {{ Number(event.details?.failed || 0) }}</span>
          <el-button text type="primary" size="small" @click="openBatchEventDrawer(event)">详情</el-button>
        </article>
      </div>
    </section>

    <section v-if="loading" class="loading-panel">
      <el-skeleton :rows="6" animated />
    </section>

    <div v-else class="queue-grid">
      <section v-for="section in filteredDocumentSections" :key="section.key" class="panel">
        <div class="panel-head">
          <div>
            <strong>{{ section.title }}</strong>
            <div class="summary-hint">{{ section.description }}</div>
          </div>
          <div class="actions">
            <el-tag size="small" effect="plain">{{ section.total }} / {{ section.items.length }}</el-tag>
            <el-button v-if="section.items.length" text size="small" :disabled="!canWrite" @click="toggleSectionSelection(section.items)">
              {{ areAllSelected(section.items) ? '取消全选' : '本列全选' }}
            </el-button>
          </div>
        </div>
        <div v-if="!section.items.length" class="empty">当前筛选下没有待处理项。</div>
        <div v-else class="list">
          <article v-for="item in section.items" :key="item.document_id" class="list-item">
            <el-checkbox :model-value="isSelected(item.document_id)" @change="toggleSelected(item.document_id, $event)" />
            <div class="item-body">
              <strong>{{ item.file_name }}</strong>
              <div class="toolbar-meta">
                <span>{{ item.base_name }}</span>
                <span v-if="item.version_label">{{ item.version_label }}</span>
                <span>负责人 {{ ownerLabel(item.owner_user_id) }}</span>
                <span v-if="item.reviewed_by_user_id">审核人 {{ reviewerLabel(item.reviewed_by_user_id, item.reviewed_by_email) }}</span>
              </div>
              <div class="toolbar-meta">
                <span>{{ reasonLabel(item.reason) }}</span>
                <span>{{ reviewLabel(item.review_status) }}</span>
                <span>文档状态 {{ item.status || '-' }}</span>
                <span>增强状态 {{ item.enhancement_status || '-' }}</span>
              </div>
              <div v-if="item.low_confidence_region_count" class="toolbar-meta">
                <span>低置信区域 {{ item.low_confidence_region_count }}</span>
                <span v-if="item.low_confidence_region_label">{{ item.low_confidence_region_label }}</span>
                <span v-if="item.low_confidence_region_confidence !== null && item.low_confidence_region_confidence !== undefined">
                  置信度 {{ (Number(item.low_confidence_region_confidence) * 100).toFixed(1) }}%
                </span>
              </div>
              <div v-if="item.reviewer_note" class="note">{{ item.reviewer_note }}</div>
              <div v-if="item.low_confidence_region_count" class="actions">
                <el-button text size="small" :loading="isLoadingLowConfidence(item.document_id)" @click="toggleLowConfidenceRegions(item)">
                  {{ isLowConfidenceExpanded(item.document_id) ? '鏀惰捣浣庣疆淇″尯鍩?' : `鏌ョ湅鍏ㄩ儴浣庣疆淇″尯鍩?${item.low_confidence_region_count}` }}
                </el-button>
              </div>
              <div v-if="isLowConfidenceExpanded(item.document_id)" class="low-confidence-region-list">
                <div v-if="isLoadingLowConfidence(item.document_id)" class="summary-hint">鍔犺浇浣庣疆淇″尯鍩熶腑...</div>
                <div v-else-if="!lowConfidenceRegionsFor(item.document_id).length" class="empty empty--compact">未找到可展开的低置信区域。</div>
                <article v-for="region in lowConfidenceRegionsFor(item.document_id)" :key="region.region_id" class="low-confidence-region-item">
                  <div class="low-confidence-region-item__meta">
                    <strong>{{ region.region_label || '鍖哄煙' }}</strong>
                    <span v-if="region.asset_file_name">{{ region.asset_file_name }}</span>
                    <span v-if="region.asset_page_number || region.page_number">椤电爜 {{ region.asset_page_number || region.page_number }}</span>
                    <span v-if="region.layout_hints?.length">{{ region.layout_hints.join(' / ') }}</span>
                    <span v-if="region.confidence !== null && region.confidence !== undefined">
                      缃俊搴?{{ (Number(region.confidence) * 100).toFixed(1) }}%
                    </span>
                    <span v-if="region.bbox?.length === 4">鍧愭爣 {{ formatBbox(region.bbox) }}</span>
                  </div>
                  <span class="summary-hint">{{ region.summary || region.ocr_text || '鏃犳憳瑕?' }}</span>
                  <div class="actions">
                    <el-button text type="warning" size="small" @click="openRegion(item.document_id, region)">瀹氫綅</el-button>
                  </div>
                </article>
              </div>
              <div class="actions">
                <el-button text type="primary" size="small" @click="openDocument(item.document_id)">查看文档</el-button>
                <el-button v-if="item.low_confidence_asset_id && item.low_confidence_region_id" text type="warning" size="small" @click="openLowConfidenceRegion(item)">定位低置信区域</el-button>
                <el-button text size="small" @click="openBase(item.base_id)">打开知识库</el-button>
                <el-button text size="small" :disabled="!canWrite || editingDocumentId === item.document_id" @click="openGovernanceEditor(item.document_id)">编辑</el-button>
              </div>
            </div>
          </article>
        </div>
      </section>
    </div>

    <section v-if="!loading" class="panel">
      <div class="panel-head">
        <strong>多当前版本冲突</strong>
        <el-tag size="small" effect="plain">{{ governance?.summary.version_conflicts ?? 0 }} / {{ conflictItems.length }}</el-tag>
      </div>
      <div v-if="!conflictItems.length" class="empty">当前没有多 current 冲突。</div>
      <div v-else class="list">
        <article v-for="item in conflictItems" :key="`${item.base_id}-${item.version_family_key}`" class="list-item">
          <strong>{{ item.version_family_key }}</strong>
          <span>{{ item.base_name }}</span>
          <span>current {{ item.current_version_count }}</span>
          <span>总版本 {{ item.total_versions }}</span>
          <el-button text type="primary" size="small" @click="openConflict(item)">查看冲突文档</el-button>
        </article>
      </div>
    </section>

    <el-drawer v-model="editDrawerVisible" title="治理修正" size="460px" destroy-on-close @close="closeGovernanceEditor">
      <el-form label-position="top">
        <el-form-item label="负责人用户 ID"><el-input v-model="documentForm.owner_user_id" placeholder="默认使用创建人，可手动调整" /></el-form-item>
        <el-form-item label="审核状态">
          <el-select v-model="documentForm.review_status" style="width: 100%">
            <el-option label="未设置" value="" />
            <el-option v-for="item in reviewStatusOptions" :key="item" :label="reviewLabel(item)" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="审核备注"><el-input v-model="documentForm.reviewer_note" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="版本家族 Key"><el-input v-model="documentForm.version_family_key" /></el-form-item>
        <el-form-item label="版本标签"><el-input v-model="documentForm.version_label" /></el-form-item>
        <el-form-item label="版本号"><el-input-number v-model="documentForm.version_number" :min="1" :max="100000" style="width: 100%" /></el-form-item>
        <el-form-item label="版本状态"><el-select v-model="documentForm.version_status" style="width: 100%"><el-option v-for="item in versionStatusOptions" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="设为当前版本"><el-switch v-model="documentForm.is_current_version" /></el-form-item>
        <el-form-item label="生效开始"><el-date-picker v-model="documentForm.effective_from" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss[Z]" style="width: 100%" /></el-form-item>
        <el-form-item label="生效结束"><el-date-picker v-model="documentForm.effective_to" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss[Z]" style="width: 100%" /></el-form-item>
        <el-form-item label="替代旧文档 ID"><el-input v-model="documentForm.supersedes_document_id" /></el-form-item>
        <div class="actions">
          <el-button :disabled="!canWrite || !currentUserId" @click="assignToMe">指派给我</el-button>
          <el-button :disabled="!canWrite || !editTarget" @click="saveGovernanceDocument('review_pending')">提交审核</el-button>
          <el-button type="success" plain :disabled="!canWrite || !editTarget" @click="saveGovernanceDocument('approved')">通过</el-button>
          <el-button type="danger" plain :disabled="!canWrite || !editTarget" @click="saveGovernanceDocument('rejected')">驳回</el-button>
          <el-button type="primary" :loading="savingEdit" :disabled="!canWrite || !editTarget" @click="saveGovernanceDocument()">保存修正</el-button>
        </div>
      </el-form>
    </el-drawer>

    <el-drawer v-model="batchEventDrawerVisible" title="批量治理审计详情" size="460px" destroy-on-close @close="closeBatchEventDrawer">
      <div v-if="batchEventDetailLoading" class="loading-panel">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="selectedBatchEventDetail" class="detail-stack">
        <div class="toolbar-meta">
          <span>任务 {{ selectedBatchEventTask?.task_id || selectedBatchEventDetail.resource_id }}</span>
          <span>状态 {{ selectedBatchEventTask?.status || 'completed' }}</span>
        </div>
        <div class="toolbar-meta">
          <span>操作人 {{ selectedBatchEventDetail.actor_email || selectedBatchEventDetail.actor_user_id || '-' }}</span>
          <span>时间 {{ formatTime(selectedBatchEventDetail.created_at) }}</span>
        </div>
        <div class="toolbar-meta">
          <span>总数 {{ Number(selectedBatchEventDetail.details?.total || 0) }}</span>
          <span>成功 {{ Number(selectedBatchEventDetail.details?.succeeded || 0) }}</span>
          <span>失败 {{ Number(selectedBatchEventDetail.details?.failed || 0) }}</span>
        </div>
        <div v-if="selectedBatchEventTask" class="toolbar-meta">
          <span>重试次数 {{ selectedBatchEventTask.retry_summary.retry_count }}</span>
          <span>失败重试 {{ selectedBatchEventTask.retry_summary.failed_retry_count }}</span>
          <span v-if="selectedBatchEventTask.retry_summary.latest_retry_task_id">
            最近重试 {{ selectedBatchEventTask.retry_summary.latest_retry_task_id }}
          </span>
          <span v-if="selectedBatchEventTask.retry_summary.latest_retry_at">
            最近时间 {{ formatTime(selectedBatchEventTask.retry_summary.latest_retry_at) }}
          </span>
        </div>
        <div v-if="selectedBatchEventDetail.details?.retry_of_task_id" class="toolbar-meta">
          <span>重试自 {{ selectedBatchEventDetail.details.retry_of_task_id }}</span>
        </div>
        <div class="toolbar-group">
          <span class="toolbar-label">时间线</span>
          <el-select v-model="batchTimelineFilter" size="small" style="width: 160px" @change="reloadSelectedBatchEventTask">
            <el-option label="全部链路" value="all" />
            <el-option label="仅重试" value="retries" />
            <el-option label="仅上游" value="upstream" />
          </el-select>
        </div>
        <div class="actions">
          <el-button
            v-if="canRetrySelectedBatchTask"
            text
            type="primary"
            size="small"
            :loading="bulkLoading"
            @click="retrySelectedBatchTaskFailedItems"
          >
            重试该任务失败项
          </el-button>
        </div>
        <div>
          <strong>失败项</strong>
          <div v-if="selectedBatchEventFailedItems.length" class="list">
            <article v-for="item in selectedBatchEventFailedItems" :key="item.document_id" class="list-item">
              <strong>{{ item.document_id }}</strong>
              <span>{{ item.code || 'unknown_error' }}</span>
              <span>{{ item.detail || '请求失败' }}</span>
            </article>
          </div>
          <div v-else class="empty">该任务没有失败项。</div>
        </div>
        <div>
          <strong>重试时间线</strong>
          <div v-if="selectedBatchEventTimeline.length" class="list">
            <article v-for="item in selectedBatchEventTimeline" :key="item.id" class="list-item">
              <strong>{{ item.resource_id }}</strong>
              <span>{{ batchActionLabel(item.details?.patch) }}</span>
              <span>{{ formatTime(item.created_at) }}</span>
              <span>成功 {{ Number(item.details?.succeeded || 0) }} / 失败 {{ Number(item.details?.failed || 0) }}</span>
            </article>
          </div>
          <div v-else class="empty">当前没有可展示的重试记录。</div>
          <div v-if="selectedBatchEventTask" class="actions">
            <span class="summary-hint">已加载 {{ selectedBatchEventTimeline.length }} / {{ selectedBatchEventTask.timeline.total }}</span>
            <el-button v-if="selectedBatchEventTask.timeline.has_more" text size="small" :loading="batchEventDetailLoading" @click="loadMoreBatchEventTimeline">加载更多</el-button>
          </div>
        </div>
        <pre class="detail-json">{{ JSON.stringify(selectedBatchEventDetail.details || {}, null, 2) }}</pre>
      </div>
      <div v-else class="empty">未获取到批量治理详情。</div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import {
  batchUpdateKBDocuments,
  getKBDocument,
  getKBDocumentVisualAssets,
  getKBGovernance,
  getKBGovernanceBatchEventDetail,
  getKBGovernanceBatchEvents,
  getKBVisualAssetRegions,
  updateKBDocument,
  type BatchUpdateKBDocumentsPayload,
  type BatchUpdateKBDocumentsResponse,
  type KBGovernanceBatchEventItem,
  type KBGovernanceBatchEventDetailResponse,
  type KBGovernanceBatchEventsResponse,
  type KBGovernanceDocumentItem,
  type KBGovernanceResponse,
  type KBGovernanceVersionConflictItem,
  type KBVisualAssetRegion
} from '@/api/kb';
import { useAuthStore } from '@/store/auth';

type BulkAction = 'assign_to_me' | 'review_pending' | 'approved' | 'rejected';
type Workset = 'all' | 'pending_me' | 'reviewed_by_me';
type BatchTimelineFilter = 'all' | 'retries' | 'upstream';
type GovernanceVisualAsset = {
  asset_id: string;
  file_name?: string;
  page_number?: number | null;
};
type GovernanceLowConfidenceRegion = KBVisualAssetRegion & {
  asset_file_name: string;
  asset_page_number?: number | null;
};

const router = useRouter();
const authStore = useAuthStore();
const LOW_CONFIDENCE_THRESHOLD = 0.8;
const loading = ref(false);
const bulkLoading = ref(false);
const batchEventsLoading = ref(false);
const batchEventDetailLoading = ref(false);
const savingEdit = ref(false);
const editingDocumentId = ref('');
const editDrawerVisible = ref(false);
const batchEventDrawerVisible = ref(false);
const governance = ref<KBGovernanceResponse | null>(null);
const batchEvents = ref<KBGovernanceBatchEventItem[]>([]);
const editTarget = ref<KBGovernanceDocumentItem | null>(null);
const selectedBatchEvent = ref<KBGovernanceBatchEventItem | null>(null);
const selectedBatchEventTask = ref<KBGovernanceBatchEventDetailResponse | null>(null);
const selectedDocumentIds = ref<string[]>([]);
const batchReviewerNote = ref('');
const lastBatchRequest = ref<BatchUpdateKBDocumentsPayload | null>(null);
const lastBatchResult = ref<BatchUpdateKBDocumentsResponse | null>(null);
const batchTimelineFilter = ref<BatchTimelineFilter>('all');
const lowConfidenceExpandedDocumentIds = ref<string[]>([]);
const loadingLowConfidenceDocuments = ref<Record<string, boolean>>({});
const lowConfidenceRegionsByDocument = ref<Record<string, GovernanceLowConfidenceRegion[]>>({});
const viewMode = ref<'personal' | 'admin'>(authStore.isAdmin() ? 'admin' : 'personal');
const limit = ref(8);
const workset = ref<Workset>('all');
const versionStatusOptions = ['active', 'draft', 'superseded', 'archived'];
const reviewStatusOptions = ['review_pending', 'approved', 'rejected'];
const documentForm = reactive({ owner_user_id: '', version_family_key: '', version_label: '', version_number: 1, version_status: 'active', is_current_version: false, effective_from: '', effective_to: '', supersedes_document_id: '', review_status: '', reviewer_note: '' });

const canWrite = computed(() => authStore.hasPermission('kb.write'));
const currentUserId = computed(() => String(authStore.user?.id || ''));
const hasDegradedSections = computed(() => (governance.value?.data_quality?.degraded_sections?.length ?? 0) > 0);
const failedBatchItems = computed(() => (lastBatchResult.value?.items ?? []).filter((item) => !item.ok));
const canRetryFailedBatch = computed(() => !!lastBatchRequest.value && failedBatchItems.value.length > 0 && canWrite.value);
const conflictItems = computed<KBGovernanceVersionConflictItem[]>(() => governance.value?.queues.version_conflicts ?? []);
const selectedBatchEventDetail = computed(() => selectedBatchEventTask.value?.item ?? selectedBatchEvent.value);
const selectedBatchEventTimeline = computed(() => selectedBatchEventTask.value?.timeline.items ?? []);
const selectedBatchEventFailedItems = computed(() => selectedBatchEventDetail.value?.details?.failed_items ?? []);
const canRetrySelectedBatchTask = computed(() => {
  const patch = selectedBatchEventDetail.value?.details?.patch;
  return Boolean(canWrite.value && patch && selectedBatchEventFailedItems.value.length > 0);
});
const summaryCards = computed(() => {
  const summary = governance.value?.summary;
  return [
    { key: 'pending_review', label: '待审核', value: summary?.pending_review ?? 0, hint: '待审核或草稿版本。', tone: '' },
    { key: 'approved_ready', label: '已通过待发布', value: summary?.approved_ready ?? 0, hint: '已通过但尚未正式切换生效。', tone: '' },
    { key: 'rejected_documents', label: '已驳回', value: summary?.rejected_documents ?? 0, hint: '被驳回后仍需补齐信息。', tone: '' },
    { key: 'visual_attention', label: '截图待处理', value: summary?.visual_attention ?? 0, hint: '视觉增强尚未 ready。', tone: '' },
    { key: 'version_conflicts', label: '多当前版本冲突', value: summary?.version_conflicts ?? 0, hint: '同一版本家族存在多个 current。', tone: '' }
  ];
});
const documentSections = computed(() => {
  const queues = governance.value?.queues;
  return [
    { key: 'pending_review', title: '待审核', description: '包含已提交审核和仍处于草稿的版本。', total: governance.value?.summary.pending_review ?? 0, items: queues?.pending_review ?? [] },
    { key: 'approved_ready', title: '已通过待发布', description: '已审核通过但还未发布。', total: governance.value?.summary.approved_ready ?? 0, items: queues?.approved_ready ?? [] },
    { key: 'rejected_documents', title: '已驳回', description: '优先查看驳回备注并补齐缺失信息。', total: governance.value?.summary.rejected_documents ?? 0, items: queues?.rejected_documents ?? [] },
    { key: 'expired_documents', title: '已过期文档', description: '建议确认是否需要归档或切换 current。', total: governance.value?.summary.expired_documents ?? 0, items: queues?.expired_documents ?? [] },
    { key: 'visual_attention', title: '截图待处理', description: '视觉增强还未就绪。', total: governance.value?.summary.visual_attention ?? 0, items: queues?.visual_attention ?? [] },
    { key: 'missing_version_family', title: '版本元数据缺口', description: '填写了版本信息但缺少 version family key。', total: governance.value?.summary.missing_version_family ?? 0, items: queues?.missing_version_family ?? [] }
  ];
});
const filteredDocumentSections = computed(() => documentSections.value.map((section) => ({ ...section, items: filterItems(section.items) })));

const formatTime = (value?: string | null) => { if (!value) return '-'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date); };
const ownerLabel = (value: string) => !value ? '未设置' : value === currentUserId.value ? '我' : value;
const reviewerLabel = (userId: string, email: string) => userId === currentUserId.value ? '我' : email || userId || '-';
const reviewLabel = (status: string) => status === 'review_pending' ? '待审核' : status === 'approved' ? '已通过' : status === 'rejected' ? '已驳回' : '未设置';
const reasonLabel = (reason: string) => reason === 'review_pending' ? '待审核' : reason === 'draft_version' ? '草稿未提交' : reason === 'scheduled_publish' ? '待发布' : reason === 'approved_ready' ? '已通过待发布' : reason === 'rejected_review' ? '已驳回' : reason === 'expired_effective_window' ? '已过期' : reason === 'version_metadata_without_family' ? '缺少版本家族' : reason === 'visual_pipeline_low_confidence' ? '低置信截图区域' : reason.startsWith('visual_pipeline_') ? `视觉待处理 ${reason.replace('visual_pipeline_', '')}` : reason || '待处理';
const batchActionLabel = (patch?: Record<string, unknown> | null) => !patch ? '批量治理' : typeof patch.owner_user_id !== 'undefined' ? '批量指派' : patch.review_status === 'review_pending' ? '批量提交审核' : patch.review_status === 'approved' ? '批量通过' : patch.review_status === 'rejected' ? '批量驳回' : '批量治理';
const cloneBatchPatch = (patch?: Record<string, unknown> | null): BatchUpdateKBDocumentsPayload['patch'] => ({ ...(patch || {}) }) as BatchUpdateKBDocumentsPayload['patch'];
const filterItems = (items: KBGovernanceDocumentItem[]) => workset.value === 'all' ? items : workset.value === 'pending_me' ? items.filter((item) => item.owner_user_id === currentUserId.value) : items.filter((item) => item.reviewed_by_user_id === currentUserId.value);
const clearSelection = () => { selectedDocumentIds.value = []; };
const resetLowConfidenceRegions = () => {
  lowConfidenceExpandedDocumentIds.value = [];
  loadingLowConfidenceDocuments.value = {};
  lowConfidenceRegionsByDocument.value = {};
};
const isSelected = (documentId: string) => selectedDocumentIds.value.includes(documentId);
const toggleSelected = (documentId: string, checked: boolean | string | number) => { selectedDocumentIds.value = checked === true ? Array.from(new Set([...selectedDocumentIds.value, documentId])) : selectedDocumentIds.value.filter((item) => item !== documentId); };
const areAllSelected = (items: KBGovernanceDocumentItem[]) => items.length > 0 && items.every((item) => selectedDocumentIds.value.includes(item.document_id));
const toggleSectionSelection = (items: KBGovernanceDocumentItem[]) => { const ids = items.map((item) => item.document_id); selectedDocumentIds.value = areAllSelected(items) ? selectedDocumentIds.value.filter((item) => !ids.includes(item)) : Array.from(new Set([...selectedDocumentIds.value, ...ids])); };
const isLowConfidenceExpanded = (documentId: string) => lowConfidenceExpandedDocumentIds.value.includes(documentId);
const isLoadingLowConfidence = (documentId: string) => Boolean(loadingLowConfidenceDocuments.value[documentId]);
const lowConfidenceRegionsFor = (documentId: string) => lowConfidenceRegionsByDocument.value[documentId] ?? [];
const formatBbox = (bbox?: number[]) => Array.isArray(bbox) && bbox.length === 4 ? bbox.map((item) => Number(item).toFixed(2)).join(', ') : '-';
const resetDocumentForm = () => { Object.assign(documentForm, { owner_user_id: '', version_family_key: '', version_label: '', version_number: 1, version_status: 'active', is_current_version: false, effective_from: '', effective_to: '', supersedes_document_id: '', review_status: '', reviewer_note: '' }); };
const hydrateDocumentForm = (document: any) => { documentForm.owner_user_id = String(document.stats_json?.owner_user_id || document.created_by || '').trim(); documentForm.version_family_key = String(document.version_family_key || '').trim(); documentForm.version_label = String(document.version_label || '').trim(); documentForm.version_number = Number(document.version_number || 1); documentForm.version_status = String(document.version_status || 'active') || 'active'; documentForm.is_current_version = Boolean(document.is_current_version); documentForm.effective_from = String(document.effective_from || ''); documentForm.effective_to = String(document.effective_to || ''); documentForm.supersedes_document_id = String(document.supersedes_document_id || '').trim(); documentForm.review_status = String(document.stats_json?.review_status || '').trim(); documentForm.reviewer_note = String(document.stats_json?.reviewer_note || '').trim(); };
const loadLowConfidenceRegions = async (documentId: string) => {
  if (!documentId || isLoadingLowConfidence(documentId)) return;
  loadingLowConfidenceDocuments.value = { ...loadingLowConfidenceDocuments.value, [documentId]: true };
  try {
    const assetsResponse = await getKBDocumentVisualAssets(documentId);
    const assetsPayload = ((assetsResponse as any).data ?? assetsResponse) as { items?: GovernanceVisualAsset[] };
    const assets = Array.isArray(assetsPayload.items) ? assetsPayload.items.filter((asset) => String(asset?.asset_id || '').trim()) : [];
    if (!assets.length) {
      lowConfidenceRegionsByDocument.value = { ...lowConfidenceRegionsByDocument.value, [documentId]: [] };
      return;
    }
    const regionGroups = await Promise.all(
      assets.map(async (asset) => {
        const regionResponse = await getKBVisualAssetRegions(String(asset.asset_id)).catch(() => ({ items: [] }));
        const regionPayload = ((regionResponse as any).data ?? regionResponse) as { items?: KBVisualAssetRegion[] };
        return (Array.isArray(regionPayload.items) ? regionPayload.items : [])
          .filter((region) => typeof region?.confidence === 'number' && Number(region.confidence) < LOW_CONFIDENCE_THRESHOLD)
          .map((region) => ({
            ...region,
            asset_file_name: String(asset.file_name || ''),
            asset_page_number: asset.page_number ?? region.page_number ?? null
          }) as GovernanceLowConfidenceRegion);
      })
    );
    lowConfidenceRegionsByDocument.value = {
      ...lowConfidenceRegionsByDocument.value,
      [documentId]: regionGroups.flat().sort((left, right) => Number(left.confidence ?? 1) - Number(right.confidence ?? 1))
    };
  } finally {
    loadingLowConfidenceDocuments.value = { ...loadingLowConfidenceDocuments.value, [documentId]: false };
  }
};
const toggleLowConfidenceRegions = async (item: KBGovernanceDocumentItem) => {
  const documentId = String(item.document_id || '');
  if (!documentId) return;
  if (isLowConfidenceExpanded(documentId)) {
    lowConfidenceExpandedDocumentIds.value = lowConfidenceExpandedDocumentIds.value.filter((value) => value !== documentId);
    return;
  }
  lowConfidenceExpandedDocumentIds.value = Array.from(new Set([...lowConfidenceExpandedDocumentIds.value, documentId]));
  if (!lowConfidenceRegionsFor(documentId).length && Number(item.low_confidence_region_count || 0) > 0) {
    await loadLowConfidenceRegions(documentId);
  }
};
const loadGovernance = async () => { loading.value = true; resetLowConfidenceRegions(); try { const response = await getKBGovernance({ view: viewMode.value, limit: limit.value }); const payload = ((response as any).data ?? response) as KBGovernanceResponse; const visualAttention = Array.isArray(payload.queues?.visual_attention) ? payload.queues.visual_attention : []; const visualLowConfidence = Array.isArray(payload.queues?.visual_low_confidence) ? payload.queues.visual_low_confidence : []; governance.value = { ...payload, summary: { ...payload.summary, visual_attention: Number(payload.summary?.visual_attention ?? 0) + Number(payload.summary?.visual_low_confidence ?? 0) }, queues: { ...payload.queues, visual_attention: [...visualAttention, ...visualLowConfidence] } }; clearSelection(); } catch { governance.value = null; } finally { loading.value = false; } };
const loadBatchEvents = async () => { batchEventsLoading.value = true; try { const response = await getKBGovernanceBatchEvents({ view: viewMode.value, limit: 8 }); const payload = ((response as any).data ?? response) as KBGovernanceBatchEventsResponse; batchEvents.value = Array.isArray(payload.items) ? payload.items : []; } catch { batchEvents.value = []; } finally { batchEventsLoading.value = false; } };
const loadAllData = async () => { await Promise.all([loadGovernance(), loadBatchEvents()]); };
const findQueueItem = (documentId: string) => [...(governance.value?.queues.pending_review ?? []), ...(governance.value?.queues.approved_ready ?? []), ...(governance.value?.queues.rejected_documents ?? []), ...(governance.value?.queues.expired_documents ?? []), ...(governance.value?.queues.visual_attention ?? []), ...(governance.value?.queues.missing_version_family ?? [])].find((item) => item.document_id === documentId) || null;
const executeBatchRequest = async (payload: BatchUpdateKBDocumentsPayload) => { const response = await batchUpdateKBDocuments(payload); const result = ((response as any).data ?? response) as BatchUpdateKBDocumentsResponse; lastBatchRequest.value = payload; lastBatchResult.value = result; const successCount = Number(result.summary?.succeeded ?? 0); const failedCount = Number(result.summary?.failed ?? 0); if (successCount > 0) ElMessage.success(`批量操作完成：成功 ${successCount} 项${failedCount ? `，失败 ${failedCount} 项` : ''}`); else ElMessage.error('批量操作失败，请查看失败项详情后重试。'); clearSelection(); await Promise.all([loadGovernance(), loadBatchEvents()]); };
const runBulkAction = async (action: BulkAction) => { if (!selectedDocumentIds.value.length) return; if (action === 'rejected' && !batchReviewerNote.value.trim()) { ElMessage.warning('批量驳回前请填写统一备注。'); return; } bulkLoading.value = true; try { await executeBatchRequest(action === 'assign_to_me' ? { document_ids: selectedDocumentIds.value, patch: { owner_user_id: currentUserId.value || null } } : { document_ids: selectedDocumentIds.value, patch: { review_status: action, reviewer_note: batchReviewerNote.value.trim() } }); batchReviewerNote.value = ''; } finally { bulkLoading.value = false; } };
const retryFailedBatchItems = async () => { if (!lastBatchRequest.value || !failedBatchItems.value.length) return; bulkLoading.value = true; try { await executeBatchRequest({ document_ids: failedBatchItems.value.map((item) => item.document_id), retry_of_task_id: lastBatchResult.value?.task_id, patch: { ...lastBatchRequest.value.patch } }); } finally { bulkLoading.value = false; } };
const openGovernanceEditor = async (documentId: string) => { if (!documentId || editingDocumentId.value === documentId) return; editingDocumentId.value = documentId; try { const response = await getKBDocument(documentId); const document = (response as any).data ?? response; editTarget.value = findQueueItem(documentId) || { document_id: String(document.id || ''), base_id: String(document.base_id || ''), base_name: '', file_name: String(document.file_name || ''), status: String(document.status || ''), enhancement_status: String(document.enhancement_status || ''), version_family_key: String(document.version_family_key || ''), version_label: String(document.version_label || ''), version_number: document.version_number == null ? null : Number(document.version_number), version_status: String(document.version_status || ''), is_current_version: Boolean(document.is_current_version), effective_from: document.effective_from || null, effective_to: document.effective_to || null, effective_now: Boolean(document.effective_now), visual_asset_count: Number(document.stats_json?.visual_asset_count || 0), low_confidence_region_count: Number(document.stats_json?.visual_region_low_confidence_count || 0), low_confidence_asset_id: '', low_confidence_region_id: '', low_confidence_region_label: '', low_confidence_region_confidence: null, low_confidence_region_bbox: [], created_at: document.created_at || null, updated_at: document.updated_at || null, owner_user_id: String(document.stats_json?.owner_user_id || document.created_by || ''), review_status: String(document.stats_json?.review_status || ''), reviewer_note: String(document.stats_json?.reviewer_note || ''), reviewed_at: document.stats_json?.reviewed_at || null, reviewed_by_user_id: String(document.stats_json?.reviewed_by_user_id || ''), reviewed_by_email: String(document.stats_json?.reviewed_by_email || ''), reason: '' }; hydrateDocumentForm(document); editDrawerVisible.value = true; } finally { editingDocumentId.value = ''; } };
const closeGovernanceEditor = () => { editDrawerVisible.value = false; editTarget.value = null; resetDocumentForm(); };
const saveGovernanceDocument = async (overrideReviewStatus?: string) => { if (!editTarget.value) return; const nextReviewStatus = overrideReviewStatus ?? documentForm.review_status; if (nextReviewStatus === 'rejected' && !documentForm.reviewer_note.trim()) { ElMessage.warning('驳回时请填写审核备注。'); return; } if (!documentForm.version_family_key.trim() && editTarget.value.reason === 'version_metadata_without_family') { ElMessage.warning('该文档缺少版本家族 key，保存前请补齐。'); return; } savingEdit.value = true; try { await updateKBDocument(editTarget.value.document_id, { owner_user_id: documentForm.owner_user_id.trim() || null, version_family_key: documentForm.version_family_key.trim(), version_label: documentForm.version_label.trim(), version_number: documentForm.version_number, version_status: documentForm.version_status, is_current_version: documentForm.is_current_version, effective_from: documentForm.effective_from || null, effective_to: documentForm.effective_to || null, supersedes_document_id: documentForm.supersedes_document_id.trim() || null, review_status: nextReviewStatus, reviewer_note: documentForm.reviewer_note.trim() }); ElMessage.success('治理修正已保存'); closeGovernanceEditor(); await loadGovernance(); } finally { savingEdit.value = false; } };
const assignToMe = () => { documentForm.owner_user_id = currentUserId.value; };
const openDocument = (documentId: string, query: Record<string, string> = {}) => { router.push({ path: `/workspace/kb/documents/${documentId}`, query }); };
const openRegion = (documentId: string, region: GovernanceLowConfidenceRegion) => {
  openDocument(documentId, {
    assetId: String(region.asset_id || ''),
    regionId: String(region.region_id || '')
  });
};
const openLowConfidenceRegion = (item: KBGovernanceDocumentItem) => {
  if (!item.low_confidence_asset_id || !item.low_confidence_region_id) {
    openDocument(item.document_id);
    return;
  }
  openDocument(item.document_id, {
    assetId: item.low_confidence_asset_id,
    regionId: item.low_confidence_region_id,
  });
};
const openBase = (baseId: string) => { router.push(`/workspace/kb/upload?baseId=${baseId}`); };
const openConflict = (item: KBGovernanceVersionConflictItem) => { const targetDocumentId = item.current_document_ids[0]; if (targetDocumentId) openDocument(targetDocumentId); else openBase(item.base_id); };
const fetchBatchEventDetail = async (taskId: string, options: { offset?: number; append?: boolean } = {}) => {
  const response = await getKBGovernanceBatchEventDetail(taskId, {
    view: viewMode.value,
    timeline_limit: 10,
    timeline_offset: options.offset ?? 0,
    timeline_filter: batchTimelineFilter.value
  });
  const payload = ((response as any).data ?? response) as KBGovernanceBatchEventDetailResponse;
  if (options.append && selectedBatchEventTask.value?.task_id === payload.task_id) {
    selectedBatchEventTask.value = {
      ...payload,
      timeline: {
        ...payload.timeline,
        offset: 0,
        items: [...selectedBatchEventTask.value.timeline.items, ...payload.timeline.items]
      }
    };
    return;
  }
  selectedBatchEventTask.value = payload;
};
const reloadSelectedBatchEventTask = async () => {
  const taskId = selectedBatchEventTask.value?.task_id || selectedBatchEvent.value?.resource_id;
  if (!taskId) return;
  batchEventDetailLoading.value = true;
  try {
    await fetchBatchEventDetail(taskId);
  } catch {
    ElMessage.warning('批量治理详情刷新失败，请稍后重试。');
  } finally {
    batchEventDetailLoading.value = false;
  }
};
const loadMoreBatchEventTimeline = async () => {
  const task = selectedBatchEventTask.value;
  if (!task?.timeline.has_more) return;
  batchEventDetailLoading.value = true;
  try {
    await fetchBatchEventDetail(task.task_id, { offset: task.timeline.items.length, append: true });
  } catch {
    ElMessage.warning('批量治理时间线加载失败，请稍后重试。');
  } finally {
    batchEventDetailLoading.value = false;
  }
};
const closeBatchEventDrawer = () => { batchEventDrawerVisible.value = false; selectedBatchEvent.value = null; selectedBatchEventTask.value = null; batchTimelineFilter.value = 'all'; };
const openBatchEventDrawer = async (event: KBGovernanceBatchEventItem) => {
  selectedBatchEvent.value = event;
  selectedBatchEventTask.value = null;
  batchTimelineFilter.value = 'all';
  batchEventDrawerVisible.value = true;
  batchEventDetailLoading.value = true;
  try {
    await fetchBatchEventDetail(event.resource_id);
  } catch {
    ElMessage.warning('批量治理详情加载失败，已回退到审计摘要。');
  } finally {
    batchEventDetailLoading.value = false;
  }
};
const retrySelectedBatchTaskFailedItems = async () => {
  const detail = selectedBatchEventDetail.value;
  const patch = detail?.details?.patch;
  if (!detail || !patch || !selectedBatchEventFailedItems.value.length) return;
  bulkLoading.value = true;
  try {
    await executeBatchRequest({
      document_ids: selectedBatchEventFailedItems.value.map((item) => item.document_id),
      retry_of_task_id: selectedBatchEventTask.value?.task_id || detail.resource_id,
      patch: cloneBatchPatch(patch)
    });
    await openBatchEventDrawer(detail);
  } finally {
    bulkLoading.value = false;
  }
};
watch(workset, clearSelection);
onMounted(loadAllData);
</script>

<style scoped>
.governance-page { gap: 20px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
.summary-card, .panel { padding: 16px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-panel); }
.summary-card { display: flex; flex-direction: column; gap: 8px; }
.summary-label, .summary-hint, .toolbar-meta { font-size: 12px; color: var(--text-secondary); }
.summary-value { font-size: 28px; color: var(--text-primary); }
.toolbar-row, .panel-head, .actions, .toolbar-meta { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
.toolbar-group, .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.degraded-text, .note { color: var(--warning-color, #e6a23c); }
.panel, .list, .item-body { display: flex; flex-direction: column; gap: 12px; }
.detail-stack { display: flex; flex-direction: column; gap: 12px; }
.list { gap: 10px; }
.list-item { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border-radius: var(--radius-sm); background: var(--bg-panel-muted); }
.item-body { flex: 1; min-width: 0; }
.low-confidence-region-list { display: grid; gap: 8px; padding: 12px; border-radius: var(--radius-sm); background: var(--bg-panel-muted); }
.low-confidence-region-item { display: grid; gap: 8px; padding: 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: var(--bg-panel); }
.low-confidence-region-item__meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--text-secondary); }
.low-confidence-region-item__meta strong { color: var(--text-primary); }
.loading-panel, .empty { padding: 12px 0; }
.empty--compact { padding: 0; }
.detail-json { margin: 0; padding: 20px; white-space: pre-wrap; word-break: break-word; font-family: var(--font-mono); }
@media (max-width: 768px) { .toolbar-row, .panel-head, .list-item { flex-direction: column; align-items: stretch; } }
</style>
