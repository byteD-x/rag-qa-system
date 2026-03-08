from __future__ import annotations

import hashlib
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.embeddings import EMBEDDING_DIM, embed_texts, load_embedding_settings, stable_content_key, vector_literal
from shared.logging import setup_logging
from shared.text_search import build_fts_lexeme_text

from .parsing import KBChunk, KBSection, ParsedKB, TXT_HEADING_RE, parse_document
from .runtime import BLOB_ROOT, db, ensure_runtime, storage


logger = setup_logging("kb-worker")
POLL_SECONDS = float(os.getenv("KB_WORKER_POLL_SECONDS", "2"))
SECTION_BATCH_SIZE = int(os.getenv("KB_SECTION_BATCH_SIZE", "50"))
CHUNK_BATCH_SIZE = int(os.getenv("KB_CHUNK_BATCH_SIZE", "500"))
EMBEDDING_SETTINGS = load_embedding_settings()


def run_forever() -> None:
    ensure_runtime()
    logger.info("kb worker started poll_seconds=%s", POLL_SECONDS)
    while True:
        job = _claim_next_job()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            _process_job(job)
        except Exception as exc:  # pragma: no cover - recovery path
            logger.exception("kb ingest job failed job_id=%s", job["id"])
            _mark_job_failed(str(job["id"]), str(job["document_id"]), str(exc))


