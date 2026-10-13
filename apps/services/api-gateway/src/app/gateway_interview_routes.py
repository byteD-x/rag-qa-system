from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser
from shared.tracing import trace_headers

from .ai_client import create_llm_completion, load_llm_settings
from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_runtime import CHAT_PERMISSION, gateway_db, logger, runtime_settings
from .gateway_schemas import InterviewAnswerRequest, InterviewStartRequest


router = APIRouter()


def _upstream_headers(request: Request) -> dict[str, str]:
    headers = dict(trace_headers())
    authorization = str(request.headers.get("authorization") or "").strip()
    if authorization:
        headers["Authorization"] = authorization
    return headers


async def _fetch_question_pool(payload: InterviewStartRequest, request: Request) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"count": payload.question_count}
    if payload.job_position_id:
        params["job_position_id"] = payload.job_position_id
    if payload.difficulty:
        params["difficulty"] = payload.difficulty
    if payload.question_type:
        params["question_type"] = payload.question_type
    url = f"{runtime_settings.kb_service_url.rstrip('/')}/api/v1/kb/bases/{payload.base_id}/question-pool"
    try:
        async with httpx.AsyncClient(timeout=runtime_settings.request_timeout_seconds) as client:
            response = await client.get(url, params=params, headers=_upstream_headers(request))
    except httpx.HTTPError as exc:
        raise_api_error(502, "kb_question_pool_unavailable", "knowledge base question pool is unavailable")
        raise AssertionError from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise_api_error(502, "kb_question_pool_invalid", "knowledge base returned an invalid question pool")
        raise AssertionError from exc
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else "question pool request failed"
        code = body.get("code") if isinstance(body, dict) else "kb_question_pool_failed"
        raise_api_error(response.status_code, str(code or "kb_question_pool_failed"), str(detail or "question pool request failed"))
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or len(items) < payload.question_count:
        raise_api_error(409, "interview_question_pool_insufficient", "not enough source-backed questions in the selected knowledge base")
    validated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("base_id") or "") != payload.base_id:
            raise_api_error(502, "kb_question_pool_scope_mismatch", "knowledge base returned a question outside the selected knowledge base")
        question_id = str(item.get("id") or "").strip()
        stem = str(item.get("stem") or "").strip()
        sources = item.get("sources")
        if not question_id or not stem or not isinstance(sources, list) or not sources:
            raise_api_error(502, "kb_question_pool_provenance_missing", "knowledge base returned a question without complete provenance")
        for source in sources:
            if not isinstance(source, dict) or not str(source.get("document_id") or "").strip() or not str(source.get("chunk_id") or "").strip():
                raise_api_error(502, "kb_question_pool_provenance_missing", "knowledge base returned an incomplete question source")
        validated.append(item)
    if len(validated) < payload.question_count:
        raise_api_error(409, "interview_question_pool_insufficient", "not enough source-backed questions in the selected knowledge base")
    return validated


def _public_question(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or row.get("question_id") or ""),
        "sequence_no": int(row.get("sequence_no") or 0),
        "stem": str(row.get("stem") or ""),
        "question_type": str(row.get("question_type") or ""),
        "difficulty": str(row.get("difficulty") or ""),
        "tags": list(row.get("tags") or []),
        "source": list(row.get("source_json") or row.get("sources") or []),
        "status": str(row.get("status") or "pending"),
    }


def _load_session(session_id: str, user_id: str) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM interview_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
            session = cur.fetchone()
    if session is None:
        raise_api_error(404, "interview_session_not_found", "interview session not found")
    return session


def _load_current_question(session_id: str) -> dict[str, Any] | None:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM interview_session_questions WHERE session_id = %s AND status = 'asked' ORDER BY sequence_no LIMIT 1",
                (session_id,),
            )
            return cur.fetchone()


def _load_pending_question(session_id: str) -> dict[str, Any] | None:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM interview_session_questions WHERE session_id = %s AND status = 'pending' ORDER BY sequence_no LIMIT 1",
                (session_id,),
            )
            return cur.fetchone()


