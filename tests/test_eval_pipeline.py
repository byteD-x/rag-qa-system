from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_long_rag_scores_quality_and_versions() -> None:
    eval_long_rag = _load_script_module("eval_long_rag_test", "scripts/evaluation/eval-long-rag.py")
    case = {
        "id": "case-1",
        "category": "policy",
        "dataset_version": "fixtures-2026-03-10",
        "expected_sections": ["Expense Approval"],
        "expected_quote_terms": ["department owner", "finance reviewer"],
        "expected_answer_terms": ["department owner", "finance reviewer"],
        "min_citations": 1,
    }
    response = {
        "answer": "Expense requests require approval from the department owner and finance reviewer.",
        "answer_mode": "grounded",
        "execution_mode": "agent",
        "evidence_status": "grounded",
        "grounding_score": 0.91,
        "trace_id": "gateway-test-1",
        "llm_trace": {
            "prompt_key": "chat_grounded_answer",
            "prompt_version": "2026-03-10",
            "model_resolved": "gpt-4.1-mini",
        },
        "retrieval": {
            "aggregate": {
                "retrieval_ms": 12.5,
                "selected_candidates": 2,
            }
        },
        "citations": [
            {
                "section_title": "Expense Approval",
                "quote": "Approval requires the department owner and finance reviewer signatures.",
                "raw_text": "Approval requires the department owner and finance reviewer signatures.",
                "document_title": "Expense Policy",
            }
        ],
    }

    result = eval_long_rag.score_case(case, response, latency_ms=42.0)

    assert result["dataset_version"] == "fixtures-2026-03-10"
    assert result["prompt_version"] == "2026-03-10"
    assert result["prompt_key"] == "chat_grounded_answer"
    assert result["model_version"] == "gpt-4.1-mini"
    assert result["execution_mode"] == "agent"
    assert result["matched"] is True
    assert result["citation_alignment"] == 1.0
    assert result["faithfulness"] > 0.5
    assert result["correctness"] > 0.8


def test_eval_long_rag_summary_aggregates_versions_and_refusal_metrics() -> None:
    eval_long_rag = _load_script_module("eval_long_rag_summary_test", "scripts/evaluation/eval-long-rag.py")
    results = [
        {
            "category": "policy",
            "matched": True,
            "latency_ms": 30.0,
            "mrr": 1.0,
            "ndcg_at_5": 1.0,
            "recall_at_1": 1.0,
            "recall_at_3": 1.0,
            "recall_at_5": 1.0,
            "citation_precision": 1.0,
            "citation_alignment": 1.0,
            "faithfulness": 0.9,
            "correctness": 0.95,
            "dataset_version": "fixtures-2026-03-10",
            "prompt_version": "2026-03-10",
            "model_version": "gpt-4.1-mini",
            "execution_mode": "grounded",
            "expected_refusal": False,
            "refused": False,
            "retrieval": {"aggregate": {"retrieval_ms": 10.0, "selected_candidates": 2}},
        },
        {
            "category": "policy",
            "matched": False,
            "latency_ms": 50.0,
            "mrr": 0.0,
            "ndcg_at_5": 0.0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "citation_precision": 0.0,
            "citation_alignment": 0.0,
            "faithfulness": 1.0,
            "correctness": 1.0,
            "dataset_version": "fixtures-2026-03-10",
            "prompt_version": "2026-03-10",
            "model_version": "gpt-4.1-mini",
            "execution_mode": "grounded",
            "expected_refusal": True,
            "refused": True,
            "retrieval": {"aggregate": {"retrieval_ms": 20.0, "selected_candidates": 1}},
        },
    ]

    summary = eval_long_rag.summarize_results(results)
    overall = summary["overall"]

    assert overall["accuracy"] == 0.5
    assert overall["correctness"] == 0.975
    assert overall["faithfulness"] == 0.95
    assert overall["citation_alignment"] == 0.5
    assert overall["dataset_versions"] == ["fixtures-2026-03-10"]
    assert overall["prompt_versions"] == ["2026-03-10"]
    assert overall["model_versions"] == ["gpt-4.1-mini"]
    assert overall["execution_modes"] == ["grounded"]
    assert overall["refusal"]["precision"] == 1.0
    assert overall["refusal"]["recall"] == 1.0
    assert overall["retrieval"]["mean_ms"] == 15.0
    assert overall["retrieval"]["mean_selected_candidates"] == 1.5


