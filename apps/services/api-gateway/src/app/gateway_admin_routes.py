from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from shared.auth import CurrentUser

from .gateway_audit_support import merge_audit_event_lists, query_gateway_audit_events, query_kb_audit_events, require_permission, write_gateway_audit_event
from .gateway_provider_billing import import_provider_billing_records
from .gateway_runtime import AUDIT_PERMISSION, runtime_settings
from .gateway_schemas import ProviderBillingImportRequest
from .gateway_transport import proxy_request, request_service_json, downstream_headers


router = APIRouter()


def _require_platform_admin(request: Request, user: CurrentUser, *, action: str, resource_type: str) -> None:
    if str(user.role or "") == "platform_admin":
        return
    write_gateway_audit_event(
        action=action,
        outcome="denied",
        request=request,
        user=user,
        resource_type=resource_type,
        scope="admin",
        details={"required_role": "platform_admin"},
    )
    raise HTTPException(status_code=403, detail={"detail": "platform_admin required", "code": "permission_denied"})


@router.get("/api/v1/audit/events")
async def list_audit_events(
    request: Request,
    user: CurrentUser,
    service: str = Query(default="", max_length=32),
    actor_user_id: str = Query(default="", max_length=128),
    resource_type: str = Query(default="", max_length=128),
    resource_id: str = Query(default="", max_length=128),
    action: str = Query(default="", max_length=128),
    outcome: str = Query(default="", max_length=32),
    created_from: str = Query(default="", max_length=64),
    created_to: str = Query(default="", max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    require_permission(request, user, AUDIT_PERMISSION, action="audit.events.list", resource_type="audit_event")
    fetch_limit = min(limit + offset, 400)
    normalized_service = service.strip().lower()
    gateway_items = query_gateway_audit_events(
        actor_user_id=actor_user_id.strip(),
        resource_type=resource_type.strip(),
        resource_id=resource_id.strip(),
        action=action.strip(),
        outcome=outcome.strip(),
        created_from=created_from.strip(),
        created_to=created_to.strip(),
        limit=fetch_limit,
    ) if normalized_service in {"", "gateway"} else []
    kb_items = await query_kb_audit_events(
        user,
        request_service_json=request_service_json,
        downstream_headers=downstream_headers,
        kb_service_url=runtime_settings.kb_service_url,
        actor_user_id=actor_user_id.strip(),
        resource_type=resource_type.strip(),
        resource_id=resource_id.strip(),
        action=action.strip(),
        outcome=outcome.strip(),
        created_from=created_from.strip(),
        created_to=created_to.strip(),
        limit=fetch_limit,
    ) if normalized_service in {"", "kb-service"} else []
    items = merge_audit_event_lists(gateway_items, kb_items, limit=limit, offset=offset)
    write_gateway_audit_event(action="audit.events.list", outcome="success", request=request, user=user, resource_type="audit_event", details={"service": normalized_service or "all", "limit": limit, "offset": offset})
    return {"items": items, "pagination": {"limit": limit, "offset": offset, "returned": len(items)}}


@router.post("/api/v1/admin/costs/provider-billing-records")
async def import_provider_billing(payload: ProviderBillingImportRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    _require_platform_admin(request, user, action="admin.cost.provider_billing.import", resource_type="provider_billing_record")
    result = import_provider_billing_records(
        [record.model_dump() for record in payload.records],
        imported_by_user_id=user.user_id,
    )
    write_gateway_audit_event(
        action="admin.cost.provider_billing.import",
        outcome="success",
        request=request,
        user=user,
        resource_type="provider_billing_record",
        scope="admin",
        details={"imported": result["imported"]},
    )
    return result


@router.api_route("/api/v1/kb/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_kb(path: str, request: Request) -> Response:
    return await proxy_request(request, service_base_url=runtime_settings.kb_service_url, service_path=f"/api/v1/kb/{path}")