def _parse_evaluation(raw: str, dimensions: list[str]) -> tuple[dict[str, float], float, str, list[str]]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        return {}, 0.0, text[:4000], []
    raw_scores = payload.get("scores") if isinstance(payload, dict) else {}
    scores: dict[str, float] = {}
    for dimension in dimensions:
        try:
            scores[dimension] = round(min(max(float(raw_scores.get(dimension, 0)), 0.0), 10.0), 2)
        except (TypeError, ValueError):
            scores[dimension] = 0.0
    try:
        total = float(payload.get("total_score"))
    except (TypeError, ValueError):
        total = sum(scores.values()) / len(scores) if scores else 0.0
    feedback = str(payload.get("feedback") or "")[:4000]
    weak_points = [str(item).strip() for item in (payload.get("weak_points") or []) if str(item).strip()][:20]
    return scores, round(min(max(total, 0.0), 10.0), 2), feedback, weak_points


async def _evaluate_answer(question: dict[str, Any], answer: str, dimensions: list[str]) -> tuple[dict[str, float], float, str, list[str], str]:
    settings = load_llm_settings(purpose="scoring")
    if not settings.configured:
        return {}, 0.0, "评分模型未配置，本题暂未评分。", [], "unscored"
    prompt = (
        "你是严格的面试评分器。只能依据参考答案和用户回答评分，不得补充题库外事实。"
        "每个评分维度使用 0-10 分。只输出 JSON："
        '{"scores":{"accuracy":0},"total_score":0,"feedback":"","weak_points":[]}。\n'
        f"评分维度: {', '.join(dimensions)}\n"
        f"题目: {question.get('stem', '')}\n"
        f"参考答案: {question.get('reference_answer', '')}\n"
        f"用户回答: {answer}"
    )
    try:
        completion = await create_llm_completion(
            settings=settings,
            messages=[{"role": "system", "content": "输出合法 JSON，不要输出 Markdown。"}, {"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=min(settings.default_max_tokens, 1200),
        )
        scores, total, feedback, weak_points = _parse_evaluation(str(completion.get("answer") or completion.get("content") or ""), dimensions)
        return scores, total, feedback, weak_points, "scored"
    except Exception:
        logger.exception("interview answer scoring failed")
        return {}, 0.0, "评分服务暂时不可用，本题暂未评分。", [], "unscored"


@router.post("/api/v1/interviews/sessions")
async def start_interview(payload: InterviewStartRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="interview.session.create", resource_type="interview_session", resource_id=payload.base_id)
    questions = await _fetch_question_pool(payload, request)
    session_id = str(uuid4())
    config = payload.model_dump()
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO interview_sessions (id, user_id, base_id, job_position_id, config_json) VALUES (%s, %s, %s, %s, %s::jsonb)",
                (session_id, user.user_id, payload.base_id, payload.job_position_id, json.dumps(config, ensure_ascii=False)),
            )
            for index, question in enumerate(questions, start=1):
                sources = list(question.get("sources") or [])
                cur.execute(
                    """
                    INSERT INTO interview_session_questions (
                        id, session_id, sequence_no, question_id, stem, reference_answer,
                        explanation, source_json, status, asked_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                    """,
                    (str(uuid4()), session_id, index, str(question.get("id") or ""), str(question.get("stem") or ""), str(question.get("reference_answer") or ""), str(question.get("explanation") or ""), json.dumps(sources, ensure_ascii=False), "pending" if index > 1 else "asked"),
                )
        conn.commit()
    first = _load_current_question(session_id)
    if first is None:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM interview_session_questions WHERE session_id = %s ORDER BY sequence_no LIMIT 1", (session_id,))
                first = cur.fetchone()
    write_gateway_audit_event(action="interview.session.create", outcome="success", request=request, user=user, resource_type="interview_session", resource_id=session_id, scope="owner", details={"base_id": payload.base_id, "question_count": len(questions)})
    return {"session_id": session_id, "status": "active", "question_count": len(questions), "question": _public_question(first or {})}


@router.post("/api/v1/interviews/sessions/{session_id}/questions/{session_question_id}/answer")
async def answer_interview_question(session_id: str, session_question_id: str, payload: InterviewAnswerRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="interview.answer.create", resource_type="interview_session", resource_id=session_id)
    session = _load_session(session_id, user.user_id)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM interview_session_questions WHERE id = %s AND session_id = %s FOR UPDATE", (session_question_id, session_id))
            question = cur.fetchone()
            if question is None:
                raise_api_error(404, "interview_question_not_found", "interview session question not found")
            if str(question.get("status") or "") != "asked":
                raise_api_error(409, "interview_question_not_current", "only the current interview question can be answered")
            cur.execute(
                "INSERT INTO interview_answers (id, session_question_id, answer_text) VALUES (%s, %s, %s) RETURNING id",
                (str(uuid4()), session_question_id, payload.answer),
            )
            answer_id = str(cur.fetchone()["id"])
            cur.execute("UPDATE interview_session_questions SET status = 'answered', answered_at = NOW() WHERE id = %s", (session_question_id,))
        conn.commit()
    dimensions = list((session.get("config_json") or {}).get("scoring_dimensions") or ["accuracy", "depth", "logic", "expression"])
    if bool((session.get("config_json") or {}).get("enable_scoring", True)):
        scores, total, feedback, weak_points, evaluation_status = await _evaluate_answer(question, payload.answer, dimensions)
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO interview_evaluations (id, answer_id, scores_json, total_score, feedback, weak_points_json) VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb)",
                    (str(uuid4()), answer_id, json.dumps(scores, ensure_ascii=False), total, feedback, json.dumps(weak_points, ensure_ascii=False)),
                )
            conn.commit()
    else:
        scores, total, feedback, weak_points, evaluation_status = {}, 0.0, "本场面试未启用评分。", [], "disabled"
    next_question = _load_pending_question(session_id)
    if next_question is None:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE interview_sessions SET status = 'completed', completed_at = NOW() WHERE id = %s", (session_id,))
            conn.commit()
    else:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE interview_session_questions SET status = 'asked', asked_at = NOW() WHERE id = %s", (next_question["id"],))
            conn.commit()
    return {
        "session_id": session_id,
        "question_id": session_question_id,
        "evaluation": {"status": evaluation_status, "scores": scores, "total_score": total, "feedback": feedback, "weak_points": weak_points},
        "next_question": _public_question(next_question) if next_question else None,
        "completed": next_question is None,
    }


