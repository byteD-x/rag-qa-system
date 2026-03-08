from __future__ import annotations

import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.embeddings import EMBEDDING_DIM, embed_texts, load_embedding_settings, stable_content_key, vector_literal
from shared.logging import setup_logging
from shared.text_search import build_fts_lexeme_text

from .parsing import AliasUnit, ChapterUnit, EventDigest, PassageUnit, SceneUnit
from .runtime import BLOB_ROOT, db, ensure_runtime, storage
from .streaming_ingest import (
    _update_alias_counter,
    _update_relation_counter,
    build_event_digest,
    build_passage_units,
    build_scene_units,
    build_summary_nodes,
    detect_heading_strategy,
    iter_chapter_blocks,
    summarize_text,
    text_hash,
)


logger = setup_logging("novel-worker")
POLL_SECONDS = float(os.getenv("NOVEL_WORKER_POLL_SECONDS", "2"))
CHAPTER_BATCH_SIZE = int(os.getenv("NOVEL_CHAPTER_BATCH_SIZE", "10"))
EMBEDDING_SETTINGS = load_embedding_settings()


def run_forever() -> None:
    ensure_runtime()
    logger.info("novel worker started poll_seconds=%s", POLL_SECONDS)
    while True:
        job = _claim_next_job()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            _process_job(job)
        except Exception as exc:  # pragma: no cover - recovery path
            logger.exception("novel ingest job failed job_id=%s", job["id"])
            _mark_job_failed(str(job["id"]), str(job["document_id"]), str(exc))


