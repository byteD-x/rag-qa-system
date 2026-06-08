from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_index import DEFAULT_INDEX_LIMIT, MAX_INDEX_LIMIT, build_knowledge_index_payload
from .kb_runtime import KB_READ_PERMISSION


router = APIRouter()


@router.get("/api/knowledge_base/index")
async def get_knowledge_index(
    request: Request,
    user: CurrentUser,
    limit: int = Query(default=DEFAULT_INDEX_LIMIT, ge=1, le=MAX_INDEX_LIMIT),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.index.list", resource_type="knowledge_base")
    return build_knowledge_index_payload(user=user, limit=limit)
