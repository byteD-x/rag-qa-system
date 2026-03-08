CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_upload_sessions (
    id UUID PRIMARY KEY,
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    storage_key TEXT NOT NULL UNIQUE,
    s3_upload_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_upload',
    content_hash TEXT NOT NULL DEFAULT '',
    document_id UUID NULL REFERENCES kb_documents(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_upload_parts (
    id BIGSERIAL PRIMARY KEY,
    upload_session_id UUID NOT NULL REFERENCES kb_upload_sessions(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL,
    etag TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (upload_session_id, part_number)
);

CREATE TABLE IF NOT EXISTS kb_ingest_jobs (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    phase TEXT NOT NULL DEFAULT 'uploaded',
    query_ready BOOLEAN NOT NULL DEFAULT FALSE,
    enhancement_status TEXT NOT NULL DEFAULT '',
    checkpoint_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_embedding_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS upload_session_id UUID NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS query_ready BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS enhancement_status TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS query_ready_at TIMESTAMPTZ NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS hybrid_ready_at TIMESTAMPTZ NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS ready_at TIMESTAMPTZ NULL;

ALTER TABLE kb_sections ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_sections ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE kb_sections ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE kb_sections ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_kb_upload_sessions_base_created ON kb_upload_sessions(base_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_ingest_jobs_status_created ON kb_ingest_jobs(status, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_kb_sections_fts ON kb_sections USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_fts ON kb_chunks USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_kb_sections_embedding ON kb_sections USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding ON kb_chunks USING hnsw (embedding vector_cosine_ops);
