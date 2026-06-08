from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from shared.auth import CurrentUser

from .db import to_json
from .kb_api_support import audit_event
from .kb_resource_store import load_document
from .kb_runtime import db
from .vector_store import delete_document_vectors, ensure_vector_store, index_document_chunks, index_document_sections


MAX_REBUILD_DOC_ID_CHARS = 128


class KnowledgeRebuildPayloadError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class KnowledgeRebuildRuntimeError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def build_knowledge_rebuild_signature(doc_id: str) -> str:
    canonical = json.dumps({"doc_id": str(doc_id or "").strip()}, ensure_ascii=False, separators=(",", ":"))
    hash_value = 0
    for char in canonical:
        hash_value = (((hash_value << 5) - hash_value) + ord(char)) & 0xFFFFFFFF
    return f"kb-rebuild:{hash_value:08x}"


def parse_knowledge_rebuild_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeRebuildPayloadError("knowledge_rebuild_payload_invalid", "request body must be an object")
    allowed_fields = {"doc_id", "dry_run", "signature"}
    extra_fields = sorted(set(raw.keys()) - allowed_fields)
    if extra_fields:
        raise KnowledgeRebuildPayloadError(
            "knowledge_rebuild_field_not_allowed",
            f"request contains forbidden fields: {', '.join(extra_fields)}",
        )
    doc_id = str(raw.get("doc_id") or "").strip()
    if not doc_id:
        raise KnowledgeRebuildPayloadError("knowledge_rebuild_doc_required", "doc_id must not be blank")
    if len(doc_id) > MAX_REBUILD_DOC_ID_CHARS:
        raise KnowledgeRebuildPayloadError(
            "knowledge_rebuild_doc_invalid",
            f"doc_id must contain no more than {MAX_REBUILD_DOC_ID_CHARS} characters",
        )
    dry_run = raw.get("dry_run") is True
    signature = str(raw.get("signature") or "").strip()
    expected_signature = build_knowledge_rebuild_signature(doc_id)
    if not dry_run and signature != expected_signature:
        raise KnowledgeRebuildPayloadError(
            "knowledge_rebuild_signature_mismatch",
            "signature must match current rebuild payload",
        )
    return {"doc_id": doc_id, "dry_run": dry_run, "signature": expected_signature}


def build_knowledge_rebuild_payload(raw: Any, *, request: Request, user: CurrentUser) -> dict[str, Any]:
    payload = parse_knowledge_rebuild_payload(raw)
    document = load_document(payload["doc_id"], user=user, request=request, action="kb.rebuild")
    doc_id = str(document.get("id") or payload["doc_id"])
    base_result = {
        "doc_id": doc_id,
        "version": document.get("version_label") or document.get("version_number") or "",
        "section_count": int(document.get("section_count") or 0),
        "chunk_count": int(document.get("chunk_count") or 0),
        "dry_run": bool(payload["dry_run"]),
        "signature": payload["signature"],
    }
    if payload["dry_run"]:
        audit_event(
            action="kb.rebuild.dry_run",
            outcome="success",
            request=request,
            user=user,
            resource_type="document",
            resource_id=doc_id,
            scope="owner",
            details={"section_count": base_result["section_count"], "chunk_count": base_result["chunk_count"]},
        )
        return base_result

    try:
        ensure_vector_store()
        delete_document_vectors(doc_id)
        section_index = index_document_sections(doc_id)
        chunk_index = index_document_chunks(doc_id)
    except Exception as exc:
        raise KnowledgeRebuildRuntimeError("knowledge_rebuild_vector_unavailable", "knowledge vector runtime is unavailable") from exc

    section_count = int(section_index.get("rows") or base_result["section_count"])
    chunk_count = int(chunk_index.get("rows") or base_result["chunk_count"])
    indexed_chunks = int(chunk_index.get("indexed") or 0)
    stats_patch = {
        "rebuild": {
            "section_count": section_count,
            "chunk_count": chunk_count,
        },
        "vector_index": {
            "sections": section_index,
            "chunks": chunk_index,
        },
    }
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_documents
                SET status = 'ready',
                    query_ready = TRUE,
                    enhancement_status = 'chunk_vectors_ready',
                    hybrid_ready_at = NOW(),
                    ready_at = NOW(),
                    section_count = %s,
                    chunk_count = %s,
                    stats_json = COALESCE(stats_json, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (section_count, chunk_count, to_json(stats_patch), doc_id),
            )
            cur.execute(
                """
                INSERT INTO kb_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'rebuild', 'document vectors rebuilt from existing sections and chunks', %s::jsonb)
                """,
                (doc_id, to_json(stats_patch)),
            )
        conn.commit()
    audit_event(
        action="kb.rebuild",
        outcome="success",
        request=request,
        user=user,
        resource_type="document",
        resource_id=doc_id,
        scope="owner",
        details={"section_count": section_count, "chunk_count": chunk_count, "indexed_chunks": indexed_chunks},
    )
    return {
        **base_result,
        "dry_run": False,
        "section_count": section_count,
        "chunk_count": chunk_count,
        "indexed_sections": int(section_index.get("indexed") or 0),
        "indexed_chunks": indexed_chunks,
        "deleted_previous": 0,
    }
