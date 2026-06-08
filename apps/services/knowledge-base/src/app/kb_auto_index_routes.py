from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_auto_index import build_knowledge_auto_index_preview_payload
from .kb_runtime import KB_WRITE_PERMISSION


router = APIRouter()


@router.get("/api/knowledge_base/auto-index/preview")
async def get_knowledge_auto_index_preview(request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.auto_index.preview", resource_type="knowledge_base")
    return build_knowledge_auto_index_preview_payload()
