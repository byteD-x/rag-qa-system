
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
        <el-button plain @click="go('/workspace/kb/upload')">知识库治理</el-button>
        <el-button v-if="authStore.hasPermission('kb.manage')" plain @click="go('/workspace/kb/operations')">知识库运维</el-button>
      </template>
    </PageHeaderCompact>

    <div class="entry-content">
      <section class="quick-actions">
        <h3 class="section-label">快捷操作</h3>
        <div class="action-row">
          <button type="button" class="action-btn" @click="go('/workspace/chat')">
            <el-icon :size="22"><ChatDotRound /></el-icon>
            <span>快速问答</span>
          </button>
          <button type="button" class="action-btn" @click="go('/workspace/kb/upload')">
            <el-icon :size="22"><UploadFilled /></el-icon>
            <span>上传文档</span>
          </button>
          <button type="button" class="action-btn" @click="go('/workspace/kb/upload')">
            <el-icon :size="22"><FolderOpened /></el-icon>
            <span>知识库管理</span>
          </button>
          <button
            v-if="authStore.hasPermission('kb.manage')"
            type="button"
            class="action-btn"
            @click="go('/workspace/kb/operations')"
          >
            <el-icon :size="22"><Monitor /></el-icon>
            <span>运维值班</span>
          </button>
        </div>
      </section>

      <!-- Dashboard Section -->
      <section v-if="loadingDashboard" class="dashboard-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载数据大盘...</span>
      </section>

      <template v-else>
        <!-- 主链路漏斗 -->
        <section v-if="dashboardData?.funnel" class="dashboard-section">
          <div class="section-header">
            <h3 class="section-label" style="margin:0;">核心转化漏斗</h3>
            <span class="degraded-hint" v-if="hasDegradedSections">部分数据暂时降级，以下为可用指标</span>
          </div>
          <div class="funnel-container">
            <div class="funnel-step">
              <div class="f-label">新建知识库</div>
              <div class="f-value">{{ dashboardData.funnel.knowledge_bases_created ?? '-' }}</div>
            </div>
            <el-icon class="f-arrow"><Right /></el-icon>
            <div class="funnel-step">
              <div class="f-label">上传文档</div>
              <div class="f-value">{{ dashboardData.funnel.documents_uploaded ?? '-' }}</div>
            </div>
            <el-icon class="f-arrow"><Right /></el-icon>
            <div class="funnel-step">
              <div class="f-label">就绪可问</div>
              <div class="f-value">{{ dashboardData.funnel.documents_ready ?? '-' }}</div>
            </div>
            <el-icon class="f-arrow"><Right /></el-icon>
            <div class="funnel-step">
              <div class="f-label">发起提问</div>
              <div class="f-value">{{ dashboardData.funnel.questions_asked ?? 0 }}</div>
            </div>
            <el-icon class="f-arrow"><Right /></el-icon>
            <div class="funnel-step" :class="{'success-text': (dashboardData.funnel.answer_outcomes?.grounded || 0) > 0}">
              <div class="f-label">有据回答</div>
              <div class="f-value">{{ dashboardData.funnel.answer_outcomes?.grounded ?? 0 }}</div>
            </div>
            <el-icon class="f-arrow"><Right /></el-icon>
            <div class="funnel-step">
              <div class="f-label">接收反馈</div>
              <div class="f-value">{{ (dashboardData.funnel.feedback?.up || 0) + (dashboardData.funnel.feedback?.down || 0) }}</div>
            </div>
          </div>
        </section>

        <!-- 健康与质量并排 -->
        <section class="health-quality-grid">
          <!-- 入库健康度 -->
          <div class="dash-card">
            <div class="card-header">
              <h3 class="dash-title">入库健康度</h3>
              <el-button link type="primary" @click="go('/workspace/kb/upload')">去处理异常</el-button>
            </div>
            <div v-if="!dashboardData?.ingest_health" class="empty-state">
              <span>暂不支持入库指标或服务降级</span>
            </div>
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
              <el-button link type="primary" @click="go('/workspace/chat')">去检索调试</el-button>
            </div>
            <div v-if="!dashboardData?.qa_quality" class="empty-state">
              <span>暂无问答质量数据</span>
            </div>
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
                  <span class="q-label">Grounded (有据)</span>
                  <div class="q-track"><div class="q-fill success" :style="{ width: percent(dashboardData.qa_quality.summary.grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }"></div></div>
                  <span class="q-percent">{{ percent(dashboardData.qa_quality.summary.grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }}</span>
                </div>
                <div class="q-bar-row">
                  <span class="q-label">Weak / Partial</span>
                  <div class="q-track"><div class="q-fill warning" :style="{ width: percent(dashboardData.qa_quality.summary.weak_grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }"></div></div>
                  <span class="q-percent">{{ percent(dashboardData.qa_quality.summary.weak_grounded_answers, dashboardData.qa_quality.summary.assistant_answers) }}</span>
                </div>
                <div class="q-bar-row">
                  <span class="q-label">Refusal (无据拒答)</span>
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
                  <div class="kind-list__tags">
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
                    <span v-if="!dashboardData.qa_quality.clarification.kind_distribution.length" class="empty-text">暂无补问数据</span>
                  </div>
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
            <ul class="zero-hit-list">
              <li v-for="(q, i) in dashboardData?.zero_hit?.top_queries" :key="i">
                <span class="q-text" :title="q.query">{{ q.query }}</span>
                <el-tag size="small" type="danger">{{ q.count }} 次</el-tag>
              </li>
              <li v-if="!dashboardData?.zero_hit?.top_queries?.length" class="empty-text">暂无无命中查询，知识库覆盖良好</li>
            </ul>
          </div>

          <!-- 热点词云 -->
          <div class="dash-card">
            <h3 class="dash-title">问答热点词</h3>
            <div class="word-cloud">
              <span v-for="(term, i) in dashboardData?.hot_terms" :key="i"
                    class="cloud-tag"
                    :style="{ fontSize: `${12 + Math.min(term.count, 20)}px`, opacity: 0.5 + (term.count / 40) }">
                {{ term.term }}
              </span>
              <span v-if="!dashboardData?.hot_terms?.length" class="empty-text">暂无热点数据</span>
            </div>
          </div>

          <!-- 用户满意度 -->
          <div class="dash-card">
            <h3 class="dash-title">用户满意度趋势</h3>
            <div class="satisfaction-bars">
              <div v-for="(trend, i) in dashboardData?.satisfaction?.trend" :key="i" class="sat-bar-wrap" :title="trend.date">
                <div class="sat-bar up" :style="{ flex: trend.up_count || 0.1 }"></div>
                <div class="sat-bar down" :style="{ flex: trend.down_count || 0.1 }"></div>
              </div>
              <span v-if="!dashboardData?.satisfaction?.trend?.length" class="empty-text">暂无趋势数据</span>
            </div>
            <div class="sat-legend" v-if="dashboardData?.satisfaction?.trend?.length">
              <span class="leg-up">■ 赞</span>
              <span class="leg-down">■ 踩</span>
            </div>
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
          <div v-if="loadingHistory" class="recent-skeleton">
            <div v-for="i in 4" :key="i" class="skeleton-item" />
          </div>
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
              <span class="recent-meta">{{ kb.docCount }} 篇</span>
            </button>
          </div>
        </div>
        <div class="recent-col">
          <h3 class="section-label">最近会话</h3>
          <div v-if="loadingHistory" class="recent-skeleton">
            <div v-for="i in 4" :key="i" class="skeleton-item" />
          </div>
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
              <span class="recent-meta">{{ session.questionCount > 0 ? session.questionCount + ' 问' : '继续' }}</span>
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
import { ChatDotRound, UploadFilled, FolderOpened, Folder, ChatLineRound, Loading, Right, Warning, CircleCheckFilled, InfoFilled, Monitor } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listKnowledgeBases } from '@/api/kb';
import { listChatSessions } from '@/api/chat';
import { getAnalyticsDashboard } from '@/api/analytics';
import type { AnalyticsDashboardResponse } from '@/api/analytics';
import { computed } from 'vue';
import { useAuthStore } from '@/store/auth';

