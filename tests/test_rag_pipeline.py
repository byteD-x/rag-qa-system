from __future__ import annotations

from pathlib import Path

from shared.jevgate import gate_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath, RetrievalStats

from conftest import prioritize_service_src


def _evidence(unit_id: str, text: str) -> EvidenceBlock:
    return EvidenceBlock(
        unit_id=unit_id,
        document_id=f"doc-{unit_id}",
        document_title="Policy",
        section_title="Rules",
        quote=text,
        raw_text=text,
        evidence_path=EvidencePath(final_score=0.2),
    )


def test_jev_gate_skips_remote_call_for_exact_candidate(monkeypatch) -> None:
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_API_URL", "https://jev.example.test/score")
    monkeypatch.setenv("JEV_API_KEY", "secret")

    def fail_remote(*args, **kwargs):
        raise AssertionError("exact candidate should be decided deterministically")

    monkeypatch.setattr("shared.jevgate._request_scores", fail_remote)
    kept, debug, meta = gate_evidence_blocks(
        "错误码 E1001 的处理方式",
        [_evidence("exact", "错误码 E1001 的处理方式：联系值班人员。"), _evidence("other", "网络连接说明")],
    )

    assert [item.unit_id for item in kept] == ["exact"]
    assert debug[0].action == "keep"
    assert debug[0].probability == 1.0
    assert meta.remote_calls == 0
    assert meta.provider == "deterministic"


def test_jev_gate_batches_scores_and_applies_calibrated_thresholds(monkeypatch) -> None:
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_API_URL", "https://jev.example.test/score")
    monkeypatch.setenv("JEV_API_KEY", "secret")
    monkeypatch.setenv("JEV_HIGH_THRESHOLD", "0.8")
    monkeypatch.setenv("JEV_LOW_THRESHOLD", "0.3")

    calls: list[dict[str, object]] = []

    def fake_request(question, items, settings):
        calls.append({"question": question, "items": items, "model": settings.model})
        return {"a": 0.9, "b": 0.5, "c": 0.1}

    monkeypatch.setattr("shared.jevgate._request_scores", fake_request)
    kept, debug, meta = gate_evidence_blocks(
        "报销审批流程",
        [_evidence("a", "部门负责人审批"), _evidence("b", "财务复核"), _evidence("c", "网络连接")],
    )

    assert [item.unit_id for item in kept] == ["a", "b"]
    assert [(item.unit_id, item.action) for item in debug] == [
        ("a", "keep"),
        ("b", "deprioritize"),
        ("c", "drop"),
    ]
    assert len(calls) == 1
    assert len(calls[0]["items"]) == 3
    assert meta.remote_calls == 1
    assert meta.provider == "jev"


def test_jev_gate_fails_open_when_provider_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_API_URL", "https://jev.example.test/score")
    monkeypatch.setenv("JEV_API_KEY", "secret")
    monkeypatch.setattr("shared.jevgate._request_scores", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))

    kept, debug, meta = gate_evidence_blocks("问题", [_evidence("a", "答案")])

    assert [item.unit_id for item in kept] == ["a"]
    assert debug[0].action == "fallback"
    assert meta.warning == "jev_unavailable"


def test_retrieval_stats_describe_exact_channel_and_context_gate() -> None:
    stats = RetrievalStats(
        grep_candidates=2,
        gate_applied=True,
        gate_evaluated_candidates=6,
        gate_kept_candidates=3,
        gate_dropped_candidates=3,
        gate_provider="jev",
    )

    assert stats.as_dict()["grep_candidates"] == 2
    assert stats.as_dict()["gate_applied"] is True
    assert stats.as_dict()["gate_kept_candidates"] == 3


def test_exact_query_terms_target_stable_identifiers_only() -> None:
    prioritize_service_src(Path(__file__).resolve().parents[1] / "apps/services/knowledge-base/src")
    import importlib

    retrieve = importlib.import_module("app.retrieve")

    assert retrieve._exact_query_terms("请解释 E1001 在 v2.3 的处理方式") == ["e1001", "v2.3"]
    assert retrieve._exact_query_terms("如何提交报销申请") == []


def test_fusion_dedupes_identical_text_within_same_section() -> None:
    prioritize_service_src(Path(__file__).resolve().parents[1] / "apps/services/knowledge-base/src")
    import importlib

    retrieve = importlib.import_module("app.retrieve")
    first = EvidenceBlock(
        unit_id="chunk-1",
        document_id="doc-1",
        document_title="Policy",
        section_title="Approval",
        raw_text="Finance approval is required.",
    )
    duplicate = EvidenceBlock(
        unit_id="chunk-2",
        document_id="doc-1",
        document_title="Policy",
        section_title="Approval",
        raw_text=" finance approval is required. ",
    )
    distinct = EvidenceBlock(
        unit_id="chunk-3",
        document_id="doc-1",
        document_title="Policy",
        section_title="Approval",
        raw_text="Department owner approval is required.",
    )

    deduped = retrieve._dedupe_fused_blocks([first, duplicate, distinct])

    assert [item.unit_id for item in deduped] == ["chunk-1", "chunk-3"]
