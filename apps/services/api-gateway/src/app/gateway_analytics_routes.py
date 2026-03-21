from __future__ import annotations

from collections import Counter
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from shared.auth import CurrentUser
from shared.text_search import tokenize_text

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_runtime import CHAT_PERMISSION, gateway_db, logger, runtime_settings
from .gateway_schemas import AnalyticsDashboardResponse
from .gateway_transport import downstream_headers, request_service_json


router = APIRouter()


def _is_platform_admin(user: CurrentUser) -> bool:
    return str(user.role or "") == "platform_admin"


def _scope_clause(user: CurrentUser, view: str) -> tuple[str, tuple[Any, ...]]:
    if view == "personal":
        return "user_id = %s", (user.user_id,)
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail={"detail": "admin dashboard requires platform_admin", "code": "permission_denied"})
    return "TRUE", ()


def _hot_terms(user: CurrentUser, *, view: str, days: int) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT question
                FROM chat_messages
                WHERE role = 'user'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                ORDER BY created_at DESC
                LIMIT 1000
                """,
                params + (days,),
            )
            rows = cur.fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        for token in tokenize_text(str(row.get("question") or "")):
            if len(token.strip()) < 2:
                continue
            counter[token] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(40)]


def _zero_hit_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    DATE(created_at) AS day,
                    COUNT(*) AS total_count
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                  AND (
                      COALESCE(jsonb_array_length(citations_json), 0) = 0
                      OR COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,selected_candidates}}', ''), '0')::int = 0
                  )
                GROUP BY DATE(created_at)
                ORDER BY day ASC
                """,
                params + (days,),
            )
            trend_rows = cur.fetchall()
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,original_query}}', ''), '') AS query,
                    COUNT(*) AS total_count
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                  AND (
                      COALESCE(jsonb_array_length(citations_json), 0) = 0
                      OR COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,selected_candidates}}', ''), '0')::int = 0
                  )
                GROUP BY query
                ORDER BY total_count DESC, query ASC
                LIMIT 20
                """,
                params + (days,),
            )
            query_rows = cur.fetchall()
    return {
        "trend": [{"date": str(row.get("day") or ""), "count": int(row.get("total_count") or 0)} for row in trend_rows],
        "top_queries": [
            {"query": str(row.get("query") or ""), "count": int(row.get("total_count") or 0)}
            for row in query_rows
            if str(row.get("query") or "").strip()
        ],
    }


def _satisfaction_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    DATE(created_at) AS day,
                    COUNT(*) FILTER (WHERE verdict = 'up') AS up_count,
                    COUNT(*) FILTER (WHERE verdict = 'down') AS down_count,
                    COUNT(*) FILTER (WHERE verdict = 'flag') AS flag_count
                FROM chat_message_feedback
                WHERE {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                GROUP BY DATE(created_at)
                ORDER BY day ASC
                """,
                params + (days,),
            )
            rows = cur.fetchall()
    return {
        "trend": [
            {
                "date": str(row.get("day") or ""),
                "up_count": int(row.get("up_count") or 0),
                "down_count": int(row.get("down_count") or 0),
                "flag_count": int(row.get("flag_count") or 0),
            }
            for row in rows
        ]
    }


def _usage_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    DATE(created_at) AS day,
                    COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'prompt_tokens', ''), '0')::double precision), 0) AS prompt_tokens,
                    COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'completion_tokens', ''), '0')::double precision), 0) AS completion_tokens,
                    COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}', ''), '0')::double precision), 0) AS estimated_cost
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                GROUP BY DATE(created_at)
                ORDER BY day ASC
                """,
                params + (days,),
            )
            trend_rows = cur.fetchall()
            cur.execute(
                f"""
                SELECT
                    COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'prompt_tokens', ''), '0')::double precision), 0) AS prompt_tokens,
                    COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'completion_tokens', ''), '0')::double precision), 0) AS completion_tokens,
                    COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}', ''), '0')::double precision), 0) AS estimated_cost,
                    COUNT(*) AS assistant_turns
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            summary_row = cur.fetchone() or {}
    return {
        "currency": runtime_settings.llm_price_currency,
        "summary": {
            "assistant_turns": int(summary_row.get("assistant_turns") or 0),
            "prompt_tokens": round(float(summary_row.get("prompt_tokens") or 0.0), 3),
            "completion_tokens": round(float(summary_row.get("completion_tokens") or 0.0), 3),
            "estimated_cost": round(float(summary_row.get("estimated_cost") or 0.0), 6),
        },
        "trend": [
            {
                "date": str(row.get("day") or ""),
                "prompt_tokens": round(float(row.get("prompt_tokens") or 0.0), 3),
                "completion_tokens": round(float(row.get("completion_tokens") or 0.0), 3),
                "estimated_cost": round(float(row.get("estimated_cost") or 0.0), 6),
            }
            for row in trend_rows
        ],
    }


