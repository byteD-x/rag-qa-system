from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from fastapi import Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser
from shared.text_search import build_fts_lexeme_text

from .db import to_json
from .kb_api_support import audit_event, can_manage_everything
from .kb_resource_store import load_document
from .kb_runtime import db
from .vector_store import delete_document_vectors, index_document_chunks, index_document_sections


def _compact_text(value: str, limit: int) -> str:
    compact = " ".join(part.strip() for part in str(value or "").splitlines() if part.strip())
    return compact[:limit].strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_chunk_search_text(section_title: str, text: str) -> str:
    return " ".join(part for part in (section_title.strip(), text.strip()) if part).strip()


def _load_chunk_row(chunk_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunks.*,
                    sections.title AS section_title,
                    sections.char_start AS section_char_start,
                    documents.base_id::text AS base_id,
                    documents.file_name AS document_title,
                    documents.created_by AS document_created_by
                FROM kb_chunks chunks
                JOIN kb_sections sections ON sections.id = chunks.section_id
                JOIN kb_documents documents ON documents.id = chunks.document_id
                WHERE chunks.id = %s
                """,
                (chunk_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "chunk_not_found", "chunk not found")
    return row


def load_chunk(
    chunk_id: str,
    *,
    user: CurrentUser,
    request: Request | None = None,
    action: str = "kb.chunk.get",
) -> dict[str, Any]:
    row = _load_chunk_row(chunk_id)
    owner_id = str(row.get("document_created_by") or "")
    if owner_id != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="chunk",
                resource_id=chunk_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "chunk is outside your scope")
    return row


def serialize_chunk(row: dict[str, Any]) -> dict[str, Any]:
    signal_scores = {
        "disabled": 1.0 if bool(row.get("disabled")) else 0.0,
    }
    return {
        "id": str(row.get("id") or ""),
        "chunk_id": str(row.get("id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "base_id": str(row.get("base_id") or ""),
        "section_id": str(row.get("section_id") or ""),
        "section_index": int(row.get("section_index") or 0),
        "chunk_index": int(row.get("chunk_index") or 0),
        "section_title": str(row.get("section_title") or ""),
        "document_title": str(row.get("document_title") or ""),
        "text_content": str(row.get("text_content") or ""),
        "char_start": int(row.get("char_start") or 0),
        "char_end": int(row.get("char_end") or 0),
        "source_kind": str(row.get("source_kind") or "text"),
        "page_number": int(row["page_number"]) if row.get("page_number") is not None else None,
        "asset_id": str(row.get("asset_id") or ""),
        "disabled": bool(row.get("disabled")),
        "disabled_reason": str(row.get("disabled_reason") or ""),
        "manual_note": str(row.get("manual_note") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "updated_at": row.get("updated_at"),
        "signal_scores": signal_scores,
    }


def list_document_chunks(
    document_id: str,
    *,
    user: CurrentUser,
    request: Request,
    include_disabled: bool = True,
) -> list[dict[str, Any]]:
    load_document(document_id, user=user, request=request, action="kb.document.chunks")
    clauses = ["chunks.document_id = %s"]
    params: list[Any] = [document_id]
    if not include_disabled:
        clauses.append("chunks.disabled = FALSE")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    chunks.*,
                    sections.title AS section_title,
                    documents.base_id::text AS base_id,
                    documents.file_name AS document_title
                FROM kb_chunks chunks
                JOIN kb_sections sections ON sections.id = chunks.section_id
                JOIN kb_documents documents ON documents.id = chunks.document_id
                WHERE {" AND ".join(clauses)}
                ORDER BY chunks.section_index ASC, chunks.chunk_index ASC
                """,
                tuple(params),
            )
            rows = cur.fetchall()
    return [serialize_chunk(row) for row in rows]


def _renumber_section_chunks(cur, section_id: str, *, base_start: int) -> None:
    cur.execute(
        """
        SELECT id::text, text_content
        FROM kb_chunks
        WHERE section_id = %s
        ORDER BY chunk_index ASC
        """,
        (section_id,),
    )
    rows = cur.fetchall()
    updates: list[tuple[int, int, str]] = []
    cursor = int(base_start or 0)
    for row in rows:
        text = str(row.get("text_content") or "")
        char_start = cursor
        char_end = char_start + len(text)
        updates.append((char_start, char_end, str(row.get("id") or "")))
        cursor = char_end + 2
    if updates:
        cur.executemany(
            """
            UPDATE kb_chunks
            SET char_start = %s,
                char_end = %s,
                updated_at = NOW()
            WHERE id = %s::uuid
            """,
            updates,
        )


