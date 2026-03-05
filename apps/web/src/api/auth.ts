import request from './request';

export function login(data: any) {
    return request.post('/auth/login', data);
}
