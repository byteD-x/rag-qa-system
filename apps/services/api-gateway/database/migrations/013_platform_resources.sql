CREATE TABLE IF NOT EXISTS auth_users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'kb_editor',
    department TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_password_reset_tokens_user ON auth_password_reset_tokens(user_id);

CREATE TABLE IF NOT EXISTS platform_api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    permissions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    quota_tokens BIGINT NOT NULL DEFAULT 100000,
    tokens_used BIGINT NOT NULL DEFAULT 0,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    request_count_this_minute INTEGER NOT NULL DEFAULT 0,
    rate_limit_reset_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    rotated_from TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_api_keys_user ON platform_api_keys(user_id);

CREATE TABLE IF NOT EXISTS platform_webhooks (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    url TEXT NOT NULL,
    events_json JSONB NOT NULL DEFAULT '["*"]'::jsonb,
    secret TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 3,
    timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 30,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_webhooks_owner ON platform_webhooks(owner_user_id);

CREATE TABLE IF NOT EXISTS platform_webhook_deliveries (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL REFERENCES platform_webhooks(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    url TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    http_status INTEGER NOT NULL DEFAULT 0,
    response_body TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 1,
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_webhook_deliveries_webhook ON platform_webhook_deliveries(webhook_id, created_at DESC);

CREATE TABLE IF NOT EXISTS platform_pii_configs (
    user_id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL DEFAULT 'mask',
    mask_char TEXT NOT NULL DEFAULT '*',
    enabled_types_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform_experiments (
    experiment_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    control_prompt TEXT NOT NULL,
    variant_prompt TEXT NOT NULL,
    metric_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    sample_size_target INTEGER NOT NULL DEFAULT 100,
    split_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_experiments_owner ON platform_experiments(owner_user_id);

CREATE TABLE IF NOT EXISTS platform_experiment_trials (
    trial_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES platform_experiments(experiment_id) ON DELETE CASCADE,
    variant TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    user_feedback TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_experiment_trials_experiment ON platform_experiment_trials(experiment_id, created_at);