def _refresh_section_materialized(cur, section_id: str) -> None:
    cur.execute("SELECT title, char_start FROM kb_sections WHERE id = %s", (section_id,))
    section = cur.fetchone()
    if section is None:
        raise_api_error(404, "section_not_found", "section not found")
    base_start = int(section.get("char_start") or 0)
    _renumber_section_chunks(cur, section_id, base_start=base_start)
    cur.execute(
        """
        SELECT text_content, disabled, char_end
        FROM kb_chunks
        WHERE section_id = %s
        ORDER BY chunk_index ASC
        """,
        (section_id,),
    )
    rows = cur.fetchall()
    enabled_text = "\n\n".join(
        str(row.get("text_content") or "").strip()
        for row in rows
        if not bool(row.get("disabled")) and str(row.get("text_content") or "").strip()
    ).strip()
    search_text = _compact_text(f"{section.get('title') or ''} {enabled_text[:1200]}", 1400)
    summary = _compact_text(enabled_text, 180)
    content_hash = _hash_text(enabled_text) if enabled_text else ""
    lexical_terms = build_fts_lexeme_text(str(section.get("title") or ""), summary, enabled_text[:1200])
    section_char_end = int(rows[-1].get("char_end") or base_start) if rows else base_start
    cur.execute(
        """
        UPDATE kb_sections
        SET summary = %s,
            search_text = %s,
            lexical_terms = %s,
            fts_document = to_tsvector('simple', %s),
            content_hash = %s,
            char_end = %s
        WHERE id = %s
        """,
        (summary, search_text, lexical_terms, lexical_terms, content_hash, section_char_end, section_id),
    )


def _refresh_document_stats(cur, document_id: str) -> None:
    cur.execute(
        """
        SELECT
            COUNT(*) AS chunk_total,
            COUNT(*) FILTER (WHERE disabled = FALSE) AS active_chunk_total,
            COUNT(*) FILTER (WHERE disabled = TRUE) AS disabled_chunk_total
        FROM kb_chunks
        WHERE document_id = %s
        """,
        (document_id,),
    )
    chunk_row = cur.fetchone() or {}
    cur.execute("SELECT COUNT(*) AS section_total FROM kb_sections WHERE document_id = %s", (document_id,))
    section_row = cur.fetchone() or {}
    cur.execute("SELECT stats_json FROM kb_documents WHERE id = %s", (document_id,))
    document = cur.fetchone() or {}
    next_stats = dict(document.get("stats_json") or {})
    next_stats["active_chunk_count"] = int(chunk_row.get("active_chunk_total") or 0)
    next_stats["disabled_chunk_count"] = int(chunk_row.get("disabled_chunk_total") or 0)
    next_stats["last_manual_chunk_review_at"] = "now"
    cur.execute(
        """
        UPDATE kb_documents
        SET section_count = %s,
            chunk_count = %s,
            stats_json = %s::jsonb,
            updated_at = NOW()
        WHERE id = %s
        """,
        (
            int(section_row.get("section_total") or 0),
            int(chunk_row.get("chunk_total") or 0),
            to_json(next_stats),
            document_id,
        ),
    )


