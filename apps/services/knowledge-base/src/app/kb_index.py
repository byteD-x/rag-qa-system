from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from shared.auth import CurrentUser

from .kb_api_support import can_manage_everything
from .kb_runtime import db
from .vector_store import check_vector_store


DEFAULT_INDEX_LIMIT = 100
MAX_INDEX_LIMIT = 500


class KnowledgeIndexUnsupported(RuntimeError):
    pass


def build_knowledge_index_payload(*, user: CurrentUser, limit: int = DEFAULT_INDEX_LIMIT) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or DEFAULT_INDEX_LIMIT), MAX_INDEX_LIMIT))
    vector_available = _vector_memory_available()
    try:
        counts = load_knowledge_index_counts(user=user)
        rows = list_knowledge_index_rows(user=user, limit=safe_limit)
    except KnowledgeIndexUnsupported:
        return {
            "success": True,
            "vector_memory_available": vector_available,
            "supports_index": False,
            "source": "knowledge_base",
            "chunk_count": 0,
            "document_count": 0,
            "documents": [],
            "truncated": False,
        }

    document_count = int(counts.get("document_count") or 0)
    documents = [_serialize_index_document(row) for row in rows]
    return {
        "success": True,
        "vector_memory_available": vector_available,
        "supports_index": True,
        "source": "knowledge_base",
        "chunk_count": int(counts.get("chunk_count") or 0),
        "document_count": document_count,
        "documents": documents,
        "truncated": document_count > len(documents),
    }


def load_knowledge_index_counts(*, user: CurrentUser) -> dict[str, Any]:
    clause, params = _scope_clause(user)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS document_count,
                    COALESCE(SUM(chunk_count), 0) AS chunk_count
                FROM kb_documents
                WHERE {clause}
                """,
                params,
            )
            return cur.fetchone() or {}


def list_knowledge_index_rows(*, user: CurrentUser, limit: int) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    documents.id::text AS document_id,
                    documents.base_id::text AS base_id,
                    bases.name AS base_name,
                    documents.file_name,
                    documents.file_type,
                    documents.status,
                    documents.query_ready,
                    documents.enhancement_status,
                    documents.section_count,
                    documents.chunk_count,
                    documents.stats_json,
                    documents.source_type,
                    documents.source_uri,
                    documents.version_family_key,
                    documents.version_label,
                    documents.version_number,
                    documents.version_status,
                    documents.is_current_version,
                    documents.created_at,
                    documents.updated_at
                FROM kb_documents documents
                JOIN kb_bases bases ON bases.id = documents.base_id
                WHERE {clause.replace("created_by", "documents.created_by")}
                ORDER BY documents.updated_at DESC, documents.created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            return cur.fetchall()


def _scope_clause(user: CurrentUser) -> tuple[str, tuple[Any, ...]]:
    if can_manage_everything(user):
        return "TRUE", ()
    return "created_by = %s", (user.user_id,)


def _serialize_index_document(row: dict[str, Any]) -> dict[str, Any]:
    stats = row.get("stats_json") if isinstance(row.get("stats_json"), dict) else {}
    file_name = _safe_leaf_name(row.get("file_name"), fallback=str(row.get("document_id") or "document"))
    source_type = str(row.get("source_type") or stats.get("source") or "").strip()
    return {
        "document_id": str(row.get("document_id") or ""),
        "base_id": str(row.get("base_id") or ""),
        "base_name": str(row.get("base_name") or ""),
        "file_name": file_name,
        "file_type": str(row.get("file_type") or ""),
        "status": str(row.get("status") or ""),
        "query_ready": bool(row.get("query_ready")),
        "enhancement_status": str(row.get("enhancement_status") or ""),
        "section_count": int(row.get("section_count") or 0),
        "chunk_count": int(row.get("chunk_count") or 0),
        "category": str(stats.get("category") or ""),
        "source_type": source_type,
        "source_ref": _safe_source_ref(row.get("source_uri")),
        "version_family_key": str(row.get("version_family_key") or ""),
        "version_label": str(row.get("version_label") or ""),
        "version_number": int(row.get("version_number") or 0),
        "version_status": str(row.get("version_status") or ""),
        "is_current_version": bool(row.get("is_current_version")),
        "created_at": _iso_timestamp(row.get("created_at")),
        "updated_at": _iso_timestamp(row.get("updated_at")),
    }


def _vector_memory_available() -> bool:
    try:
        status = check_vector_store()
    except Exception:
        return False
    return str(status.get("status") or "ok").strip().lower() not in {"", "failed", "error", "unavailable"}


def _safe_source_ref(raw: Any) -> str:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return ""
    normalized = cleaned.replace("\\", "/")
    if len(normalized) > 1 and normalized[1] == ":":
        return _safe_leaf_name(normalized, fallback="")
    if "://" not in normalized:
        return _safe_leaf_name(normalized, fallback="")
    try:
        parts = urlsplit(normalized)
    except ValueError:
        return _safe_leaf_name(normalized, fallback="")
    if parts.scheme in {"http", "https"}:
        return parts.netloc
    return parts.scheme


def _safe_leaf_name(raw: Any, *, fallback: str) -> str:
    cleaned = str(raw or "").strip().replace("\\", "/")
    leaf = PurePosixPath(cleaned).name.strip()
    if not leaf or leaf in {".", ".."}:
        leaf = fallback
    return leaf[:160]


def _iso_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")
