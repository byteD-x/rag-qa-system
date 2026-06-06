from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_report_module():
    module_path = REPO_ROOT / "scripts/observability/rag-daily-report.py"
    spec = importlib.util.spec_from_file_location("rag_daily_report_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rag_daily_report_test"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rag_daily_report_builds_status_and_metrics(tmp_path: Path) -> None:
    report_module = _load_report_module()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    _write_json(
        reports_dir / "local_ingest_benchmark.json",
        {
            "kb": {
                "file_count": 1,
                "throughput_mib_per_s": 1.25,
                "chunks": 8,
                "sections": 3,
                "mean_parse_ms": 12.5,
            }
        },
    )
    _write_json(
        reports_dir / "retrieval_ablation_report.json",
        {
            "summary": {
                "fusion_only": {"recall_at_1": 0.5, "recall_at_3": 1.0, "mrr": 0.5, "ndcg_at_3": 0.75},
                "rewrite_plus_fusion": {"recall_at_1": 1.0, "recall_at_3": 1.0, "mrr": 1.0, "ndcg_at_3": 1.0},
            }
        },
    )
    _write_json(
        reports_dir / "embedding_retrieval_benchmark.json",
        {
            "backends": [
                {"label": "local-projection", "summary": {"recall_at_1": 1.0, "mrr": 1.0}},
                {"label": "external", "skipped": True, "reason": "no api key"},
            ]
        },
    )
    _write_json(
        reports_dir / "agent_smoke_evidence_pack.json",
        {
            "suite_name": "agent_smoke",
            "suite_version": "smoke-eval-2026-03-10",
            "status": "passed",
            "failures": [],
            "eval_fixtures": [{"case_count": 1}, {"case_count": 1}, {"case_count": 1}],
            "corpus_fixtures": [{}, {}],
        },
    )
    _write_json(
        reports_dir / "eval_suite_report.json",
        {
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
                                "latency": {"p95_ms": 42.0},
                                "execution_modes": ["grounded"],
                                "dataset_versions": ["agent-smoke-grounded-2026-03-10"],
                            }
                        }
                    },
                }
            ],
        },
    )
    _write_json(
        reports_dir / "agent_smoke_regression_gate.json",
        {
            "suite_name": "agent_smoke",
            "suite_version": "smoke-eval-2026-03-10",
            "status": "passed",
            "failures": [],
            "overall_metrics": {"correctness": 0.9},
        },
    )

    report = report_module.build_daily_report(reports_dir)
    markdown = report_module.render_markdown_report(report)

    assert report["status"] == "passed"
    assert report["missing_required_reports"] == []
    assert report["metrics"]["retrieval"]["best_config"] == "rewrite_plus_fusion"
    assert report["metrics"]["evidence_pack"]["eval_case_count"] == 3
    assert report["metrics"]["eval_suite"]["jobs"][0]["p95_latency_ms"] == 42.0
    assert "# RAG Daily Report" in markdown
    assert "## Report Inventory" in markdown
    assert "## Evidence Pack" in markdown


def test_rag_daily_report_marks_missing_required_reports_as_partial(tmp_path: Path) -> None:
    report_module = _load_report_module()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    _write_json(
        reports_dir / "local_ingest_benchmark.json",
        {"kb": {"file_count": 1, "throughput_mib_per_s": 0.5, "chunks": 1, "sections": 1}},
    )

    report = report_module.build_daily_report(reports_dir)
    markdown = report_module.render_markdown_report(report)

    assert report["status"] == "partial"
    assert "retrieval_ablation_report.json" in report["missing_required_reports"]
    assert "embedding_retrieval_benchmark.json" in report["missing_required_reports"]
    assert "agent_smoke_evidence_pack.json" in report["missing_required_reports"]
    assert "Missing required reports" in markdown


def test_rag_daily_report_cli_writes_markdown_and_json(monkeypatch, tmp_path: Path) -> None:
    report_module = _load_report_module()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_json(
        reports_dir / "local_ingest_benchmark.json",
        {"kb": {"file_count": 1, "throughput_mib_per_s": 0.5, "chunks": 1, "sections": 1}},
    )
    markdown_path = tmp_path / "daily.md"
    json_path = tmp_path / "daily.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rag-daily-report.py",
            "--reports-dir",
            str(reports_dir),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ],
    )

    exit_code = report_module.main()

    assert exit_code == 0
    assert "# RAG Daily Report" in markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "partial"
    assert "retrieval_ablation_report.json" in payload["missing_required_reports"]