def _claim_next_job() -> dict[str, Any] | None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT id
                    FROM novel_ingest_jobs
                    WHERE status IN ('queued', 'retry')
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE novel_ingest_jobs AS jobs
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
    trace_id = f"novel-job-{job['id']}"
    document_id = str(job["document_id"])
    document = _load_document(document_id)
    target_dir = BLOB_ROOT / document_id
    target_dir.mkdir(parents=True, exist_ok=True)
    source_path = target_dir / (document.get("file_name") or "source.txt")

    storage.download_file(str(document["storage_key"]), source_path)
    _append_event(document_id, "uploaded", "object storage download complete", {"trace_id": trace_id})
    _update_job(str(job["id"]), phase="parsing_fast", checkpoint={"downloaded": True})
    _update_document(document_id, status="parsing_fast", enhancement_status="fts_pending")

    parse_started = time.perf_counter()
    stats = _index_txt_document(document_id=document_id, path=source_path)
    stats["parse_ms"] = round((time.perf_counter() - parse_started) * 1000.0, 3)
    _update_document(
        document_id,
        status="fast_index_ready",
        query_ready=True,
        enhancement_status="fts_only",
        query_ready_at=True,
        chapter_count=stats["chapter_count"],
        scene_count=stats["scene_count"],
        passage_count=stats["passage_count"],
        query_ready_until_chapter=stats["chapter_count"],
        stats=stats,
    )
    _append_event(
        document_id,
        "fast_index_ready",
        "chapter/scene/passage lexical index ready",
        {"trace_id": trace_id, **stats},
    )
    _update_job(
        str(job["id"]),
        phase="fast_index_ready",
        query_ready=True,
        enhancement_status="fts_only",
        checkpoint=stats,
    )

    summary_started = time.perf_counter()
    relation_stats = _build_summary_and_relations(document_id)
    summary_embed_stats = _embed_rows(
        document_id=document_id,
        table_name="novel_summary_nodes",
        id_column="id",
        text_column="summary",
        hash_column=None,
    )
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
        "summary tree ready",
        {
            "trace_id": trace_id,
            "summary_ms": round((time.perf_counter() - summary_started) * 1000.0, 3),
            **relation_stats,
            "embedding_cache": summary_embed_stats,
        },
    )
    _update_job(
        str(job["id"]),
        phase="hybrid_ready",
        query_ready=True,
        enhancement_status="summary_vectors_ready",
    )

    chunk_embed_started = time.perf_counter()
    chapter_embed_stats = _embed_rows(
        document_id=document_id,
        table_name="novel_chapters",
        id_column="id",
        text_column="summary",
        hash_column="content_hash",
    )
    event_embed_stats = _embed_rows(
        document_id=document_id,
        table_name="novel_event_digests",
        id_column="id",
        text_column="what_text",
        hash_column="content_hash",
    )
    passage_embed_stats = _embed_rows(
        document_id=document_id,
        table_name="novel_passages",
        id_column="id",
        text_column="text_content",
        hash_column="content_hash",
    )
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
        "passage vectors and relation graph ready",
        {
            "trace_id": trace_id,
            "chunk_embed_ms": round((time.perf_counter() - chunk_embed_started) * 1000.0, 3),
            "chapter_embedding_cache": chapter_embed_stats,
            "event_embedding_cache": event_embed_stats,
            "passage_embedding_cache": passage_embed_stats,
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
            cur.execute("SELECT * FROM novel_documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"novel document not found: {document_id}")
    return row


def _index_txt_document(*, document_id: str, path: Path) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM novel_relation_edges WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_summary_nodes WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_aliases WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_event_digests WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_passages WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_scenes WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM novel_chapters WHERE document_id = %s", (document_id,))
        conn.commit()

    all_chapters: list[ChapterUnit] = []
    strategy_counts: Counter[str] = Counter()
    alias_counter: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    relation_counter: Counter[tuple[str, str]] = Counter()
    relation_support: dict[tuple[str, str], list[dict[str, object]]] = {}

    chapter_batch: list[ChapterUnit] = []
    scene_batch: list[SceneUnit] = []
    passage_batch: list[PassageUnit] = []
    digest_batch: list[EventDigest] = []

    chapter_count = 0
    scene_count = 0
    passage_count = 0
    query_opened = False

    for chapter_index, block in enumerate(iter_chapter_blocks(path), start=1):
        strategy_counts[block.strategy] += 1
        chapter = ChapterUnit(
            id=str(uuid4()),
            chapter_index=chapter_index,
            chapter_number=_extract_chapter_number_from_title(block.title, chapter_index),
            title=block.title or f"Chapter {chapter_index}",
            summary=summarize_text(block.body, 220),
            text=block.body,
            char_start=block.char_start,
            char_end=block.char_start + len(block.body),
        )
        all_chapters.append(chapter)
        chapter_batch.append(chapter)
        chapter_count += 1
        _update_alias_counter(alias_counter, first_seen, chapter.chapter_index, chapter.title)

        chapter_scenes = build_scene_units(chapter)
        scene_batch.extend(chapter_scenes)
        scene_count += len(chapter_scenes)
        for scene in chapter_scenes:
            digest = build_event_digest(scene)
            digest_batch.append(digest)
            _update_alias_counter(alias_counter, first_seen, chapter.chapter_index, scene.text[:500])
            _update_relation_counter(
                relation_counter,
                relation_support,
                chapter.chapter_index,
                scene.scene_index,
                scene.text,
            )
            scene_passages = build_passage_units(scene)
            passage_batch.extend(scene_passages)
            passage_count += len(scene_passages)

        if chapter_index % CHAPTER_BATCH_SIZE == 0:
            _flush_batches(document_id, chapter_batch, scene_batch, passage_batch, digest_batch)
            chapter_batch = []
            scene_batch = []
            passage_batch = []
            digest_batch = []
            _update_document(
                document_id,
                query_ready=True,
                query_ready_at=True,
                query_ready_until_chapter=chapter_index,
                chapter_count=chapter_count,
                scene_count=scene_count,
                passage_count=passage_count,
            )
            _update_job(
                _job_id_for_document(document_id),
                checkpoint={
                    "chapter_count": chapter_count,
                    "scene_count": scene_count,
                    "passage_count": passage_count,
                    "query_ready_until_chapter": chapter_index,
                },
            )
            if not query_opened:
                query_opened = True
                _append_event(document_id, "query_window_open", f"queryable through chapter {chapter_index}")

    if chapter_batch or scene_batch or passage_batch or digest_batch:
        _flush_batches(document_id, chapter_batch, scene_batch, passage_batch, digest_batch)
        _update_document(
            document_id,
            query_ready=True,
            query_ready_at=True,
            query_ready_until_chapter=chapter_count,
            chapter_count=chapter_count,
            scene_count=scene_count,
            passage_count=passage_count,
        )
        if not query_opened:
            _append_event(document_id, "query_window_open", f"queryable through chapter {chapter_count}")

    _insert_aliases(
        document_id,
        [
            AliasUnit(alias=name, canonical=name, kind="entity", first_chapter_index=first_seen[name])
            for name, count in alias_counter.most_common(120)
            if count >= 4
        ],
    )
    _insert_relation_edges(
        document_id,
        relation_counter=relation_counter,
        relation_support=relation_support,
    )

    return {
        "chapter_count": chapter_count,
        "scene_count": scene_count,
        "passage_count": passage_count,
        "alias_count": sum(1 for count in alias_counter.values() if count >= 4),
        "relation_edge_count": sum(1 for count in relation_counter.values() if count >= 2),
        "heading_strategy_counts": dict(strategy_counts),
        "chapter_preview": [chapter.title for chapter in all_chapters[:10]],
    }


def _build_summary_and_relations(document_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM novel_chapters
                WHERE document_id = %s
                ORDER BY chapter_index ASC
                """,
                (document_id,),
            )
            chapters = cur.fetchall()
        conn.commit()

    chapter_units = [
        ChapterUnit(
            id=str(item["id"]),
            chapter_index=int(item["chapter_index"]),
            chapter_number=int(item["chapter_number"]),
            title=str(item["title"]),
            summary=str(item["summary"]),
            text="",
            char_start=int(item["char_start"]),
            char_end=int(item["char_end"]),
        )
        for item in chapters
    ]
    nodes = build_summary_nodes(chapter_units)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM novel_summary_nodes WHERE document_id = %s", (document_id,))
            cur.executemany(
                """
                INSERT INTO novel_summary_nodes (
                    id, document_id, node_level, node_key, title, summary,
                    source_chapter_from, source_chapter_to, lexical_terms, fts_document
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, to_tsvector('simple', %s)
                )
                """,
                [
                    (
                        node["id"],
                        document_id,
                        node["node_level"],
                        node["node_key"],
                        node["title"],
                        node["summary"],
                        node["source_chapter_from"],
                        node["source_chapter_to"],
                        build_fts_lexeme_text(str(node["title"]), str(node["summary"])),
                        build_fts_lexeme_text(str(node["title"]), str(node["summary"])),
                    )
                    for node in nodes
                ],
            )
        conn.commit()
    return {"summary_node_count": len(nodes)}


def _flush_batches(
    document_id: str,
    chapters: list[ChapterUnit],
    scenes: list[SceneUnit],
    passages: list[PassageUnit],
    digests: list[EventDigest],
) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            _insert_chapters(cur, document_id, chapters)
            _insert_scenes(cur, document_id, scenes)
            _insert_passages(cur, document_id, passages)
            _insert_event_digests(cur, document_id, digests)
        conn.commit()


def _insert_chapters(cur, document_id: str, chapters: list[ChapterUnit]) -> None:
    if not chapters:
        return
    cur.executemany(
        """
        INSERT INTO novel_chapters (
            id, document_id, chapter_index, chapter_number, title, summary,
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
                item.chapter_index,
                item.chapter_number,
                item.title,
                item.summary,
                item.summary,
                build_fts_lexeme_text(item.title, item.summary),
                build_fts_lexeme_text(item.title, item.summary),
                text_hash(item.summary or item.title),
                item.char_start,
                item.char_end,
            )
            for item in chapters
        ],
    )


def _insert_scenes(cur, document_id: str, scenes: list[SceneUnit]) -> None:
    if not scenes:
        return
    cur.executemany(
        """
        INSERT INTO novel_scenes (
            id, document_id, chapter_id, chapter_index, scene_index, title, summary,
            search_text, lexical_terms, fts_document, content_hash, char_start, char_end
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, to_tsvector('simple', %s), %s, %s, %s
        )
        """,
        [
            (
                item.id,
                document_id,
                item.chapter_id,
                item.chapter_index,
                item.scene_index,
                item.title,
                item.summary,
                item.search_text,
                build_fts_lexeme_text(item.title, item.summary, item.text[:1200]),
                build_fts_lexeme_text(item.title, item.summary, item.text[:1200]),
                text_hash(item.text),
                item.char_start,
                item.char_end,
            )
            for item in scenes
        ],
    )


def _insert_passages(cur, document_id: str, passages: list[PassageUnit]) -> None:
    if not passages:
        return
    cur.executemany(
        """
        INSERT INTO novel_passages (
            id, document_id, chapter_id, scene_id, chapter_index, scene_index, passage_index,
            text_content, search_text, lexical_terms, fts_document, content_hash, char_start, char_end
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, to_tsvector('simple', %s), %s, %s, %s
        )
        """,
        [
            (
                item.id,
                document_id,
                item.chapter_id,
                item.scene_id,
                item.chapter_index,
                item.scene_index,
                item.passage_index,
                item.text,
                item.search_text,
                build_fts_lexeme_text(item.text[:1400]),
                build_fts_lexeme_text(item.text[:1400]),
                text_hash(item.text),
                item.char_start,
                item.char_end,
            )
            for item in passages
        ],
    )


def _insert_event_digests(cur, document_id: str, digests: list[EventDigest]) -> None:
    if not digests:
        return
    cur.executemany(
        """
        INSERT INTO novel_event_digests (
            id, document_id, chapter_id, scene_id, chapter_index, scene_index,
            who_text, where_text, what_text, result_text, search_text,
            lexical_terms, fts_document, content_hash
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, to_tsvector('simple', %s), %s
        )
        """,
        [
            (
                item.id,
                document_id,
                item.chapter_id,
                item.scene_id,
                item.chapter_index,
                item.scene_index,
                item.who_text,
                item.where_text,
                item.what_text,
                item.result_text,
                item.search_text,
                build_fts_lexeme_text(item.who_text, item.where_text, item.what_text, item.result_text),
                build_fts_lexeme_text(item.who_text, item.where_text, item.what_text, item.result_text),
                text_hash(item.what_text + item.result_text),
            )
            for item in digests
        ],
    )


def _insert_aliases(document_id: str, aliases: list[AliasUnit]) -> None:
    if not aliases:
        return
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO novel_aliases (document_id, alias, canonical, kind, first_chapter_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        document_id,
                        item.alias,
                        item.canonical,
                        item.kind,
                        item.first_chapter_index,
                    )
                    for item in aliases
                ],
            )
        conn.commit()


