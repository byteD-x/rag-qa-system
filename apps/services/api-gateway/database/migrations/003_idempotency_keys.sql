CREATE TABLE IF NOT EXISTS gateway_idempotency_keys (
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

CREATE INDEX IF NOT EXISTS idx_gateway_idempotency_expires_at
    ON gateway_idempotency_keys(expires_at ASC);
