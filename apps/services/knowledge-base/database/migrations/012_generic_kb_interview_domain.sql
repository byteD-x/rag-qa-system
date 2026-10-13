-- Generic knowledge-base taxonomy and interview question provenance.
-- Existing bases remain queryable and are classified as "general".

CREATE TABLE IF NOT EXISTS kb_type_registry (
    type_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO kb_type_registry (type_key, display_name, description, schema_json, created_by)
VALUES
    ('general', '通用知识库', '通用文档问答知识库', '{}'::jsonb, 'system'),
    (
        'interview',
        '面试题知识库',
        '包含可追溯面试题的知识库',
        '{"type":"object","properties":{"locale":{"type":"string","maxLength":32},"question_types":{"type":"array","items":{"type":"string"}},"difficulties":{"type":"array","items":{"type":"string"}}},"additionalProperties":true}'::jsonb,
        'system'
    )
ON CONFLICT (type_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS kb_base_types (
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    type_key TEXT NOT NULL REFERENCES kb_type_registry(type_key) ON DELETE RESTRICT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (base_id, type_key)
);

INSERT INTO kb_base_types (base_id, type_key, is_primary)
SELECT id, 'general', TRUE
FROM kb_bases
ON CONFLICT (base_id, type_key) DO NOTHING;

ALTER TABLE kb_bases
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS job_positions (
    id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    locale TEXT NOT NULL DEFAULT 'zh-CN',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_base_job_positions (
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    job_position_id UUID NOT NULL REFERENCES job_positions(id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (base_id, job_position_id)
);

ALTER TABLE kb_documents
    ADD COLUMN IF NOT EXISTS content_kind TEXT NOT NULL DEFAULT 'document',
    ADD COLUMN IF NOT EXISTS question_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS difficulty TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE kb_upload_sessions
    ADD COLUMN IF NOT EXISTS content_kind TEXT NOT NULL DEFAULT 'document',
    ADD COLUMN IF NOT EXISTS question_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS difficulty TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS interview_questions (
    id UUID PRIMARY KEY,
    base_id UUID NOT NULL REFERENCES kb_bases(id) ON DELETE CASCADE,
    stem TEXT NOT NULL,
    reference_answer TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    question_type TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    job_position_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    locale TEXT NOT NULL DEFAULT 'zh-CN',
    status TEXT NOT NULL DEFAULT 'draft',
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_note TEXT NOT NULL DEFAULT '',
    version_number INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE interview_questions
    ADD COLUMN IF NOT EXISTS job_position_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS interview_question_sources (
    question_id UUID NOT NULL REFERENCES interview_questions(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE RESTRICT,
    chunk_id UUID NOT NULL REFERENCES kb_chunks(id) ON DELETE RESTRICT,
    quote TEXT NOT NULL DEFAULT '',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (question_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS interview_question_revisions (
    id UUID PRIMARY KEY,
    question_id UUID NOT NULL REFERENCES interview_questions(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    snapshot_json JSONB NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (question_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_kb_base_types_type
    ON kb_base_types(type_key, base_id);
CREATE INDEX IF NOT EXISTS idx_kb_base_job_positions_job
    ON kb_base_job_positions(job_position_id, base_id);
CREATE INDEX IF NOT EXISTS idx_job_positions_status
    ON job_positions(status, name);
CREATE INDEX IF NOT EXISTS idx_interview_questions_pool
    ON interview_questions(base_id, status, difficulty, question_type);
CREATE INDEX IF NOT EXISTS idx_interview_questions_tags
    ON interview_questions USING GIN (tags_json);
CREATE INDEX IF NOT EXISTS idx_interview_questions_job_positions
    ON interview_questions USING GIN (job_position_ids_json);
CREATE INDEX IF NOT EXISTS idx_interview_question_sources_chunk
    ON interview_question_sources(chunk_id);
