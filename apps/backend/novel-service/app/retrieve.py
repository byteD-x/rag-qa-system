from __future__ import annotations

import re
import time
from typing import Any

from shared.embeddings import embed_texts, vector_literal
from shared.query_rewrite import rewrite_query
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath, RetrievalResult, RetrievalStats, weighted_rrf
from shared.text_search import build_simple_tsquery

from .query import compact_quote, extract_entity_hint
from .runtime import db


FUSION_WEIGHTS = {
    "structure": 1.3,
    "fts": 1.0,
    "vector": 0.9,
}


def retrieve_novel_evidence(
    *,
    library_id: str,
    question: str,
    document_ids: list[str] | None = None,
    limit: int = 8,
) -> list[EvidenceBlock]:
    return retrieve_novel_result(
        library_id=library_id,
        question=question,
        document_ids=document_ids,
        limit=limit,
    ).items


def retrieve_novel_result(
    *,
    library_id: str,
    question: str,
    document_ids: list[str] | None = None,
    limit: int = 8,
) -> RetrievalResult:
    """Retrieve novel evidence blocks with structure, FTS and vector fusion."""
    started = time.perf_counter()
    doc_ids = _resolve_document_ids(library_id=library_id, document_ids=document_ids or [])
    rewrite = rewrite_query(question)
    if not doc_ids:
        return RetrievalResult(
            items=[],
            stats=RetrievalStats(
                original_query=rewrite.original_query,
                rewritten_query=rewrite.retrieval_query,
                focus_query=rewrite.focus_query,
                rewrite_tags=list(rewrite.strategy_tags),
                expansion_terms=list(rewrite.expansion_terms),
                retrieval_ms=round((time.perf_counter() - started) * 1000.0, 3),
            ),
        )

    results: dict[str, EvidenceBlock] = {}
    signal_lists: dict[str, list[str]] = {}
    tsquery = build_simple_tsquery(rewrite.retrieval_query)
    query_vector_literal = vector_literal(embed_texts([rewrite.retrieval_query])[0]) if rewrite.retrieval_query else ""
    entity_hint = extract_entity_hint(rewrite.focus_query or question)
    chapter_number = _extract_question_chapter_number(question)

    with db.connect() as conn:
        with conn.cursor() as cur:
            if chapter_number > 0:
                cur.execute(
                    """
                    SELECT
                        p.id AS unit_id,
                        p.document_id,
                        d.title AS document_title,
                        c.title AS chapter_title,
                        p.scene_index,
                        p.char_start,
                        p.char_end,
                        p.text_content,
                        8.0 AS structure_score
                    FROM novel_passages p
                    JOIN novel_chapters c ON c.id = p.chapter_id
                    JOIN novel_documents d ON d.id = p.document_id
                    WHERE d.library_id = %s
                      AND d.query_ready = TRUE
                      AND p.document_id = ANY(%s::uuid[])
                      AND c.chapter_number = %s
                    ORDER BY p.scene_index ASC, p.passage_index ASC
                    LIMIT 20
                    """,
                    (library_id, doc_ids, chapter_number),
                )
                _merge_rows(results, signal_lists, cur.fetchall(), "structure", "structure_score")

            if entity_hint:
                cur.execute(
                    """
                    SELECT
                        p.id AS unit_id,
                        p.document_id,
                        d.title AS document_title,
                        c.title AS chapter_title,
                        p.scene_index,
                        p.char_start,
                        p.char_end,
                        p.text_content,
                        6.0 AS structure_score
                    FROM novel_passages p
                    JOIN novel_documents d ON d.id = p.document_id
                    JOIN novel_chapters c ON c.id = p.chapter_id
                    JOIN novel_aliases a ON a.document_id = p.document_id
                    WHERE d.library_id = %s
                      AND d.query_ready = TRUE
                      AND p.document_id = ANY(%s::uuid[])
                      AND a.alias = %s
                      AND (position(%s in p.text_content) > 0 OR position(%s in p.search_text) > 0)
                    ORDER BY p.chapter_index ASC, p.scene_index ASC
                    LIMIT 20
                    """,
                    (library_id, doc_ids, entity_hint, entity_hint, entity_hint),
                )
                _merge_rows(results, signal_lists, cur.fetchall(), "structure", "structure_score")

            if tsquery:
                cur.execute(
                    """
                    WITH query AS (
                        SELECT to_tsquery('simple', %s) AS tsq
                    )
                    SELECT
                        p.id AS unit_id,
                        p.document_id,
                        d.title AS document_title,
                        c.title AS chapter_title,
                        p.scene_index,
                        p.char_start,
                        p.char_end,
                        p.text_content,
                        ts_rank_cd(p.fts_document, query.tsq) AS fts_score
                    FROM novel_passages p
                    JOIN novel_documents d ON d.id = p.document_id
                    JOIN novel_chapters c ON c.id = p.chapter_id
                    JOIN query ON TRUE
                    WHERE d.library_id = %s
                      AND d.query_ready = TRUE
                      AND p.document_id = ANY(%s::uuid[])
                      AND p.fts_document @@ query.tsq
                    ORDER BY fts_score DESC, p.chapter_index ASC, p.scene_index ASC
                    LIMIT 80
                    """,
                    (tsquery, library_id, doc_ids),
                )
                _merge_rows(results, signal_lists, cur.fetchall(), "fts", "fts_score")

                cur.execute(
                    """
                    WITH query AS (
                        SELECT to_tsquery('simple', %s) AS tsq
                    )
                    SELECT
                        p.id AS unit_id,
                        p.document_id,
                        d.title AS document_title,
                        c.title AS chapter_title,
                        p.scene_index,
                        p.char_start,
                        p.char_end,
                        p.text_content,
                        ts_rank_cd(e.fts_document, query.tsq) + 1 AS structure_score
                    FROM novel_event_digests e
                    JOIN novel_passages p ON p.scene_id = e.scene_id
                    JOIN novel_documents d ON d.id = p.document_id
                    JOIN novel_chapters c ON c.id = p.chapter_id
                    JOIN query ON TRUE
                    WHERE d.library_id = %s
                      AND d.query_ready = TRUE
                      AND p.document_id = ANY(%s::uuid[])
                      AND e.fts_document @@ query.tsq
                    ORDER BY structure_score DESC, p.chapter_index ASC, p.scene_index ASC
                    LIMIT 20
                    """,
                    (tsquery, library_id, doc_ids),
                )
                _merge_rows(results, signal_lists, cur.fetchall(), "structure", "structure_score")

            if query_vector_literal:
                cur.execute(
                    """
                    SELECT
                        p.id AS unit_id,
                        p.document_id,
                        d.title AS document_title,
                        c.title AS chapter_title,
                        p.scene_index,
                        p.char_start,
                        p.char_end,
                        p.text_content,
                        1 - (p.embedding <=> %s::vector) AS vector_score
                    FROM novel_passages p
                    JOIN novel_documents d ON d.id = p.document_id
                    JOIN novel_chapters c ON c.id = p.chapter_id
                    WHERE d.library_id = %s
                      AND d.query_ready = TRUE
                      AND p.document_id = ANY(%s::uuid[])
                      AND p.embedding IS NOT NULL
                    ORDER BY p.embedding <=> %s::vector
                    LIMIT 40
                    """,
                    (query_vector_literal, library_id, doc_ids, query_vector_literal),
                )
                _merge_rows(results, signal_lists, cur.fetchall(), "vector", "vector_score")

    fused = weighted_rrf(signal_lists, weights=FUSION_WEIGHTS)
    ordered = sorted(fused.items(), key=lambda item: item[1], reverse=True)

    fused_blocks: list[EvidenceBlock] = []
    for final_rank, (unit_id, final_score) in enumerate(ordered, start=1):
        block = results[unit_id]
        fused_blocks.append(
            EvidenceBlock(
                unit_id=block.unit_id,
                document_id=block.document_id,
                document_title=block.document_title,
                section_title=block.section_title,
                chapter_title=block.chapter_title,
                scene_index=block.scene_index,
                char_range=block.char_range,
                quote=block.quote,
                raw_text=block.raw_text,
                corpus_id=block.corpus_id,
                corpus_type=block.corpus_type,
                service_type=block.service_type,
                signal_scores=dict(block.signal_scores),
                evidence_path=EvidencePath(
                    structure_hit="structure" in block.signal_scores,
                    fts_rank=_rank_of(signal_lists.get("fts", []), unit_id),
                    vector_rank=_rank_of(signal_lists.get("vector", []), unit_id),
                    final_rank=final_rank,
                    final_score=round(float(final_score), 6),
                ),
            )
        )
    rerank_pool = fused_blocks[: max(limit * 3, 12)]
    reranked_blocks, rerank_debug = rerank_evidence_blocks(
        rewrite.focus_query or question,
        rerank_pool,
        limit=limit,
    )
    debug_by_unit = {item.unit_id: item.score for item in rerank_debug}

    evidence: list[EvidenceBlock] = []
    for final_rank, block in enumerate(reranked_blocks, start=1):
        signal_scores = dict(block.signal_scores)
        if block.unit_id in debug_by_unit:
            signal_scores["rerank"] = debug_by_unit[block.unit_id]
        evidence.append(
            EvidenceBlock(
                unit_id=block.unit_id,
                document_id=block.document_id,
                document_title=block.document_title,
                section_title=block.section_title,
                chapter_title=block.chapter_title,
                scene_index=block.scene_index,
                char_range=block.char_range,
                quote=block.quote,
                raw_text=block.raw_text,
                corpus_id=block.corpus_id,
                corpus_type=block.corpus_type,
                service_type=block.service_type,
                signal_scores=signal_scores,
                evidence_path=EvidencePath(
                    structure_hit=block.evidence_path.structure_hit,
                    fts_rank=block.evidence_path.fts_rank,
                    vector_rank=block.evidence_path.vector_rank,
                    final_rank=final_rank,
                    final_score=block.evidence_path.final_score,
                ),
            )
        )

    stats = RetrievalStats(
        original_query=rewrite.original_query,
        rewritten_query=rewrite.retrieval_query,
        focus_query=rewrite.focus_query,
        rewrite_tags=list(rewrite.strategy_tags),
        expansion_terms=list(rewrite.expansion_terms),
        structure_candidates=len(dict.fromkeys(signal_lists.get("structure", []))),
        fts_candidates=len(dict.fromkeys(signal_lists.get("fts", []))),
        vector_candidates=len(dict.fromkeys(signal_lists.get("vector", []))),
        fused_candidates=len(fused_blocks),
        reranked_candidates=len(rerank_pool),
        selected_candidates=len(evidence),
        retrieval_ms=round((time.perf_counter() - started) * 1000.0, 3),
        rerank_applied=bool(rerank_pool),
    )
    return RetrievalResult(items=evidence, stats=stats)


