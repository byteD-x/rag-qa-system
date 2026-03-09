from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, Response

from shared.auth import CurrentUser
from shared.metrics import CONTENT_TYPE_LATEST, generate_latest

from .kb_api_support import audit_event, check_readiness, list_audit_events, refresh_metrics_snapshot, require_kb_permission
from .kb_runtime import AUDIT_PERMISSION


router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, Any]:
    checks = check_readiness()
    failed = [name for name, item in checks.items() if item.get("status") == "failed"]
    if failed:
        from shared.api_errors import raise_api_error

        raise_api_error(503, "kb_service_not_ready", f"kb-service dependencies are not ready: {', '.join(failed)}")
    return {"status": "ready", "checks": checks}


@router.get("/metrics")
def metrics() -> Response:
    refresh_metrics_snapshot()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/kb/audit/events")
def list_kb_audit_events(
    request: Request,
    user: CurrentUser,
    actor_user_id: str = Query(default="", max_length=128),
    resource_type: str = Query(default="", max_length=128),
    resource_id: str = Query(default="", max_length=128),
    action: str = Query(default="", max_length=128),
    outcome: str = Query(default="", max_length=32),
    created_from: str = Query(default="", max_length=64),
    created_to: str = Query(default="", max_length=64),
    limit: int = Query(default=100, ge=1, le=400),
) -> dict[str, Any]:
    require_kb_permission(request, user, AUDIT_PERMISSION, action="audit.events.list", resource_type="audit_event")
    items = list_audit_events(
        actor_user_id=actor_user_id.strip(),
        resource_type=resource_type.strip(),
        resource_id=resource_id.strip(),
        action=action.strip(),
        outcome=outcome.strip(),
        created_from=created_from.strip(),
        created_to=created_to.strip(),
        limit=limit,
    )
    audit_event(
        action="audit.events.list",
        outcome="success",
        request=request,
        user=user,
        resource_type="audit_event",
        details={"limit": limit},
    )
    return {"items": items}
