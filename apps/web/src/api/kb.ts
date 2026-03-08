import request, { streamRequest, type StreamRequestOptions } from './request';

export interface UploadPartPayload {
  part_number: number;
  etag: string;
  size_bytes: number;
}

export function listKnowledgeBases() {
  return request.get('/kb/bases');
}

export function createKnowledgeBase(data: { name: string; description?: string; category?: string }) {
  return request.post('/kb/bases', data);
}

export function listKBDocuments(baseId: string) {
  return request.get(`/kb/bases/${baseId}/documents`);
}

export function getKBDocument(documentId: string) {
  return request.get(`/kb/documents/${documentId}`);
}

export function getKBDocumentEvents(documentId: string) {
  return request.get(`/kb/documents/${documentId}/events`);
}

export function createKBUpload(data: {
  base_id: string;
  file_name: string;
  file_type: string;
  size_bytes: number;
  category?: string;
}) {
  return request.post('/kb/uploads', data);
}

export function getKBUpload(uploadId: string) {
  return request.get(`/kb/uploads/${uploadId}`);
}

export function presignKBUploadParts(uploadId: string, partNumbers: number[]) {
  return request.post(`/kb/uploads/${uploadId}/parts/presign`, {
    part_numbers: partNumbers
  });
}

export function completeKBUpload(uploadId: string, parts: UploadPartPayload[], contentHash = '') {
  return request.post(`/kb/uploads/${uploadId}/complete`, {
    parts,
    content_hash: contentHash
  });
}

export function getKBIngestJob(jobId: string) {
  return request.get(`/kb/ingest-jobs/${jobId}`);
}

export async function uploadKBDocuments(payload: {
  baseId: string;
  category?: string;
  files: File[];
}) {
  const form = new FormData();
  form.append('base_id', payload.baseId);
  form.append('category', payload.category || '');
  for (const file of payload.files) {
    form.append('files', file);
  }
  return request.post('/kb/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
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