def _resolve_document_ids(*, library_id: str, document_ids: list[str]) -> list[str]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            if document_ids:
                cur.execute(
                    """
                    SELECT id::text
                    FROM novel_documents
                    WHERE library_id = %s
                      AND id = ANY(%s::uuid[])
                      AND query_ready = TRUE
                    ORDER BY created_at DESC
                    """,
                    (library_id, document_ids),
                )
            else:
                cur.execute(
                    """
                    SELECT id::text
                    FROM novel_documents
                    WHERE library_id = %s
                      AND query_ready = TRUE
                    ORDER BY created_at DESC
                    """,
                    (library_id,),
                )
            return [str(row["id"]) for row in cur.fetchall()]


def _merge_rows(
    results: dict[str, EvidenceBlock],
    signal_lists: dict[str, list[str]],
    rows: list[dict[str, Any]],
    signal_name: str,
    score_key: str,
) -> None:
    signal_lists.setdefault(signal_name, [])
    for row in rows:
        unit_id = str(row["unit_id"])
        signal_lists[signal_name].append(unit_id)
        existing = results.get(unit_id)
        signal_scores = dict(existing.signal_scores) if existing else {}
        signal_scores[signal_name] = round(float(row.get(score_key) or 0), 6)
        chapter_title = str(row.get("chapter_title") or "")
        scene_index = int(row.get("scene_index") or 0)
        results[unit_id] = EvidenceBlock(
            unit_id=unit_id,
            document_id=str(row["document_id"]),
            document_title=str(row.get("document_title") or ""),
            section_title=f"{chapter_title} / Scene {scene_index}" if chapter_title else f"Scene {scene_index}",
            chapter_title=chapter_title,
            scene_index=scene_index,
            char_range=f"{row.get('char_start', 0)}-{row.get('char_end', 0)}",
            quote=compact_quote(str(row.get("text_content") or ""), 180),
            raw_text=str(row.get("text_content") or ""),
            corpus_type="novel",
            signal_scores=signal_scores,
        )


def _extract_question_chapter_number(question: str) -> int:
    match = re.search(r"第\s*([0-9]+)\s*[章节回卷部篇]", question)
    if match:
        return int(match.group(1))
    return 0


def _rank_of(items: list[str], unit_id: str) -> int | None:
    try:
        return items.index(unit_id) + 1
    except ValueError:
        return None
