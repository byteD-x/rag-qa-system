import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/store/auth';

const routes = [
    {
        path: '/',
        redirect: '/chat'
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
        path: '/chat',
        name: 'ChatRoot',
        component: () => import('@/layouts/MainLayout.vue'),
        meta: { requiresAuth: true },
        children: [
            {
                path: '',
                name: 'ChatHome',
                component: () => import('@/views/Chat/ChatView.vue')
            }
        ]
    },
    {
        path: '/dashboard',
        name: 'DashboardRoot',
        component: () => import('@/layouts/MainLayout.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
        children: [
            {
                path: 'corpora',
                name: 'CorporaList',
                component: () => import('@/views/Dashboard/CorporaList.vue')
            },
            {
                path: 'corpus/:id',
                name: 'CorpusDetail',
                component: () => import('@/views/Dashboard/CorpusDetail.vue')
            }
        ]
    }
];

const router = createRouter({
    history: createWebHistory(),
    routes
});

router.beforeEach((to, _from, next) => {
    const authStore = useAuthStore();

    if (to.meta.requiresAuth && !authStore.token) {
        next({ path: '/login', query: { redirect: to.fullPath } });
        return;
    }

    if (to.meta.requiresAdmin && !authStore.isAdmin()) {
        next({ path: '/chat' });
        return;
    }

    next();
});

export default router;
