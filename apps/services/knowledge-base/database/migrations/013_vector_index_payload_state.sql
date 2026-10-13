-- Tracks vector payload migrations that require rebuilding existing points.
-- The first run after this migration is intentionally pending; stack-init
-- rebuilds existing document vectors and marks the state ready atomically.
CREATE TABLE IF NOT EXISTS kb_vector_index_state (
    state_key TEXT PRIMARY KEY,
    state_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO kb_vector_index_state (state_key, state_value)
VALUES ('payload_schema_version', 'pending')
ON CONFLICT (state_key) DO NOTHING;
