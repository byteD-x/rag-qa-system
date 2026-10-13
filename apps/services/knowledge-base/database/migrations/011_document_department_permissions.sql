ALTER TABLE kb_documents
    ADD COLUMN IF NOT EXISTS allowed_departments TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE kb_upload_sessions
    ADD COLUMN IF NOT EXISTS allowed_departments TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_kb_documents_allowed_departments
    ON kb_documents USING GIN (allowed_departments);
