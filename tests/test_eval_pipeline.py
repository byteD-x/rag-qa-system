from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
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

    calls: list[dict[str, object]] = []

    def fake_run(command: list[str], check: bool, cwd: str, timeout: int) -> None:
        calls.append({"command": command, "timeout": timeout})
        assert check is True
        assert cwd == str(REPO_ROOT)
        assert timeout == 123

    monkeypatch.setattr(smoke_eval.subprocess, "run", fake_run)

    report_path = tmp_path / "agent_smoke_report.json"
    output_path, summary_path = smoke_eval.run_regression_gate(report_path, timeout_seconds=123)

    assert output_path == tmp_path / "agent_smoke_regression_gate.json"
    assert summary_path == tmp_path / "agent_smoke_regression_gate.md"
    assert calls == [
        {
            "command": [
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
            ],
            "timeout": 123,
        }
    ]


def _write_smoke_evidence_pack(fixture_dir: Path, *, include_agent_fixture: bool = True) -> Path:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    baseline = {
        "suite_name": "agent_smoke",
        "suite_version": "smoke-eval-2026-03-10",
        "required_dataset_versions": [
            "agent-smoke-grounded-2026-03-10",
            "agent-smoke-agent-2026-03-10",
            "agent-smoke-refusal-2026-03-10",
        ],
        "overall_thresholds": {"correctness": 0.85},
        "jobs": {
            "grounded_single": {
                "dataset_version": "agent-smoke-grounded-2026-03-10",
                "execution_modes": ["grounded"],
                "thresholds": {"correctness": 0.85},
            },
            "agent_multi": {
                "dataset_version": "agent-smoke-agent-2026-03-10",
                "execution_modes": ["agent"],
                "thresholds": {"correctness": 0.7},
            },
            "strict_refusal": {
                "dataset_version": "agent-smoke-refusal-2026-03-10",
                "execution_modes": ["grounded"],
                "thresholds": {"correctness": 1.0},
            },
        },
    }
    fixtures = {
        "agent_smoke_grounded.json": ("grounded_single", False, 1),
        "agent_smoke_agent.json": ("agent_multi", False, 1),
        "agent_smoke_refusal.json": ("strict_refusal", True, 0),
    }
    for file_name, (category, must_refuse, min_citations) in fixtures.items():
        if file_name == "agent_smoke_agent.json" and not include_agent_fixture:
            continue
        (fixture_dir / file_name).write_text(
            json.dumps(
                [
                    {
                        "id": file_name.removesuffix(".json"),
                        "category": category,
                        "question": "What evidence is required?",
                        "expected_sections": [],
                        "min_citations": min_citations,
                        "must_refuse_without_evidence": must_refuse,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    (fixture_dir / "agent_smoke_policy.txt").write_text("Expense policy evidence.\n", encoding="utf-8")
    (fixture_dir / "agent_smoke_travel.txt").write_text("Travel policy evidence.\n", encoding="utf-8")
    baseline_path = fixture_dir / "agent_smoke_baseline.json"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return baseline_path


def test_agent_smoke_evidence_pack_validator_passes_for_complete_pack(tmp_path: Path) -> None:
    validator = _load_script_module(
        "agent_smoke_evidence_pack_pass_test",
        "scripts/evaluation/verify-agent-smoke-evidence.py",
    )
    fixture_dir = tmp_path / "fixtures"
    baseline_path = _write_smoke_evidence_pack(fixture_dir)

    result = validator.validate_evidence_pack(baseline_path=baseline_path, fixture_dir=fixture_dir)

    assert result["status"] == "passed"
    assert result["failures"] == []
    assert result["required_dataset_versions"] == result["job_dataset_versions"]
    assert [item["case_count"] for item in result["eval_fixtures"]] == [1, 1, 1]


def test_agent_smoke_evidence_pack_validator_fails_on_missing_fixture_and_version_mismatch(tmp_path: Path) -> None:
    validator = _load_script_module(
        "agent_smoke_evidence_pack_fail_test",
        "scripts/evaluation/verify-agent-smoke-evidence.py",
    )
    fixture_dir = tmp_path / "fixtures"
    baseline_path = _write_smoke_evidence_pack(fixture_dir, include_agent_fixture=False)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["required_dataset_versions"] = ["agent-smoke-grounded-2026-03-10"]
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    result = validator.validate_evidence_pack(baseline_path=baseline_path, fixture_dir=fixture_dir)

    assert result["status"] == "failed"
    assert any("agent_smoke_agent.json: missing" in item for item in result["failures"])
    assert any("required_dataset_versions must match jobs dataset_version values" in item for item in result["failures"])


def test_smoke_eval_subprocess_timeout_has_actionable_error(monkeypatch) -> None:
    smoke_eval = _load_script_module("smoke_eval_timeout_test", "scripts/dev/smoke_eval.py")

    def fake_run(command: list[str], check: bool, cwd: str, timeout: int) -> None:
        raise smoke_eval.subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(smoke_eval.subprocess, "run", fake_run)

    try:
        smoke_eval.run_checked_subprocess(["python", "slow.py"], timeout_seconds=7)
    except RuntimeError as exc:
        assert "timed out after 7s" in str(exc)
        assert "python slow.py" in str(exc)
    else:
        raise AssertionError("expected timeout to raise RuntimeError")


def test_http_helpers_poll_job_times_out_with_last_status(monkeypatch) -> None:
    http_helpers = _load_script_module("http_helpers_timeout_test", "scripts/evaluation/http_helpers.py")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "status": "processing",
                "document_status": "uploaded",
                "phase": "parsing",
                "query_ready": False,
            }

    class FakeClient:
        def get(self, *_args, **_kwargs) -> FakeResponse:
            return FakeResponse()

    ticks = iter([0.0, 0.0, 0.0, 0.2])
    monkeypatch.setattr(http_helpers.time, "time", lambda: next(ticks))
    monkeypatch.setattr(http_helpers.time, "sleep", lambda _seconds: None)

    try:
        http_helpers.poll_job(
            FakeClient(),
            base_url="http://example.test/api/v1",
            headers={},
            job_id="job-timeout",
            timeout_seconds=0.1,
            poll_seconds=0.01,
            upload_ack_seconds=0.1,
        )
    except TimeoutError as exc:
        assert "job-timeout" in str(exc)
        assert '"document_status": "uploaded"' in str(exc)
        assert '"phase": "parsing"' in str(exc)
    else:
        raise AssertionError("expected poll timeout")


def test_pytest_group_runner_discovers_test_files(tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_discovery_test", "scripts/quality/run_pytest_groups.py")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text("def test_alpha(): pass\n", encoding="utf-8")
    (tests_dir / "helper.py").write_text("", encoding="utf-8")

    groups = runner.build_groups([str(tests_dir)])

    assert [group.name for group in groups] == [(tests_dir / "test_alpha.py").as_posix()]
    assert groups[0].args == [str(tests_dir / "test_alpha.py")]


def test_fast_test_selector_prunes_nodeids_covered_by_file_target() -> None:
    selector = _load_script_module("fast_test_selector_file_prune_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(["apps/services/api-gateway/src/app/gateway_admin_routes.py"])

    assert targets == ["tests/test_backend_infra.py"]


def test_fast_test_selector_keeps_focused_targets_when_not_covered() -> None:
    selector = _load_script_module("fast_test_selector_focused_targets_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(["apps/services/api-gateway/src/app/gateway_provider_billing.py"])

    assert targets == [
        "tests/test_backend_infra.py::test_provider_billing_import_request_normalizes_records",
        "tests/test_backend_infra.py::test_import_provider_billing_route_imports_records_and_audits",
        "tests/test_backend_infra.py::test_gateway_usage_stats_includes_provider_billing",
    ]


def test_fast_test_selector_prunes_paths_covered_by_directory_target() -> None:
    selector = _load_script_module("fast_test_selector_directory_prune_test", "scripts/quality/select_fast_tests.py")

    targets = selector.normalize_targets(
        [
            "tests",
            "tests/test_backend_infra.py",
            "tests/test_backend_infra.py::test_gateway_usage_stats_includes_provider_billing",
        ]
    )

    assert targets == ["tests"]


def test_fast_test_selector_keeps_direct_test_file_changes() -> None:
    selector = _load_script_module("fast_test_selector_direct_test_file_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(["tests/test_backend_infra.py"])

    assert targets == ["tests/test_backend_infra.py"]


def test_fast_test_selector_routes_agent_tooling_to_focused_tests() -> None:
    selector = _load_script_module("fast_test_selector_agent_tooling_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/business_tools.py",
            "apps/services/api-gateway/src/app/tool_registry.py",
        ]
    )

    assert targets == [
        "tests/test_agent_capabilities.py::TestIntegration::test_business_tools_can_extend_agent_runtime_contract",
        "tests/test_agent_capabilities.py::TestToolRegistry",
        "tests/test_agent_capabilities.py::TestIntegration::test_tool_registry_compatible_with_agent",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_prunes_nodeids_covered_by_class_target() -> None:
    selector = _load_script_module("fast_test_selector_class_prune_test", "scripts/quality/select_fast_tests.py")

    targets = selector.normalize_targets(
        [
            "tests/test_agent_capabilities.py::TestToolRegistry",
            "tests/test_agent_capabilities.py::TestToolRegistry::test_business_tools_register_idempotently",
        ]
    )

    assert targets == ["tests/test_agent_capabilities.py::TestToolRegistry"]


def test_fast_test_selector_routes_agent_runtime_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_agent_runtime_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/agent_orchestrator.py",
            "apps/services/api-gateway/src/app/agent_metacognition.py",
            "apps/services/api-gateway/src/app/task_decomposer.py",
        ]
    )

    assert targets == [
        "tests/test_agent_orchestration.py",
        "tests/test_agent_metacognition.py",
        "tests/test_agent_capabilities.py::TestTaskDecomposer",
        "tests/test_agent_capabilities.py::TestIntegration::test_decomposition_result_feeds_agent",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_optimization_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_optimization_modules_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/agent_error_recovery.py",
            "apps/services/api-gateway/src/app/context_window.py",
            "apps/services/api-gateway/src/app/context_compressor.py",
            "apps/services/api-gateway/src/app/context_prioritizer.py",
            "apps/services/api-gateway/src/app/semantic_cache.py",
            "apps/services/api-gateway/src/app/api_key_manager.py",
            "apps/services/api-gateway/src/app/cost_attribution.py",
            "apps/services/api-gateway/src/app/cost_budget.py",
            "apps/services/api-gateway/src/app/model_health.py",
            "apps/services/api-gateway/src/app/complexity_classifier.py",
        ]
    )

    assert targets == [
        "tests/test_agent_metacognition.py::TestErrorClassifier",
        "tests/test_agent_metacognition.py::TestRecoveryAction",
        "tests/test_agent_metacognition.py::TestErrorRecoveryEngine",
        "tests/test_context_optimization.py::TestEstimateTokens",
        "tests/test_context_optimization.py::TestContextWindowManager",
        "tests/test_context_optimization.py::TestExtractiveCompressor",
        "tests/test_context_optimization.py::TestContextPrioritizer",
        "tests/test_context_optimization.py::TestQuestionFeatures",
        "tests/test_inference_optimization.py::TestSemanticCache",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_cache_invalidate_on_document_update",
        "tests/test_platform_ecosystem_phase2.py::TestAPIKeyManager",
        "tests/test_cost_management.py::TestCostAttribution",
        "tests/test_agent_orchestration.py::TestCostEstimation",
        "tests/test_agent_orchestration.py::TestCostBudgetController",
        "tests/test_inference_optimization.py::TestModelHealth",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_model_health_informs_routing",
        "tests/test_inference_optimization.py::TestComplexityClassifier",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_complexity_drives_cache_decision",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_platform_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_platform_modules_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/instruction_merger.py",
            "apps/services/api-gateway/src/app/scene_templates.py",
            "apps/services/api-gateway/src/app/hallucination_detector.py",
            "apps/services/api-gateway/src/app/pii_detector.py",
            "apps/services/api-gateway/src/app/instruction_hotreload.py",
            "apps/services/api-gateway/src/app/instruction_evaluator.py",
            "apps/services/api-gateway/src/app/ttft_optimizer.py",
        ]
    )

    assert targets == [
        "tests/test_platform_ecosystem.py::TestInstructionMerger",
        "tests/test_platform_ecosystem.py::TestSceneTemplates",
        "tests/test_platform_ecosystem.py::TestHallucinationDetector",
        "tests/test_platform_ecosystem_phase2.py::TestPIIDetector",
        "tests/test_platform_ecosystem_phase2.py::TestInstructionHotReloader",
        "tests/test_platform_ecosystem_phase2.py::TestInstructionABEvaluator",
        "tests/test_platform_ecosystem_phase2.py::TestTTFTTracker",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_memory_enhancement_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_memory_enhancement_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/memory_importance.py",
            "apps/services/api-gateway/src/app/user_profile.py",
            "apps/services/api-gateway/src/app/memory_injection.py",
        ]
    )

    assert targets == [
        "tests/test_memory_enhancement.py::TestMemoryImportanceScorer",
        "tests/test_memory_enhancement.py::TestForgettingCurve",
        "tests/test_memory_enhancement.py::TestUserProfile",
        "tests/test_memory_enhancement.py::TestMemoryInjector",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_gateway_support_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_gateway_support_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/request_coalescer.py",
            "apps/services/api-gateway/src/app/gateway_pricing.py",
            "apps/services/api-gateway/src/app/gateway_handoff.py",
        ]
    )

    assert targets == [
        "tests/test_inference_optimization.py::TestRequestCoalescer",
        "tests/test_gateway_pricing.py",
        "tests/test_backend_infra.py::test_local_handoff_queue_claims_highest_priority_matching_skill_group",
        "tests/test_backend_infra.py::test_local_handoff_queue_does_not_claim_same_session_twice",
        "tests/test_backend_infra.py::test_claim_next_handoff_route_returns_claim_result_and_audit",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_tool_workflow_and_mcp_modules_to_owned_suites() -> None:
    selector = _load_script_module("fast_test_selector_tool_mcp_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/api-gateway/src/app/tool_workflow.py",
            "apps/services/api-gateway/src/app/gateway_mcp_adapter.py",
            "apps/services/api-gateway/src/app/gateway_mcp_routes.py",
        ]
    )

    assert targets == [
        "tests/test_tool_workflow.py",
        "tests/test_backend_infra.py::test_gateway_tool_workflow_route_passes_workflow_mode",
        "tests/test_mcp_adapter.py",
        "tests/test_backend_infra.py::test_gateway_mcp_route_lists_readonly_tools_and_writes_audit",
        "tests/test_backend_infra.py::test_gateway_mcp_route_calls_tool_and_blocks_non_object_arguments",
        "tests/test_backend_infra.py::test_gateway_mcp_route_requires_chat_permission",
    ]
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_dockerignore_to_container_asset_tests() -> None:
    selector = _load_script_module("fast_test_selector_dockerignore_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets([".dockerignore"])

    assert targets == ["tests/test_container_assets.py"]


def test_fast_test_selector_routes_qdrant_readiness_modules_to_focused_tests() -> None:
    selector = _load_script_module("fast_test_selector_qdrant_readiness_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "packages/python/shared/qdrant_store.py",
            "apps/services/knowledge-base/src/app/kb_support.py",
            "apps/services/knowledge-base/src/app/kb_api_support.py",
            "apps/services/knowledge-base/src/app/vector_store.py",
        ]
    )

    assert targets == [
        "tests/test_backend_infra.py::test_qdrant_runtime_config_uses_safe_defaults",
        "tests/test_backend_infra.py::test_qdrant_runtime_config_masks_sensitive_endpoint_and_key",
        "tests/test_backend_infra.py::test_qdrant_runtime_config_falls_back_for_invalid_numbers",
        "tests/test_backend_infra.py::test_qdrant_point_id_is_stable_uuid",
        "tests/test_backend_infra.py::test_kb_readiness_checks_require_storage",
        "tests/test_backend_infra.py::test_search_vector_evidence_degrades_when_qdrant_query_fails",
    ]
    assert "tests/test_shared_stack.py" not in targets


def test_fast_test_selector_routes_kb_connector_modules_to_focused_tests() -> None:
    selector = _load_script_module("fast_test_selector_kb_connectors_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "apps/services/knowledge-base/src/app/kb_local_sync.py",
            "apps/services/knowledge-base/src/app/kb_notion_sync.py",
            "apps/services/knowledge-base/src/app/kb_url_sync.py",
            "apps/services/knowledge-base/src/app/kb_sql_sync.py",
            "apps/services/knowledge-base/src/app/kb_connector_sync.py",
            "apps/services/knowledge-base/src/app/kb_connector_scheduler.py",
        ]
    )

    assert targets == [
        "tests/test_kb_local_sync.py",
        "tests/test_kb_notion_sync.py",
        "tests/test_platform_and_connector_extensions.py::test_execute_url_sync_dry_run_builds_text_candidates",
        "tests/test_platform_and_connector_extensions.py::test_execute_sql_sync_dry_run_converts_rows_to_documents",
        "tests/test_backend_infra.py::test_connector_scheduler_manager_runs_only_when_active",
    ]
    assert "tests/test_ai_platform_capabilities.py" not in targets
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_kb_version_assist_to_visual_stack_tests() -> None:
    selector = _load_script_module("fast_test_selector_kb_version_assist_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(["apps/services/knowledge-base/src/app/kb_version_assist.py"])

    assert targets == [
        "tests/test_visual_stack.py::test_build_version_assist_marks_high_confidence_continuous_version_for_auto_apply",
        "tests/test_visual_stack.py::test_build_version_assist_respects_manual_version_metadata",
    ]
    assert "tests/test_ai_platform_capabilities.py" not in targets
    assert "tests/test_backend_infra.py" not in targets


def test_fast_test_selector_routes_quality_powershell_script_to_eval_pipeline() -> None:
    selector = _load_script_module("fast_test_selector_quality_powershell_test", "scripts/quality/select_fast_tests.py")

    targets = selector.select_targets(
        [
            "scripts/quality/ci-check.ps1",
            "scripts/dev/common.ps1",
            "scripts/dev/preflight.ps1",
        ]
    )

    assert targets == ["tests/test_eval_pipeline.py"]


def test_quality_ci_check_streams_and_forwards_pytest_runner_options() -> None:
    script = (REPO_ROOT / "scripts/quality/ci-check.ps1").read_text(encoding="utf-8")

    assert "[int]$PytestHeartbeatSeconds = 30" in script
    assert "[string[]]$PytestArg = @()" in script
    assert '[string]$PytestSummaryOutput = ""' in script
    assert "Start-Process" in script
    assert "$process.Handle" in script
    assert "Write-NewLogContent" in script
    assert '"--heartbeat-seconds",' in script
    assert '"--summary-output"' in script
    assert '"--pytest-arg=$item"' in script
    assert '            "$PytestHeartbeatSeconds",' in script
    assert "-HeartbeatSeconds $PytestHeartbeatSeconds" in script


def test_preflight_forwards_pytest_runner_options() -> None:
    script = (REPO_ROOT / "scripts/dev/preflight.ps1").read_text(encoding="utf-8")
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "[int]$PytestHeartbeatSeconds = 30" in script
    assert "[int]$PytestMaxWorkers = 1" in script
    assert "[string[]]$PytestArg = @()" in script
    assert '[string]$PytestSummaryOutput = ""' in script
    assert "$effectivePytestTargets" in script
    assert '"--heartbeat-seconds",' in script
    assert '"--summary-output"' in script
    assert '"--pytest-arg=$item"' in script
    assert "PREFLIGHT_ARGS ?=" in makefile
    assert "scripts/dev/preflight.ps1 $(PREFLIGHT_ARGS)" in makefile


def test_pytest_group_runner_prunes_covered_nodeids_before_building_groups() -> None:
    runner = _load_script_module("pytest_group_runner_prune_targets_test", "scripts/quality/run_pytest_groups.py")

    groups = runner.build_groups(
        [
            "tests/test_backend_infra.py",
            "tests/test_backend_infra.py::test_gateway_usage_stats_includes_provider_billing",
        ]
    )

    assert [group.args for group in groups] == [["tests/test_backend_infra.py"]]


def test_pytest_group_runner_timeout_is_actionable(monkeypatch, tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_timeout_test", "scripts/quality/run_pytest_groups.py")

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

    closed: list[str] = []

    class FakeHandle:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    terminated: list[int] = []

    def fake_start_process(_command, *, stdout_path: Path, stderr_path: Path, disable_plugin_autoload: bool = True):
        assert disable_plugin_autoload is True
        return FakeProcess(), FakeHandle(stdout_path.name), FakeHandle(stderr_path.name)

    ticks = iter([0.0, 2.0, 2.1])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_start_process", fake_start_process)
    monkeypatch.setattr(runner, "terminate_process_tree", lambda process: terminated.append(process.pid))

    result = runner.run_group(
        runner.TestGroup(name="tests/test_slow.py", args=["tests/test_slow.py"]),
        python="python",
        pytest_args=["-q"],
        timeout_seconds=1,
        heartbeat_seconds=1,
        log_dir=tmp_path,
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert terminated == [12345]
    assert len(closed) == 2
    assert result.stdout_path.parent == tmp_path


def test_pytest_group_runner_heartbeat_reports_log_progress(monkeypatch, tmp_path: Path, capsys) -> None:
    runner = _load_script_module("pytest_group_runner_heartbeat_test", "scripts/quality/run_pytest_groups.py")

    class FakeProcess:
        pid = 23456

        def __init__(self) -> None:
            self.calls = 0

        def poll(self):
            self.calls += 1
            return None if self.calls == 1 else 0

    class FakeHandle:
        def close(self) -> None:
            return None

    def fake_start_process(_command, *, stdout_path: Path, stderr_path: Path, disable_plugin_autoload: bool = True):
        stdout_path.write_bytes(b"hello\n")
        stderr_path.write_bytes(b"err\n")
        return FakeProcess(), FakeHandle(), FakeHandle()

    ticks = iter([0.0, 2.0, 2.1, 2.2])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_start_process", fake_start_process)

    result = runner.run_group(
        runner.TestGroup(name="tests/test_progress.py", args=["tests/test_progress.py"]),
        python="python",
        pytest_args=["-q"],
        timeout_seconds=10,
        heartbeat_seconds=1,
        log_dir=tmp_path,
    )

    output = capsys.readouterr().out
    assert result.exit_code == 0
    assert "stdout_bytes=6" in output
    assert "stderr_bytes=4" in output
    assert "idle=2.0s" in output


def test_pytest_group_runner_idle_timeout_is_actionable(monkeypatch, tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_idle_timeout_test", "scripts/quality/run_pytest_groups.py")

    class FakeProcess:
        pid = 34567

        def poll(self):
            return None

    class FakeHandle:
        def close(self) -> None:
            return None

    terminated: list[int] = []

    def fake_start_process(_command, *, stdout_path: Path, stderr_path: Path, disable_plugin_autoload: bool = True):
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return FakeProcess(), FakeHandle(), FakeHandle()

    ticks = iter([0.0, 6.0, 6.1])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_start_process", fake_start_process)
    monkeypatch.setattr(runner, "terminate_process_tree", lambda process: terminated.append(process.pid))

    result = runner.run_group(
        runner.TestGroup(name="tests/test_idle.py", args=["tests/test_idle.py"]),
        python="python",
        pytest_args=["-q"],
        timeout_seconds=30,
        heartbeat_seconds=1,
        log_dir=tmp_path,
        idle_timeout_seconds=5,
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.timeout_reason == "idle_timeout"
    assert result.idle_seconds == 6.1
    assert terminated == [34567]


def test_pytest_group_runner_failure_prints_limited_log_tail(monkeypatch, tmp_path: Path, capsys) -> None:
    runner = _load_script_module("pytest_group_runner_tail_test", "scripts/quality/run_pytest_groups.py")

    class FakeProcess:
        pid = 45678

        def poll(self):
            return 2

    class FakeHandle:
        def close(self) -> None:
            return None

    def fake_start_process(_command, *, stdout_path: Path, stderr_path: Path, disable_plugin_autoload: bool = True):
        stdout_path.write_text("out-1\nout-2\nout-3\n", encoding="utf-8")
        stderr_path.write_text("err-1\nerr-2\nerr-3\n", encoding="utf-8")
        return FakeProcess(), FakeHandle(), FakeHandle()

    ticks = iter([0.0, 0.2, 0.3])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "_start_process", fake_start_process)

    result = runner.run_group(
        runner.TestGroup(name="tests/test_failure.py", args=["tests/test_failure.py"]),
        python="python",
        pytest_args=["-q"],
        timeout_seconds=30,
        heartbeat_seconds=1,
        log_dir=tmp_path,
        tail_lines_on_failure=2,
    )

    output = capsys.readouterr().out
    assert result.exit_code == 2
    assert "stdout tail (2 lines)" in output
    assert "stderr tail (2 lines)" in output
    assert "stdout> out-2" in output
    assert "stdout> out-3" in output
    assert "stdout> out-1" not in output
    assert "stderr> err-2" in output
    assert "stderr> err-3" in output
    assert "stderr> err-1" not in output


def test_pytest_group_runner_summary_records_failures_and_slowest(tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_summary_test", "scripts/quality/run_pytest_groups.py")
    passed = runner.GroupResult(
        group=runner.TestGroup(name="tests/test_fast.py", args=["tests/test_fast.py"]),
        exit_code=0,
        elapsed_seconds=1.25,
        timed_out=False,
        stdout_path=tmp_path / "fast.out.log",
        stderr_path=tmp_path / "fast.err.log",
    )
    timeout = runner.GroupResult(
        group=runner.TestGroup(name="tests/test_slow.py", args=["tests/test_slow.py"]),
        exit_code=124,
        elapsed_seconds=9.5,
        timed_out=True,
        stdout_path=tmp_path / "slow.out.log",
        stderr_path=tmp_path / "slow.err.log",
        timeout_reason="hard_timeout",
        stdout_bytes=42,
        stderr_bytes=9,
        idle_seconds=3.5,
    )

    scheduled_group_names = ["tests/test_fast.py", "tests/test_slow.py", "tests/test_later.py"]
    summary = runner.build_summary(
        [passed, timeout],
        scheduled_groups=3,
        scheduled_group_names=scheduled_group_names,
        max_workers=4,
    )

    assert summary["status"] == "failed"
    assert summary["scheduled_groups"] == 3
    assert summary["completed_groups"] == 2
    assert summary["skipped_groups"] == 1
    assert summary["skipped_group_names"] == ["tests/test_later.py"]
    assert summary["max_workers"] == 4
    assert summary["failed_groups"] == 1
    assert summary["timed_out_groups"] == 1
    assert summary["slowest_groups"][0]["group"] == "tests/test_slow.py"
    assert summary["results"][1]["status"] == "timeout"
    assert summary["results"][1]["timeout_reason"] == "hard_timeout"
    assert summary["results"][1]["stdout_bytes"] == 42
    assert summary["results"][1]["stderr_bytes"] == 9
    assert summary["results"][1]["idle_seconds"] == 3.5
    assert summary["results"][1]["stdout_log"].endswith("slow.out.log")

    wall_clock_summary = runner.build_summary(
        [passed, timeout],
        scheduled_groups=3,
        max_workers=4,
        elapsed_seconds=5.5,
    )

    assert wall_clock_summary["elapsed_seconds"] == 5.5


def test_pytest_group_runner_console_summary_prints_slowest_groups(tmp_path: Path, capsys) -> None:
    runner = _load_script_module("pytest_group_runner_console_summary_test", "scripts/quality/run_pytest_groups.py")
    results = [
        runner.GroupResult(
            group=runner.TestGroup(name="tests/test_fast.py", args=["tests/test_fast.py"]),
            exit_code=0,
            elapsed_seconds=0.5,
            timed_out=False,
            stdout_path=tmp_path / "fast.out.log",
            stderr_path=tmp_path / "fast.err.log",
        ),
        runner.GroupResult(
            group=runner.TestGroup(name="tests/test_slow.py", args=["tests/test_slow.py"]),
            exit_code=0,
            elapsed_seconds=8.0,
            timed_out=False,
            stdout_path=tmp_path / "slow.out.log",
            stderr_path=tmp_path / "slow.err.log",
        ),
        runner.GroupResult(
            group=runner.TestGroup(name="tests/test_timeout.py", args=["tests/test_timeout.py"]),
            exit_code=124,
            elapsed_seconds=9.0,
            timed_out=True,
            stdout_path=tmp_path / "timeout.out.log",
            stderr_path=tmp_path / "timeout.err.log",
        ),
        runner.GroupResult(
            group=runner.TestGroup(name="tests/test_medium.py", args=["tests/test_medium.py"]),
            exit_code=3,
            elapsed_seconds=3.0,
            timed_out=False,
            stdout_path=tmp_path / "medium.out.log",
            stderr_path=tmp_path / "medium.err.log",
        ),
    ]

    runner._print_summary(
        results,
        scheduled_groups=5,
        scheduled_group_names=[
            "tests/test_fast.py",
            "tests/test_slow.py",
            "tests/test_timeout.py",
            "tests/test_medium.py",
            "tests/test_later.py",
        ],
        elapsed_seconds=12.5,
    )

    output = capsys.readouterr().out
    assert "summary groups=4 failed=2 scheduled=5 skipped=1 elapsed=12.5s" in output
    assert "skipped groups: tests/test_later.py" in output
    assert "failure tests/test_timeout.py: timeout" in output
    assert "failure tests/test_medium.py: exit_code=3" in output
    assert "slowest tests/test_timeout.py: elapsed=9.0s status=timeout" in output
    assert "slowest tests/test_slow.py: elapsed=8.0s status=passed" in output
    assert "slowest tests/test_medium.py: elapsed=3.0s status=exit_code=3" in output
    assert "tests/test_fast.py: elapsed=0.5s" not in output
    assert "timeout.out.log" in output


def test_pytest_group_runner_parallel_batches_stop_after_failure(monkeypatch, tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_parallel_test", "scripts/quality/run_pytest_groups.py")
    groups = [
        runner.TestGroup(name="tests/test_first.py", args=["tests/test_first.py"]),
        runner.TestGroup(name="tests/test_second.py", args=["tests/test_second.py"]),
        runner.TestGroup(name="tests/test_third.py", args=["tests/test_third.py"]),
    ]
    calls: list[str] = []

    def fake_run_group(group, **_kwargs):
        calls.append(group.name)
        return runner.GroupResult(
            group=group,
            exit_code=7 if group.name.endswith("second.py") else 0,
            elapsed_seconds=0.25,
            timed_out=False,
            stdout_path=tmp_path / f"{Path(group.name).stem}.out.log",
            stderr_path=tmp_path / f"{Path(group.name).stem}.err.log",
        )

    monkeypatch.setattr(runner, "run_group", fake_run_group)

    results = runner.run_groups(
        groups,
        python="python",
        pytest_args=["-q"],
        timeout_seconds=10,
        heartbeat_seconds=1,
        log_dir=tmp_path,
        max_workers=2,
    )

    assert [item.group.name for item in results] == ["tests/test_first.py", "tests/test_second.py"]
    assert results[1].exit_code == 7
    assert set(calls) == {"tests/test_first.py", "tests/test_second.py"}


def test_pytest_group_runner_writes_summary_on_first_failure(monkeypatch, tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_main_summary_test", "scripts/quality/run_pytest_groups.py")
    groups = [
        runner.TestGroup(name="tests/test_first.py", args=["tests/test_first.py"]),
        runner.TestGroup(name="tests/test_second.py", args=["tests/test_second.py"]),
    ]
    calls: list[str] = []

    def fake_build_groups(_paths):
        return groups

    def fake_run_group(group, **_kwargs):
        calls.append(group.name)
        return runner.GroupResult(
            group=group,
            exit_code=2,
            elapsed_seconds=0.5,
            timed_out=False,
            stdout_path=tmp_path / "first.out.log",
            stderr_path=tmp_path / "first.err.log",
        )

    monkeypatch.setattr(runner, "build_groups", fake_build_groups)
    monkeypatch.setattr(runner, "run_group", fake_run_group)

    summary_path = tmp_path / "pytest-summary.json"
    exit_code = runner.main(["--summary-output", str(summary_path), "tests"])
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert calls == ["tests/test_first.py"]
    assert payload["status"] == "failed"
    assert payload["scheduled_groups"] == 2
    assert payload["completed_groups"] == 1
    assert payload["skipped_groups"] == 1
    assert payload["skipped_group_names"] == ["tests/test_second.py"]
    assert payload["results"][0]["group"] == "tests/test_first.py"


def test_pytest_group_runner_main_records_parallel_worker_count(monkeypatch, tmp_path: Path) -> None:
    runner = _load_script_module("pytest_group_runner_main_parallel_summary_test", "scripts/quality/run_pytest_groups.py")
    groups = [
        runner.TestGroup(name="tests/test_first.py", args=["tests/test_first.py"]),
        runner.TestGroup(name="tests/test_second.py", args=["tests/test_second.py"]),
    ]
    observed_kwargs: list[dict[str, object]] = []

    def fake_build_groups(_paths):
        return groups

    def fake_run_groups(_groups, **kwargs):
        observed_kwargs.append(kwargs)
        return [
            runner.GroupResult(
                group=group,
                exit_code=0,
                elapsed_seconds=0.1,
                timed_out=False,
                stdout_path=tmp_path / f"{Path(group.name).stem}.out.log",
                stderr_path=tmp_path / f"{Path(group.name).stem}.err.log",
            )
            for group in _groups
        ]

    monkeypatch.setattr(runner, "build_groups", fake_build_groups)
    monkeypatch.setattr(runner, "run_groups", fake_run_groups)
    ticks = iter([10.0, 11.25])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))

    summary_path = tmp_path / "pytest-summary.json"
    exit_code = runner.main(
        [
            "--max-workers",
            "3",
            "--idle-timeout-seconds",
            "12",
            "--tail-lines-on-failure",
            "7",
            "--summary-output",
            str(summary_path),
            "tests",
        ]
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert observed_kwargs[0]["max_workers"] == 3
    assert observed_kwargs[0]["idle_timeout_seconds"] == 12
    assert observed_kwargs[0]["tail_lines_on_failure"] == 7
    assert payload["status"] == "passed"
    assert payload["max_workers"] == 3
    assert payload["completed_groups"] == 2
    assert payload["elapsed_seconds"] == 1.25
