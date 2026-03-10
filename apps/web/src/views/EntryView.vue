<template>
  <div class="page-shell entry-page">
    <PageHeaderCompact title="业务总览">
      <template #actions>
        <el-radio-group v-if="authStore.isAdmin()" v-model="viewMode" size="small" @change="loadDashboard" style="margin-right: 16px;">
          <el-radio-button value="personal">个人数据</el-radio-button>
          <el-radio-button value="admin">全局大盘</el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="go('/workspace/chat')">统一问答</el-button>
        <el-button plain @click="go('/workspace/kb/upload')">知识库治理</el-button>
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
        </div>
      </section>

      <!-- Dashboard Section -->
      <section v-if="loadingDashboard" class="dashboard-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载数据大盘...</span>
      </section>

      <section v-else class="dashboard-grid">
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

        <!-- 成本与Token消耗 -->
        <div class="dash-card">
          <h3 class="dash-title">消耗统计 ({{ dashboardData?.usage?.currency || 'CNY' }})</h3>
          <div class="usage-summary">
            <div class="usage-item">
              <span class="usage-val">{{ dashboardData?.usage?.summary?.assistant_turns || 0 }}</span>
              <span class="usage-label">助手对话轮数</span>
            </div>
            <div class="usage-item">
              <span class="usage-val">{{ (dashboardData?.usage?.summary?.estimated_cost || 0).toFixed(2) }}</span>
              <span class="usage-label">预估成本</span>
            </div>
          </div>
          <div class="usage-details">
            Prompt Tokens: {{ dashboardData?.usage?.summary?.prompt_tokens || 0 }}<br/>
            Completion Tokens: {{ dashboardData?.usage?.summary?.completion_tokens || 0 }}
          </div>
        </div>

        <!-- 用户满意度 -->
        <div class="dash-card">
          <h3 class="dash-title">用户满意度趋势 (近14天)</h3>
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

        <!-- Zero-hit 拦截统计 -->
        <div class="dash-card">
          <h3 class="dash-title">知识盲区 (无命中拦截)</h3>
          <ul class="zero-hit-list">
            <li v-for="(q, i) in dashboardData?.zero_hit?.top_queries" :key="i">
              <span class="q-text">{{ q.query }}</span>
              <el-tag size="small" type="danger">{{ q.count }} 次</el-tag>
            </li>
            <li v-if="!dashboardData?.zero_hit?.top_queries?.length" class="empty-text">暂无无命中查询</li>
          </ul>
        </div>
      </section>

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
import { ChatDotRound, UploadFilled, FolderOpened, Folder, ChatLineRound, Loading } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listKnowledgeBases } from '@/api/kb';
import { listChatSessions } from '@/api/chat';
import { getAnalyticsDashboard } from '@/api/analytics';
import { useAuthStore } from '@/store/auth';

const router = useRouter();
const authStore = useAuthStore();

const recentKnowledgeBases = ref<{ id: string; name: string; docCount: number }[]>([]);
const recentSessions = ref<{ id: string; title: string; questionCount: number }[]>([]);
const loadingHistory = ref(true);

const viewMode = ref<'personal' | 'admin'>('personal');
const dashboardData = ref<any>(null);
const loadingDashboard = ref(true);

const loadDashboard = async () => {
  loadingDashboard.value = true;
  try {
    const res: any = await getAnalyticsDashboard({ view: viewMode.value, days: 14 });
    dashboardData.value = res;
  } catch (e) {
    dashboardData.value = {};
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
</style>