const router = useRouter();
const authStore = useAuthStore();

const recentKnowledgeBases = ref<{ id: string; name: string; docCount: number }[]>([]);
const recentSessions = ref<{ id: string; title: string; questionCount: number }[]>([]);
const loadingHistory = ref(true);

const viewMode = ref<'personal' | 'admin'>('personal');
const days = ref(14);
const dashboardData = ref<AnalyticsDashboardResponse | null>(null);
const hasDegradedSections = computed(() => (dashboardData.value?.data_quality?.degraded_sections?.length ?? 0) > 0);

const percent = (part: number, total: number) => {
  if (!total) return '0%';
  return Math.round((part / total) * 100) + '%';
};
const percentByRate = (rate: number) => `${Math.round((Number(rate || 0) || 0) * 100)}%`;
const loadingDashboard = ref(true);

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
  try {
    const res = await getAnalyticsDashboard({ view: viewMode.value, days: days.value });
    dashboardData.value = (res as any).data ?? res;
  } catch (e) {
    dashboardData.value = null;
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
      name: String(b.name || '未命名'),
      docCount: Number(b.document_count ?? 0)
    }));
    recentSessions.value = sessionItems.slice(0, 6).map((s: any) => ({
      id: String(s.id || ''),
      title: String(s.title || '未命名会话').trim() || '未命名会话',
      questionCount: Number(s.message_count ?? s.question_count ?? 0)
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

.quick-actions {
  flex-shrink: 0;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  color: var(--text-primary);
  font-size: var(--text-body, 0.9375rem);
  font-weight: 500;
  cursor: pointer;
  transition: border-color var(--transition-base), background var(--transition-base);
}

.action-btn:hover {
  border-color: var(--blue-600);
  background: var(--blue-50);
}

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--section-gap, 24px);
}

.dashboard-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-muted);
  padding: 20px 0;
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
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-text {
  font-size: 13px;
  color: var(--text-muted);
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
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
}

