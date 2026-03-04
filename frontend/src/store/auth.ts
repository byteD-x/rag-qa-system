import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useAuthStore = defineStore('auth', () => {
    const token = ref<string | null>(localStorage.getItem('access_token') || null);
    const user = ref<any>(JSON.parse(localStorage.getItem('user') || 'null'));

    const setAuth = (newToken: string, newUser: any) => {
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
        return user.value?.role === 'admin';
    };

    return { token, user, setAuth, logout, isAdmin };
});
