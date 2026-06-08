from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from fastapi import Request

from shared.auth import CurrentUser

from .db import to_json
from .kb_api_support import audit_event
from .kb_batch_dry_run import KnowledgeBatchPayloadError, parse_knowledge_batch_payload
from .kb_resource_store import ensure_base_exists
from .kb_runtime import db, logger
from .parsing import parse_text_content
from .vector_store import ensure_vector_store, index_document_chunks, index_document_sections
from .worker import _insert_chunks, _insert_sections


MAX_BATCH_INGEST_TEXT_FIELD_CHARS = 160


class KnowledgeBatchRuntimeError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def parse_knowledge_batch_ingest_payload(raw: Any) -> list[dict[str, Any]]:
    parsed = parse_knowledge_batch_payload(raw)
    raw_documents = raw.get("documents") if isinstance(raw, dict) else []
    documents: list[dict[str, Any]] = []
    for index, document in enumerate(parsed):
        raw_document = raw_documents[index] if index < len(raw_documents) and isinstance(raw_documents[index], dict) else {}
        base_id = str(raw_document.get("base_id") or "").strip()
        if not base_id:
            raise KnowledgeBatchPayloadError("knowledge_batch_base_required", f"documents[{index}].base_id must not be blank")
        documents.append(
            {
                **document,
                "base_id": base_id[:MAX_BATCH_INGEST_TEXT_FIELD_CHARS],
                "category": str(raw_document.get("category") or "").strip()[:MAX_BATCH_INGEST_TEXT_FIELD_CHARS],
            }
        )
    return documents


def build_knowledge_batch_ingest_payload(raw: Any, *, request: Request, user: CurrentUser) -> dict[str, Any]:
    documents = parse_knowledge_batch_ingest_payload(raw)
    try:
        ensure_vector_store()
    except Exception as exc:  # pragma: no cover - exercised through route tests with monkeypatching
        raise KnowledgeBatchRuntimeError("knowledge_batch_vector_unavailable", "knowledge vector runtime is unavailable") from exc

    task_id = str(uuid4())
    items: list[dict[str, Any]] = []
    totals = {
        "section_count": 0,
        "chunk_count": 0,
        "indexed_sections": 0,
        "indexed_chunks": 0,
        "skipped_chunks": 0,
    }
    failed_status = 0
    for index, document in enumerate(documents):
        try:
            item = ingest_inline_knowledge_document(document, index=index, request=request, user=user)
        except KnowledgeBatchRuntimeError:
            raise
        except Exception as exc:
            logger.warning("knowledge batch ingest item failed index=%s", index, exc_info=True)
            item = {
                "index": index,
                "ok": False,
                "input_doc_id": str(document.get("doc_id") or ""),
                "file_name": str(document.get("file_name") or ""),
                "base_id": str(document.get("base_id") or ""),
                "code": _failure_code(exc),
                "detail": _failure_detail(exc),
            }
            failed_status = 400
        else:
            for key in totals:
                totals[key] += int(item.get(key) or 0)
        items.append(item)

    failed_documents = sum(1 for item in items if not item.get("ok"))
    result = {
        "success": failed_documents == 0,
        "batch": {
            "task_id": task_id,
            "status": "completed" if failed_documents == 0 else "failed",
        },
        "document_count": len(items),
        "succeeded_documents": len(items) - failed_documents,
        "failed_documents": failed_documents,
        **totals,
        "documents": items,
    }
    if failed_status:
        result["code"] = "knowledge_batch_ingest_failed"
        result["detail"] = "one or more documents failed to ingest"
    audit_event(
        action="kb.batch_ingest",
        outcome="success" if failed_documents == 0 else "partial_success",
        request=request,
        user=user,
        resource_type="document_batch",
        resource_id=task_id,
        scope="managed",
        details={
            "total": len(items),
            "succeeded": len(items) - failed_documents,
            "failed": failed_documents,
            "document_ids": [str(item.get("document_id") or "") for item in items if item.get("ok")],
        },
    )
    return result