def _reindex_document(document_id: str) -> dict[str, Any]:
    delete_document_vectors(document_id)
    section_stats = index_document_sections(document_id)
    chunk_stats = index_document_chunks(document_id)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stats_json FROM kb_documents WHERE id = %s", (document_id,))
            row = cur.fetchone() or {}
            next_stats = dict(row.get("stats_json") or {})
            next_stats["vector_index"] = {
                "sections": section_stats,
                "chunks": chunk_stats,
            }
            cur.execute(
                """
                UPDATE kb_documents
                SET stats_json = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (to_json(next_stats), document_id),
            )
        conn.commit()
    return {"sections": section_stats, "chunks": chunk_stats}


def update_chunk(
    chunk_id: str,
    *,
    text_content: str | None,
    disabled: bool | None,
    disabled_reason: str,
    manual_note: str,
    user: CurrentUser,
    request: Request,
) -> dict[str, Any]:
    chunk = load_chunk(chunk_id, user=user, request=request, action="kb.chunk.update")
    next_text = text_content if text_content is not None else str(chunk.get("text_content") or "")
    next_disabled = bool(disabled) if disabled is not None else bool(chunk.get("disabled"))
    next_disabled_reason = disabled_reason if next_disabled else ""
    next_manual_note = manual_note if manual_note else str(chunk.get("manual_note") or "")
    search_text = _normalize_chunk_search_text(str(chunk.get("section_title") or ""), next_text)
    lexical_terms = build_fts_lexeme_text(next_text[:1400])
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_chunks
                SET text_content = %s,
                    search_text = %s,
                    lexical_terms = %s,
                    fts_document = to_tsvector('simple', %s),
                    content_hash = %s,
                    disabled = %s,
                    disabled_reason = %s,
                    manual_note = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    next_text,
                    search_text,
                    lexical_terms,
                    lexical_terms,
                    _hash_text(next_text),
                    next_disabled,
                    next_disabled_reason,
                    next_manual_note,
                    chunk_id,
                ),
            )
            _refresh_section_materialized(cur, str(chunk.get("section_id") or ""))
            _refresh_document_stats(cur, str(chunk.get("document_id") or ""))
        conn.commit()
    vector_index = _reindex_document(str(chunk.get("document_id") or ""))
    audit_event(
        action="kb.chunk.update",
        outcome="success",
        request=request,
        user=user,
        resource_type="chunk",
        resource_id=chunk_id,
        scope="owner" if str(chunk.get("document_created_by") or "") == user.user_id else "managed",
        details={
            "document_id": str(chunk.get("document_id") or ""),
            "disabled": next_disabled,
            "reindexed_chunks": int(((vector_index.get("chunks") or {}).get("indexed") or 0)),
        },
    )
    updated = load_chunk(chunk_id, user=user, request=request, action="kb.chunk.get")
    payload = serialize_chunk(updated)
    payload["vector_index"] = vector_index
    return payload


def split_chunk(
    chunk_id: str,
    *,
    parts: list[str],
    user: CurrentUser,
    request: Request,
) -> dict[str, Any]:
    chunk = load_chunk(chunk_id, user=user, request=request, action="kb.chunk.split")
    section_id = str(chunk.get("section_id") or "")
    document_id = str(chunk.get("document_id") or "")
    original_index = int(chunk.get("chunk_index") or 0)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_chunks
                SET chunk_index = chunk_index + %s
                WHERE section_id = %s
                  AND chunk_index > %s
                """,
                (len(parts) - 1, section_id, original_index),
            )
            first_text = parts[0]
            cur.execute(
                """
                UPDATE kb_chunks
                SET text_content = %s,
                    search_text = %s,
                    lexical_terms = %s,
                    fts_document = to_tsvector('simple', %s),
                    content_hash = %s,
                    disabled = FALSE,
                    disabled_reason = '',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    first_text,
                    _normalize_chunk_search_text(str(chunk.get("section_title") or ""), first_text),
                    build_fts_lexeme_text(first_text[:1400]),
                    build_fts_lexeme_text(first_text[:1400]),
                    _hash_text(first_text),
                    chunk_id,
                ),
            )
            insert_rows: list[tuple[Any, ...]] = []
            for offset, part in enumerate(parts[1:], start=1):
                insert_rows.append(
                    (
                        str(uuid4()),
                        document_id,
                        section_id,
                        int(chunk.get("section_index") or 0),
                        original_index + offset,
                        part,
                        _normalize_chunk_search_text(str(chunk.get("section_title") or ""), part),
                        build_fts_lexeme_text(part[:1400]),
                        build_fts_lexeme_text(part[:1400]),
                        _hash_text(part),
                        0,
                        0,
                        str(chunk.get("source_kind") or "text"),
                        chunk.get("page_number"),
                        chunk.get("asset_id"),
                    )
                )
            if insert_rows:
                cur.executemany(
                    """
                    INSERT INTO kb_chunks (
                        id, document_id, section_id, section_index, chunk_index, text_content,
                        search_text, lexical_terms, fts_document, content_hash, char_start, char_end,
                        source_kind, page_number, asset_id
                    )
                    VALUES (
                        %s::uuid, %s::uuid, %s::uuid, %s, %s, %s,
                        %s, %s, to_tsvector('simple', %s), %s, %s, %s,
                        %s, %s, %s
                    )
                    """,
                    insert_rows,
                )
            _refresh_section_materialized(cur, section_id)
            _refresh_document_stats(cur, document_id)
        conn.commit()
    vector_index = _reindex_document(document_id)
    audit_event(
        action="kb.chunk.split",
        outcome="success",
        request=request,
        user=user,
        resource_type="chunk",
        resource_id=chunk_id,
        scope="owner" if str(chunk.get("document_created_by") or "") == user.user_id else "managed",
        details={"document_id": document_id, "part_count": len(parts)},
    )
    return {
        "document_id": document_id,
        "section_id": section_id,
        "items": list_document_chunks(document_id, user=user, request=request, include_disabled=True),
        "vector_index": vector_index,
    }


def merge_chunks(
    chunk_ids: list[str],
    *,
    separator: str,
    user: CurrentUser,
    request: Request,
) -> dict[str, Any]:
    loaded = [load_chunk(chunk_id, user=user, request=request, action="kb.chunk.merge") for chunk_id in chunk_ids]
    ordered = sorted(loaded, key=lambda row: int(row.get("chunk_index") or 0))
    if len({str(row.get("document_id") or "") for row in ordered}) != 1:
        raise_api_error(400, "chunk_merge_document_conflict", "all chunks must belong to the same document")
    if len({str(row.get("section_id") or "") for row in ordered}) != 1:
        raise_api_error(400, "chunk_merge_section_conflict", "all chunks must belong to the same section")
    indices = [int(row.get("chunk_index") or 0) for row in ordered]
    expected = list(range(indices[0], indices[0] + len(indices)))
    if indices != expected:
        raise_api_error(409, "chunk_merge_requires_contiguous_range", "chunks must be contiguous before merge")
    first = ordered[0]
    merged_text = separator.join(str(row.get("text_content") or "").strip() for row in ordered if str(row.get("text_content") or "").strip()).strip()
    if not merged_text:
        raise_api_error(400, "chunk_merge_empty", "merged chunk text would be empty")
    document_id = str(first.get("document_id") or "")
    section_id = str(first.get("section_id") or "")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_chunks
                SET text_content = %s,
                    search_text = %s,
                    lexical_terms = %s,
                    fts_document = to_tsvector('simple', %s),
                    content_hash = %s,
                    disabled = %s,
                    disabled_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    merged_text,
                    _normalize_chunk_search_text(str(first.get("section_title") or ""), merged_text),
                    build_fts_lexeme_text(merged_text[:1400]),
                    build_fts_lexeme_text(merged_text[:1400]),
                    _hash_text(merged_text),
                    all(bool(row.get("disabled")) for row in ordered),
                    _compact_text(" ".join(str(row.get("disabled_reason") or "") for row in ordered if str(row.get("disabled_reason") or "").strip()), 240)
                    if all(bool(row.get("disabled")) for row in ordered)
                    else "",
                    str(first.get("id") or ""),
                ),
            )
            delete_ids = [str(row.get("id") or "") for row in ordered[1:]]
            if delete_ids:
                cur.execute("DELETE FROM kb_chunks WHERE id = ANY(%s::uuid[])", (delete_ids,))
            cur.execute(
                """
                UPDATE kb_chunks
                SET chunk_index = chunk_index - %s,
                    updated_at = NOW()
                WHERE section_id = %s
                  AND chunk_index > %s
                """,
                (len(ordered) - 1, section_id, indices[-1]),
            )
            _refresh_section_materialized(cur, section_id)
            _refresh_document_stats(cur, document_id)
        conn.commit()
    vector_index = _reindex_document(document_id)
    audit_event(
        action="kb.chunk.merge",
        outcome="success",
        request=request,
        user=user,
        resource_type="document",
        resource_id=document_id,
        scope="owner" if str(first.get("document_created_by") or "") == user.user_id else "managed",
        details={"chunk_count": len(ordered), "section_id": section_id},
    )
    return {
        "document_id": document_id,
        "section_id": section_id,
        "merged_chunk_id": str(first.get("id") or ""),
        "items": list_document_chunks(document_id, user=user, request=request, include_disabled=True),
        "vector_index": vector_index,
    }

