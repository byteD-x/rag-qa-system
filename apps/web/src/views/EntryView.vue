<template>
  <div class="page-shell entry-page">
    <PageHeaderCompact title="业务总览">
      <template #actions>
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

      <section class="recent-grid">
        <div class="recent-col">
          <h3 class="section-label">知识库</h3>
          <div v-if="loading" class="recent-skeleton">
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
          <div v-if="loading" class="recent-skeleton">
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
import { ChatDotRound, UploadFilled, FolderOpened, Folder, ChatLineRound } from '@element-plus/icons-vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listKnowledgeBases } from '@/api/kb';
import { listChatSessions } from '@/api/chat';

const router = useRouter();

const recentKnowledgeBases = ref<{ id: string; name: string; docCount: number }[]>([]);
const recentSessions = ref<{ id: string; title: string; questionCount: number }[]>([]);
const loading = ref(true);

onMounted(async () => {
  loading.value = true;
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
    loading.value = false;
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

.recent-empty-inline :deep(.default-illustration) {
  width: 56px;
  height: 56px;
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
