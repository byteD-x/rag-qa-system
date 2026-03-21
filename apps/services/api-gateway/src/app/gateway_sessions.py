from __future__ import annotations

from typing import Any
from uuid import uuid4

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .db import to_json
from .gateway_runtime import gateway_db


def _message_meta_payload(row: dict[str, Any]) -> dict[str, Any]:
    return dict((dict(row.get("usage_json") or {}).get("_meta") or {}))


def serialize_feedback(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row.get("id") or ""),
        "session_id": str(row.get("session_id") or ""),
        "message_id": str(row.get("message_id") or ""),
        "verdict": str(row.get("verdict") or ""),
        "reason_code": str(row.get("reason_code") or ""),
        "notes": str(row.get("notes") or ""),
        "trace_id": str(row.get("trace_id") or ""),
        "prompt_key": str(row.get("prompt_key") or ""),
        "prompt_version": str(row.get("prompt_version") or ""),
        "route_key": str(row.get("route_key") or ""),
        "model": str(row.get("model") or ""),
        "provider": str(row.get("provider") or ""),
        "execution_mode": str(row.get("execution_mode") or ""),
        "answer_mode": str(row.get("answer_mode") or ""),
        "cost": dict(row.get("cost_json") or {}),
        "llm_trace": dict(row.get("llm_trace_json") or {}),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def load_session_for_user(session_id: str, user: CurrentUser, *, default_scope_fn: Any) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user.user_id))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "chat_session_not_found", "chat session not found")
    if not row.get("scope_json"):
        row["scope_json"] = default_scope_fn()
    return row


def serialize_chat_message(row: dict[str, Any], *, feedback: dict[str, Any] | None = None) -> dict[str, Any]:
    role = str(row.get("role") or "")
    content = str(row.get("question") or "") if role == "user" else str(row.get("answer") or "")
    usage_payload = dict(row.get("usage_json") or {})
    meta_payload = _message_meta_payload(row)
    return {
        "id": str(row.get("id") or ""),
        "session_id": str(row.get("session_id") or ""),
        "role": role,
        "content": content,
        "question": str(row.get("question") or ""),
        "answer": str(row.get("answer") or ""),
        "answer_mode": str(row.get("answer_mode") or ""),
        "execution_mode": str((row.get("scope_snapshot_json") or {}).get("execution_mode") or "grounded"),
        "evidence_status": str(row.get("evidence_status") or ""),
        "grounding_score": float(row.get("grounding_score") or 0.0),
        "refusal_reason": str(row.get("refusal_reason") or ""),
        "citations": list(row.get("citations_json") or []),
        "evidence_path": list(row.get("evidence_path_json") or []),
        "scope_snapshot": dict(row.get("scope_snapshot_json") or {}),
        "provider": str(row.get("provider") or ""),
        "model": str(row.get("model") or ""),
        "usage": usage_payload,
        "trace_id": str(meta_payload.get("trace_id") or ""),
        "retrieval": dict(meta_payload.get("retrieval") or {}),
        "latency": dict(meta_payload.get("latency") or {}),
        "cost": dict(meta_payload.get("cost") or {}),
        "llm_trace": dict(meta_payload.get("llm_trace") or {}),
        "answer_basis": dict(meta_payload.get("answer_basis") or {}),
        "feedback": feedback,
        "created_at": row.get("created_at"),
    }


