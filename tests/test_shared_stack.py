from __future__ import annotations

from shared.embeddings import embed_texts, load_embedding_settings
from shared.query_rewrite import rewrite_query
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath
from shared.tracing import ensure_trace_id, trace_headers


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
