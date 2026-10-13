from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .db import to_json
from .kb_api_support import audit_event, require_kb_permission
from .kb_resource_store import ensure_base_exists
from .kb_runtime import KB_READ_PERMISSION, KB_WRITE_PERMISSION, db
from .kb_taxonomy import validate_type_schema
from .kb_schemas import (
    CreateInterviewQuestionRequest,
    CreateJobPositionRequest,
    CreateKBTypeRequest,
    InterviewQuestionSourceRequest,
    UpdateInterviewQuestionRequest,
    UpdateJobPositionRequest,
    UpdateKBTypeRequest,
)


router = APIRouter()


def _serialize_question(row: dict[str, Any], sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = dict(row)
    payload["id"] = str(payload.get("id") or "")
    payload["base_id"] = str(payload.get("base_id") or "")
    payload["tags"] = list(payload.pop("tags_json", None) or [])
    payload["job_position_ids"] = [str(item) for item in list(payload.pop("job_position_ids_json", None) or [])]
    if sources is not None:
        payload["sources"] = sources
    return payload


def _load_question(question_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM interview_questions WHERE id = %s", (question_id,))
            row = cur.fetchone()
            if row is None:
                raise_api_error(404, "interview_question_not_found", "interview question not found")
            cur.execute(
                """
                SELECT s.question_id::text, s.document_id::text, s.chunk_id::text,
                       s.quote, s.is_primary, d.file_name, c.text_content
                FROM interview_question_sources s
                JOIN kb_documents d ON d.id = s.document_id
                JOIN kb_chunks c ON c.id = s.chunk_id
                WHERE s.question_id = %s
                ORDER BY s.is_primary DESC, s.document_id, s.chunk_id
                """,
                (question_id,),
            )
            sources = [dict(item) for item in cur.fetchall()]
    return row, sources


def _validate_sources(cur, *, base_id: str, sources: list[InterviewQuestionSourceRequest]) -> None:
    if not sources:
        raise_api_error(400, "interview_question_source_required", "at least one source chunk is required")
    chunk_ids = [str(item.chunk_id) for item in sources]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise_api_error(400, "interview_question_source_duplicate", "source chunks must be unique")
    cur.execute(
        """
        SELECT c.id::text AS chunk_id, c.document_id::text AS document_id,
               d.base_id::text AS base_id, d.query_ready, d.source_deleted_at
        FROM kb_chunks c
        JOIN kb_documents d ON d.id = c.document_id
        WHERE c.id = ANY(%s::uuid[])
        """,
        (chunk_ids,),
    )
    found = {str(row["chunk_id"]): row for row in cur.fetchall()}
    for source in sources:
        row = found.get(str(source.chunk_id))
        if row is None or str(row.get("base_id") or "") != base_id:
            raise_api_error(400, "interview_question_source_invalid", "source chunk must belong to the question knowledge base")
        if str(row.get("document_id") or "") != str(source.document_id):
            raise_api_error(400, "interview_question_source_mismatch", "source document does not contain the source chunk")
        if not bool(row.get("query_ready")) or row.get("source_deleted_at") is not None:
            raise_api_error(409, "interview_question_source_not_ready", "source document is not queryable")


def _validate_question_job_positions(cur, *, base_id: str, job_position_ids: list[str]) -> None:
    if not job_position_ids:
        return
    try:
        normalized_ids = [str(UUID(str(item))) for item in job_position_ids]
    except (ValueError, TypeError) as exc:
        raise_api_error(400, "job_position_id_invalid", "job position id must be a valid UUID")
        raise AssertionError from exc
    cur.execute(
        """
        SELECT jp.id::text
        FROM job_positions jp
        WHERE jp.id = ANY(%s::uuid[])
          AND jp.status = 'active'
        """,
        (normalized_ids,),
    )
    found = {str(row["id"]) for row in cur.fetchall()}
    missing = sorted(set(normalized_ids) - found)
    if missing:
        raise_api_error(400, "job_position_not_found", f"unknown or disabled job position: {', '.join(missing)}")
    cur.execute(
        """
        SELECT job_position_id::text
        FROM kb_base_job_positions
        WHERE base_id = %s AND job_position_id = ANY(%s::uuid[])
        """,
        (base_id, normalized_ids),
    )
    mapped = {str(row["job_position_id"]) for row in cur.fetchall()}
    if set(normalized_ids) - mapped:
        raise_api_error(400, "job_position_not_mapped", "question job position must be mapped to its knowledge base")


def _ensure_interview_type(cur, *, base_id: str) -> None:
    cur.execute("SELECT 1 FROM kb_type_registry WHERE type_key = 'interview' AND enabled = TRUE")
    if cur.fetchone() is None:
        raise_api_error(409, "interview_type_disabled", "interview knowledge base type is disabled")
    cur.execute("SELECT 1 FROM kb_base_types WHERE base_id = %s AND type_key = 'interview'", (base_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO kb_base_types (base_id, type_key, is_primary) VALUES (%s, 'interview', FALSE) ON CONFLICT DO NOTHING",
            (base_id,),
        )


@router.get("/api/v1/kb/types")
def list_kb_types(request: Request, user: CurrentUser, include_disabled: bool = False) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.type.list", resource_type="knowledge_base_type")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kb_type_registry WHERE (%s OR enabled = TRUE) ORDER BY type_key",
                (bool(include_disabled),),
            )
            rows = cur.fetchall()
    return {"items": rows}


@router.post("/api/v1/kb/types")
def create_kb_type(payload: CreateKBTypeRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.type.create", resource_type="knowledge_base_type")
    validate_type_schema(payload.config_schema)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kb_type_registry (type_key, display_name, description, schema_json, enabled, created_by)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (type_key) DO NOTHING
                RETURNING *
                """,
                (payload.type_key, payload.display_name.strip(), payload.description.strip(), to_json(payload.config_schema), payload.enabled, user.user_id),
            )
            row = cur.fetchone()
            if row is None:
                raise_api_error(409, "kb_type_exists", "knowledge base type already exists")
        conn.commit()
    audit_event(action="kb.type.create", outcome="success", request=request, user=user, resource_type="knowledge_base_type", resource_id=payload.type_key, scope="managed")
    return row


@router.patch("/api/v1/kb/types/{type_key}")
def update_kb_type(type_key: str, payload: UpdateKBTypeRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.type.update", resource_type="knowledge_base_type", resource_id=type_key)
    if payload.config_schema is not None:
        validate_type_schema(payload.config_schema)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_type_registry WHERE type_key = %s", (type_key,))
            current = cur.fetchone()
            if current is None:
                raise_api_error(404, "kb_type_not_found", "knowledge base type not found")
            cur.execute(
                """
                UPDATE kb_type_registry
                SET display_name = %s, description = %s, schema_json = %s::jsonb,
                    enabled = %s, updated_at = NOW()
                WHERE type_key = %s
                RETURNING *
                """,
                (
                    payload.display_name.strip() if payload.display_name is not None else current["display_name"],
                    payload.description.strip() if payload.description is not None else current["description"],
                    to_json(payload.config_schema if payload.config_schema is not None else dict(current.get("schema_json") or {})),
                    payload.enabled if payload.enabled is not None else bool(current["enabled"]),
                    type_key,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row


@router.get("/api/v1/kb/job-positions")
def list_job_positions(request: Request, user: CurrentUser, include_inactive: bool = False) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.job_position.list", resource_type="job_position")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM job_positions WHERE (%s OR status = 'active') ORDER BY name",
                (bool(include_inactive),),
            )
            rows = cur.fetchall()
    return {"items": rows}


@router.post("/api/v1/kb/job-positions")
def create_job_position(payload: CreateJobPositionRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.job_position.create", resource_type="job_position")
    position_id = str(uuid4())
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO job_positions (id, code, name, description, locale, metadata_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (code) DO NOTHING
                RETURNING *
                """,
                (position_id, payload.code, payload.name.strip(), payload.description.strip(), payload.locale, to_json(payload.metadata), user.user_id),
            )
            row = cur.fetchone()
            if row is None:
                raise_api_error(409, "job_position_exists", "job position code already exists")
        conn.commit()
    return row


@router.patch("/api/v1/kb/job-positions/{position_id}")
def update_job_position(position_id: str, payload: UpdateJobPositionRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.job_position.update", resource_type="job_position", resource_id=position_id)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM job_positions WHERE id = %s", (position_id,))
            current = cur.fetchone()
            if current is None:
                raise_api_error(404, "job_position_not_found", "job position not found")
            cur.execute(
                """
                UPDATE job_positions
                SET name = %s, description = %s, status = %s, locale = %s,
                    metadata_json = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    payload.name.strip() if payload.name is not None else current["name"],
                    payload.description.strip() if payload.description is not None else current["description"],
                    payload.status.strip().lower() if payload.status is not None else current["status"],
                    payload.locale.strip() if payload.locale is not None else current["locale"],
                    to_json(payload.metadata if payload.metadata is not None else dict(current.get("metadata_json") or {})),
                    position_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row


@router.get("/api/v1/kb/bases/{base_id}/questions")
def list_questions(
    base_id: str,
    request: Request,
    user: CurrentUser,
    status: str = Query(default=""),
    difficulty: str = Query(default=""),
    question_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.question.list", resource_type="knowledge_base", resource_id=base_id)
    ensure_base_exists(base_id, user=user, request=request, action="kb.question.list", allow_shared_read=True)
    conditions = ["q.base_id = %s"]
    params: list[Any] = [base_id]
    if status.strip():
        conditions.append("q.status = %s")
        params.append(status.strip().lower())
    if difficulty.strip():
        conditions.append("q.difficulty = %s")
        params.append(difficulty.strip().lower())
    if question_type.strip():
        conditions.append("q.question_type = %s")
        params.append(question_type.strip().lower())
    params.append(limit)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT q.* FROM interview_questions q WHERE {' AND '.join(conditions)} ORDER BY q.updated_at DESC LIMIT %s", tuple(params))
            rows = cur.fetchall()
            result = []
            for row in rows:
                cur.execute(
                    "SELECT question_id::text, document_id::text, chunk_id::text, quote, is_primary FROM interview_question_sources WHERE question_id = %s ORDER BY is_primary DESC",
                    (row["id"],),
                )
                result.append(_serialize_question(row, [dict(item) for item in cur.fetchall()]))
    return {"items": result}


@router.post("/api/v1/kb/questions")
def create_question(payload: CreateInterviewQuestionRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.question.create", resource_type="knowledge_base", resource_id=payload.base_id)
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.question.create")
    question_id = str(uuid4())
    with db.connect() as conn:
        with conn.cursor() as cur:
            _ensure_interview_type(cur, base_id=payload.base_id)
            _validate_sources(cur, base_id=payload.base_id, sources=payload.sources)
            _validate_question_job_positions(cur, base_id=payload.base_id, job_position_ids=payload.job_position_ids)
            cur.execute(
                """
                INSERT INTO interview_questions (
                    id, base_id, stem, reference_answer, explanation, question_type,
                    difficulty, tags_json, job_position_ids_json, locale, status, source_type, source_note, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, 'draft', %s, %s, %s)
                RETURNING *
                """,
                (question_id, payload.base_id, payload.stem.strip(), payload.reference_answer, payload.explanation, payload.question_type, payload.difficulty, to_json(payload.tags), to_json(payload.job_position_ids), payload.locale, payload.source_type, payload.source_note, user.user_id),
            )
            row = cur.fetchone()
            for source in payload.sources:
                cur.execute(
                    "INSERT INTO interview_question_sources (question_id, document_id, chunk_id, quote, is_primary) VALUES (%s, %s, %s, %s, %s)",
                    (question_id, source.document_id, source.chunk_id, source.quote, source.is_primary),
                )
            cur.execute(
                "INSERT INTO interview_question_revisions (id, question_id, version_number, snapshot_json, created_by) VALUES (%s, %s, 1, %s::jsonb, %s)",
                (str(uuid4()), question_id, to_json(_serialize_question(row)), user.user_id),
            )
        conn.commit()
    audit_event(action="kb.question.create", outcome="success", request=request, user=user, resource_type="interview_question", resource_id=question_id, scope="owner")
    question, sources = _load_question(question_id)
    return _serialize_question(question, sources)


@router.get("/api/v1/kb/questions/{question_id}")
def get_question(question_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.question.get", resource_type="interview_question", resource_id=question_id)
    row, sources = _load_question(question_id)
    ensure_base_exists(str(row["base_id"]), user=user, request=request, action="kb.question.get", allow_shared_read=True)
    return _serialize_question(row, sources)


@router.patch("/api/v1/kb/questions/{question_id}")
def update_question(question_id: str, payload: UpdateInterviewQuestionRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.question.update", resource_type="interview_question", resource_id=question_id)
    current, sources = _load_question(question_id)
    base_id = str(current["base_id"])
    ensure_base_exists(base_id, user=user, request=request, action="kb.question.update")
    next_version = int(current.get("version_number") or 1) + 1
    values = {
        "stem": payload.stem.strip() if payload.stem is not None else current["stem"],
        "reference_answer": payload.reference_answer if payload.reference_answer is not None else current["reference_answer"],
        "explanation": payload.explanation if payload.explanation is not None else current["explanation"],
        "question_type": payload.question_type.strip().lower() if payload.question_type is not None else current["question_type"],
        "difficulty": payload.difficulty.strip().lower() if payload.difficulty is not None else current["difficulty"],
        "tags_json": payload.tags if payload.tags is not None else list(current.get("tags_json") or []),
        "job_position_ids_json": payload.job_position_ids if payload.job_position_ids is not None else list(current.get("job_position_ids_json") or []),
        "status": payload.status.strip().lower() if payload.status is not None else current["status"],
        "source_note": payload.source_note if payload.source_note is not None else current["source_note"],
    }
    if values["status"] not in {"draft", "published", "archived"}:
        raise_api_error(400, "interview_question_status_invalid", "unsupported interview question status")
    with db.connect() as conn:
        with conn.cursor() as cur:
            _validate_question_job_positions(cur, base_id=base_id, job_position_ids=values["job_position_ids_json"])
            cur.execute(
                """
                UPDATE interview_questions
                SET stem = %s, reference_answer = %s, explanation = %s,
                    question_type = %s, difficulty = %s, tags_json = %s::jsonb,
                    job_position_ids_json = %s::jsonb,
                    status = %s, source_note = %s, version_number = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (values["stem"], values["reference_answer"], values["explanation"], values["question_type"], values["difficulty"], to_json(values["tags_json"]), to_json(values["job_position_ids_json"]), values["status"], values["source_note"], next_version, question_id),
            )
            row = cur.fetchone()
            cur.execute(
                "INSERT INTO interview_question_revisions (id, question_id, version_number, snapshot_json, created_by) VALUES (%s, %s, %s, %s::jsonb, %s)",
                (str(uuid4()), question_id, next_version, to_json(_serialize_question(row, sources)), user.user_id),
            )
        conn.commit()
    return _serialize_question(row, sources)


@router.post("/api/v1/kb/questions/{question_id}/publish")
def publish_question(question_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.question.publish", resource_type="interview_question", resource_id=question_id)
    row, sources = _load_question(question_id)
    ensure_base_exists(str(row["base_id"]), user=user, request=request, action="kb.question.publish")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM interview_question_sources WHERE question_id = %s LIMIT 1", (question_id,))
            if cur.fetchone() is None:
                raise_api_error(409, "interview_question_source_required", "published question must have a source chunk")
            cur.execute("UPDATE interview_questions SET status = 'published', updated_at = NOW() WHERE id = %s RETURNING *", (question_id,))
            updated = cur.fetchone()
        conn.commit()
    audit_event(action="kb.question.publish", outcome="success", request=request, user=user, resource_type="interview_question", resource_id=question_id, scope="managed")
    return _serialize_question(updated, sources)


@router.delete("/api/v1/kb/questions/{question_id}")
def delete_question(question_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.question.delete", resource_type="interview_question", resource_id=question_id)
    row, _sources = _load_question(question_id)
    ensure_base_exists(str(row["base_id"]), user=user, request=request, action="kb.question.delete")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM interview_questions WHERE id = %s", (question_id,))
        conn.commit()
    return {"deleted": True, "question_id": question_id}


@router.get("/api/v1/kb/bases/{base_id}/question-pool")
def question_pool(
    base_id: str,
    request: Request,
    user: CurrentUser,
    count: int = Query(default=1, ge=1, le=100),
    job_position_id: str = Query(default=""),
    difficulty: str = Query(default=""),
    question_type: str = Query(default=""),
    tags: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    """Return only published, source-backed questions; insufficient pools are never completed by the LLM."""
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.question.pool", resource_type="knowledge_base", resource_id=base_id)
    ensure_base_exists(base_id, user=user, request=request, action="kb.question.pool", allow_shared_read=True)
    conditions = [
        "q.base_id = %s",
        "q.status = 'published'",
        "EXISTS (SELECT 1 FROM kb_bases b WHERE b.id = q.base_id AND b.status = 'active')",
        "EXISTS (SELECT 1 FROM kb_base_types bt JOIN kb_type_registry tr ON tr.type_key = bt.type_key WHERE bt.base_id = q.base_id AND bt.type_key = 'interview' AND tr.enabled = TRUE)",
        "EXISTS (SELECT 1 FROM interview_question_sources s JOIN kb_documents d ON d.id = s.document_id WHERE s.question_id = q.id AND d.query_ready = TRUE AND d.source_deleted_at IS NULL)",
    ]
    params: list[Any] = [base_id]
    requested_job_position_id = job_position_id.strip()
    if requested_job_position_id:
        with db.connect() as conn:
            with conn.cursor() as cur:
                _validate_question_job_positions(
                    cur,
                    base_id=base_id,
                    job_position_ids=[requested_job_position_id],
                )
        conditions.append(
            "EXISTS (SELECT 1 FROM kb_base_job_positions bpj JOIN job_positions jp ON jp.id = bpj.job_position_id "
            "WHERE bpj.base_id = q.base_id AND bpj.job_position_id = %s::uuid AND jp.status = 'active')"
        )
        params.append(requested_job_position_id)
        conditions.append("(q.job_position_ids_json = '[]'::jsonb OR q.job_position_ids_json ? %s)")
        params.append(requested_job_position_id)
    if difficulty.strip():
        conditions.append("q.difficulty = %s")
        params.append(difficulty.strip().lower())
    if question_type.strip():
        conditions.append("q.question_type = %s")
        params.append(question_type.strip().lower())
    normalized_tags = sorted({item.strip().lower() for item in (tags or []) if item.strip()})
    if normalized_tags:
        conditions.append("q.tags_json ?| %s::text[]")
        params.append(normalized_tags)
    params.append(count)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT q.* FROM interview_questions q WHERE {' AND '.join(conditions)} ORDER BY md5(q.id::text) LIMIT %s", tuple(params))
            rows = cur.fetchall()
            if len(rows) < count:
                raise_api_error(409, "interview_question_pool_insufficient", "not enough source-backed questions in the selected knowledge base")
            result = []
            for row in rows:
                cur.execute(
                    """
                    SELECT s.question_id::text, s.document_id::text, s.chunk_id::text,
                           s.quote, s.is_primary
                    FROM interview_question_sources s
                    JOIN kb_documents d ON d.id = s.document_id
                    WHERE s.question_id = %s
                      AND d.query_ready = TRUE
                      AND d.source_deleted_at IS NULL
                    ORDER BY s.is_primary DESC
                    """,
                    (row["id"],),
                )
                result.append(_serialize_question(row, [dict(item) for item in cur.fetchall()]))
    return {"base_id": base_id, "count": len(result), "items": result}
