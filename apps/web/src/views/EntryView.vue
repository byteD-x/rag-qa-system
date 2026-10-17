
<template>
  <div class="page-shell entry-page">
    <PageHeaderCompact title="业务总览">
      <template #actions>
        <el-radio-group v-if="authStore.isAdmin()" v-model="viewMode" size="small" @change="loadDashboard" style="margin-right: 16px;">
          <el-radio-button value="personal">个人数据</el-radio-button>
          <el-radio-button value="admin">全局大盘</el-radio-button>
        </el-radio-group>
        <el-select v-model="days" size="small" style="width: 100px; margin-right: 16px;" @change="loadDashboard">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 14 天" :value="14" />
          <el-option label="近 30 天" :value="30" />
        </el-select>
        <el-button type="primary" @click="go('/workspace/chat')">统一问答</el-button>
        <span v-if="loadingDashboard && dashboardData" class="header-loading" role="status" aria-live="polite">
          <el-icon class="is-loading" :size="14"><Loading /></el-icon>
          更新中
        </span>
      </template>
    </PageHeaderCompact>

    <div class="entry-content">
      <!-- Dashboard Section：仅首次加载（页面尚无任何数据）时整段 loading -->
      <LoadingState v-if="loadingDashboard && !dashboardData" label="加载数据大盘…" />

      <!-- 加载失败且没有可用数据：与「真的没有数据」区分开，并给出重试 -->
      <section v-else-if="loadError && !dashboardData" role="alert">
        <EnhancedEmpty
          variant="default"
          title="数据大盘加载失败"
          description="可能是服务暂时不可用或网络异常，请重试。"
        >
          <template #actions>
            <el-button type="primary" @click="loadDashboard">重试</el-button>
          </template>
        </EnhancedEmpty>
      </section>

      <template v-else>
        <!-- 刷新失败但保留旧数据：不整段卸载，只提示失败并提供重试 -->
        <section v-if="loadError" class="dashboard-failure-bar" role="alert">
          <el-icon><Warning /></el-icon>
          <span>数据刷新失败，以下为上次加载结果</span>
          <el-button link type="primary" @click="loadDashboard">重试</el-button>
        </section>

        <!-- 健康与质量并排 -->
        <section class="health-quality-grid">
          <!-- 入库健康度 -->
          <div class="dash-card">
            <div class="card-header">
              <h3 class="dash-title">入库健康度</h3>
              <el-button link type="primary" @click="go('/workspace/kb/upload')">去处理异常</el-button>
            </div>
            <EnhancedEmpty
              v-if="!dashboardData?.ingest_health"
              class="card-empty"
              variant="document"
              title="暂不支持入库指标或服务降级"
              description="当前视图没有可用的入库健康度数据"
              :image-size="24"
            />
            <div v-else class="health-content">
              <div class="metric-row">
                <div class="metric-box">
                  <div class="m-val">{{ dashboardData.ingest_health.summary.total_documents }}</div>
                  <div class="m-label">总文档</div>
                </div>
                <div class="metric-box success-bg">
                  <div class="m-val">{{ dashboardData.ingest_health.summary.ready_documents }}</div>
                  <div class="m-label">就绪状态</div>
                </div>
                <div class="metric-box" :class="{'danger-bg': dashboardData.ingest_health.summary.failed_documents > 0}">
                  <div class="m-val">{{ dashboardData.ingest_health.summary.failed_documents }}</div>
                  <div class="m-label">解析失败</div>
                </div>
                <div class="metric-box" :class="{'warning-bg': dashboardData.ingest_health.summary.stalled_documents > 0}">
                  <div class="m-val">{{ dashboardData.ingest_health.summary.stalled_documents }}</div>
                  <div class="m-label">长期卡住</div>
                </div>
              </div>
              <div v-if="dashboardData.ingest_health.summary.failed_documents > 0 || dashboardData.ingest_health.summary.stalled_documents > 0" class="health-alert danger">
                <el-icon><Warning /></el-icon> 有文档未能正常解析入库，请前往知识库进行排查。
              </div>
              <div v-else-if="dashboardData.ingest_health.summary.in_progress_documents > 0" class="health-alert info">
                <el-icon><Loading /></el-icon> 正在处理 {{ dashboardData.ingest_health.summary.in_progress_documents }} 篇文档...
              </div>
              <div v-else class="health-alert success">
                <el-icon><CircleCheckFilled /></el-icon> 所有文档均已就绪
              </div>
            </div>
          </div>

          <!-- 问答质量 -->
          <div class="dash-card">
            <div class="card-header">
              <h3 class="dash-title">问答质量洞察</h3>
            </div>
            <EnhancedEmpty
              v-if="!dashboardData?.qa_quality"
              class="card-empty"
              variant="question"
              title="暂无问答质量数据"
              description="当前视图没有可用的问答质量数据"
              :image-size="24"
            />
            <div v-else class="qa-content">
              <div class="metric-row">
                <div class="metric-box">
                  <div class="m-val">{{ dashboardData.qa_quality.summary.assistant_answers }}</div>
                  <div class="m-label">总回答数</div>
                </div>
                <div class="metric-box" :class="{'warning-bg': dashboardData.qa_quality.zero_hit.selected_candidates_zero > 0}">
                  <div class="m-val">{{ dashboardData.qa_quality.zero_hit.selected_candidates_zero }}</div>
                  <div class="m-label">零命中拦截</div>
                </div>
                <div class="metric-box" :class="{'danger-bg': dashboardData.qa_quality.low_quality.count > 0}">
                  <div class="m-val">{{ dashboardData.qa_quality.low_quality.count }}</div>
                  <div class="m-label">低质量回答</div>
                </div>
              </div>
              <div class="quality-bars" v-if="dashboardData.qa_quality.summary.assistant_answers > 0">
                <div class="q-bar-row">
                  <span class="q-label">有依据</span>
                  <div class="q-track"><div class="q-fill success" :style="{ width: percent(dashboardData.qa_quality.summary.grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }"></div></div>
                  <span class="q-percent">{{ percent(dashboardData.qa_quality.summary.grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }}</span>
                </div>
                <div class="q-bar-row">
                  <span class="q-label">依据不足</span>
                  <div class="q-track"><div class="q-fill warning" :style="{ width: percent(dashboardData.qa_quality.summary.weak_grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }"></div></div>
                  <span class="q-percent">{{ percent(dashboardData.qa_quality.summary.weak_grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }}</span>
                </div>
                <div class="q-bar-row">
                  <span class="q-label">无依据拒答</span>
                  <div class="q-track"><div class="q-fill danger" :style="{ width: percent(dashboardData.qa_quality.summary.refusal_answers, dashboardData.qa_quality.summary.assistant_answers) }"></div></div>
                  <span class="q-percent">{{ percent(dashboardData.qa_quality.summary.refusal_answers, dashboardData.qa_quality.summary.assistant_answers) }}</span>
                </div>
              </div>
              <div v-if="dashboardData.qa_quality.clarification" class="clarification-panel">
                <div class="clarification-panel__header">
                  <div class="clarification-panel__heading">
                    <span class="clarification-panel__title">补问闭环</span>
                    <el-tooltip :content="clarificationPanelTooltip" placement="top" effect="light">
                      <el-icon class="clarification-panel__info"><InfoFilled /></el-icon>
                    </el-tooltip>
                  </div>
                  <span class="clarification-panel__hint">观察版本确认、截图确认等补问是否顺利完成</span>
                  <div class="clarification-panel__meta">
                    <span>统计窗口：最近 {{ days }} 天</span>
                    <span>待处理表示当前仍停留在补问中断态</span>
                  </div>
                </div>
                <div class="metric-row clarification-metrics">
                  <div class="metric-box">
                    <div class="m-val">{{ dashboardData.qa_quality.clarification.triggered_runs }}</div>
                    <div class="m-label">触发补问</div>
                  </div>
                  <div class="metric-box">
                    <div class="m-val">{{ dashboardData.qa_quality.clarification.completed_runs }}</div>
                    <div class="m-label">已完成</div>
                  </div>
                  <div class="metric-box" :class="{ 'warning-bg': dashboardData.qa_quality.clarification.pending_runs > 0 }">
                    <div class="m-val">{{ dashboardData.qa_quality.clarification.pending_runs }}</div>
                    <div class="m-label">待处理</div>
                  </div>
                </div>
                <div class="q-bar-row">
                  <span class="q-label">补问完成率</span>
                  <div class="q-track"><div class="q-fill info" :style="{ width: percentByRate(dashboardData.qa_quality.clarification.completion_rate) }"></div></div>
                  <span class="q-percent">{{ percentByRate(dashboardData.qa_quality.clarification.completion_rate) }}</span>
                </div>
                <div class="clarification-detail-row">
                  <span>结构化选择 {{ dashboardData.qa_quality.clarification.selection_runs }}</span>
                  <span>自由补充 {{ dashboardData.qa_quality.clarification.free_text_runs }}</span>
                </div>
                <div class="clarification-kind-list">
                  <span class="kind-list__label">补问类型分布</span>
                  <div v-if="dashboardData.qa_quality.clarification.kind_distribution.length" class="kind-list__tags">
                    <el-tooltip
                      v-for="item in dashboardData.qa_quality.clarification.kind_distribution"
                      :key="item.key"
                      :content="clarificationKindDescription(item.key)"
                      placement="top"
                      effect="light"
                    >
                      <el-tag
                        size="small"
                        effect="plain"
                        class="clarification-kind-tag"
                      >
                        {{ clarificationKindLabel(item.key) }} {{ item.count }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                  <EnhancedEmpty
                    v-else
                    class="card-empty"
                    variant="question"
                    title="暂无补问数据"
                    description="当前时间窗口内没有触发补问"
                    :image-size="24"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 辅助指标网格 -->
        <section class="dashboard-grid" style="margin-bottom: 24px;">
          <!-- 知识盲区 -->
          <div class="dash-card">
            <h3 class="dash-title">知识盲区 (高频无命中)</h3>
            <ul v-if="dashboardData?.zero_hit?.top_queries?.length" class="zero-hit-list">
              <li v-for="(q, i) in dashboardData?.zero_hit?.top_queries" :key="i">
                <span class="q-text" :title="q.query">{{ q.query }}</span>
                <el-tag size="small" type="danger">{{ q.count }} 次</el-tag>
              </li>
            </ul>
            <EnhancedEmpty
              v-else
              class="card-empty"
              variant="search"
              title="暂无无命中查询"
              description="当前时间窗口内的提问都能命中已有文档"
              :image-size="24"
            />
          </div>

          <!-- 热点词云 -->
          <div class="dash-card">
            <h3 class="dash-title">问答热点词</h3>
            <div v-if="dashboardData?.hot_terms?.length" class="word-cloud">
              <span v-for="(term, i) in dashboardData?.hot_terms" :key="i"
                    class="cloud-tag"
                    :style="{ fontSize: `${12 + Math.min(term.count, 20)}px`, opacity: 0.5 + (term.count / 40) }">
                {{ term.term }}
              </span>
            </div>
            <EnhancedEmpty
              v-else
              class="card-empty"
              variant="default"
              title="暂无热点词"
              description="当前时间窗口内没有可用于统计的提问词"
              :image-size="24"
            />
          </div>

          <!-- 成本与Token消耗 -->
          <div class="dash-card">
            <h3 class="dash-title">消耗统计 ({{ dashboardData?.usage?.currency || 'CNY' }})</h3>
            <div class="usage-summary">
              <div class="usage-item">
                <span class="usage-val">{{ dashboardData?.usage?.summary?.assistant_turns || 0 }}</span>
                <span class="usage-label">对话轮数</span>
              </div>
              <div class="usage-item">
                <span class="usage-val">{{ (dashboardData?.usage?.summary?.estimated_cost || 0).toFixed(2) }}</span>
                <span class="usage-label">预估成本</span>
              </div>
            </div>
            <div class="usage-details">
              Prompt: {{ dashboardData?.usage?.summary?.prompt_tokens || 0 }}<br/>
              Completion: {{ dashboardData?.usage?.summary?.completion_tokens || 0 }}
            </div>
          </div>
        </section>
      </template>

      <!-- Recent History -->
      <section class="recent-grid">
        <div class="recent-col">
          <h3 class="section-label">最近知识库</h3>
          <LoadingState v-if="loadingHistory" label="加载最近知识库…" />
          <EnhancedEmpty
            v-else-if="!recentKnowledgeBases.length"
            variant="folder"
            title="暂无知识库"
            description="创建知识库后，文档将在此展示"
            class="recent-empty-inline"
          />
          <div v-else class="recent-list">
            <button
              v-for="kb in recentKnowledgeBases.slice(0, 4)"
              :key="kb.id"
              type="button"
              class="recent-item"
              @click="go(`/workspace/kb/upload?baseId=${kb.id}`)"
            >
              <el-icon :size="16"><Folder /></el-icon>
              <span class="recent-name">{{ kb.name }}</span>
            </button>
          </div>
        </div>
        <div class="recent-col">
          <h3 class="section-label">最近会话</h3>
          <LoadingState v-if="loadingHistory" label="加载最近会话…" />
          <EnhancedEmpty
            v-else-if="!recentSessions.length"
            variant="chat"
            title="暂无会话"
            description="开始新对话后，最近会话将在此展示"
            class="recent-empty-inline"
          />
          <div v-else class="recent-list">
            <button
              v-for="session in recentSessions.slice(0, 4)"
              :key="session.id"
              type="button"
              class="recent-item"
              @click="go(`/workspace/chat?sessionId=${session.id}`)"
            >
              <el-icon :size="16"><ChatLineRound /></el-icon>
              <span class="recent-name">{{ session.title }}</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Folder, ChatLineRound, Loading, Warning, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import LoadingState from '@/components/LoadingState.vue';
import { listKnowledgeBases } from '@/api/kb';
import { listChatSessions } from '@/api/chat';
import { getAnalyticsDashboard } from '@/api/analytics';
import type { AnalyticsDashboardResponse } from '@/api/analytics';
import { useAuthStore } from '@/store/auth';

const router = useRouter();
const authStore = useAuthStore();

const recentKnowledgeBases = ref<{ id: string; name: string }[]>([]);
const recentSessions = ref<{ id: string; title: string }[]>([]);
const loadingHistory = ref(true);

const viewMode = ref<'personal' | 'admin'>('personal');
const days = ref(14);
const dashboardData = ref<AnalyticsDashboardResponse | null>(null);

const percent = (part: number, total: number) => {
  if (!total) return '0%';
  return Math.round((part / total) * 100) + '%';
};
const percentByRate = (rate: number) => `${Math.round((Number(rate || 0) || 0) * 100)}%`;
const loadingDashboard = ref(true);
const loadError = ref(false);

const clarificationPanelTooltip = '已完成表示补问后成功恢复并继续完成回答；待处理表示当前仍停留在 interrupted 状态。';

const clarificationKindLabel = (value: string) => {
  if (value === 'time_ambiguity') return '时间歧义';
  if (value === 'version_conflict') return '版本冲突';
  if (value === 'visual_ambiguity') return '截图歧义';
  if (value === 'scope_ambiguity') return '范围确认';
  if (value === 'insufficient_evidence') return '证据不足';
  return value || '未知类型';
};

const clarificationKindDescription = (value: string) => {
  if (value === 'time_ambiguity') return '检索结果跨越多个时间点或版本区间，系统需要先确认你关心的是哪个时间范围。';
  if (value === 'version_conflict') return '同一文档家族命中了多个版本，系统需要先确认是看当前版、历史版，还是先比较差异。';
  if (value === 'visual_ambiguity') return '问题涉及截图，但命中了多个区域或页面，系统需要先确认具体截图位置。';
  if (value === 'scope_ambiguity') return '当前提问缺少明确的文档范围或对象，系统需要先缩小检索范围。';
  if (value === 'insufficient_evidence') return '现有证据不足以稳定作答，系统会先请求更多上下文，避免直接给出不可靠答案。';
  return '该类型暂未配置额外说明。';
};

const loadDashboard = async () => {
  loadingDashboard.value = true;
  loadError.value = false;
  try {
    const res = await getAnalyticsDashboard({ view: viewMode.value, days: days.value });
    dashboardData.value = (res as any).data ?? res;
  } catch (e) {
    loadError.value = true;
  } finally {
    loadingDashboard.value = false;
  }
};

onMounted(async () => {
  if (authStore.isAdmin()) {
    viewMode.value = 'admin';
  } else {
    viewMode.value = 'personal';
  }
  loadDashboard();

  loadingHistory.value = true;
  try {
    const [kbRes, sessionRes] = await Promise.all([
      listKnowledgeBases().catch(() => ({ items: [] })),
      listChatSessions().catch(() => ({ items: [] }))
    ]);
    const kbItems = (kbRes as any).items || [];
    const sessionItems = (sessionRes as any).items || [];
    recentKnowledgeBases.value = kbItems.slice(0, 6).map((b: any) => ({
      id: String(b.id || ''),
      name: String(b.name || '未命名')
    }));
    recentSessions.value = sessionItems.slice(0, 6).map((s: any) => ({
      id: String(s.id || ''),
      title: String(s.title || '未命名会话').trim() || '未命名会话'
    }));
  } finally {
    loadingHistory.value = false;
  }
});

const go = (path: string) => {
  router.push(path);
};
</script>
<style scoped>
.entry-page {
  gap: var(--content-gap, 20px);
}

.entry-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
  min-height: 0;
  overflow-y: auto;
}

.section-label {
  margin: 0 0 12px;
  font-size: var(--text-body, 0.9375rem);
  font-weight: 600;
  color: var(--text-secondary);
}

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--section-gap, 24px);
}

