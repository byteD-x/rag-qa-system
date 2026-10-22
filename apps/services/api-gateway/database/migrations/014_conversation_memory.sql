ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS conversation_summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS conversation_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS summary_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS summary_updated_at TIMESTAMPTZ;

ALTER TABLE agent_memory_entries
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS scope_type TEXT NOT NULL DEFAULT 'user',
    ADD COLUMN IF NOT EXISTS scope_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS evidence_quote TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_message_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS entity_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS supersedes_id UUID NULL REFERENCES agent_memory_entries(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS decay_rate DOUBLE PRECISION NOT NULL DEFAULT 0.1;

CREATE INDEX IF NOT EXISTS idx_agent_memory_scope_active
    ON agent_memory_entries(user_id, scope_type, scope_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_validity
    ON agent_memory_entries(user_id, valid_from, valid_to, expires_at);
CREATE INDEX IF NOT EXISTS idx_agent_memory_subject_predicate
    ON agent_memory_entries(user_id, subject, predicate, is_active);