.usage-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.usage-details {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.satisfaction-bars {
  display: flex;
  gap: 4px;
  height: 100px;
  align-items: flex-end;
  flex: 1;
}

.sat-bar-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  justify-content: flex-end;
  gap: 2px;
}

.sat-bar {
  width: 100%;
  border-radius: 2px;
}

.sat-bar.up {
  background: var(--success-color, #67c23a);
}

.sat-bar.down {
  background: var(--danger-color, #f56c6c);
}

.sat-legend {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.leg-up { color: var(--success-color, #67c23a); }
.leg-down { color: var(--danger-color, #f56c6c); }

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
  font-size: 13px;
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
  transition: border-color var(--transition-base), background var(--transition-base);
}

.recent-item:hover {
  border-color: var(--border-color);
  background: var(--bg-panel);
}

.recent-name {
  flex: 1;
  font-size: var(--text-body, 0.9375rem);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-meta {
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-muted);
  flex-shrink: 0;
}

.recent-empty-inline {
  padding: 32px 16px !important;
}

.recent-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skeleton-item {
  height: 48px;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--bg-panel-muted) 25%, var(--border-color) 50%, var(--bg-panel-muted) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.2s ease-in-out infinite;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Dashboard Specific Styles */
.dashboard-section {
  margin-bottom: var(--section-gap, 24px);
}
.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.degraded-hint {
  font-size: 12px;
  color: var(--warning-color, #e6a23c);
  background: var(--warning-bg, #fdf6ec);
  padding: 2px 8px;
  border-radius: 4px;
}

/* Funnel */
.funnel-container {
  display: flex;
  align-items: center;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  overflow-x: auto;
}
.funnel-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 80px;
}
.f-label {
  font-size: 13px;
  color: var(--text-secondary);
}
.f-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}
.f-arrow {
  font-size: 20px;
  color: var(--border-color);
  margin: 0 16px;
  flex-shrink: 0;
}
.success-text .f-value {
  color: var(--success-color, #67c23a);
}

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
  gap: 12px;
  margin-bottom: 16px;
}
.metric-box {
  flex: 1;
  background: var(--bg-panel-muted);
  border-radius: var(--radius-sm);
  padding: 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid transparent;
}
.metric-box.success-bg {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.2);
}
.metric-box.warning-bg {
  background: rgba(230, 162, 60, 0.1);
  border-color: rgba(230, 162, 60, 0.2);
}
.metric-box.danger-bg {
  background: rgba(245, 108, 108, 0.1);
  border-color: rgba(245, 108, 108, 0.2);
}
.m-val {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}
.m-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.health-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.health-alert.danger {
  background: rgba(245, 108, 108, 0.1);
  color: var(--danger-color, #f56c6c);
}
.health-alert.warning {
  background: rgba(230, 162, 60, 0.1);
  color: var(--warning-color, #e6a23c);
}
.health-alert.info {
  background: rgba(64, 158, 255, 0.1);
  color: var(--blue-600);
}
.health-alert.success {
  background: rgba(103, 194, 58, 0.1);
  color: var(--success-color, #67c23a);
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
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
  flex-shrink: 0;
}
.q-track {
  flex: 1;
  height: 8px;
  background: var(--bg-panel-muted);
  border-radius: 4px;
  overflow: hidden;
}
.q-fill {
  height: 100%;
  border-radius: 4px;
}
.q-fill.success { background: var(--success-color, #67c23a); }
.q-fill.warning { background: var(--warning-color, #e6a23c); }
.q-fill.danger { background: var(--danger-color, #f56c6c); }
.q-fill.info { background: var(--blue-600); }
.q-percent {
  width: 40px;
  font-size: 12px;
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
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.clarification-panel__info {
  color: var(--blue-600);
  cursor: help;
}

.clarification-panel__hint {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

.clarification-panel__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.clarification-metrics {
  margin-bottom: 0;
}

.clarification-detail-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.clarification-kind-list {
  display: grid;
  gap: 8px;
}

.kind-list__label {
  font-size: 12px;
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