.header-loading {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 12px;
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-muted);
}

.dashboard-failure-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(230, 162, 60, 0.1);
  color: var(--el-color-warning);
  font-size: var(--text-caption, 0.75rem);
}

.card-empty {
  padding: 24px 0 !important;
}

.card-empty :deep(.default-illustration) {
  width: 48px;
  height: 48px;
}

.card-empty :deep(.empty-illustration) {
  margin-bottom: 12px;
}

.card-empty :deep(.empty-title) {
  font-size: var(--text-body, 0.9375rem);
}

.card-empty :deep(.empty-description) {
  font-size: var(--text-caption, 0.75rem);
}

.dash-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.dash-title {
  margin: 0 0 16px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.word-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: center;
  flex: 1;
}

.cloud-tag {
  color: var(--blue-600);
  font-weight: bold;
}

.usage-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}

.usage-item {
  display: flex;
  flex-direction: column;
}

.usage-val {
  font-size: var(--text-h1);
  font-weight: bold;
  color: var(--text-primary);
}

.usage-label {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.usage-details {
  font-size: var(--text-caption);
  color: var(--text-muted);
  line-height: 1.5;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.zero-hit-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.zero-hit-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-caption);
}

.q-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  margin-right: 12px;
}

/* Recent Grid */
.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--section-gap, 24px);
}

