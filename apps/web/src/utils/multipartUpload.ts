const DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024;
const DEFAULT_CONCURRENCY = 4;

export interface MultipartUploadedPart {
  part_number: number;
  etag: string;
  size_bytes: number;
}

interface UploadSessionShape {
  id?: string;
  upload_id?: string;
  status?: string;
  document_id?: string;
  uploaded_parts?: MultipartUploadedPart[];
}

interface PresignResponseShape {
  presigned_parts?: Array<{ part_number: number; url: string }>;
  uploaded_parts?: MultipartUploadedPart[];
  chunk_size_bytes?: number;
}

export interface MultipartUploadController<TSession extends UploadSessionShape, TResult> {
  createUpload: () => Promise<TSession>;
  getUpload: (uploadId: string) => Promise<TSession>;
  presignParts: (uploadId: string, partNumbers: number[]) => Promise<PresignResponseShape>;
  completeUpload: (uploadId: string, parts: MultipartUploadedPart[]) => Promise<TResult>;
}

export interface MultipartUploadOptions<TSession extends UploadSessionShape, TResult> {
  file: File;
  resumeKey: string;
  controller: MultipartUploadController<TSession, TResult>;
  chunkSizeBytes?: number;
  concurrency?: number;
  onProgress?: (progress: { loadedBytes: number; totalBytes: number; ratio: number }) => void;
}

function readStoredUploadId(resumeKey: string): string {
  return window.localStorage.getItem(resumeKey) || '';
}

function storeUploadId(resumeKey: string, uploadId: string): void {
  window.localStorage.setItem(resumeKey, uploadId);
}

function clearUploadId(resumeKey: string): void {
  window.localStorage.removeItem(resumeKey);
}

function normalizeUploadId(session: UploadSessionShape): string {
  return String(session.id || session.upload_id || '');
}

function normalizeUploadedParts(parts: MultipartUploadedPart[] | undefined): Map<number, MultipartUploadedPart> {
  const map = new Map<number, MultipartUploadedPart>();
  for (const item of parts || []) {
    map.set(Number(item.part_number), {
      part_number: Number(item.part_number),
      etag: String(item.etag || ''),
      size_bytes: Number(item.size_bytes || 0)
    });
  }
  return map;
}

function emitProgress(
  onProgress: MultipartUploadOptions<UploadSessionShape, unknown>['onProgress'],
  file: File,
  uploadedParts: Map<number, MultipartUploadedPart>,
  inflightBytes: Map<number, number>
): void {
  if (!onProgress) {
    return;
  }
  let loadedBytes = 0;
  uploadedParts.forEach((item) => {
    loadedBytes += Number(item.size_bytes || 0);
  });
  inflightBytes.forEach((value) => {
    loadedBytes += value;
  });
  onProgress({
    loadedBytes: Math.min(loadedBytes, file.size),
    totalBytes: file.size,
    ratio: file.size ? Math.min(loadedBytes / file.size, 1) : 0
  });
}

function uploadPartWithXhr(
  url: string,
  blob: Blob,
  onProgress?: (loaded: number) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(event.loaded);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader('ETag') || xhr.getResponseHeader('etag') || '';
        if (!etag) {
          reject(new Error('missing ETag header from object storage upload response'));
          return;
        }
        resolve(etag);
        return;
      }
      reject(new Error(`upload part failed with status ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('upload part failed'));
    xhr.send(blob);
  });
}

async function ensureUploadSession<TSession extends UploadSessionShape, TResult>(
  options: MultipartUploadOptions<TSession, TResult>
): Promise<TSession> {
  const stored = readStoredUploadId(options.resumeKey);
  if (stored) {
    try {
      const existing = await options.controller.getUpload(stored);
      if (normalizeUploadId(existing)) {
        return existing;
      }
    } catch {
      clearUploadId(options.resumeKey);
    }
  }

  const created = await options.controller.createUpload();
  const uploadId = normalizeUploadId(created);
  if (!uploadId) {
    throw new Error('upload session id missing');
  }
  storeUploadId(options.resumeKey, uploadId);
  return created;
}

export async function uploadMultipartFile<TSession extends UploadSessionShape, TResult>(
  options: MultipartUploadOptions<TSession, TResult>
): Promise<{ uploadId: string; session: TSession; result: TResult }> {
  const session = await ensureUploadSession(options);
  const uploadId = normalizeUploadId(session);
  if (!uploadId) {
    throw new Error('upload session id missing');
  }

  const uploadedParts = normalizeUploadedParts(session.uploaded_parts);
  const inflightBytes = new Map<number, number>();
  emitProgress(options.onProgress, options.file, uploadedParts, inflightBytes);

  if (session.document_id && session.status === 'completed') {
    const result = await options.controller.completeUpload(uploadId, Array.from(uploadedParts.values()));
    clearUploadId(options.resumeKey);
    return { uploadId, session, result };
  }

  const chunkSizeBytes = options.chunkSizeBytes || DEFAULT_CHUNK_SIZE;
  const totalParts = Math.max(1, Math.ceil(options.file.size / chunkSizeBytes));
  const missingParts: number[] = [];
  for (let partNumber = 1; partNumber <= totalParts; partNumber += 1) {
    if (!uploadedParts.has(partNumber)) {
      missingParts.push(partNumber);
    }
  }

  if (missingParts.length) {
    const presign = await options.controller.presignParts(uploadId, missingParts);
    for (const part of presign.uploaded_parts || []) {
      uploadedParts.set(Number(part.part_number), {
        part_number: Number(part.part_number),
        etag: String(part.etag || ''),
        size_bytes: Number(part.size_bytes || 0)
      });
    }

    const urlMap = new Map<number, string>();
    for (const item of presign.presigned_parts || []) {
      urlMap.set(Number(item.part_number), String(item.url || ''));
    }

    const queue = missingParts.filter((partNumber) => !uploadedParts.has(partNumber));
    const concurrency = options.concurrency || DEFAULT_CONCURRENCY;

    let cursor = 0;
    const workers = Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
      while (cursor < queue.length) {
        const currentIndex = cursor;
        cursor += 1;
        const partNumber = queue[currentIndex];
        if (partNumber === undefined) {
          continue;
        }
        const url = urlMap.get(partNumber);
        if (!url) {
          throw new Error(`missing presigned url for part ${partNumber}`);
        }
        const start = (partNumber - 1) * chunkSizeBytes;
        const end = Math.min(start + chunkSizeBytes, options.file.size);
        const blob = options.file.slice(start, end);
        inflightBytes.set(partNumber, 0);
        emitProgress(options.onProgress, options.file, uploadedParts, inflightBytes);
        const etag = await uploadPartWithXhr(url, blob, (loaded) => {
          inflightBytes.set(partNumber, loaded);
          emitProgress(options.onProgress, options.file, uploadedParts, inflightBytes);
        });
        inflightBytes.delete(partNumber);
        uploadedParts.set(partNumber, {
          part_number: partNumber,
          etag,
          size_bytes: blob.size
        });
        emitProgress(options.onProgress, options.file, uploadedParts, inflightBytes);
      }
    });
    await Promise.all(workers);
  }

  const completeParts = Array.from(uploadedParts.values()).sort((left, right) => left.part_number - right.part_number);
  const result = await options.controller.completeUpload(uploadId, completeParts);
  clearUploadId(options.resumeKey);
  emitProgress(options.onProgress, options.file, uploadedParts, inflightBytes);
  return { uploadId, session, result };
}