def _insert_relation_edges(
    document_id: str,
    *,
    relation_counter: Counter[tuple[str, str]],
    relation_support: dict[tuple[str, str], list[dict[str, object]]],
) -> None:
    edges = [
        (
            str(uuid4()),
            document_id,
            pair[0],
            pair[1],
            f"{pair[0]} and {pair[1]} co-occur across scenes",
            _to_json(relation_support.get(pair, [])[:8]),
        )
        for pair, count in relation_counter.most_common(100)
        if count >= 2
    ]
    if not edges:
        return
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO novel_relation_edges (id, document_id, entity_a, entity_b, relation_summary, support_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                edges,
            )
        conn.commit()


def _embed_rows(
    *,
    document_id: str,
    table_name: str,
    id_column: str,
    text_column: str,
    hash_column: str | None,
) -> dict[str, Any]:
    hash_sql = hash_column if hash_column else f"md5({text_column})"
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {id_column}::text AS row_id, {text_column} AS row_text, {hash_sql} AS content_hash
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
            cache_values[item[0]] = vectors[index]

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
                FROM novel_embedding_cache
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
                INSERT INTO novel_embedding_cache (cache_key, provider, model, content_hash, embedding)
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
                UPDATE novel_ingest_jobs
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
                FROM novel_ingest_jobs
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
    query_ready_until_chapter: int | None = None,
    chapter_count: int | None = None,
    scene_count: int | None = None,
    passage_count: int | None = None,
    stats: dict[str, Any] | None = None,
) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE novel_documents
                SET status = COALESCE(%s, status),
                    query_ready = COALESCE(%s, query_ready),
                    enhancement_status = COALESCE(%s, enhancement_status),
                    query_ready_at = CASE WHEN %s THEN COALESCE(query_ready_at, NOW()) ELSE query_ready_at END,
                    hybrid_ready_at = CASE WHEN %s THEN COALESCE(hybrid_ready_at, NOW()) ELSE hybrid_ready_at END,
                    ready_at = CASE WHEN %s THEN COALESCE(ready_at, NOW()) ELSE ready_at END,
                    query_ready_until_chapter = COALESCE(%s, query_ready_until_chapter),
                    chapter_count = COALESCE(%s, chapter_count),
                    scene_count = COALESCE(%s, scene_count),
                    passage_count = COALESCE(%s, passage_count),
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
                    query_ready_until_chapter,
                    chapter_count,
                    scene_count,
                    passage_count,
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
                INSERT INTO novel_document_events (document_id, stage, message, details_json)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (document_id, stage, message, _to_json(details)),
            )
        conn.commit()


def _mark_job_failed(job_id: str, document_id: str, message: str) -> None:
    _update_job(job_id, status="failed", phase="failed", checkpoint={"error": message}, finished=True)
    _update_document(document_id, status="failed", enhancement_status="failed")
    _append_event(document_id, "failed", message)


def _extract_chapter_number_from_title(title: str, fallback: int) -> int:
    match = re.search(r"第\s*([0-9]+)\s*[章节卷回部篇]", title)
    if match:
        return int(match.group(1))
    return fallback


def _to_json(data: dict[str, Any] | list[dict[str, Any]] | None) -> str:
    import json

    return json.dumps(data or {}, ensure_ascii=False)


if __name__ == "__main__":
    run_forever()
