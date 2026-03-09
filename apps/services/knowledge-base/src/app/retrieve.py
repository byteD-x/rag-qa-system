from __future__ import annotations

import time
from typing import Any

from shared.embeddings import embed_query_text, vector_literal
from shared.logging import setup_logging
from shared.query_rewrite import rewrite_query
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath, RetrievalResult, RetrievalStats, weighted_rrf
from shared.text_search import build_simple_tsquery

from .query import compact_quote
from .runtime import db


logger = setup_logging("kb-retrieve")
FUSION_WEIGHTS = {
    "structure": 1.3,
    "fts": 1.0,
    "vector": 0.9,
}


def retrieve_kb_evidence(
    *,
    base_id: str,
    question: str,
    document_ids: list[str] | None = None,
    limit: int = 8,
) -> list[EvidenceBlock]:
    return retrieve_kb_result(
        base_id=base_id,
        question=question,
        document_ids=document_ids,
        limit=limit,
    ).items


def retrieve_kb_result(
    *,
    base_id: str,
    question: str,
    document_ids: list[str] | None = None,
    limit: int = 8,
) -> RetrievalResult:
    """Retrieve KB evidence blocks with structure, FTS and vector fusion."""
    started = time.perf_counter()
    doc_ids = _resolve_document_ids(base_id=base_id, document_ids=document_ids or [])
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
    query_vector_literal, degraded_signals, warnings = _build_query_vector_literal(rewrite.retrieval_query)

    with db.connect() as conn:
        with conn.cursor() as cur:
            structure_rows: list[dict[str, Any]] = []
            if question.strip():
                cur.execute(
                    """
                    SELECT
                        c.id AS unit_id,
                        c.document_id,
                        d.file_name AS document_title,
                        s.title AS section_title,
                        c.char_start,
                        c.char_end,
                        c.text_content,
                        (
                            CASE WHEN lower(s.title) = lower(%s) THEN 8 ELSE 0 END
                            + CASE WHEN lower(s.title) LIKE lower(%s) THEN 4 ELSE 0 END
                            + CASE WHEN position(lower(%s) in lower(c.text_content)) > 0 THEN 2 ELSE 0 END
                        ) AS structure_score
                    FROM kb_chunks c
                    JOIN kb_sections s ON s.id = c.section_id
                    JOIN kb_documents d ON d.id = c.document_id
                    WHERE d.base_id = %s
                      AND d.query_ready = TRUE
                      AND c.document_id = ANY(%s::uuid[])
                      AND (
                          lower(s.title) = lower(%s)
                          OR lower(s.title) LIKE lower(%s)
                          OR position(lower(%s) in lower(c.text_content)) > 0
                      )
                    ORDER BY structure_score DESC, c.section_index ASC, c.chunk_index ASC
                    LIMIT 20
                    """,
                    (
                        rewrite.focus_query or question,
                        f"%{(rewrite.focus_query or question).strip()}%",
                        rewrite.focus_query or question,
                        base_id,
                        doc_ids,
                        rewrite.focus_query or question,
                        f"%{(rewrite.focus_query or question).strip()}%",
                        rewrite.focus_query or question,
                    ),
                )
                structure_rows = cur.fetchall()
            _merge_rows(results, signal_lists, structure_rows, "structure", "structure_score")

            fts_rows: list[dict[str, Any]] = []
            if tsquery:
                cur.execute(
                    """
                    WITH query AS (
                        SELECT to_tsquery('simple', %s) AS tsq
                    )
                    SELECT
                        c.id AS unit_id,
                        c.document_id,
                        d.file_name AS document_title,
                        s.title AS section_title,
                        c.char_start,
                        c.char_end,
                        c.text_content,
                        ts_rank_cd(c.fts_document, query.tsq) AS fts_score
                    FROM kb_chunks c
                    JOIN kb_sections s ON s.id = c.section_id
                    JOIN kb_documents d ON d.id = c.document_id
                    JOIN query ON TRUE
                    WHERE d.base_id = %s
                      AND d.query_ready = TRUE
                      AND c.document_id = ANY(%s::uuid[])
                      AND c.fts_document @@ query.tsq
                    ORDER BY fts_score DESC, c.section_index ASC, c.chunk_index ASC
                    LIMIT 80
                    """,
                    (tsquery, base_id, doc_ids),
                )
                fts_rows = cur.fetchall()
            _merge_rows(results, signal_lists, fts_rows, "fts", "fts_score")

            vector_rows: list[dict[str, Any]] = []
            if query_vector_literal:
                cur.execute(
                    """
                    SELECT
                        c.id AS unit_id,
                        c.document_id,
                        d.file_name AS document_title,
                        s.title AS section_title,
                        c.char_start,
                        c.char_end,
                        c.text_content,
                        1 - (c.embedding <=> %s::vector) AS vector_score
                    FROM kb_chunks c
                    JOIN kb_sections s ON s.id = c.section_id
                    JOIN kb_documents d ON d.id = c.document_id
                    WHERE d.base_id = %s
                      AND d.query_ready = TRUE
                      AND c.document_id = ANY(%s::uuid[])
                      AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT 40
                    """,
                    (query_vector_literal, base_id, doc_ids, query_vector_literal),
                )
                vector_rows = cur.fetchall()
            _merge_rows(results, signal_lists, vector_rows, "vector", "vector_score")

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
        degraded_signals=degraded_signals,
        warnings=warnings,
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


def _build_query_vector_literal(query: str) -> tuple[str, list[str], list[str]]:
    cleaned = query.strip()
    if not cleaned:
        return "", [], []
    try:
        return vector_literal(embed_query_text(cleaned)), [], []
    except Exception:
        logger.warning("vector retrieval degraded because query embedding generation failed", exc_info=True)
        return "", ["vector"], ["vector retrieval disabled because query embedding generation failed"]


def _resolve_document_ids(*, base_id: str, document_ids: list[str]) -> list[str]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            if document_ids:
                cur.execute(
                    """
                    SELECT id::text
                    FROM kb_documents
                    WHERE base_id = %s
                      AND id = ANY(%s::uuid[])
                      AND query_ready = TRUE
                    ORDER BY created_at DESC
                    """,
                    (base_id, document_ids),
                )
            else:
                cur.execute(
                    """
                    SELECT id::text
                    FROM kb_documents
                    WHERE base_id = %s
                      AND query_ready = TRUE
                    ORDER BY created_at DESC
                    """,
                    (base_id,),
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
        results[unit_id] = EvidenceBlock(
            unit_id=unit_id,
            document_id=str(row["document_id"]),
            document_title=str(row.get("document_title") or ""),
            section_title=str(row.get("section_title") or ""),
            char_range=f"{row.get('char_start', 0)}-{row.get('char_end', 0)}",
            quote=compact_quote(str(row.get("text_content") or ""), 180),
            raw_text=str(row.get("text_content") or ""),
            corpus_type="kb",
            signal_scores=signal_scores,
        )


def _rank_of(items: list[str], unit_id: str) -> int | None:
    try:
        return items.index(unit_id) + 1
    except ValueError:
        return None
