CREATE TABLE IF NOT EXISTS kb_audit_events (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id TEXT NOT NULL DEFAULT '',
    actor_email TEXT NOT NULL DEFAULT '',
    actor_role TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'success',
    trace_id TEXT NOT NULL DEFAULT '',
    request_path TEXT NOT NULL DEFAULT '',
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_audit_events_created_desc
    ON kb_audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_audit_events_actor_created_desc
    ON kb_audit_events(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_audit_events_action_created_desc
    ON kb_audit_events(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_audit_events_resource_created_desc
    ON kb_audit_events(resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_audit_events_outcome_created_desc
    ON kb_audit_events(outcome, created_at DESC);