def _claim_next_job() -> dict[str, Any] | None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT id
                    FROM kb_ingest_jobs
                    WHERE status IN ('queued', 'retry')
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE kb_ingest_jobs AS jobs
                SET status = 'processing',
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW()
                FROM picked
                WHERE jobs.id = picked.id
                RETURNING jobs.*
                """
            )
            row = cur.fetchone()
        conn.commit()
    return row


def _process_job(job: dict[str, Any]) -> None:
    trace_id = f"kb-job-{job['id']}"
    document_id = str(job["document_id"])
    document = _load_document(document_id)
    target_dir = BLOB_ROOT / document_id
    target_dir.mkdir(parents=True, exist_ok=True)
    source_path = target_dir / (document.get("file_name") or "source.txt")

    storage.download_file(str(document["storage_key"]), source_path)
    _append_event(document_id, "uploaded", "object storage download complete", {"trace_id": trace_id})
    _update_job(str(job["id"]), phase="parsing_fast", checkpoint={"downloaded": True})
    _update_document(
        document_id,
        status="parsing_fast",
        query_ready=False,
        enhancement_status="fts_pending",
    )

    parse_started = time.perf_counter()
    if str(document.get("file_type") or "").lower() == "txt":
        stats = _index_txt_document(document_id=document_id, path=source_path)
    else:
        stats = _index_binary_document(document_id=document_id, path=source_path, file_type=str(document["file_type"]))
    stats["parse_ms"] = round((time.perf_counter() - parse_started) * 1000.0, 3)

    _update_document(
        document_id,
        status="fast_index_ready",
        query_ready=True,
        enhancement_status="fts_only",
        query_ready_at=True,
        section_count=stats["section_count"],
        chunk_count=stats["chunk_count"],
        stats=stats,
    )
    _append_event(document_id, "fast_index_ready", "core lexical index ready", {"trace_id": trace_id, **stats})
    _update_job(
        str(job["id"]),
        phase="fast_index_ready",
        query_ready=True,
        enhancement_status="fts_only",
        checkpoint=stats,
    )

    section_embed_started = time.perf_counter()
    section_embed_stats = _embed_sections(document_id)
    _update_document(
        document_id,
        status="hybrid_ready",
        query_ready=True,
        enhancement_status="summary_vectors_ready",
        hybrid_ready_at=True,
    )
    _append_event(
        document_id,
        "hybrid_ready",
        "section embeddings ready",
        {
            "trace_id": trace_id,
            "section_embed_ms": round((time.perf_counter() - section_embed_started) * 1000.0, 3),
            "embedding_cache": section_embed_stats,
        },
    )
    _update_job(
        str(job["id"]),
        phase="hybrid_ready",
        query_ready=True,
        enhancement_status="summary_vectors_ready",
    )

    chunk_embed_started = time.perf_counter()
    chunk_embed_stats = _embed_chunks(document_id)
    _update_document(
        document_id,
        status="ready",
        query_ready=True,
        enhancement_status="chunk_vectors_ready",
        ready_at=True,
    )
    _append_event(
        document_id,
        "ready",
        "chunk embeddings ready",
        {
            "trace_id": trace_id,
            "chunk_embed_ms": round((time.perf_counter() - chunk_embed_started) * 1000.0, 3),
            "embedding_cache": chunk_embed_stats,
        },
    )
    _update_job(
        str(job["id"]),
        status="done",
        phase="ready",
        query_ready=True,
        enhancement_status="chunk_vectors_ready",
        finished=True,
    )


def _load_document(document_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"kb document not found: {document_id}")
    return row


def _index_binary_document(*, document_id: str, path: Path, file_type: str) -> dict[str, Any]:
    parsed = parse_document(path, file_type)
    _replace_document_units(document_id, parsed)
    return {
        "section_count": len(parsed.sections),
        "chunk_count": len(parsed.chunks),
    }


def _index_txt_document(*, document_id: str, path: Path) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kb_chunks WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM kb_sections WHERE document_id = %s", (document_id,))
        conn.commit()

    section_buffer: list[KBSection] = []
    chunk_buffer: list[KBChunk] = []
    section_total = 0
    chunk_total = 0
    query_opened = False

    current_title = "Section 1"
    current_lines: list[str] = []
    section_index = 1
    cursor = 0
    start = 0

    for raw in _iter_text_lines(path):
        stripped = raw.strip()
        is_heading = bool(stripped and TXT_HEADING_RE.match(stripped))
        if is_heading and current_lines:
            section, chunks = _build_section_and_chunks(
                section_index=section_index,
                title=current_title,
                raw_text="".join(current_lines),
                char_start=start,
            )
            if section is not None:
                section_buffer.append(section)
                chunk_buffer.extend(chunks)
                section_total += 1
                chunk_total += len(chunks)
                section_index += 1
            current_title = stripped[:80]
            current_lines = [raw]
            start = cursor
        else:
            if not current_lines and stripped:
                start = cursor
            current_lines.append(raw)
        cursor += len(raw)

        if len(section_buffer) >= SECTION_BATCH_SIZE or len(chunk_buffer) >= CHUNK_BATCH_SIZE:
            _flush_txt_batch(document_id, section_buffer, chunk_buffer)
            if not query_opened and chunk_total > 0:
                query_opened = True
                _update_document(document_id, query_ready=True, query_ready_at=True)
                _append_event(document_id, "query_window_open", f"queryable after {section_total} sections")
            _update_job(
                _job_id_for_document(document_id),
                checkpoint={"section_count": section_total, "chunk_count": chunk_total},
            )
            section_buffer = []
            chunk_buffer = []

    if current_lines:
        section, chunks = _build_section_and_chunks(
            section_index=section_index,
            title=current_title,
            raw_text="".join(current_lines),
            char_start=start,
        )
        if section is not None:
            section_buffer.append(section)
            chunk_buffer.extend(chunks)
            section_total += 1
            chunk_total += len(chunks)

    if section_buffer or chunk_buffer:
        _flush_txt_batch(document_id, section_buffer, chunk_buffer)
        if not query_opened and chunk_total > 0:
            _update_document(document_id, query_ready=True, query_ready_at=True)
            _append_event(document_id, "query_window_open", f"queryable after {section_total} sections")

    return {
        "section_count": section_total,
        "chunk_count": chunk_total,
    }


def _iter_text_lines(path: Path):
    encoding = _detect_text_encoding(path)
    with path.open("r", encoding=encoding, errors="replace") as handle:
        for raw in handle:
            yield raw


def _detect_text_encoding(path: Path) -> str:
    with path.open("rb") as handle:
        sample = handle.read(65536)
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "gb18030", "gbk"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _build_section_and_chunks(
    *,
    section_index: int,
    title: str,
    raw_text: str,
    char_start: int,
) -> tuple[KBSection | None, list[KBChunk]]:
    content = raw_text.strip()
    if not content:
        return None, []
    section_id = str(uuid4())
    summary = _summary(content, 180)
    section = KBSection(
        id=section_id,
        section_index=section_index,
        title=title or f"Section {section_index}",
        summary=summary,
        search_text=" ".join([title, content[:600]]).strip(),
        text=content,
        char_start=char_start,
        char_end=char_start + len(content),
    )

    chunks: list[KBChunk] = []
    cursor = 0
    chunk_index = 1
    while cursor < len(content):
        end = min(cursor + 1000, len(content))
        snippet = content[cursor:end].strip()
        if snippet:
            chunks.append(
                KBChunk(
                    id=str(uuid4()),
                    section_id=section_id,
                    section_index=section_index,
                    chunk_index=chunk_index,
                    text=snippet,
                    search_text=snippet,
                    char_start=char_start + cursor,
                    char_end=char_start + end,
                )
            )
            chunk_index += 1
        if end >= len(content):
            break
        cursor = max(end - 120, cursor + 1)
    return section, chunks


def _flush_txt_batch(document_id: str, sections: list[KBSection], chunks: list[KBChunk]) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            _insert_sections(cur, document_id, sections)
            _insert_chunks(cur, document_id, chunks)
        conn.commit()


def _replace_document_units(document_id: str, parsed: ParsedKB) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kb_chunks WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM kb_sections WHERE document_id = %s", (document_id,))
            _insert_sections(cur, document_id, parsed.sections)
            _insert_chunks(cur, document_id, parsed.chunks)
        conn.commit()


def _insert_sections(cur, document_id: str, sections: list[KBSection]) -> None:
    if not sections:
        return
    cur.executemany(
        """
        INSERT INTO kb_sections (
            id, document_id, section_index, title, summary, search_text,
            lexical_terms, fts_document, content_hash, char_start, char_end
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, to_tsvector('simple', %s), %s, %s, %s
        )
        """,
        [
            (
                item.id,
                document_id,
                item.section_index,
                item.title,
                item.summary,
                item.search_text,
                build_fts_lexeme_text(item.title, item.summary, item.text[:1200]),
                build_fts_lexeme_text(item.title, item.summary, item.text[:1200]),
                _hash_text(item.text),
                item.char_start,
                item.char_end,
            )
            for item in sections
        ],
    )


def _insert_chunks(cur, document_id: str, chunks: list[KBChunk]) -> None:
    if not chunks:
        return
    cur.executemany(
        """
        INSERT INTO kb_chunks (
            id, document_id, section_id, section_index, chunk_index, text_content,
            search_text, lexical_terms, fts_document, content_hash, char_start, char_end
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, to_tsvector('simple', %s), %s, %s, %s
        )
        """,
        [
            (
                item.id,
                document_id,
                item.section_id,
                item.section_index,
                item.chunk_index,
                item.text,
                item.search_text,
                build_fts_lexeme_text(item.text[:1400]),
                build_fts_lexeme_text(item.text[:1400]),
                _hash_text(item.text),
                item.char_start,
                item.char_end,
            )
            for item in chunks
        ],
    )


def _embed_sections(document_id: str) -> dict[str, Any]:
    return _embed_rows(
        document_id=document_id,
        table_name="kb_sections",
        id_column="id",
        text_column="summary",
        hash_column="content_hash",
    )


def _embed_chunks(document_id: str) -> dict[str, Any]:
    return _embed_rows(
        document_id=document_id,
        table_name="kb_chunks",
        id_column="id",
        text_column="text_content",
        hash_column="content_hash",
    )


def _embed_rows(*, document_id: str, table_name: str, id_column: str, text_column: str, hash_column: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {id_column}::text AS row_id, {text_column} AS row_text, {hash_column} AS content_hash
                FROM {table_name}
                WHERE document_id = %s
                  AND embedding IS NULL
                ORDER BY row_id
                """,
                (document_id,),
            )
            rows = cur.fetchall()
        conn.commit()

    if not rows:
        return {"rows": 0, "cache_hits": 0, "cache_misses": 0, "updated": 0}

    cache_values = _load_embedding_cache([str(row["content_hash"]) for row in rows])
    to_compute: list[str] = []
    compute_items: list[tuple[str, str]] = []
    cache_hits = 0
    for row in rows:
        content_hash = str(row["content_hash"])
        cache_key = stable_content_key(content_hash, EMBEDDING_SETTINGS.provider, EMBEDDING_SETTINGS.model, str(EMBEDDING_DIM))
        if cache_key in cache_values:
            cache_hits += 1
            continue
        to_compute.append(str(row["row_text"] or ""))
        compute_items.append((cache_key, content_hash))

    if to_compute:
        vectors = embed_texts(to_compute, settings=EMBEDDING_SETTINGS)
        _store_embedding_cache(compute_items, vectors)
        for index, item in enumerate(compute_items):
            cache_key = item[0]
            cache_values[cache_key] = vectors[index]

    updates: list[tuple[str, str]] = []
    for row in rows:
        content_hash = str(row["content_hash"])
        cache_key = stable_content_key(content_hash, EMBEDDING_SETTINGS.provider, EMBEDDING_SETTINGS.model, str(EMBEDDING_DIM))
        vector = cache_values.get(cache_key)
        if vector is None:
            continue
        updates.append((vector_literal(vector), str(row["row_id"])))

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                f"UPDATE {table_name} SET embedding = %s::vector WHERE {id_column} = %s::uuid",
                updates,
            )
        conn.commit()
    return {
        "rows": len(rows),
        "cache_hits": cache_hits,
        "cache_misses": len(compute_items),
        "updated": len(updates),
    }


