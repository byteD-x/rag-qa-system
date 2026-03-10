from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shared.auth import CurrentUser
from shared.text_search import tokenize_text

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_runtime import CHAT_PERMISSION, gateway_db, runtime_settings


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


@router.get("/api/v1/analytics/dashboard")
async def get_dashboard(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16),
    days: int = Query(default=14, ge=1, le=90),
) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="analytics.dashboard.get", resource_type="analytics_dashboard")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported analytics view", "code": "analytics_view_invalid"})
    payload = {
        "view": normalized_view,
        "days": days,
        "hot_terms": _hot_terms(user, view=normalized_view, days=days),
        "zero_hit": _zero_hit_stats(user, view=normalized_view, days=days),
        "satisfaction": _satisfaction_stats(user, view=normalized_view, days=days),
        "usage": _usage_stats(user, view=normalized_view, days=days),
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
