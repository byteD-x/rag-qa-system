ALTER TABLE model_stage_bindings
    ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_model_stage_bindings_stage_model
    ON model_stage_bindings(stage_key, model_name);