def _load_embedding_cache(content_hashes: list[str]) -> dict[str, list[float]]:
    if not content_hashes:
        return {}
    keys = [stable_content_key(content_hash, EMBEDDING_SETTINGS.provider, EMBEDDING_SETTINGS.model, str(EMBEDDING_DIM)) for content_hash in content_hashes]
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cache_key, embedding::text AS embedding_text
                FROM kb_embedding_cache
                WHERE cache_key = ANY(%s::text[])
                """,
                (keys,),
            )
            rows = cur.fetchall()
        conn.commit()
    values: dict[str, list[float]] = {}
    for row in rows:
        values[str(row["cache_key"])] = _parse_vector_text(str(row["embedding_text"]))
    return values


def _store_embedding_cache(items: list[tuple[str, str]], vectors: list[list[float]]) -> None:
    if not items:
        return
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO kb_embedding_cache (cache_key, provider, model, content_hash, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (cache_key) DO NOTHING
                """,
                [
                    (
                        items[index][0],
                        EMBEDDING_SETTINGS.provider,
                        EMBEDDING_SETTINGS.model,
                        items[index][1],
                        vector_literal(vectors[index]),
                    )
                    for index in range(len(items))
                ],
            )
        conn.commit()


def _parse_vector_text(raw: str) -> list[float]:
    cleaned = raw.strip().lstrip("[").rstrip("]")
    if not cleaned:
        return [0.0] * EMBEDDING_DIM
    return [float(item) for item in cleaned.split(",")]


