import request from './request';

export function getAnalyticsDashboard(params: { view: 'personal' | 'admin'; days?: number }) {
  return request.get('/analytics/dashboard', { params });
}
