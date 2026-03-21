import request, { createIdempotencyKey, streamRequest, type StreamRequestOptions } from './request';

export interface UploadPartPayload {
  part_number: number;
  etag: string;
  size_bytes: number;
}

export function listKnowledgeBases() {
  return request.get('/kb/bases');
}

export function getKnowledgeBase(baseId: string) {
  return request.get(`/kb/bases/${baseId}`);
}

export function createKnowledgeBase(data: { name: string; description?: string; category?: string }) {
  return request.post('/kb/bases', data);
}

export function updateKnowledgeBase(baseId: string, data: { name?: string; description?: string; category?: string }) {
  return request.patch(`/kb/bases/${baseId}`, data);
}

export function deleteKnowledgeBase(baseId: string) {
  return request.delete(`/kb/bases/${baseId}`);
}

export function listKBDocuments(baseId: string) {
  return request.get(`/kb/bases/${baseId}/documents`);
}

export function getKBDocument(documentId: string) {
  return request.get(`/kb/documents/${documentId}`);
}

export function getKBDocumentVersions(documentId: string) {
  return request.get(`/kb/documents/${documentId}/versions`);
}

export function getKBDocumentVersionContent(documentId: string, versionId: string, includeDisabled: boolean = true) {
  return request.get(`/kb/documents/${documentId}/versions/${versionId}/content`, {
    params: { include_disabled: includeDisabled }
  });
}

export function getKBDocumentVersionDiff(documentId: string, versionId: string, compareToDocumentId?: string) {
  return request.get(`/kb/documents/${documentId}/versions/${versionId}/diff`, {
    params: { compare_to_document_id: compareToDocumentId || '' }
  });
}

export function updateKBDocument(documentId: string, data: {
  file_name?: string;
  category?: string;
  version_family_key?: string;
  version_label?: string;
  version_number?: number;
  version_status?: string;
  is_current_version?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  supersedes_document_id?: string | null;
  owner_user_id?: string | null;
  review_status?: string;
  reviewer_note?: string;
}) {
  return request.patch(`/kb/documents/${documentId}`, data);
}

export interface BatchUpdateKBDocumentsPayload {
  document_ids: string[];
  task_id?: string;
  retry_of_task_id?: string;
  patch: {
    file_name?: string;
    category?: string;
    version_family_key?: string;
    version_label?: string;
    version_number?: number;
    version_status?: string;
    is_current_version?: boolean;
    effective_from?: string | null;
    effective_to?: string | null;
    supersedes_document_id?: string | null;
    owner_user_id?: string | null;
    review_status?: string;
    reviewer_note?: string;
  };
}

export interface BatchUpdateKBDocumentsResultItem {
  document_id: string;
  ok: boolean;
  document?: any;
  status_code?: number;
  code?: string;
  detail?: string;
}

export interface BatchUpdateKBDocumentsResponse {
  task_id: string;
  retry_of_task_id?: string | null;
  status: string;
  items: BatchUpdateKBDocumentsResultItem[];
  summary: {
    total: number;
    succeeded: number;
    failed: number;
  };
}

export function batchUpdateKBDocuments(data: BatchUpdateKBDocumentsPayload) {
  return request.post<BatchUpdateKBDocumentsResponse>('/kb/documents/batch-update', data);
}

export interface KBGovernanceBatchEventItem {
  id: string;
  service: string;
  actor_user_id: string;
  actor_email: string;
  actor_role: string;
  action: string;
  resource_type: string;
  resource_id: string;
  scope: string;
  outcome: string;
  trace_id: string;
  request_path: string;
  created_at: string | null;
  details: {
    task_id?: string;
    retry_of_task_id?: string | null;
    document_ids?: string[];
    total?: number;
    succeeded?: number;
    failed?: number;
    patch?: Record<string, unknown>;
    success_document_ids?: string[];
    failed_items?: Array<{
      document_id: string;
      status_code: number;
      code: string;
      detail: string;
    }>;
  };
}

export interface KBGovernanceBatchEventsResponse {
  view: 'personal' | 'admin';
  limit: number;
  generated_at: string;
  items: KBGovernanceBatchEventItem[];
}

export function getKBGovernanceBatchEvents(params: { view: 'personal' | 'admin'; limit?: number }) {
  return request.get<KBGovernanceBatchEventsResponse>('/kb/analytics/governance/batch-events', { params });
}