def _feedback_map_for_message_ids(message_ids: list[str], user: CurrentUser) -> dict[str, dict[str, Any]]:
    if not message_ids:
        return {}
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM chat_message_feedback
                WHERE user_id = %s
                  AND message_id = ANY(%s)
                """,
                (user.user_id, message_ids),
            )
            rows = cur.fetchall()
    return {str(row.get("message_id") or ""): serialize_feedback(row) for row in rows}


def list_session_messages(session_id: str, user: CurrentUser, *, load_session_fn: Any) -> list[dict[str, Any]]:
    load_session_fn(session_id, user)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_messages WHERE session_id = %s AND user_id = %s ORDER BY created_at ASC", (session_id, user.user_id))
            rows = cur.fetchall()
    feedback_map = _feedback_map_for_message_ids([str(row.get("id") or "") for row in rows], user)
    return [serialize_chat_message(row, feedback=feedback_map.get(str(row.get("id") or ""))) for row in rows]


def recent_history_messages(session_id: str, user: CurrentUser, *, load_session_fn: Any, limit: int = 8) -> list[dict[str, Any]]:
    load_session_fn(session_id, user)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM (
                    SELECT *
                    FROM chat_messages
                    WHERE session_id = %s AND user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) AS recent_messages
                ORDER BY created_at ASC
                """,
                (session_id, user.user_id, limit),
            )
            rows = cur.fetchall()
    return [serialize_chat_message(row) for row in rows]


def load_assistant_message_for_user(*, session_id: str, message_id: str, user: CurrentUser) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM chat_messages
                WHERE id = %s
                  AND session_id = %s
                  AND user_id = %s
                """,
                (message_id, session_id, user.user_id),
            )
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "chat_message_not_found", "chat message not found")
    if str(row.get("role") or "") != "assistant":
        raise_api_error(409, "chat_feedback_requires_assistant_message", "feedback only supports assistant messages")
    return row


def upsert_chat_message_feedback(
    *,
    session_id: str,
    message_id: str,
    user: CurrentUser,
    verdict: str,
    reason_code: str,
    notes: str,
) -> dict[str, Any]:
    message_row = load_assistant_message_for_user(session_id=session_id, message_id=message_id, user=user)
    meta_payload = _message_meta_payload(message_row)
    llm_trace = dict(meta_payload.get("llm_trace") or {})
    feedback_id = str(uuid4())
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_message_feedback (
                    id, session_id, message_id, user_id, verdict, reason_code, notes,
                    trace_id, prompt_key, prompt_version, route_key, model, provider,
                    execution_mode, answer_mode, cost_json, llm_trace_json
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb
                )
                ON CONFLICT (message_id, user_id)
                DO UPDATE SET
                    verdict = EXCLUDED.verdict,
                    reason_code = EXCLUDED.reason_code,
                    notes = EXCLUDED.notes,
                    trace_id = EXCLUDED.trace_id,
                    prompt_key = EXCLUDED.prompt_key,
                    prompt_version = EXCLUDED.prompt_version,
                    route_key = EXCLUDED.route_key,
                    model = EXCLUDED.model,
                    provider = EXCLUDED.provider,
                    execution_mode = EXCLUDED.execution_mode,
                    answer_mode = EXCLUDED.answer_mode,
                    cost_json = EXCLUDED.cost_json,
                    llm_trace_json = EXCLUDED.llm_trace_json,
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    feedback_id,
                    session_id,
                    message_id,
                    user.user_id,
                    verdict,
                    reason_code,
                    notes,
                    str(meta_payload.get("trace_id") or ""),
                    str(llm_trace.get("prompt_key") or ""),
                    str(llm_trace.get("prompt_version") or ""),
                    str(llm_trace.get("route_key") or ""),
                    str(message_row.get("model") or ""),
                    str(message_row.get("provider") or ""),
                    str((message_row.get("scope_snapshot_json") or {}).get("execution_mode") or "grounded"),
                    str(message_row.get("answer_mode") or ""),
                    to_json(dict(meta_payload.get("cost") or {})),
                    to_json(llm_trace),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return serialize_feedback(row)


def session_cost_summary(session_id: str, user: CurrentUser, *, load_session_fn: Any) -> dict[str, Any]:
    load_session_fn(session_id, user)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE role = 'assistant') AS assistant_turns,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN role = 'assistant'
                                THEN COALESCE(NULLIF(usage_json #>> '{_meta,cost,estimated_cost}', '')::double precision, 0)
                                ELSE 0
                            END
                        ),
                        0
                    ) AS estimated_cost_total
                FROM chat_messages
                WHERE session_id = %s AND user_id = %s
                """,
                (session_id, user.user_id),
            )
            row = cur.fetchone() or {}
    return {
        "assistant_turns": int(row.get("assistant_turns") or 0),
        "estimated_cost_total": round(float(row.get("estimated_cost_total") or 0.0), 6),
    }


