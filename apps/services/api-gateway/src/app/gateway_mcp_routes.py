from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from shared.auth import CurrentUser

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_mcp_adapter import handle_mcp_request, mcp_audit_details
from .gateway_runtime import CHAT_PERMISSION


router = APIRouter()


@router.post("/api/v1/mcp")
async def post_mcp(payload: dict[str, Any], request: Request, user: CurrentUser) -> dict[str, Any]:
    require_permission(request, user, CHAT_PERMISSION, action="mcp.request", resource_type="mcp_adapter")
    response = await handle_mcp_request(payload)
    details = mcp_audit_details(payload, response)
    write_gateway_audit_event(
        action="mcp.request",
        outcome="failed" if details["has_error"] else "success",
        request=request,
        user=user,
        resource_type="mcp_adapter",
        resource_id=str(details.get("tool_name") or details.get("method") or ""),
        scope="jsonrpc",
        details=details,
    )
    return response
