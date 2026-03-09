import request from './request';

export interface AuditQuery {
  service?: string;
  actor_user_id?: string;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  outcome?: string;
  created_from?: string;
  created_to?: string;
  limit?: number;
  offset?: number;
}

export function listAuditEvents(params: AuditQuery) {
  return request.get('/audit/events', { params });
}
