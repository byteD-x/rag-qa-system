from __future__ import annotations

from dataclasses import dataclass

from .retrieval import EvidenceBlock
from .text_search import normalize_text, score_term_overlap


@dataclass(frozen=True)
class RerankDebug:
    unit_id: str
    score: float


def rerank_evidence_blocks(
    question: str,
    items: list[EvidenceBlock],
    *,
    focus_query: str = "",
    limit: int | None = None,
) -> tuple[list[EvidenceBlock], list[RerankDebug]]:
    if not items:
        return [], []

    primary = (focus_query or question or "").strip()
    ranked = sorted(
        items,
        key=lambda item: _rerank_score(primary, item),
        reverse=True,
    )
    if limit is not None:
        ranked = ranked[:limit]
    debug = [RerankDebug(unit_id=item.unit_id, score=round(_rerank_score(primary, item), 6)) for item in ranked]
    return ranked, debug


def _rerank_score(question: str, item: EvidenceBlock) -> float:
    query = normalize_text(question)
    quote_text = f"{item.document_title} {item.section_title} {item.chapter_title} {item.quote or item.raw_text}"
    lexical = score_term_overlap(query, quote_text)
    title_boost = 0.0
    if query and query in normalize_text(f"{item.section_title} {item.chapter_title}"):
        title_boost += 1.5
    structure_boost = 1.0 if item.signal_scores.get("structure") else 0.0
    fusion_score = float(item.evidence_path.final_score or 0.0)
    return round((fusion_score * 100.0) + lexical + title_boost + structure_boost, 6)