def persist_chat_turn(
    *,
    session_id: str,
    user: CurrentUser,
    question: str,
    session_scope: dict[str, Any],
    response_payload: dict[str, Any],
    compact_text_fn: Any,
    usage_with_meta_fn: Any,
) -> dict[str, Any]:
    user_message_id = str(uuid4())
    assistant_message_id = str(uuid4())
    title = compact_text_fn(question, 48)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET scope_json = %s::jsonb,
                    title = CASE WHEN title = '' THEN %s ELSE title END,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (to_json(session_scope), title, session_id, user.user_id),
            )
            cur.execute(
                "INSERT INTO chat_messages (id, session_id, user_id, role, question, scope_snapshot_json) VALUES (%s, %s, %s, 'user', %s, %s::jsonb)",
                (user_message_id, session_id, user.user_id, question.strip(), to_json(session_scope)),
            )
            cur.execute(
                """
                INSERT INTO chat_messages (
                    id, session_id, user_id, role, answer, answer_mode, evidence_status,
                    grounding_score, refusal_reason, citations_json, evidence_path_json,
                    scope_snapshot_json, provider, model, usage_json
                )
                VALUES (
                    %s, %s, %s, 'assistant', %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb,
                    %s::jsonb, %s, %s, %s::jsonb
                )
                """,
                (
                    assistant_message_id,
                    session_id,
                    user.user_id,
                    response_payload["answer"],
                    response_payload["answer_mode"],
                    response_payload["evidence_status"],
                    response_payload["grounding_score"],
                    response_payload["refusal_reason"],
                    to_json(response_payload["citations"]),
                    to_json(response_payload["evidence_path"]),
                    to_json(session_scope),
                    response_payload["provider"],
                    response_payload["model"],
                    to_json(
                        usage_with_meta_fn(
                            response_payload["usage"],
                            trace_id=str(response_payload.get("trace_id") or ""),
                            retrieval=dict(response_payload.get("retrieval") or {}),
                            latency=dict(response_payload.get("latency") or {}),
                            cost=dict(response_payload.get("cost") or {}),
                            llm_trace=dict(response_payload.get("llm_trace") or {}),
                            answer_basis=dict(response_payload.get("answer_basis") or {}),
                        )
                    ),
                ),
            )
        conn.commit()
    return serialize_chat_message(
        {
            "id": assistant_message_id,
            "session_id": session_id,
            "role": "assistant",
            "question": "",
            "answer": response_payload["answer"],
            "answer_mode": response_payload["answer_mode"],
            "evidence_status": response_payload["evidence_status"],
            "grounding_score": response_payload["grounding_score"],
            "refusal_reason": response_payload["refusal_reason"],
            "citations_json": response_payload["citations"],
            "evidence_path_json": response_payload["evidence_path"],
            "scope_snapshot_json": session_scope,
            "provider": response_payload["provider"],
            "model": response_payload["model"],
            "usage_json": usage_with_meta_fn(
                response_payload["usage"],
                trace_id=str(response_payload.get("trace_id") or ""),
                retrieval=dict(response_payload.get("retrieval") or {}),
                latency=dict(response_payload.get("latency") or {}),
                cost=dict(response_payload.get("cost") or {}),
                llm_trace=dict(response_payload.get("llm_trace") or {}),
                answer_basis=dict(response_payload.get("answer_basis") or {}),
            ),
            "created_at": None,
        },
        feedback=None,
    )
