import request from './request';

export function login(data: any) {
    return request.post('/auth/login', data);
}

export function getMe() {
    return request.get('/auth/me');
}

export function register(data: { email: string; password: string; department?: string }) {
    return request.post('/auth/register', data);
}

export function requestPasswordReset(data: { email: string }) {
    return request.post('/auth/password-reset/request', data);
}

export function confirmPasswordReset(data: { token: string; password: string }) {
    return request.post('/auth/password-reset/confirm', data);
}
