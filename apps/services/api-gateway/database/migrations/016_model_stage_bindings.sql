CREATE TABLE IF NOT EXISTS model_stage_bindings (
    stage_key TEXT PRIMARY KEY,
    config_id UUID REFERENCES model_provider_configs(id) ON DELETE SET NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_stage_bindings_config ON model_stage_bindings(config_id);
