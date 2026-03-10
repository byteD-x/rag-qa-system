ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_uri TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_deleted_at TIMESTAMPTZ NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ NULL;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_kb_documents_base_source_type ON kb_documents(base_id, source_type);
CREATE INDEX IF NOT EXISTS idx_kb_documents_source_deleted_at ON kb_documents(source_deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_documents_base_source_uri_unique
    ON kb_documents(base_id, source_type, source_uri)
    WHERE source_uri <> '';