def _update_job(
    job_id: str | None,
    *,
    status: str | None = None,
    phase: str | None = None,
    query_ready: bool | None = None,
    enhancement_status: str | None = None,
    checkpoint: dict[str, Any] | None = None,
    finished: bool = False,
) -> None:
    if not job_id:
        return
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_ingest_jobs
                SET status = COALESCE(%s, status),
                    phase = COALESCE(%s, phase),
                    query_ready = COALESCE(%s, query_ready),
                    enhancement_status = COALESCE(%s, enhancement_status),
                    checkpoint_json = COALESCE(%s::jsonb, checkpoint_json),
                    finished_at = CASE WHEN %s THEN NOW() ELSE finished_at END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    phase,
                    query_ready,
                    enhancement_status,
                    _to_json(checkpoint) if checkpoint is not None else None,
                    finished,
                    job_id,
                ),
            )
        conn.commit()


def _job_id_for_document(document_id: str) -> str | None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text
                FROM kb_ingest_jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
    return str(row["id"]) if row else None


def _update_document(
    document_id: str,
    *,
    status: str | None = None,
    query_ready: bool | None = None,
    enhancement_status: str | None = None,
    query_ready_at: bool = False,
    hybrid_ready_at: bool = False,
    ready_at: bool = False,
    section_count: int | None = None,
    chunk_count: int | None = None,
    stats: dict[str, Any] | None = None,
) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_documents
                SET status = COALESCE(%s, status),
                    query_ready = COALESCE(%s, query_ready),
                    enhancement_status = COALESCE(%s, enhancement_status),
                    query_ready_at = CASE WHEN %s THEN COALESCE(query_ready_at, NOW()) ELSE query_ready_at END,
                    hybrid_ready_at = CASE WHEN %s THEN COALESCE(hybrid_ready_at, NOW()) ELSE hybrid_ready_at END,
                    ready_at = CASE WHEN %s THEN COALESCE(ready_at, NOW()) ELSE ready_at END,
                    section_count = COALESCE(%s, section_count),
                    chunk_count = COALESCE(%s, chunk_count),
                    stats_json = COALESCE(%s::jsonb, stats_json),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    query_ready,
                    enhancement_status,
                    query_ready_at,
                    hybrid_ready_at,
                    ready_at,
                    section_count,
                    chunk_count,
                    _to_json(stats) if stats is not None else None,
                    document_id,
                ),
            )
        conn.commit()


def _append_event(document_id: str, stage: str, message: str, details: dict[str, Any] | None = None) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kb_document_events (document_id, stage, message, details_json)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (document_id, stage, message, _to_json(details)),
            )
        conn.commit()


def _mark_job_failed(job_id: str, document_id: str, message: str) -> None:
    _update_job(job_id, status="failed", phase="failed", checkpoint={"error": message}, finished=True)
    _update_document(document_id, status="failed", enhancement_status="failed")
    _append_event(document_id, "failed", message)


def _summary(text: str, limit: int) -> str:
    compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
    return compact[:limit].strip()


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _to_json(data: dict[str, Any] | None) -> str:
    import json

    return json.dumps(data or {}, ensure_ascii=False)


if __name__ == "__main__":
    run_forever()
