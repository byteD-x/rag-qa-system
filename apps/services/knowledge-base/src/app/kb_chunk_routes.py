from __future__ import annotations

from fastapi import APIRouter, Query, Request

from shared.auth import CurrentUser

from .kb_api_support import require_kb_permission
from .kb_chunk_governance import list_document_chunks, merge_chunks, split_chunk, update_chunk
from .kb_resource_store import load_document
from .kb_runtime import KB_READ_PERMISSION, KB_WRITE_PERMISSION
from .kb_schemas import MergeChunksRequest, SplitChunkRequest, UpdateChunkRequest


router = APIRouter()


@router.get("/api/v1/kb/documents/{document_id}/chunks")
def get_document_chunks(
    document_id: str,
    request: Request,
    user: CurrentUser,
    include_disabled: bool = Query(default=True),
) -> dict[str, object]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.document.chunks", resource_type="document", resource_id=document_id)
    document = load_document(document_id, user=user, request=request, action="kb.document.chunks")
    items = list_document_chunks(document_id, user=user, request=request, include_disabled=include_disabled)
    return {
        "document_id": document_id,
        "base_id": str(document.get("base_id") or ""),
        "items": items,
        "counts": {
            "total": len(items),
            "active": sum(1 for item in items if not bool(item.get("disabled"))),
            "disabled": sum(1 for item in items if bool(item.get("disabled"))),
        },
    }


@router.patch("/api/v1/kb/chunks/{chunk_id}")
def patch_chunk(chunk_id: str, payload: UpdateChunkRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.chunk.update", resource_type="chunk", resource_id=chunk_id)
    return update_chunk(
        chunk_id,
        text_content=payload.text_content,
        disabled=payload.disabled,
        disabled_reason=payload.disabled_reason,
        manual_note=payload.manual_note,
        user=user,
        request=request,
    )


@router.post("/api/v1/kb/chunks/{chunk_id}/split")
def split_document_chunk(chunk_id: str, payload: SplitChunkRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.chunk.split", resource_type="chunk", resource_id=chunk_id)
    return split_chunk(chunk_id, parts=payload.parts, user=user, request=request)


@router.post("/api/v1/kb/chunks/merge")
def merge_document_chunks(payload: MergeChunksRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.chunk.merge", resource_type="chunk")
    return merge_chunks(payload.chunk_ids, separator=payload.separator, user=user, request=request)
