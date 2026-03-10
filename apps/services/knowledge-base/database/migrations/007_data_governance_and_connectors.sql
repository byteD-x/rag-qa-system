ALTER TABLE kb_chunks
    ADD COLUMN IF NOT EXISTS disabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE kb_chunks
    ADD COLUMN IF NOT EXISTS disabled_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_chunks
    ADD COLUMN IF NOT EXISTS manual_note TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_chunks
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_kb_chunks_document_disabled
    ON kb_chunks(document_id, disabled, section_index, chunk_index);

CREATE TABLE IF NOT EXISTS kb_connectors (
    id UUID PRIMARY KEY,
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    schedule_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    schedule_interval_minutes INTEGER NULL,
    last_run_at TIMESTAMPTZ NULL,
    next_run_at TIMESTAMPTZ NULL,
    last_result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_connector_runs (
    id UUID PRIMARY KEY,
    connector_id UUID NOT NULL REFERENCES kb_connectors(id) ON DELETE CASCADE,
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    connector_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    created_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kb_connectors_base_updated
    ON kb_connectors(base_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_connectors_due
    ON kb_connectors(status, schedule_enabled, next_run_at ASC);
CREATE INDEX IF NOT EXISTS idx_kb_connector_runs_connector_started
    ON kb_connector_runs(connector_id, started_at DESC);
