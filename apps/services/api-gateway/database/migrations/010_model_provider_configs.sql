CREATE TABLE IF NOT EXISTS model_provider_configs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    provider_type TEXT NOT NULL,
    api_key_ciphertext TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    max_tokens INTEGER NOT NULL DEFAULT 2048,
    timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 120,
    proxy_url TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default_chat BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_embedding BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_interview BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_scoring BOOLEAN NOT NULL DEFAULT FALSE,
    extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_provider_configs_enabled ON model_provider_configs(enabled, provider_type);
CREATE INDEX IF NOT EXISTS idx_model_provider_configs_defaults ON model_provider_configs(is_default_chat, is_default_interview, is_default_scoring);
