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
    meta: { requiresAuth: true },
    children: [
      {
        path: 'entry',
        name: 'EntryView',
        component: () => import('@/views/EntryView.vue')
      },
      {
        path: 'chat',
        name: 'UnifiedChatView',
        component: () => import('@/views/chat/UnifiedChatView.vue')
      },
      {
        path: 'ai/chat',
        name: 'AIChatView',
        component: () => import('@/views/ai/AIChatView.vue')
      },
      {
        path: 'novel/upload',
        name: 'NovelUploadView',
        component: () => import('@/views/novel/NovelUploadView.vue')
      },
      {
        path: 'novel/chat',
        redirect: (to: any) => ({
          path: '/workspace/chat',
          query: {
            ...to.query,
            preset: 'novel'
          }
        })
      },
      {
        path: 'novel/documents/:id',
        name: 'NovelDocumentView',
        component: () => import('@/views/novel/NovelDocumentView.vue')
      },
      {
        path: 'kb/upload',
        name: 'KBUploadView',
        component: () => import('@/views/kb/KBUploadView.vue')
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
        component: () => import('@/views/kb/KBDocumentView.vue')
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
});

export default router;
