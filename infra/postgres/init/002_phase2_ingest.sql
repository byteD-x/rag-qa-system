CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE ingest_jobs
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS doc_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    page_or_loc TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    qdrant_point_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_document_id ON doc_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs (status, updated_at);