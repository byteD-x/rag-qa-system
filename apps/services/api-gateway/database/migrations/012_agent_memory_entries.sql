CREATE TABLE IF NOT EXISTS agent_memory_entries (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'fact',
    subject TEXT NOT NULL DEFAULT '',
    predicate TEXT NOT NULL DEFAULT '',
    object TEXT NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source_session_id UUID NULL REFERENCES chat_sessions(id) ON DELETE SET NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_entries_user_active
    ON agent_memory_entries(user_id, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memory_entries_type
    ON agent_memory_entries(user_id, memory_type, updated_at DESC);