.recent-col {
  min-width: 0;
  padding: 18px 20px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--transition-base);
}

@media (hover: hover) and (pointer: fine) {
  .recent-item:hover {
    border-color: var(--border-color);
  }
}

.recent-name {
  flex: 1;
  font-size: var(--text-body, 0.9375rem);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-empty-inline {
  padding: 32px 16px !important;
}

/* Dashboard Specific Styles */
/* Health & Quality Grid */
.health-quality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: var(--section-gap, 24px);
  margin-bottom: var(--section-gap, 24px);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.card-header .dash-title {
  margin: 0;
}
.metric-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.metric-box {
  flex: 1;
  padding: 8px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric-box.success-bg {
  background: rgba(103, 194, 58, 0.1);
}
.metric-box.warning-bg {
  background: rgba(230, 162, 60, 0.1);
}
.metric-box.danger-bg {
  background: rgba(245, 108, 108, 0.1);
}
.m-val {
  font-size: var(--text-h2);
  font-weight: 600;
  color: var(--text-primary);
}
.m-label {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}
.health-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: var(--text-caption);
}
.health-alert.danger {
  background: rgba(245, 108, 108, 0.1);
  color: var(--el-color-danger);
}
.health-alert.warning {
  background: rgba(230, 162, 60, 0.1);
  color: var(--el-color-warning);
}
.health-alert.info {
  background: rgba(64, 158, 255, 0.1);
  color: var(--blue-600);
}
.health-alert.success {
  background: rgba(103, 194, 58, 0.1);
  color: var(--el-color-success);
}

/* Quality Bars */
.quality-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.q-bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.q-label {
  width: 120px;
  font-size: var(--text-caption);
  color: var(--text-secondary);
  text-align: right;
  flex-shrink: 0;
}
.q-track {
  flex: 1;
  height: 8px;
  background: var(--bg-panel-muted);
  border-radius: var(--radius-xs);
  overflow: hidden;
}
.q-fill {
  height: 100%;
  border-radius: var(--radius-xs);
}
.q-fill.success { background: var(--el-color-success); }
.q-fill.warning { background: var(--el-color-warning); }
.q-fill.danger { background: var(--el-color-danger); }
.q-fill.info { background: var(--blue-600); }
.q-percent {
  width: 40px;
  font-size: var(--text-caption);
  color: var(--text-primary);
  font-weight: 500;
  text-align: right;
  flex-shrink: 0;
}

.clarification-panel {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--border-color);
  display: grid;
  gap: 12px;
}

.clarification-panel__header {
  display: grid;
  gap: 4px;
}

.clarification-panel__heading {
  display: flex;
  align-items: center;
  gap: 6px;
}

.clarification-panel__title {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-primary);
}

.clarification-panel__info {
  color: var(--blue-600);
  cursor: help;
}

.clarification-panel__hint {
  font-size: var(--text-caption);
  color: var(--text-muted);
  line-height: 1.5;
}

.clarification-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.clarification-metrics {
  margin-bottom: 0;
}

.clarification-detail-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.clarification-kind-list {
  display: grid;
  gap: 8px;
}

.kind-list__label {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.kind-list__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.clarification-kind-tag {
  cursor: help;
}
</style>
