from __future__ import annotations

from shared.embeddings import embed_texts, load_embedding_settings
from shared.grounded_answering import classify_evidence, dedupe_citations, public_citations
from shared.query_rewrite import rewrite_query
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath
from shared.text_encoding import detect_text_encoding_from_bytes
from shared.tracing import current_trace_id, ensure_trace_id, reset_trace_id, set_trace_id, trace_headers


def test_query_rewrite_extracts_entity_and_chapter_focus() -> None:
    plan = rewrite_query("第10章里夏德是谁")
    assert "entity_focus" in plan.strategy_tags
    assert "chapter_focus" in plan.strategy_tags
    assert any("夏德" in term for term in plan.expansion_terms)
    assert "第10章" in plan.retrieval_query


def test_reranker_promotes_exact_match_candidate() -> None:
    weaker = EvidenceBlock(
        unit_id="b",
        document_id="b",
        document_title="doc",
        section_title="其他说明",
        quote="这里提到的是模糊背景。",
        raw_text="这里提到的是模糊背景。",
        signal_scores={"vector": 0.9},
        evidence_path=EvidencePath(final_score=0.03),
    )
    stronger = EvidenceBlock(
        unit_id="a",
        document_id="a",
        document_title="doc",
        section_title="审批签字要求",
        quote="报销审批需经部门负责人、财务审核人与分管领导签字。",
        raw_text="报销审批需经部门负责人、财务审核人与分管领导签字。",
        signal_scores={"fts": 1.2},
        evidence_path=EvidencePath(final_score=0.02),
    )
    ranked, debug = rerank_evidence_blocks("报销审批需要哪些角色签字", [weaker, stronger], focus_query="报销审批 角色 签字")
    assert ranked[0].unit_id == "a"
    assert debug[0].unit_id == "a"


def test_projection_embedding_is_stable_and_dense() -> None:
    settings = load_embedding_settings()
    vectors = embed_texts(["夏德是侦探学徒", "夏德是侦探学徒"], settings=settings)
    assert len(vectors) == 2
    assert vectors[0] == vectors[1]
    assert any(abs(item) > 0 for item in vectors[0])


def test_trace_id_generation_and_headers() -> None:
    trace_id = ensure_trace_id(None, prefix="gateway-")
    headers = trace_headers(trace_id)
    assert trace_id.startswith("gateway-")
    assert headers["X-Trace-Id"] == trace_id
    assert trace_headers("candidate-trace")["X-Trace-Id"] == "candidate-trace"


def test_trace_id_is_cleaned_and_limited() -> None:
    assert ensure_trace_id("  trace id:/unsafe?ok._-  ") == "traceidunsafeok._-"
    assert ensure_trace_id("a" * 120) == "a" * 96


def test_trace_headers_use_current_trace_id_and_reset_context() -> None:
    original_trace_id = current_trace_id()
    trace_context = set_trace_id("context-trace")
    try:
        assert current_trace_id() == "context-trace"
        assert trace_headers() == {"X-Trace-Id": "context-trace"}
    finally:
        reset_trace_id(trace_context)

    assert current_trace_id() == original_trace_id


def test_detect_text_encoding_prefers_utf8_without_bom() -> None:
    sample = "第01章：将死之人\n夏德来到这里。".encode("utf-8")
    assert detect_text_encoding_from_bytes(sample) == "utf-8"


def _evidence(*, unit_id: str, relevance: float, document_id: str = "doc-1", section_title: str = "章节") -> dict:
    return {
        "unit_id": unit_id,
        "document_id": document_id,
        "section_title": section_title,
        "evidence_path": {"relevance": relevance},
    }


def test_classify_evidence_ignores_rrf_final_score() -> None:
    """RRF 相对分不再是判据:两路信号各有一条高分文档时应判拒答,而非 grounded。"""
    evidence = [
        {"unit_id": "a", "document_id": "d1", "section_title": "s1", "evidence_path": {"final_score": 0.0305}},
        {"unit_id": "b", "document_id": "d2", "section_title": "s2", "evidence_path": {"final_score": 0.0289}},
    ]

    answer_mode, evidence_status, grounding_score, refusal_reason = classify_evidence(evidence)

    assert answer_mode == "refusal"
    assert evidence_status == "insufficient"
    assert grounding_score == 0.0
    assert refusal_reason == "insufficient_evidence"


def test_classify_evidence_grounds_on_two_distinct_strong_sections() -> None:
    evidence = [
        _evidence(unit_id="a", relevance=0.78, section_title="年假申请时限"),
        _evidence(unit_id="b", relevance=0.70, section_title="销假要求"),
    ]

    answer_mode, evidence_status, grounding_score, _ = classify_evidence(evidence)

    assert answer_mode == "grounded"
    assert evidence_status == "grounded"
    assert 0.0 < grounding_score <= 0.95


def test_classify_evidence_does_not_double_count_section_and_chunk_granularity() -> None:
    """同一章节的 section / chunk 两个粒度各返回一条,不能凑成「两条强证据」。"""
    evidence = [
        _evidence(unit_id="section-1", relevance=0.78, section_title="年假申请时限"),
        _evidence(unit_id="chunk-1", relevance=0.78, section_title="年假申请时限"),
    ]

    answer_mode, evidence_status, _, refusal_reason = classify_evidence(evidence)

    assert answer_mode == "weak_grounded"
    assert evidence_status == "partial"
    assert refusal_reason == "partial_evidence"


def test_classify_evidence_refuses_when_no_section_reaches_weak_relevance() -> None:
    evidence = [_evidence(unit_id="a", relevance=0.43), _evidence(unit_id="b", relevance=0.37, document_id="d2")]

    answer_mode, evidence_status, _, refusal_reason = classify_evidence(evidence)

    assert answer_mode == "refusal"
    assert evidence_status == "insufficient"
    assert refusal_reason == "insufficient_evidence"


def test_classify_evidence_accepts_strong_rerank_signal_for_known_fact() -> None:
    evidence = [
        {
            "unit_id": "policy-chunk",
            "document_id": "policy",
            "section_title": "报销审批",
            "quote": "超过 1000 RMB 需要部门负责人审批和财务复核。",
            "evidence_path": {"relevance": 0.49},
            "signal_scores": {"rerank": 5.1},
        }
    ]

    answer_mode, evidence_status, _, refusal_reason = classify_evidence(evidence)

    assert answer_mode == "weak_grounded"
    assert evidence_status == "partial"
    assert refusal_reason == "partial_evidence"


def test_dedupe_citations_keeps_best_chunk_per_section() -> None:
    citations = [
        {"unit_id": "section", "document_id": "doc", "version_label": "v1", "section_title": "审批", "evidence_path": {"relevance": 0.6}},
        {"unit_id": "chunk", "document_id": "doc", "version_label": "v1", "section_title": "审批", "evidence_path": {"relevance": 0.8}},
        {"unit_id": "other", "document_id": "doc", "version_label": "v1", "section_title": "提交", "evidence_path": {"relevance": 0.7}},
    ]

    result = dedupe_citations(citations)

    assert [item["unit_id"] for item in result] == ["chunk", "other"]


def test_refusal_citations_are_not_public() -> None:
    citations = [{"unit_id": "candidate"}]

    assert public_citations(citations, answer_mode="refusal", refusal_reason="insufficient_evidence") == []
    assert public_citations(citations, answer_mode="weak_grounded", refusal_reason="partial_evidence") == citations