export interface KBGovernanceBatchEventDetailResponse {
  view: 'personal' | 'admin';
  task_id: string;
  generated_at: string;
  status: string;
  item: KBGovernanceBatchEventItem;
  retry_summary: {
    parent_task_id?: string | null;
    retry_count: number;
    failed_retry_count: number;
    latest_retry_task_id?: string | null;
    latest_retry_outcome?: string | null;
    latest_retry_at?: string | null;
    latest_retry_failed: number;
    latest_retry_succeeded: number;
  };
  timeline: {
    items: KBGovernanceBatchEventItem[];
    total: number;
    limit: number;
    offset: number;
    filter: 'all' | 'retries' | 'upstream' | string;
    has_more: boolean;
  };
}

export function getKBGovernanceBatchEventDetail(taskId: string, params: {
  view: 'personal' | 'admin';
  timeline_limit?: number;
  timeline_offset?: number;
  timeline_filter?: 'all' | 'retries' | 'upstream';
}) {
  return request.get<KBGovernanceBatchEventDetailResponse>(`/kb/analytics/governance/batch-events/${taskId}`, { params });
}

export function deleteKBDocument(documentId: string) {
  return request.delete(`/kb/documents/${documentId}`);
}

export function getKBDocumentEvents(documentId: string) {
  return request.get(`/kb/documents/${documentId}/events`);
}

export function getKBDocumentVisualAssets(documentId: string) {
  return request.get(`/kb/documents/${documentId}/visual-assets`);
}

export interface KBVisualAssetRegion {
  region_id: string;
  asset_id: string;
  document_id: string;
  page_number?: number | null;
  region_label: string;
  layout_hints: string[];
  bbox: number[];
  confidence?: number | null;
  summary: string;
  ocr_text: string;
  thumbnail_url?: string;
}

export function getKBVisualAssetRegions(assetId: string) {
  return request.get<{ items: KBVisualAssetRegion[] }>(`/kb/visual-assets/${assetId}/regions`);
}

export interface KBGovernanceDocumentItem {
  document_id: string;
  base_id: string;
  base_name: string;
  file_name: string;
  status: string;
  enhancement_status: string;
  version_family_key: string;
  version_label: string;
  version_number: number | null;
  version_status: string;
  is_current_version: boolean;
  effective_from: string | null;
  effective_to: string | null;
  effective_now: boolean;
  visual_asset_count: number;
  low_confidence_region_count: number;
  low_confidence_asset_id: string;
  low_confidence_region_id: string;
  low_confidence_region_label: string;
  low_confidence_region_confidence: number | null;
  low_confidence_region_bbox: number[];
  created_at: string | null;
  updated_at: string | null;
  owner_user_id: string;
  review_status: string;
  reviewer_note: string;
  reviewed_at: string | null;
  reviewed_by_user_id: string;
  reviewed_by_email: string;
  reason: string;
}

export interface KBGovernanceVersionConflictItem {
  base_id: string;
  base_name: string;
  version_family_key: string;
  current_version_count: number;
  active_version_count: number;
  total_versions: number;
  latest_version_number: number | null;
  current_document_ids: string[];
  current_labels: string[];
}

export interface KBGovernanceResponse {
  view: 'personal' | 'admin';
  limit: number;
  generated_at: string;
  summary: {
    pending_review: number;
    approved_ready: number;
    rejected_documents: number;
    expired_documents: number;
    visual_attention: number;
    visual_low_confidence: number;
    missing_version_family: number;
    version_conflicts: number;
  };
  queues: {
    pending_review: KBGovernanceDocumentItem[];
    approved_ready: KBGovernanceDocumentItem[];
    rejected_documents: KBGovernanceDocumentItem[];
    expired_documents: KBGovernanceDocumentItem[];
    visual_attention: KBGovernanceDocumentItem[];
    visual_low_confidence: KBGovernanceDocumentItem[];
    missing_version_family: KBGovernanceDocumentItem[];
    version_conflicts: KBGovernanceVersionConflictItem[];
  };
  data_quality: {
    unsupported_fields: string[];
    degraded_sections: any[];
  };
}

export function getKBGovernance(params: { view: 'personal' | 'admin'; limit?: number }) {
  return request.get<KBGovernanceResponse>('/kb/analytics/governance', { params });
}

