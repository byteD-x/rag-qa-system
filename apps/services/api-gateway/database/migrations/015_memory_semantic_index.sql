ALTER TABLE agent_memory_entries
    ADD COLUMN IF NOT EXISTS embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS embedding_model TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding_presence
    ON agent_memory_entries(user_id, updated_at DESC)
    WHERE is_active = TRUE AND jsonb_array_length(embedding_json) > 0;
