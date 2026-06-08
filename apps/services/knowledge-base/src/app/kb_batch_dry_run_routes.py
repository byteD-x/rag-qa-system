from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_batch_dry_run import KnowledgeBatchPayloadError, build_knowledge_batch_dry_run_payload
from .kb_runtime import KB_WRITE_PERMISSION


router = APIRouter()


@router.post("/api/knowledge_base/batch-dry-run")
async def post_knowledge_batch_dry_run(request: Request, user: CurrentUser, payload: Any = Body(...)) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.batch_dry_run", resource_type="knowledge_base")
    try:
        return build_knowledge_batch_dry_run_payload(payload)
    except KnowledgeBatchPayloadError as exc:
        raise_api_error(400, exc.code, exc.detail)