def ingest_inline_knowledge_document(document: dict[str, Any], *, index: int, request: Request, user: CurrentUser) -> dict[str, Any]:
    base_id = str(document["base_id"])
    ensure_base_exists(base_id, user=user, request=request, action="kb.batch_ingest")
    parsed = parse_text_content(str(document["content"]))
    if not parsed.chunks:
        raise ValueError("document contains no extractable text")

    document_id = str(uuid4())
    content = str(document["content"])
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    file_name = str(document["file_name"])
    stats = {
        "source": "batch_ingest",
        "category": str(document.get("category") or ""),
        "input_doc_id": str(document.get("doc_id") or ""),
        "section_count": len(parsed.sections),
        "chunk_count": len(parsed.chunks),
    }
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kb_documents (
                    id, base_id, file_name, file_type, content_hash, storage_path,
                    storage_key, size_bytes, status, query_ready, enhancement_status,
                    created_by, stats_json, upload_session_id,
                    source_type, source_uri, source_metadata_json,
                    version_family_key, version_label, version_number, version_status,
                    is_current_version
                )
                VALUES (
                    %s, %s, %s, 'txt', %s, '',
                    '', %s, 'fast_index_ready', TRUE, 'fts_only',
                    %s, %s::jsonb, NULL,
                    'batch_ingest', '', %s::jsonb,
                    %s, 'v1', 1, 'active',
                    TRUE
                )
                """,
                (
                    document_id,
                    base_id,
                    file_name,
                    content_hash,
                    len(content.encode("utf-8")),
                    user.user_id,
                    to_json(stats),
                    to_json({"input_doc_id": str(document.get("doc_id") or ""), "file_name": file_name}),
                    document_id,
                ),
            )
            _insert_sections(cur, document_id, parsed.sections)
            _insert_chunks(cur, document_id, parsed.chunks)
            cur.execute(
                """
                INSERT INTO kb_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'batch_ingested', 'inline batch document indexed for search', %s::jsonb)
                """,
                (document_id, to_json({"section_count": len(parsed.sections), "chunk_count": len(parsed.chunks)})),
            )
        conn.commit()

    try:
        section_index = index_document_sections(document_id)
        chunk_index = index_document_chunks(document_id)
    except Exception as exc:
        _mark_document_failed(document_id, reason="vector_index_failed")
        raise KnowledgeBatchRuntimeError("knowledge_batch_vector_unavailable", "knowledge vector runtime is unavailable") from exc

    section_indexed = int(section_index.get("indexed") or 0)
    chunk_indexed = int(chunk_index.get("indexed") or 0)
    vector_stats = {"sections": section_index, "chunks": chunk_index}
    final_stats = {**stats, "vector_index": vector_stats}
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_documents
                SET status = 'ready',
                    query_ready = TRUE,
                    enhancement_status = 'chunk_vectors_ready',
                    query_ready_at = NOW(),
                    hybrid_ready_at = NOW(),
                    ready_at = NOW(),
                    section_count = %s,
                    chunk_count = %s,
                    stats_json = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (len(parsed.sections), len(parsed.chunks), to_json(final_stats), document_id),
            )
            cur.execute(
                """
                INSERT INTO kb_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'ready', 'inline batch document vectors indexed', %s::jsonb)
                """,
                (document_id, to_json({"vector_index": vector_stats})),
            )
        conn.commit()

    return {
        "index": index,
        "ok": True,
        "input_doc_id": str(document.get("doc_id") or ""),
        "document_id": document_id,
        "base_id": base_id,
        "file_name": file_name,
        "section_count": len(parsed.sections),
        "chunk_count": len(parsed.chunks),
        "indexed_sections": section_indexed,
        "indexed_chunks": chunk_indexed,
        "skipped_chunks": max(len(parsed.chunks) - chunk_indexed, 0),
        "status": "ready",
    }


def _mark_document_failed(document_id: str, *, reason: str) -> None:
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE kb_documents
                    SET status = 'failed',
                        enhancement_status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (reason, document_id),
                )
            conn.commit()
    except Exception:
        logger.warning("failed to mark batch-ingested document failed document_id=%s", document_id, exc_info=True)


def _failure_code(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])
    if isinstance(exc, ValueError):
        return "knowledge_batch_document_invalid"
    return "knowledge_batch_document_failed"


def _failure_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and detail.get("detail"):
        return str(detail["detail"])
    if isinstance(exc, ValueError):
        return str(exc) or "invalid document payload"
    return "document ingest failed"
