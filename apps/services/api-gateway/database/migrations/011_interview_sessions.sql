CREATE TABLE IF NOT EXISTS interview_sessions (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    base_id TEXT NOT NULL,
    job_position_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS interview_session_questions (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    stem TEXT NOT NULL,
    reference_answer TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    source_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    asked_at TIMESTAMPTZ,
    answered_at TIMESTAMPTZ,
    UNIQUE (session_id, sequence_no),
    UNIQUE (session_id, question_id)
);

CREATE TABLE IF NOT EXISTS interview_answers (
    id UUID PRIMARY KEY,
    session_question_id UUID NOT NULL REFERENCES interview_session_questions(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interview_evaluations (
    id UUID PRIMARY KEY,
    answer_id UUID NOT NULL REFERENCES interview_answers(id) ON DELETE CASCADE,
    scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    feedback TEXT NOT NULL DEFAULT '',
    weak_points_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_user ON interview_sessions(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_interview_session_questions_status ON interview_session_questions(session_id, status, sequence_no);
CREATE INDEX IF NOT EXISTS idx_interview_evaluations_answer ON interview_evaluations(answer_id);