def test_smoke_eval_runtime_suite_is_versioned(monkeypatch, tmp_path: Path) -> None:
    smoke_eval = _load_script_module("smoke_eval_test", "scripts/dev/smoke_eval.py")
    monkeypatch.setattr(smoke_eval, "REPORT_DIR", tmp_path)

    runtime_suite_path = smoke_eval.write_runtime_suite("kb:policy", "kb:travel")
    payload = smoke_eval.json.loads(runtime_suite_path.read_text(encoding="utf-8"))

    assert runtime_suite_path.parent == tmp_path
    assert payload["suite_version"] == "smoke-eval-2026-03-10"
    assert payload["dataset_version"] == "agent-smoke-fixtures-2026-03-10"
    assert [job["name"] for job in payload["jobs"]] == [
        "grounded_single",
        "agent_multi",
        "strict_refusal",
    ]
    assert payload["jobs"][0]["dataset_version"] == "agent-smoke-grounded-2026-03-10"
    assert payload["jobs"][1]["execution_mode"] == "agent"
    assert payload["jobs"][2]["execution_mode"] == "grounded"


def test_eval_regression_gate_passes_for_expected_versions_and_thresholds() -> None:
    regression_gate = _load_script_module(
        "eval_regression_gate_pass_test",
        "scripts/evaluation/check-eval-regression.py",
    )
    baseline = {
        "suite_name": "agent_smoke",
        "suite_version": "smoke-eval-2026-03-10",
        "required_dataset_versions": [
            "agent-smoke-agent-2026-03-10",
            "agent-smoke-grounded-2026-03-10",
            "agent-smoke-refusal-2026-03-10",
        ],
        "overall_thresholds": {
            "correctness": 0.85,
            "faithfulness": 0.8,
            "citation_alignment": 0.6,
        },
        "jobs": {
            "grounded_single": {
                "dataset_version": "agent-smoke-grounded-2026-03-10",
                "execution_modes": ["grounded"],
                "prompt_versions_required": True,
                "model_versions_required": True,
                "thresholds": {
                    "accuracy": 1.0,
                    "correctness": 0.85,
                    "faithfulness": 0.75,
                    "citation_alignment": 1.0,
                },
            },
            "agent_multi": {
                "dataset_version": "agent-smoke-agent-2026-03-10",
                "execution_modes": ["agent"],
                "prompt_versions_required": True,
                "model_versions_required": True,
                "thresholds": {
                    "accuracy": 1.0,
                    "correctness": 0.7,
                    "faithfulness": 0.6,
                    "citation_alignment": 0.8,
                },
            },
            "strict_refusal": {
                "dataset_version": "agent-smoke-refusal-2026-03-10",
                "execution_modes": ["grounded"],
                "prompt_versions_required": True,
                "model_versions_required": True,
                "thresholds": {
                    "correctness": 1.0,
                    "faithfulness": 1.0,
                    "refusal_precision": 1.0,
                    "refusal_recall": 1.0,
                },
            },
        },
    }
    report = {
        "suite_version": "smoke-eval-2026-03-10",
        "jobs": [
            {
                "name": "grounded_single",
                "report": {
                    "summary": {
                        "overall": {
                            "accuracy": 1.0,
                            "correctness": 0.9,
                            "faithfulness": 0.8,
                            "citation_alignment": 1.0,
                            "execution_modes": ["grounded"],
                            "dataset_versions": ["agent-smoke-grounded-2026-03-10"],
                            "prompt_versions": ["2026-03-10"],
                            "model_versions": ["gpt-4.1-mini"],
                            "refusal": {"precision": 0.0, "recall": 0.0},
                        }
                    }
                },
            },
            {
                "name": "agent_multi",
                "report": {
                    "summary": {
                        "overall": {
                            "accuracy": 1.0,
                            "correctness": 0.82,
                            "faithfulness": 0.74,
                            "citation_alignment": 0.85,
                            "execution_modes": ["agent"],
                            "dataset_versions": ["agent-smoke-agent-2026-03-10"],
                            "prompt_versions": ["2026-03-10"],
                            "model_versions": ["gpt-4.1-mini"],
                            "refusal": {"precision": 0.0, "recall": 0.0},
                        }
                    }
                },
            },
            {
                "name": "strict_refusal",
                "report": {
                    "summary": {
                        "overall": {
                            "accuracy": 0.0,
                            "correctness": 1.0,
                            "faithfulness": 1.0,
                            "citation_alignment": 0.0,
                            "execution_modes": ["grounded"],
                            "dataset_versions": ["agent-smoke-refusal-2026-03-10"],
                            "prompt_versions": ["2026-03-10"],
                            "model_versions": ["gpt-4.1-mini"],
                            "refusal": {"precision": 1.0, "recall": 1.0},
                        }
                    }
                },
            },
        ],
    }

    result = regression_gate.evaluate_report_against_baseline(report, baseline)

    assert result["status"] == "passed"
    assert result["failures"] == []
    assert result["overall_metrics"]["correctness"] == 0.9067
    assert result["observed_dataset_versions"] == [
        "agent-smoke-agent-2026-03-10",
        "agent-smoke-grounded-2026-03-10",
        "agent-smoke-refusal-2026-03-10",
    ]