def _chat_funnel_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(DISTINCT session_id) AS chat_sessions_with_questions,
                    COUNT(*) AS questions_asked
                FROM chat_messages
                WHERE role = 'user'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            question_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE answer_mode = 'refusal') AS refusal_count,
                    COUNT(*) FILTER (WHERE answer_mode = 'weak_grounded' OR evidence_status = 'partial') AS weak_grounded_count,
                    COUNT(*) FILTER (WHERE answer_mode = 'grounded' OR evidence_status = 'grounded') AS grounded_count,
                    COUNT(*) FILTER (
                        WHERE answer_mode NOT IN ('refusal', 'weak_grounded', 'grounded')
                          AND evidence_status NOT IN ('grounded', 'partial')
                    ) AS other_count
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            answer_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE verdict = 'up') AS up_count,
                    COUNT(*) FILTER (WHERE verdict = 'down') AS down_count,
                    COUNT(*) FILTER (WHERE verdict = 'flag') AS flag_count
                FROM chat_message_feedback
                WHERE {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            feedback_row = cur.fetchone() or {}
    return {
        "chat_sessions_with_questions": int(question_row.get("chat_sessions_with_questions") or 0),
        "questions_asked": int(question_row.get("questions_asked") or 0),
        "answer_outcomes": {
            "grounded": int(answer_row.get("grounded_count") or 0),
            "weak_grounded": int(answer_row.get("weak_grounded_count") or 0),
            "refusal": int(answer_row.get("refusal_count") or 0),
            "other": int(answer_row.get("other_count") or 0),
        },
        "feedback": {
            "up": int(feedback_row.get("up_count") or 0),
            "down": int(feedback_row.get("down_count") or 0),
            "flag": int(feedback_row.get("flag_count") or 0),
        },
    }


def _clarification_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS clarification_runs,
                    COUNT(*) FILTER (WHERE status = 'completed') AS clarification_completed_runs,
                    COUNT(*) FILTER (WHERE status = 'interrupted') AS clarification_pending_runs,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1
                            FROM chat_graph_interrupts interrupt_row
                            WHERE interrupt_row.run_id = chat_workflow_runs.id
                              AND COALESCE(NULLIF(interrupt_row.response_json->>'free_text', ''), '') <> ''
                        )
                    ) AS clarification_with_free_text_runs,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1
                            FROM chat_graph_interrupts interrupt_row
                            WHERE interrupt_row.run_id = chat_workflow_runs.id
                              AND jsonb_typeof(COALESCE(interrupt_row.response_json->'selected_option_ids', '[]'::jsonb)) = 'array'
                              AND jsonb_array_length(COALESCE(interrupt_row.response_json->'selected_option_ids', '[]'::jsonb)) > 0
                        )
                    ) AS clarification_with_selection_runs
                FROM chat_workflow_runs
                WHERE {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                  AND COALESCE(workflow_state_json #>> '{{retrieval,aggregate,clarification_required}}', 'false') = 'true'
                """,
                params + (days,),
            )
            summary_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(workflow_state_json #>> '{{retrieval,aggregate,clarification_kind}}', ''), 'unknown') AS key,
                    COUNT(*) AS total_count
                FROM chat_workflow_runs
                WHERE {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                  AND COALESCE(workflow_state_json #>> '{{retrieval,aggregate,clarification_required}}', 'false') = 'true'
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params + (days,),
            )
            kind_rows = cur.fetchall()
    clarification_runs = int(summary_row.get("clarification_runs") or 0)
    clarification_completed_runs = int(summary_row.get("clarification_completed_runs") or 0)
    return {
        "triggered_runs": clarification_runs,
        "completed_runs": clarification_completed_runs,
        "pending_runs": int(summary_row.get("clarification_pending_runs") or 0),
        "completion_rate": round(float(clarification_completed_runs) / float(clarification_runs), 4) if clarification_runs > 0 else 0.0,
        "free_text_runs": int(summary_row.get("clarification_with_free_text_runs") or 0),
        "selection_runs": int(summary_row.get("clarification_with_selection_runs") or 0),
        "kind_distribution": [
            {"key": str(row.get("key") or ""), "count": int(row.get("total_count") or 0)}
            for row in kind_rows
        ],
    }


def _qa_quality_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS assistant_answers,
                    COUNT(*) FILTER (WHERE answer_mode = 'refusal') AS refusal_answers,
                    COUNT(*) FILTER (WHERE answer_mode = 'weak_grounded' OR evidence_status = 'partial') AS weak_grounded_answers,
                    COUNT(*) FILTER (WHERE answer_mode = 'grounded' OR evidence_status = 'grounded') AS grounded_answers,
                    COUNT(*) FILTER (
                        WHERE COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,selected_candidates}}', ''), '0')::int = 0
                    ) AS selected_candidates_zero,
                    COUNT(*) FILTER (
                        WHERE COALESCE(jsonb_array_length(citations_json), 0) = 0
                    ) AS missing_citations,
                    COUNT(*) FILTER (
                        WHERE COALESCE(jsonb_array_length(citations_json), 0) = 0
                          AND answer_mode <> 'refusal'
                    ) AS missing_citations_non_refusal,
                    COUNT(*) FILTER (
                        WHERE COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,selected_candidates}}', ''), '0')::int = 0
                          AND answer_mode <> 'refusal'
                    ) AS zero_hit_non_refusal,
                    COUNT(*) FILTER (
                        WHERE grounding_score > 0
                          AND grounding_score < 0.5
                    ) AS grounding_score_lt_0_5,
                    COUNT(*) FILTER (
                        WHERE answer_mode = 'weak_grounded'
                           OR evidence_status = 'partial'
                    ) AS partial_evidence,
                    COUNT(*) FILTER (
                        WHERE (
                            COALESCE(jsonb_array_length(citations_json), 0) = 0
                            AND answer_mode <> 'refusal'
                        )
                        OR (
                            COALESCE(NULLIF(usage_json #>> '{{_meta,retrieval,aggregate,selected_candidates}}', ''), '0')::int = 0
                            AND answer_mode <> 'refusal'
                        )
                        OR (
                            grounding_score > 0
                            AND grounding_score < 0.5
                        )
                        OR answer_mode = 'weak_grounded'
                        OR evidence_status = 'partial'
                    ) AS low_quality_answers
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            summary_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(answer_mode, ''), 'unknown') AS key,
                    COUNT(*) AS total_count
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params + (days,),
            )
            answer_mode_rows = cur.fetchall()
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(evidence_status, ''), 'unknown') AS key,
                    COUNT(*) AS total_count
                FROM chat_messages
                WHERE role = 'assistant'
                  AND {clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params + (days,),
            )
            evidence_rows = cur.fetchall()
    assistant_answers = int(summary_row.get("assistant_answers") or 0)

    def _rate(count: int) -> float:
        if assistant_answers <= 0:
            return 0.0
        return round(float(count) / float(assistant_answers), 4)

    return {
        "summary": {
            "assistant_answers": assistant_answers,
            "grounded_answers": int(summary_row.get("grounded_answers") or 0),
            "weak_grounded_answers": int(summary_row.get("weak_grounded_answers") or 0),
            "refusal_answers": int(summary_row.get("refusal_answers") or 0),
        },
        "answer_mode_distribution": [
            {"key": str(row.get("key") or ""), "count": int(row.get("total_count") or 0)}
            for row in answer_mode_rows
        ],
        "evidence_status_distribution": [
            {"key": str(row.get("key") or ""), "count": int(row.get("total_count") or 0)}
            for row in evidence_rows
        ],
        "zero_hit": {
            "selected_candidates_zero": int(summary_row.get("selected_candidates_zero") or 0),
            "selected_candidates_zero_rate": _rate(int(summary_row.get("selected_candidates_zero") or 0)),
            "missing_citations": int(summary_row.get("missing_citations") or 0),
            "missing_citations_rate": _rate(int(summary_row.get("missing_citations") or 0)),
        },
        "low_quality": {
            "count": int(summary_row.get("low_quality_answers") or 0),
            "rate": _rate(int(summary_row.get("low_quality_answers") or 0)),
            "score_threshold": 0.5,
            "reason_breakdown": [
                {"key": "missing_citations", "count": int(summary_row.get("missing_citations_non_refusal") or 0)},
                {"key": "zero_hit_non_refusal", "count": int(summary_row.get("zero_hit_non_refusal") or 0)},
                {"key": "grounding_score_lt_0_5", "count": int(summary_row.get("grounding_score_lt_0_5") or 0)},
                {"key": "partial_evidence", "count": int(summary_row.get("partial_evidence") or 0)},
            ],
        },
        "clarification": _clarification_stats(user, view=view, days=days),
    }


async def _kb_dashboard_snapshot(user: CurrentUser, *, view: str, days: int) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await request_service_json(
                client,
                "GET",
                f"{runtime_settings.kb_service_url}/api/v1/kb/analytics/dashboard",
                headers=downstream_headers(user),
                params={"view": view, "days": days},
            )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail or "kb analytics unavailable"), "code": "upstream_request_failed"}
        logger.warning("kb analytics unavailable view=%s days=%s code=%s", view, days, detail.get("code"))
        return None, [
            {
                "section": "kb_ingest_health",
                "code": str(detail.get("code") or "upstream_request_failed"),
                "detail": str(detail.get("detail") or "kb analytics unavailable"),
            }
        ]
    return (payload if isinstance(payload, dict) else None), []


def _data_quality_payload(kb_payload: dict[str, Any] | None, *, degraded_sections: list[dict[str, str]]) -> dict[str, Any]:
    data_quality = dict((kb_payload or {}).get("data_quality") or {})
    unsupported_fields = list(data_quality.get("unsupported_fields") or [])
    if kb_payload is None:
        unsupported_fields.extend(
            [
                "funnel.knowledge_bases_created",
                "funnel.documents_uploaded",
                "funnel.documents_ready",
                "ingest_health",
            ]
        )
    deduped: list[str] = []
    for item in unsupported_fields:
        normalized = str(item or "").strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return {
        "unsupported_fields": deduped,
        "degraded_sections": list(data_quality.get("degraded_sections") or []) + degraded_sections,
    }


@router.get(
    "/api/v1/analytics/dashboard",
    response_model=AnalyticsDashboardResponse,
    summary="可信知识助手运营看板",
    description="聚合知识库创建、文档 ready 漏斗、问答质量、反馈与成本趋势，供前端直接渲染主链路运营看板。",
)
async def get_dashboard(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅统计当前用户；admin 统计平台范围，需 platform_admin。"),
    days: int = Query(default=14, ge=1, le=90, description="滚动时间窗口，单位为天。"),
) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="analytics.dashboard.get", resource_type="analytics_dashboard")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported analytics view", "code": "analytics_view_invalid"})
    kb_payload, degraded_sections = await _kb_dashboard_snapshot(user, view=normalized_view, days=days)
    funnel = _chat_funnel_stats(user, view=normalized_view, days=days)
    qa_quality = _qa_quality_stats(user, view=normalized_view, days=days)
    kb_funnel = dict((kb_payload or {}).get("funnel") or {})
    payload = {
        "view": normalized_view,
        "days": days,
        "hot_terms": _hot_terms(user, view=normalized_view, days=days),
        "zero_hit": _zero_hit_stats(user, view=normalized_view, days=days),
        "satisfaction": _satisfaction_stats(user, view=normalized_view, days=days),
        "usage": _usage_stats(user, view=normalized_view, days=days),
        "funnel": {
            "knowledge_bases_created": kb_funnel.get("knowledge_bases_created"),
            "documents_uploaded": kb_funnel.get("documents_uploaded"),
            "documents_ready": kb_funnel.get("documents_ready"),
            "chat_sessions_with_questions": funnel["chat_sessions_with_questions"],
            "questions_asked": funnel["questions_asked"],
            "answer_outcomes": funnel["answer_outcomes"],
            "feedback": funnel["feedback"],
        },
        "ingest_health": (kb_payload or {}).get("ingest_health"),
        "qa_quality": qa_quality,
        "data_quality": _data_quality_payload(kb_payload, degraded_sections=degraded_sections),
    }
    write_gateway_audit_event(
        action="analytics.dashboard.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="analytics_dashboard",
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "days": days},
    )
    return payload
