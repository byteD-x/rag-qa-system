CREATE TABLE IF NOT EXISTS chat_prompt_templates (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'personal',
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_agent_profiles (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    persona_prompt TEXT NOT NULL DEFAULT '',
    enabled_tools_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_corpus_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt_template_id UUID NULL REFERENCES chat_prompt_templates(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_prompt_templates_user_updated
    ON chat_prompt_templates(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_prompt_templates_visibility_updated
    ON chat_prompt_templates(visibility, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_agent_profiles_user_updated
    ON chat_agent_profiles(user_id, updated_at DESC);