export function createKBUpload(data: {
  base_id: string;
  file_name: string;
  file_type: string;
  size_bytes: number;
  category?: string;
  version_family_key?: string;
  version_label?: string;
  version_number?: number;
  version_status?: string;
  is_current_version?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  supersedes_document_id?: string | null;
}, options: { idempotencyKey?: string } = {}) {
  return request.post('/kb/uploads', data, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('kb-upload-create')
    }
  });
}

export function getKBUpload(uploadId: string) {
  return request.get(`/kb/uploads/${uploadId}`);
}

export function presignKBUploadParts(uploadId: string, partNumbers: number[]) {
  return request.post(`/kb/uploads/${uploadId}/parts/presign`, {
    part_numbers: partNumbers
  });
}

export function completeKBUpload(
  uploadId: string,
  parts: UploadPartPayload[],
  contentHash = '',
  options: { idempotencyKey?: string } = {}
) {
  return request.post(`/kb/uploads/${uploadId}/complete`, {
    parts,
    content_hash: contentHash
  }, {
    headers: {
      'Idempotency-Key': options.idempotencyKey || createIdempotencyKey('kb-upload-complete')
    }
  });
}

export function getKBIngestJob(jobId: string) {
  return request.get(`/kb/ingest-jobs/${jobId}`);
}

export function retryKBIngestJob(jobId: string) {
  return request.post(`/kb/ingest-jobs/${jobId}/retry`);
}

export function queryKB(data: {
  base_id: string;
  question: string;
  document_ids?: string[];
  debug?: boolean;
}) {
  return request.post('/kb/query', data);
}

export function streamKBQuery(data: {
  base_id: string;
  question: string;
  document_ids?: string[];
  debug?: boolean;
}, options?: StreamRequestOptions) {
  return streamRequest('/api/v1/kb/query/stream', data, options);
}

export function syncLocalDirectory(data: {
  base_id: string;
  source_path: string;
  category?: string;
  recursive?: boolean;
  delete_missing?: boolean;
  dry_run?: boolean;
  max_files?: number;
}) {
  return request.post('/kb/connectors/local-directory/sync', data);
}

export function syncNotion(data: {
  base_id: string;
  page_ids: string[];
  category?: string;
  delete_missing?: boolean;
  dry_run?: boolean;
  max_pages?: number;
}) {
  return request.post('/kb/connectors/notion/sync', data);
}

// ---- Chunk Management ----
export function getKBChunks(documentId: string, includeDisabled: boolean = false) {
  return request.get(`/kb/documents/${documentId}/chunks`, { params: { include_disabled: includeDisabled } });
}

export function updateKBChunk(chunkId: string, data: { text_content?: string, disabled?: boolean, disabled_reason?: string, manual_note?: string }) {
  return request.patch(`/kb/chunks/${chunkId}`, data);
}

export function splitKBChunk(chunkId: string, parts: string[]) {
  return request.post(`/kb/chunks/${chunkId}/split`, { parts });
}

export function mergeKBChunks(chunkIds: string[], separator: string = '\n\n') {
  return request.post(`/kb/chunks/merge`, { chunk_ids: chunkIds, separator });
}

// ---- Retrieval Debugger ----
export function retrieveDebugKB(data: { query: string; base_id?: string; document_ids?: string[]; top_k?: number; [key: string]: any }) {
  return request.post('/kb/retrieve/debug', data);
}

// ---- Connectors ----
export function listConnectors(baseId?: string) {
  return request.get('/kb/connectors', { params: { base_id: baseId } });
}

export function createConnector(data: { base_id: string; name: string; connector_type: string; config: any; schedule?: any }) {
  return request.post('/kb/connectors', data);
}

export function getConnector(connectorId: string) {
  return request.get(`/kb/connectors/${connectorId}`);
}

export function updateConnector(connectorId: string, data: any) {
  return request.patch(`/kb/connectors/${connectorId}`, data);
}

export function deleteConnector(connectorId: string) {
  return request.delete(`/kb/connectors/${connectorId}`);
}

export function getConnectorRuns(connectorId: string) {
  return request.get(`/kb/connectors/${connectorId}/runs`);
}

export function syncConnector(connectorId: string, dryRun: boolean = false) {
  return request.post(`/kb/connectors/${connectorId}/sync`, { dry_run: dryRun });
}

export function runDueConnectors(limit: number = 10, dryRun: boolean = false) {
  return request.post('/kb/connectors/run-due', { limit, dry_run: dryRun });
}
