CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS novel_upload_sessions (
    id UUID PRIMARY KEY,
    library_id UUID NOT NULL REFERENCES novel_libraries(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    volume_label TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    s3_upload_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_upload',
    content_hash TEXT NOT NULL DEFAULT '',
    document_id UUID NULL REFERENCES novel_documents(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL,
    spoiler_ack BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS novel_upload_parts (
    id BIGSERIAL PRIMARY KEY,
    upload_session_id UUID NOT NULL REFERENCES novel_upload_sessions(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL,
    etag TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (upload_session_id, part_number)
);

CREATE TABLE IF NOT EXISTS novel_ingest_jobs (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES novel_documents(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS novel_embedding_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS novel_summary_nodes (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES novel_documents(id) ON DELETE CASCADE,
    node_level TEXT NOT NULL,
    node_key TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_chapter_from INTEGER NOT NULL DEFAULT 0,
    source_chapter_to INTEGER NOT NULL DEFAULT 0,
    lexical_terms TEXT NOT NULL DEFAULT '',
    fts_document TSVECTOR,
    embedding VECTOR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, node_level, node_key)
);

CREATE TABLE IF NOT EXISTS novel_relation_edges (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES novel_documents(id) ON DELETE CASCADE,
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    relation_summary TEXT NOT NULL,
    support_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS upload_session_id UUID NULL;
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS query_ready BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS enhancement_status TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS query_ready_until_chapter INTEGER NOT NULL DEFAULT 0;
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS query_ready_at TIMESTAMPTZ NULL;
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS hybrid_ready_at TIMESTAMPTZ NULL;
ALTER TABLE novel_documents ADD COLUMN IF NOT EXISTS ready_at TIMESTAMPTZ NULL;

ALTER TABLE novel_chapters ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_chapters ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_chapters ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE novel_chapters ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE novel_chapters ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE novel_scenes ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_scenes ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE novel_scenes ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE novel_scenes ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE novel_passages ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_passages ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE novel_passages ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE novel_passages ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE novel_event_digests ADD COLUMN IF NOT EXISTS lexical_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE novel_event_digests ADD COLUMN IF NOT EXISTS fts_document TSVECTOR;
ALTER TABLE novel_event_digests ADD COLUMN IF NOT EXISTS embedding VECTOR(512);
ALTER TABLE novel_event_digests ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_novel_upload_sessions_library_created ON novel_upload_sessions(library_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_novel_ingest_jobs_status_created ON novel_ingest_jobs(status, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_novel_chapters_fts ON novel_chapters USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_novel_scenes_fts ON novel_scenes USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_novel_passages_fts ON novel_passages USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_novel_event_digests_fts ON novel_event_digests USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_novel_summary_nodes_fts ON novel_summary_nodes USING GIN (fts_document);
CREATE INDEX IF NOT EXISTS idx_novel_chapters_embedding ON novel_chapters USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_novel_scenes_embedding ON novel_scenes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_novel_passages_embedding ON novel_passages USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_novel_event_digests_embedding ON novel_event_digests USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_novel_summary_nodes_embedding ON novel_summary_nodes USING hnsw (embedding vector_cosine_ops);
