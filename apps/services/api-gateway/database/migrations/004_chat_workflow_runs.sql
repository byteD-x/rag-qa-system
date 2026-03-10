CREATE TABLE IF NOT EXISTS chat_workflow_runs (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    execution_mode TEXT NOT NULL DEFAULT 'grounded',
    workflow_kind TEXT NOT NULL DEFAULT 'chat_grounded',
    status TEXT NOT NULL DEFAULT 'running',
    question TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '',
    scope_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    workflow_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    workflow_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_calls_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_workflow_runs_session_created
    ON chat_workflow_runs(session_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_chat_workflow_runs_user_created
    ON chat_workflow_runs(user_id, created_at DESC);
