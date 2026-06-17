from __future__ import annotations

import importlib.util
import json
import sys
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    module_path = REPO_ROOT / "scripts" / "quality" / "check-job-readiness.py"
    spec = importlib.util.spec_from_file_location("check_job_readiness_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_job_readiness_test"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_minimal_pass_reports(reports_dir: Path) -> None:
    _write_json(
        reports_dir / "agent_smoke_evidence_pack.json",
        {
            "suite_name": "agent_smoke",
            "suite_version": "smoke-eval-2026-03-10",
            "status": "passed",
            "jobs": [{"name": "grounded_single"}],
            "eval_fixtures": [{"case_count": 1}],
            "corpus_fixtures": [{"path": "policy.txt"}],
        },
    )
    _write_json(
        reports_dir / "job_retrieval_ablation.json",
        {
            "summary": {
                "rewrite_plus_fusion_plus_rerank": {
                    "recall_at_1": 1.0,
                    "recall_at_3": 1.0,
                    "mrr": 1.0,
                    "ndcg_at_3": 1.0,
                }
            }
        },
    )


def test_job_readiness_passes_with_required_reports(tmp_path: Path) -> None:
    script = _load_script_module()
    _write_minimal_pass_reports(tmp_path)

    report = script.build_job_readiness_report(tmp_path)

    assert report["status"] == "passed"
    assert report["missing_required_reports"] == []
    assert report["failures"] == []
    retrieval = next(item for item in report["reports"] if item["key"] == "retrieval_ablation")
    assert retrieval["summary"]["mrr"] == 1.0


def test_job_readiness_is_partial_when_required_report_missing(tmp_path: Path) -> None:
    script = _load_script_module()
    _write_json(
        tmp_path / "agent_smoke_evidence_pack.json",
        {"suite_name": "agent_smoke", "suite_version": "v1", "status": "passed"},
    )

    report = script.build_job_readiness_report(tmp_path)

    assert report["status"] == "partial"
    assert report["missing_required_reports"] == ["job_retrieval_ablation.json"]


def test_job_readiness_fails_on_invalid_json(tmp_path: Path) -> None:
    script = _load_script_module()
    _write_minimal_pass_reports(tmp_path)
    (tmp_path / "agent_smoke_evidence_pack.json").write_text("{", encoding="utf-8")

    report = script.build_job_readiness_report(tmp_path)

    assert report["status"] == "failed"
    assert any("invalid_json" in item for item in report["failures"])


def test_job_readiness_fails_on_failed_status(tmp_path: Path) -> None:
    script = _load_script_module()
    _write_minimal_pass_reports(tmp_path)
    _write_json(
        tmp_path / "agent_smoke_evidence_pack.json",
        {"suite_name": "agent_smoke", "suite_version": "v1", "status": "failed", "failures": ["bad"]},
    )

    report = script.build_job_readiness_report(tmp_path)

    assert report["status"] == "failed"
    assert "agent_smoke_evidence_pack.json: status failed" in report["failures"]


def test_job_readiness_cli_returns_nonzero_for_partial(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "agent_smoke_evidence_pack.json",
        {"suite_name": "agent_smoke", "suite_version": "v1", "status": "passed"},
    )

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "quality" / "check-job-readiness.py"), "--reports-dir", str(tmp_path), "--no-write"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert '"status": "partial"' in result.stdout
