from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from shared.eval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank, summarize_latencies


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_REPORTS_DIR = REPO_ROOT / "artifacts/reports"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_metrics_summary_helpers() -> None:
    assert recall_at_k([1, 0, 0], 1) == 1.0
    assert reciprocal_rank([0, 1, 0]) == 0.5
    assert ndcg_at_k([1, 0, 1], 3) > 0.9
    latency = summarize_latencies([10.0, 20.0, 30.0])
    assert latency["p50_ms"] == 20.0
    assert latency["max_ms"] == 30.0


def test_eval_long_rag_scoring_exposes_latency_and_refusal() -> None:
    module = _load_module(REPO_ROOT / "scripts/evaluation/eval-long-rag.py", "eval_long_rag_test")
    case = {
        "id": "case-1",
        "category": "refusal",
        "question": "请编造一个不存在的规则",
        "expected_sections": [],
        "min_citations": 0,
        "must_refuse_without_evidence": True,
    }
    response = {
        "answer_mode": "refusal",
        "evidence_status": "insufficient",
        "grounding_score": 0.0,
        "citations": [],
        "retrieval": {"aggregate": {"selected_candidates": 0, "retrieval_ms": 12.5}},
        "trace_id": "gateway-123",
    }
    scored = module.score_case(case, response, latency_ms=33.0)
    assert scored["expected_refusal"] is True
    assert scored["refused"] is True
    assert scored["latency_ms"] == 33.0


def test_retrieval_ablation_script_runs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluation/run-retrieval-ablation.py",
            "--fixture",
            "tests/fixtures/evals/retrieval-ablation-fixture.json",
            "--output",
            str(ARTIFACT_REPORTS_DIR / "test_retrieval_ablation.json"),
            "--summary-output",
            str(ARTIFACT_REPORTS_DIR / "test_retrieval_ablation.md"),
        ],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    assert "fusion_only" in result.stdout


def test_embedding_benchmark_script_runs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluation/compare-embedding-providers.py",
            "--output",
            str(ARTIFACT_REPORTS_DIR / "test_embedding_retrieval_benchmark.json"),
            "--summary-output",
            str(ARTIFACT_REPORTS_DIR / "test_embedding_retrieval_benchmark.md"),
        ],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    assert "local-projection" in result.stdout
