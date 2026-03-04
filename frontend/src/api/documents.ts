import request from './request';
import axios from 'axios';

export interface CorpusDocument {
    id: string;
    corpus_id: string;
    file_name: string;
    file_type: 'txt' | 'pdf' | 'docx';
    size_bytes: number;
    status: 'uploaded' | 'indexing' | 'ready' | 'failed';
    created_at: string;
    created_by?: string;
}

export interface UploadUrlRequest {
    corpus_id: string;
    file_name: string;
    file_type: string;
    size_bytes: number;
}

export interface UploadUrlResponse {
    upload_url: string;
    storage_key: string;
}

export interface IngestJob {
    id: string;
    status: 'queued' | 'running' | 'done' | 'failed';
    progress: number;
}

export interface DocumentPreviewResponse {
    document: CorpusDocument;
    preview_mode: 'text' | 'url';
    editable: boolean;
    content_type: string;
    text?: string;
    view_url?: string;
    max_inline_bytes?: number;
    expires_in_seconds?: number;
}

export interface UpdateDocumentContentResponse {
    document_id: string;
    job_id: string;
    status: 'queued';
    message: string;
}

export async function listCorpusDocuments(corpusId: string): Promise<{ items: CorpusDocument[]; count: number }> {
    const res = await request.get(`/corpora/${corpusId}/documents`);
    return res as unknown as { items: CorpusDocument[]; count: number };
}

export async function getDocumentDetail(documentId: string): Promise<CorpusDocument> {
    const res = await request.get(`/documents/${documentId}`);
    return res as unknown as CorpusDocument;
}

export async function getDocumentPreview(documentId: string): Promise<DocumentPreviewResponse> {
    const res = await request.get(`/documents/${documentId}/preview`);
    return res as unknown as DocumentPreviewResponse;
}

export async function updateDocumentContent(documentId: string, content: string): Promise<UpdateDocumentContentResponse> {
    const res = await request.put(`/documents/${documentId}/content`, { content });
    return res as unknown as UpdateDocumentContentResponse;
}

export function getUploadUrl(data: UploadUrlRequest) {
    return request.post<UploadUrlResponse>('/documents/upload-url', data);
}

export function uploadToS3(url: string, file: File, onProgress?: (percent: number) => void) {
    return axios.put(url, file, {
        headers: {
            'Content-Type': file.type || 'application/octet-stream'
        },
        onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
                const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                if (onProgress) onProgress(percent);
            }
        }
    });
}

export function notifyUploadComplete(data: {
    corpus_id: string;
    storage_key: string;
    file_name: string;
    file_type: string;
    size_bytes: number;
}) {
    return request.post<{ job_id: string, document_id: string }>('/documents/upload', data);
}

export function getIngestJob(job_id: string) {
    return request.get<IngestJob>(`/ingest-jobs/${job_id}`);
}
