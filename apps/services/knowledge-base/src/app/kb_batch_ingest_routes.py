from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_batch_dry_run import KnowledgeBatchPayloadError
from .kb_batch_ingest import KnowledgeBatchRuntimeError, build_knowledge_batch_ingest_payload
from .kb_runtime import KB_WRITE_PERMISSION


router = APIRouter()


@router.post("/api/knowledge_base/batch-ingest", response_model=None)
async def post_knowledge_batch_ingest(request: Request, user: CurrentUser, payload: Any = Body(...)) -> Any:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.batch_ingest", resource_type="knowledge_base")
    try:
        result = build_knowledge_batch_ingest_payload(payload, request=request, user=user)
    except KnowledgeBatchPayloadError as exc:
        raise_api_error(400, exc.code, exc.detail)
    except KnowledgeBatchRuntimeError as exc:
        raise_api_error(409, exc.code, exc.detail)
    if int(result.get("failed_documents") or 0) > 0:
        return JSONResponse(status_code=400, content=result)
    return result
