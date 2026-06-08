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

// ---- LLM Providers ----
export interface LlmRouteSummary {
  provider?: string;
  base_url?: string;
  model?: string;
  fallback_route_key?: string;
  temperature?: number;
  max_tokens?: number;
  timeout_seconds?: number;
  api_key_configured: boolean;
}

export interface LlmConfigSummary {
  enabled: boolean;
  configured: boolean;
  provider: string;
  base_url: string;
  api_key_configured: boolean;
  current_model: string;
  common_knowledge_model: string;
  model_routing: Record<string, LlmRouteSummary>;
}

export interface LlmModelItem {
  id: string;
  object: string;
  owned_by: string;
  created: number | null;
}

export interface LlmModelDiscoveryResult {
  provider: string;
  base_url: string;
  models_url: string;
  api_key_configured: boolean;
  current_model: string;
  models: LlmModelItem[];
  count: number;
}

export interface LlmModelDiscoveryPayload {
  provider?: string;
  base_url?: string;
  api_key?: string;
  max_models?: number;
}

export function getLlmConfig() {
  return request.get<LlmConfigSummary>('/platform/llm/config');
}

export function discoverLlmModels(data: LlmModelDiscoveryPayload) {
  return request.post<LlmModelDiscoveryResult>('/platform/llm/models/discover', data);
}

// ---- Tool Registry ----
export interface ToolRegistrySummary {
  registered_tools: number;
  categories: number;
  mcp_servers: number;
  cache_entries: number;
  tools: Record<string, {
    category: string;
    total_calls: number;
    success_rate: number;
    avg_duration_ms: number;
  }>;
}

export function getToolRegistrySummary() {
  return request.get<ToolRegistrySummary>('/platform/agent/registry/summary');
}

export function listAgentTools(params?: { category?: string }) {
  return request.get('/platform/agent/tools', { params });
}

export function toggleAgentTool(toolName: string, enabled: boolean) {
  return request.post(`/platform/agent/tools/${toolName}/toggle`, { enabled });
}

// ---- Agent Runs (Execution Monitoring) ----

export interface AgentRunSummary {
  id: string;
  session_id: string;
  status: string;
  execution_mode: string;
  question: string;
  created_at: string;
  completed_at?: string;
  tool_calls_used: number;
  total_latency_ms: number;
  answer_mode: string;
}

export interface AgentTaskNode {
  id: string;
  description: string;
  question: string;
  category: string;
  depends_on: string[];
  status: string;
  tool_calls: number;
  evidence_count: number;
  duration_ms: number;
  error?: string;
}

export interface AgentRunDetail {
  id: string;
  session_id: string;
  status: string;
  execution_mode: string;
  question: string;
  contextualized_question: string;
  complexity_score: number;
  requires_decomposition: boolean;
  sub_tasks: AgentTaskNode[];
  execution_order: string[][];
  agent_events: Array<{
    type: string;
    round?: number;
    tool?: string;
    tool_call_count?: number;
    message_preview?: string;
    [key: string]: any;
  }>;
  tool_calls: Array<{
    tool: string;
    question?: string;
    result_count?: number;
    expression?: string;
    result?: any;
    error?: string;
  }>;
  reflection?: {
    passed: boolean;
    confidence: number;
    completeness_score: number;
    accuracy_score: number;
    citation_score: number;
    issues: string[];
    suggestions: string[];
    needs_retry: boolean;
  };
  evidence_count: number;
  answer_mode: string;
  total_latency_ms: number;
  retrieval_ms: number;
  generation_ms: number;
  created_at: string;
  completed_at?: string;
}

export function listAgentRuns(params?: { limit?: number; status?: string }) {
  return request.get('/platform/agent/runs', { params });
}

export function getAgentRunDetail(runId: string) {
  return request.get<AgentRunDetail>(`/platform/agent/runs/${runId}`);
}

// ---- Memory Management ----

