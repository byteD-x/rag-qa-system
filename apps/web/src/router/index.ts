import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/store/auth';

const routes = [
  {
    path: '/',
    redirect: '/workspace/chat'
  },
  {
    path: '/entry',
    redirect: '/workspace/entry'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/layouts/AuthLayout.vue'),
    meta: {
      title: '登录',
      subtitle: ''
    },
    children: [
      {
        path: '',
        name: 'LoginView',
        component: () => import('@/views/LoginView.vue')
      }
    ]
  },
  {
    path: '/workspace',
    name: 'WorkspaceRoot',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: {
      requiresAuth: true,
      title: 'RAG-QA 工作台',
      subtitle: '',
      breadcrumb: ['工作台']
    },
    children: [
      {
        path: 'entry',
        name: 'EntryView',
        component: () => import('@/views/EntryView.vue'),
        meta: {
          title: '业务总览',
          subtitle: '',
          breadcrumb: ['工作台', '业务总览']
        }
      },
      {
        path: 'chat',
        name: 'UnifiedChatView',
        component: () => import('@/views/chat/UnifiedChatView.vue'),
        meta: {
          requiresPermission: 'chat.use',
          title: '统一问答',
          subtitle: '',
          breadcrumb: ['工作台', '统一问答']
        }
      },
      {
        path: 'kb/upload',
        name: 'KBUploadView',
        component: () => import('@/views/kb/KBUploadView.vue'),
        meta: {
          requiresPermission: 'kb.read',
          title: '知识库治理',
          subtitle: '',
          breadcrumb: ['工作台', '知识库治理']
        }
      },
      {
        path: 'kb/connectors',
        name: 'KBConnectorsView',
        component: () => import('@/views/kb/KBConnectorsView.vue'),
        meta: {
          requiresPermission: 'kb.manage',
          title: '多源同步',
          subtitle: '',
          breadcrumb: ['工作台', '多源同步']
        }
      },
      {
        path: 'kb/debugger',
        name: 'RetrievalDebuggerView',
        component: () => import('@/views/kb/RetrievalDebuggerView.vue'),
        meta: {
          requiresPermission: 'kb.manage',
          title: '检索测试',
          subtitle: '',
          breadcrumb: ['工作台', '检索测试']
        }
      },
      {
        path: 'kb/chat',
        redirect: (to: any) => ({
          path: '/workspace/chat',
          query: {
            ...to.query,
            preset: 'kb'
          }
        })
      },
      {
        path: 'kb/documents/:id',
        name: 'KBDocumentView',
        component: () => import('@/views/kb/KBDocumentView.vue'),
        meta: {
          requiresPermission: 'kb.read',
          title: '文档详情',
          subtitle: '',
          breadcrumb: ['工作台', '知识库治理', '文档详情']
        }
      },
      {
        path: 'kb/documents/:id/chunks',
        name: 'KBChunkReviewView',
        component: () => import('@/views/kb/KBChunkReviewView.vue'),
        meta: {
          requiresPermission: 'kb.write',
          title: '切片管理',
          subtitle: '',
          breadcrumb: ['工作台', '知识库治理', '文档详情', '切片管理']
        }
      },
      {
        path: 'platform/agents',
        name: 'AgentProfileView',
        component: () => import('@/views/platform/AgentProfileView.vue'),
        meta: {
          requiresPermission: 'chat.use',
          title: 'Agent 工作台',
          subtitle: '',
          breadcrumb: ['工作台', 'Agent 工作台']
        }
      },
      {
        path: 'platform/prompts',
        name: 'PromptTemplateView',
        component: () => import('@/views/platform/PromptTemplateView.vue'),
        meta: {
          requiresPermission: 'chat.use',
          title: 'Prompt 库',
          subtitle: '',
          breadcrumb: ['工作台', 'Prompt 库']
        }
      },
      {
        path: 'audit',
        name: 'AuditView',
        component: () => import('@/views/AuditView.vue'),
        meta: {
          requiresPermission: 'audit.read',
          title: '审计日志',
          subtitle: '',
          breadcrumb: ['工作台', '审计日志']
        }
      }
    ]
  },
  {
    path: '/chat',
    redirect: '/workspace/chat'
  },
  {
    path: '/dashboard/:pathMatch(.*)*',
    redirect: '/workspace/chat'
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to) => {
  const authStore = useAuthStore();

  if (to.meta.requiresAuth && !authStore.token) {
    return { path: '/login', query: { redirect: to.fullPath } };
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin()) {
    return { path: '/workspace/chat' };
  }

  const requiredPermission = String(to.meta.requiresPermission || '');
  if (requiredPermission && !authStore.hasPermission(requiredPermission)) {
    return { path: '/workspace/entry' };
  }
});

router.afterEach((to) => {
  const routeTitle = String(to.meta.title || 'RAG-QA 工作台');
  document.title = `${routeTitle} | RAG-QA 控制台`;
});

export default router;
