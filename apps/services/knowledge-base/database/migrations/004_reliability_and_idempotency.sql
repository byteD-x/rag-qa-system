CREATE TABLE IF NOT EXISTS kb_idempotency_keys (
    idempotency_key TEXT NOT NULL,
    request_scope TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    resource_id TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (idempotency_key, request_scope, actor_user_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_idempotency_expires_at
    ON kb_idempotency_keys(expires_at ASC);

ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 5;
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ NULL;
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS last_error_code TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS lease_token TEXT NOT NULL DEFAULT '';
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ NULL;
ALTER TABLE kb_ingest_jobs ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ NULL;

UPDATE kb_ingest_jobs
SET next_retry_at = COALESCE(next_retry_at, created_at)
WHERE next_retry_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_kb_ingest_jobs_retry_schedule
    ON kb_ingest_jobs(status, next_retry_at ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_kb_ingest_jobs_lease_expires_at
    ON kb_ingest_jobs(status, lease_expires_at ASC);