export interface MemoryEntryItem {
  id: string;
  user_id: string;
  memory_type: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  source_session_id: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MemoryStats {
  total_entries: number;
  active_entries: number;
  by_type: Record<string, number>;
  top_subjects: Array<{ subject: string; count: number }>;
}

export function listMemoryEntries(params?: { memory_type?: string; limit?: number; offset?: number }) {
  return request.get('/platform/memory/entries', { params });
}

export function searchMemoryEntries(params: { query: string; memory_type?: string; limit?: number }) {
  return request.get('/platform/memory/search', { params });
}

export function deactivateMemory(memoryId: string) {
  return request.delete(`/platform/memory/entries/${memoryId}`);
}

export function getMemoryStats() {
  return request.get<MemoryStats>('/platform/memory/stats');
}

// ---- Cost Analytics ----
export interface CostBreakdown {
  by_model: Array<{ model: string; input_tokens: number; output_tokens: number; estimated_cost: number; calls: number }>;
  by_day: Array<{ date: string; cost: number; calls: number }>;
  by_scene: Array<{ scene: string; cost: number; percentage: number }>;
  total_cost: number;
  total_tokens: number;
  total_calls: number;
  currency: string;
  period_days: number;
}

export function getCostBreakdown(params?: { period_days?: number }) {
  return request.get<CostBreakdown>('/platform/cost/breakdown', { params });
}

export interface ModelHealthItem {
  health_score: number;
  success_rate: number;
  total_calls: number;
  p50_ms: number;
  p95_ms: number;
  avg_latency_ms: number;
  circuit_open: boolean;
  consecutive_failures: number;
  estimated_cost: number;
}

export interface ModelHealthSummary {
  models: Record<string, ModelHealthItem>;
  total_models: number;
  healthy_models: number;
  circuit_open_models: number;
}

export function getModelHealth() {
  return request.get<ModelHealthSummary>('/platform/cost/model-health');
}

// ---- Cache Management ----
export interface CacheStats {
  total_entries: number;
  total_hits: number;
  hit_rate_estimate: number;
  avg_age_seconds: number;
  memory_usage_estimate: number;
}

export function getCacheStats() {
  return request.get<CacheStats>('/platform/cache/stats');
}

export function invalidateCache(params: { corpus_id?: string; question?: string; model_name?: string }) {
  return request.post('/platform/cache/invalidate', params);
}

export function getCacheConfig() {
  return request.get('/platform/cache/config');
}

export function updateCacheConfig(data: { semantic_threshold?: number; default_ttl?: number; max_entries?: number }) {
  return request.patch('/platform/cache/config', data);
}

function dataEnvelope<T>(data: T): { data: T } {
  return { data };
}

function unwrapItems(payload: any): any[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.items)) {
    return payload.items;
  }
  if (Array.isArray(payload?.data)) {
    return payload.data;
  }
  return [];
}

async function requestData(promise: Promise<any>): Promise<{ data: any }> {
  return dataEnvelope(await promise);
}

async function requestItems(promise: Promise<any>): Promise<{ data: any[] }> {
  return dataEnvelope(unwrapItems(await promise));
}

export const platformApi = {
  listPromptTemplates: (params?: any) => requestItems(listPromptTemplates(params)),
  applyPromptTemplate: (templateId: string) => requestData(request.post(`/platform/prompt-templates/${templateId}/apply`)),

  listExperiments: () => requestItems(request.get('/platform/experiments')),
  startExperiment: (data: any) => requestData(request.post('/platform/experiments', data)),
  stopExperiment: (experimentId: string) => requestData(request.post(`/platform/experiments/${experimentId}/stop`)),

  listOrchestrationRuns: () => requestItems(request.get('/platform/orchestration/runs')),

  listApiKeys: () => requestItems(request.get('/platform/api-keys')),
  createApiKey: (data: any) => requestData(request.post('/platform/api-keys', data)),
  rotateApiKey: (keyId: string) => requestData(request.post(`/platform/api-keys/${keyId}/rotate`)),
  revokeApiKey: (keyId: string) => requestData(request.post(`/platform/api-keys/${keyId}/revoke`)),

  getPiiConfig: () => requestData(request.get('/platform/pii/config')),
  savePiiConfig: (data: any) => requestData(request.patch('/platform/pii/config', data)),
  testPiiDetection: (data: any) => requestData(request.post('/platform/pii/test', data)),

  listWebhooks: () => requestItems(request.get('/platform/webhooks')),
  webhookDeliveries: () => requestItems(request.get('/platform/webhooks/deliveries')),
  registerWebhook: (data: any) => requestData(request.post('/platform/webhooks', data)),
  testWebhook: (webhookId: string) => requestData(request.post(`/platform/webhooks/${webhookId}/test`)),
  updateWebhook: (webhookId: string, data: any) => requestData(request.patch(`/platform/webhooks/${webhookId}`, data)),
  deleteWebhook: (webhookId: string) => requestData(request.delete(`/platform/webhooks/${webhookId}`)),
};
