from __future__ import annotations

from typing import Any

from shared.tracing import current_trace_id

from .query import build_refusal_response, compact_quote, detect_strategy
from .retrieve import retrieve_kb_result


def serialize_evidence(item: Any, *, corpus_id: str) -> dict[str, Any]:
    payload = item.as_dict()
    payload["corpus_id"] = corpus_id
    payload["service_type"] = "kb"
    return payload


def grounded_answer(evidence: list[Any]) -> str:
    first = evidence[0]
    answer = f"最直接的证据来自《{first.document_title}》的 {first.section_title}：{compact_quote(first.raw_text, 130)} [1]"
    if len(evidence) > 1:
        second = evidence[1]
        answer += f"；补充证据见 {second.section_title}：{compact_quote(second.raw_text, 90)} [2]"
    return answer


def build_query_response(*, base_id: str, question: str, document_ids: list[str]) -> dict[str, Any]:
    strategy = detect_strategy(question)
    retrieval = retrieve_kb_result(
        base_id=base_id,
        question=question,
        document_ids=document_ids,
        limit=8,
    )
    evidence = retrieval.items
    if not evidence:
        result = build_refusal_response(strategy=strategy, reason="no_relevant_evidence")
        result["answer_mode"] = "refusal"
        result["evidence_path"] = []
        result["retrieval"] = retrieval.stats.as_dict()
        result["trace_id"] = current_trace_id()
        return result

    top_score = evidence[0].evidence_path.final_score
    strong_items = [item for item in evidence if item.evidence_path.final_score >= 0.02]
    if len(strong_items) >= 2 and top_score >= 0.02:
        answer_mode = "grounded"
        evidence_status = "grounded"
        grounding_score = min(0.95, 0.6 + (len(strong_items) * 0.05) + top_score)
        answer = grounded_answer(evidence[:2])
        refusal_reason = ""
    elif top_score >= 0.01:
        answer_mode = "weak_grounded"
        evidence_status = "partial"
        grounding_score = min(0.7, 0.45 + top_score)
        answer = f"根据当前证据，我只能保守确认：{compact_quote(evidence[0].raw_text, 140)}。现有证据不足以支持更强结论。"
        refusal_reason = "partial_evidence"
    else:
        answer_mode = "refusal"
        evidence_status = "insufficient"
        grounding_score = 0.0
        answer = "当前知识范围内没有足够证据支持可靠回答。"
        refusal_reason = "insufficient_evidence"

    citations = [serialize_evidence(item, corpus_id=f"kb:{base_id}") for item in evidence]
    return {
        "answer": answer,
        "answer_mode": answer_mode,
        "strategy_used": strategy,
        "evidence_status": evidence_status,
        "grounding_score": grounding_score,
        "refusal_reason": refusal_reason,
        "citations": citations,
        "evidence_path": [item["evidence_path"] for item in citations],
        "retrieval": retrieval.stats.as_dict(),
        "trace_id": current_trace_id(),
    }
