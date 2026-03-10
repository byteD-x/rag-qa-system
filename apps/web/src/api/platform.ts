import request from './request';

// ---- Prompt Templates ----
export function listPromptTemplates(params?: any) {
  return request.get('/platform/prompt-templates', { params });
}

export function createPromptTemplate(data: { name: string; content: string; visibility: string; tags?: string[]; favorite?: boolean }) {
  return request.post('/platform/prompt-templates', data);
}

export function getPromptTemplate(templateId: string) {
  return request.get(`/platform/prompt-templates/${templateId}`);
}

export function updatePromptTemplate(templateId: string, data: any) {
  return request.patch(`/platform/prompt-templates/${templateId}`, data);
}

export function deletePromptTemplate(templateId: string) {
  return request.delete(`/platform/prompt-templates/${templateId}`);
}

// ---- Agent Profiles ----
export function listAgentProfiles(params?: any) {
  return request.get('/platform/agent-profiles', { params });
}

export function createAgentProfile(data: { name: string; description?: string; persona_prompt?: string; enabled_tools?: string[]; default_corpus_ids?: string[]; prompt_template_id?: string }) {
  return request.post('/platform/agent-profiles', data);
}

export function getAgentProfile(profileId: string) {
  return request.get(`/platform/agent-profiles/${profileId}`);
}

export function updateAgentProfile(profileId: string, data: any) {
  return request.patch(`/platform/agent-profiles/${profileId}`, data);
}

export function deleteAgentProfile(profileId: string) {
  return request.delete(`/platform/agent-profiles/${profileId}`);
}
