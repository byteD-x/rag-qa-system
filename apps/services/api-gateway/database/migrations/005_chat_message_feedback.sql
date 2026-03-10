CREATE TABLE IF NOT EXISTS chat_message_feedback (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    prompt_key TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    route_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    execution_mode TEXT NOT NULL DEFAULT '',
    answer_mode TEXT NOT NULL DEFAULT '',
    cost_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chat_message_feedback_verdict_check CHECK (verdict IN ('up', 'down', 'flag')),
    CONSTRAINT chat_message_feedback_message_user_unique UNIQUE (message_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_session_created
    ON chat_message_feedback(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_user_created
    ON chat_message_feedback(user_id, created_at DESC);
