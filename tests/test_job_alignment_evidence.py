from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    module_path = REPO_ROOT / "scripts" / "quality" / "check-job-alignment-evidence.py"
    spec = importlib.util.spec_from_file_location("check_job_alignment_evidence_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_job_alignment_evidence_test"] = module
    spec.loader.exec_module(module)
    return module


def test_readme_evidence_check_tracks_offline_demo_entry() -> None:
    script = _load_script_module()

    readme_check = next(item for item in script.EVIDENCE_CHECKS if item.path == "README.md")

    assert "make demo-offline" in readme_check.keywords
    assert "make job-evidence" in readme_check.keywords


def test_job_alignment_evidence_checks_pass_current_repo() -> None:
    script = _load_script_module()

    failures: list[str] = []
    for check in script.EVIDENCE_CHECKS:
        failures.extend(script.validate_check(REPO_ROOT, check))

    assert failures == []