@router.get("/api/v1/interviews/sessions/{session_id}/report")
async def interview_report(session_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="interview.report.get", resource_type="interview_session", resource_id=session_id)
    session = _load_session(session_id, user.user_id)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.sequence_no, q.question_id, q.stem, q.source_json,
                       e.scores_json, e.total_score, e.feedback, e.weak_points_json
                FROM interview_session_questions q
                LEFT JOIN interview_answers a ON a.session_question_id = q.id
                LEFT JOIN interview_evaluations e ON e.answer_id = a.id
                WHERE q.session_id = %s ORDER BY q.sequence_no
                """,
                (session_id,),
            )
            items = [
                {
                    "sequence_no": int(row["sequence_no"]),
                    "question_id": str(row["question_id"]),
                    "stem": str(row["stem"]),
                    "source": list(row.get("source_json") or []),
                    "scores": dict(row.get("scores_json") or {}),
                    "total_score": float(row.get("total_score") or 0),
                    "feedback": str(row.get("feedback") or ""),
                    "weak_points": list(row.get("weak_points_json") or []),
                }
                for row in cur.fetchall()
            ]
    scored = [item for item in items if item["scores"]]
    dimensions: dict[str, list[float]] = {}
    for item in scored:
        for name, score in item["scores"].items():
            dimensions.setdefault(name, []).append(float(score))
    dimension_scores = {name: round(sum(values) / len(values), 2) for name, values in dimensions.items() if values}
    total_score = round(sum(item["total_score"] for item in scored) / len(scored), 2) if scored else 0.0
    return {"session_id": session_id, "status": session.get("status"), "total_score": total_score, "dimension_scores": dimension_scores, "items": items}
