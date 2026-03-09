import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface AuthUser {
    id: string;
    email: string;
    role: string;
    permissions: string[];
    role_version?: number;
}

export const useAuthStore = defineStore('auth', () => {
    const token = ref<string | null>(localStorage.getItem('access_token') || null);
    const user = ref<AuthUser | null>(JSON.parse(localStorage.getItem('user') || 'null'));

    const setAuth = (newToken: string, newUser: AuthUser) => {
        token.value = newToken;
        user.value = newUser;
        localStorage.setItem('access_token', newToken);
        localStorage.setItem('user', JSON.stringify(newUser));
    };

    const logout = () => {
        token.value = null;
        user.value = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
    };

    const isAdmin = () => {
        return user.value?.role === 'platform_admin';
    };

    const hasPermission = (permission: string) => {
        return !!user.value?.permissions?.includes(permission);
    };

    const roleLabel = () => {
        const mapping: Record<string, string> = {
            platform_admin: '平台管理员',
            kb_admin: '知识库管理员',
            kb_editor: '知识库编辑者',
            kb_viewer: '知识库只读',
            audit_viewer: '审计查看者'
        };
        return mapping[user.value?.role || ''] || '成员';
    };

    return { token, user, setAuth, logout, isAdmin, hasPermission, roleLabel };
});