def test_eval_regression_gate_fails_when_versions_or_thresholds_regress() -> None:
    regression_gate = _load_script_module(
        "eval_regression_gate_fail_test",
        "scripts/evaluation/check-eval-regression.py",
    )
    baseline = {
        "suite_name": "agent_smoke",
        "suite_version": "smoke-eval-2026-03-10",
        "required_dataset_versions": ["agent-smoke-grounded-2026-03-10"],
        "overall_thresholds": {"correctness": 0.9},
        "jobs": {
            "grounded_single": {
                "dataset_version": "agent-smoke-grounded-2026-03-10",
                "execution_modes": ["grounded"],
                "prompt_versions_required": True,
                "model_versions_required": True,
                "thresholds": {"accuracy": 1.0, "correctness": 0.85},
            }
        },
    }
    report = {
        "suite_version": "smoke-eval-2026-03-11",
        "jobs": [
            {
                "name": "grounded_single",
                "report": {
                    "summary": {
                        "overall": {
                            "accuracy": 0.5,
                            "correctness": 0.6,
                            "faithfulness": 0.7,
                            "citation_alignment": 0.9,
                            "execution_modes": ["agent"],
                            "dataset_versions": ["agent-smoke-grounded-2026-03-09"],
                            "prompt_versions": [],
                            "model_versions": [],
                            "refusal": {"precision": 0.0, "recall": 0.0},
                        }
                    }
                },
            }
        ],
    }

    result = regression_gate.evaluate_report_against_baseline(report, baseline)

    assert result["status"] == "failed"
    assert any("suite_version mismatch" in item for item in result["failures"])
    assert any("execution_modes expected ['grounded']" in item for item in result["failures"])
    assert any("accuracy expected >= 1.0000" in item for item in result["failures"])
    assert any("required_dataset_versions expected ['agent-smoke-grounded-2026-03-10']" in item for item in result["failures"])


def test_smoke_eval_runs_regression_gate_with_repo_baseline(monkeypatch, tmp_path: Path) -> None:
    smoke_eval = _load_script_module("smoke_eval_regression_gate_test", "scripts/dev/smoke_eval.py")
    monkeypatch.setattr(smoke_eval, "REPORT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool, cwd: str) -> None:
        calls.append(command)
        assert check is True
        assert cwd == str(REPO_ROOT)

    monkeypatch.setattr(smoke_eval.subprocess, "run", fake_run)

    report_path = tmp_path / "agent_smoke_report.json"
    output_path, summary_path = smoke_eval.run_regression_gate(report_path)

    assert output_path == tmp_path / "agent_smoke_regression_gate.json"
    assert summary_path == tmp_path / "agent_smoke_regression_gate.md"
    assert calls == [
        [
            smoke_eval.sys.executable,
            str(smoke_eval.REGRESSION_GATE_SCRIPT),
            "--report",
            str(report_path),
            "--baseline",
            str(smoke_eval.REGRESSION_BASELINE),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    ]
