from __future__ import annotations

from typing import Any

import httpx
from fastapi import Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser, has_permission
from shared.tracing import current_trace_id

from .db import to_json
from .gateway_runtime import GATEWAY_AUDIT_WRITE_FAILURES_TOTAL, gateway_db, logger, runtime_settings


def serialize_timestamp(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def write_gateway_audit_event(
    *,
    action: str,
    outcome: str,
    request: Request | None = None,
    user: CurrentUser | None = None,
    actor_email: str = "",
    resource_type: str = "",
    resource_id: str = "",
    scope: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gateway_audit_events (
                        actor_user_id, actor_email, actor_role, action, resource_type,
                        resource_id, scope, outcome, trace_id, request_path, details_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        str(user.user_id if user else ""),
                        str(user.email if user else actor_email),
                        str(user.role if user else ""),
                        action,
                        resource_type,
                        resource_id,
                        scope,
                        outcome,
                        current_trace_id(),
                        str(request.url.path if request else ""),
                        to_json(details or {}),
                    ),
                )
            conn.commit()
    except Exception:
        GATEWAY_AUDIT_WRITE_FAILURES_TOTAL.inc()
        logger.exception("gateway audit write failed action=%s outcome=%s", action, outcome)


def require_permission(
    request: Request,
    user: CurrentUser,
    permission: str,
    *,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    if has_permission(user, permission):
        return
    write_gateway_audit_event(
        action=action,
        outcome="denied",
        request=request,
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        scope="permission",
        details={"permission": permission, **(details or {})},
    )
    raise_api_error(403, "permission_denied", f"missing permission: {permission}")


def query_gateway_audit_events(
    *,
    actor_user_id: str = "",
    resource_type: str = "",
    resource_id: str = "",
    action: str = "",
    outcome: str = "",
    created_from: str = "",
    created_to: str = "",
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["TRUE"]
    params: list[Any] = []
    if actor_user_id:
        clauses.append("actor_user_id = %s")
        params.append(actor_user_id)
    if resource_type:
        clauses.append("resource_type = %s")
        params.append(resource_type)
    if resource_id:
        clauses.append("resource_id = %s")
        params.append(resource_id)
    if action:
        clauses.append("action = %s")
        params.append(action)
    if outcome:
        clauses.append("outcome = %s")
        params.append(outcome)
    if created_from:
        clauses.append("created_at >= %s::timestamptz")
        params.append(created_from)
    if created_to:
        clauses.append("created_at <= %s::timestamptz")
        params.append(created_to)
    params.append(limit)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM gateway_audit_events
                WHERE {" AND ".join(clauses)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [
                {
                    "id": str(row.get("id") or ""),
                    "service": "gateway",
                    "actor_user_id": str(row.get("actor_user_id") or ""),
                    "actor_email": str(row.get("actor_email") or ""),
                    "actor_role": str(row.get("actor_role") or ""),
                    "action": str(row.get("action") or ""),
                    "resource_type": str(row.get("resource_type") or ""),
                    "resource_id": str(row.get("resource_id") or ""),
                    "scope": str(row.get("scope") or ""),
                    "outcome": str(row.get("outcome") or ""),
                    "trace_id": str(row.get("trace_id") or ""),
                    "request_path": str(row.get("request_path") or ""),
                    "details": dict(row.get("details_json") or {}),
                    "created_at": serialize_timestamp(row.get("created_at")),
                }
                for row in cur.fetchall()
            ]


async def query_kb_audit_events(
    user: CurrentUser,
    *,
    request_service_json: Any,
    downstream_headers: Any,
    kb_service_url: str,
    actor_user_id: str = "",
    resource_type: str = "",
    resource_id: str = "",
    action: str = "",
    outcome: str = "",
    created_from: str = "",
    created_to: str = "",
    limit: int,
) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    params = {
        "actor_user_id": actor_user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "outcome": outcome,
        "created_from": created_from,
        "created_to": created_to,
        "limit": limit,
    }
    filtered_params = {key: value for key, value in params.items() if value not in ("", None)}
    async with httpx.AsyncClient(timeout=timeout) as client:
        payload = await request_service_json(
            client,
            "GET",
            f"{kb_service_url}/api/v1/kb/audit/events",
            headers=downstream_headers(user),
            params=filtered_params,
        )
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [dict(item) for item in items if isinstance(item, dict)]


def merge_audit_event_lists(*lists: list[dict[str, Any]], limit: int, offset: int) -> list[dict[str, Any]]:
    merged = [item for values in lists for item in values]
    merged.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return merged[offset : offset + limit]
