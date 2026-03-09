from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from shared.auth import CurrentUser
from shared.sse import iter_query_sse_messages
from shared.tracing import current_trace_id

from .kb_api_support import require_kb_permission
from .kb_query_helpers import build_query_response, serialize_evidence
from .kb_resource_store import ensure_base_exists
from .kb_runtime import CHAT_PERMISSION, KB_READ_PERMISSION, KB_RETRIEVE_LATENCY_MS, KB_RETRIEVE_REQUESTS_TOTAL
from .kb_schemas import KBQueryRequest, RetrieveRequest
from .retrieve import retrieve_kb_result


router = APIRouter()


@router.post("/api/v1/kb/retrieve")
def retrieve_kb(payload: RetrieveRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.retrieve", resource_type="knowledge_base", resource_id=payload.base_id)
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.retrieve")
    result = retrieve_kb_result(
        base_id=payload.base_id,
        question=payload.question,
        document_ids=payload.document_ids,
        limit=payload.limit,
    )
    degraded = "true" if result.stats.degraded_signals else "false"
    KB_RETRIEVE_REQUESTS_TOTAL.labels("success", degraded).inc()
    KB_RETRIEVE_LATENCY_MS.observe(float(result.stats.retrieval_ms))
    return {
        "items": [serialize_evidence(item, corpus_id=f"kb:{payload.base_id}") for item in result.items],
        "retrieval": result.stats.as_dict(),
        "trace_id": current_trace_id(),
    }


@router.post("/api/v1/kb/query")
def query_kb(payload: KBQueryRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.query", resource_type="knowledge_base", resource_id=payload.base_id)
    require_kb_permission(request, user, CHAT_PERMISSION, action="kb.query", resource_type="knowledge_base", resource_id=payload.base_id)
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.query")
    result = build_query_response(base_id=payload.base_id, question=payload.question, document_ids=payload.document_ids)
    degraded = "true" if list((result.get("retrieval") or {}).get("degraded_signals") or []) else "false"
    result_label = "refusal" if str(result.get("answer_mode") or "") == "refusal" else "success"
    KB_RETRIEVE_REQUESTS_TOTAL.labels(result_label, degraded).inc()
    KB_RETRIEVE_LATENCY_MS.observe(float((result.get("retrieval") or {}).get("retrieval_ms") or 0.0))
    return result


@router.post("/api/v1/kb/query/stream")
def stream_query_kb(payload: KBQueryRequest, request: Request, user: CurrentUser) -> StreamingResponse:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.query.stream", resource_type="knowledge_base", resource_id=payload.base_id)
    require_kb_permission(request, user, CHAT_PERMISSION, action="kb.query.stream", resource_type="knowledge_base", resource_id=payload.base_id)
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.query.stream")
    result = build_query_response(base_id=payload.base_id, question=payload.question, document_ids=payload.document_ids)
    degraded = "true" if list((result.get("retrieval") or {}).get("degraded_signals") or []) else "false"
    result_label = "refusal" if str(result.get("answer_mode") or "") == "refusal" else "success"
    KB_RETRIEVE_REQUESTS_TOTAL.labels(result_label, degraded).inc()
    KB_RETRIEVE_LATENCY_MS.observe(float((result.get("retrieval") or {}).get("retrieval_ms") or 0.0))

    def generate() -> Any:
        yield from iter_query_sse_messages(result)

    return StreamingResponse(generate(), media_type="text/event-stream")
