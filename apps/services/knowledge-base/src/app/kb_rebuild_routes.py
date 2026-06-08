from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_rebuild import KnowledgeRebuildPayloadError, KnowledgeRebuildRuntimeError, build_knowledge_rebuild_payload
from .kb_runtime import KB_WRITE_PERMISSION


router = APIRouter()


@router.post("/api/knowledge_base/rebuild")
async def post_knowledge_rebuild(request: Request, user: CurrentUser, payload: Any = Body(...)) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.rebuild", resource_type="document")
    try:
        return build_knowledge_rebuild_payload(payload, request=request, user=user)
    except KnowledgeRebuildPayloadError as exc:
        raise_api_error(400, exc.code, exc.detail)
    except KnowledgeRebuildRuntimeError as exc:
        raise_api_error(409, exc.code, exc.detail)
