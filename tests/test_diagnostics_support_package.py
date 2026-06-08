from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/inspect_diagnostics_support_package.py"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/diagnostics_support_package_minimal.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("inspect_diagnostics_support_package_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def test_inspect_minimal_fixture_reports_blocking_readiness() -> None:
    module = _load_module()

    report = module.inspect_support_package(FIXTURE_PATH)

    failures = report["readiness"]["blocking_failures"]
    assert report["redaction_passed"] is True
    assert report["update"] == {
        "status": "pending",
        "version": "2026.06.08",
        "checksum": "sha256:fixture",
    }
    assert len(failures) == 1
    assert failures[0]["name"] == "knowledge_base"
    assert failures[0]["status"] == "failed"
    assert failures[0]["blocking"] is True
    assert any("knowledge_base" in item["source"] for item in report["logs"])


def test_cli_json_outputs_machine_readable_report(capsys) -> None:
    module = _load_module()

    assert module.main([str(FIXTURE_PATH), "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["manifest"]["package_id"] == "diag-minimal-001"
    assert report["readiness"]["blocking_failure_count"] == 1
    assert report["redaction_passed"] is True


def test_missing_structures_return_warnings() -> None:
    module = _load_module()

    report = module.inspect_package({})

    assert "missing or invalid manifest" in report["warnings"]
    assert "missing or invalid snapshot" in report["warnings"]
    assert "missing readiness checks" in report["warnings"]
    assert "missing update summary" in report["warnings"]
    assert "missing logs summary" in report["warnings"]


def test_sensitive_scan_reports_only_categories_and_paths(tmp_path: Path, capsys) -> None:
    module = _load_module()
    key_name = "api" + "_key"
    token_value = "Bearer " + "tok_" + ("A" * 24)
    key_value = "sk-" + ("B" * 24)
    local_path = "C:" + "\\Users\\LocalOperator\\diagnostics\\package.json"
    chat_text = "private customer deployment question"
    payload = {
        "manifest": {"package_id": "sensitive-sample", "source": local_path},
        "snapshot": {
            "runtime": {
                "readiness": {"checks": [{"name": "gateway", "status": "ok", "blocking": False}]},
                "status": {"diagnostics": [{"message": token_value}]},
            },
            "update": {"status": "ok", "version": "local", "checksum": "sha256:test"},
            "logs": [{"message": f"path={local_path}"}],
            "credentials": {key_name: key_value},
            "chat": {"question": chat_text},
        },
    }
    support_package = tmp_path / "support.json"
    support_package.write_text(json.dumps(payload), encoding="utf-8")

    report = module.inspect_support_package(support_package)
    assert report["redaction_passed"] is False
    assert {"api_key", "bearer_token", "local_user_path", "chat_text"} <= {
        item["category"] for item in report["sensitive_findings"]
    }

    assert module.main([str(support_package), "--json"]) == 0
    output = capsys.readouterr().out
    assert key_value not in output
    assert token_value not in output
    assert local_path not in output
    assert chat_text not in output
    assert "sensitive-sample" in output
    assert "$.snapshot.credentials.api_key" in output
    assert "$.snapshot.chat.question" in output


def test_text_report_is_sanitized() -> None:
    module = _load_module()
    report = module.inspect_package(
        {
            "manifest": {"package_id": "sample"},
            "snapshot": {
                "runtime": {
                    "readiness": {
                        "checks": [
                            {
                                "name": "gateway",
                                "status": "failed",
                                "blocking": True,
                                "detail": "Bearer " + "tok_" + ("C" * 24),
                            }
                        ]
                    }
                },
                "update": {"status": "ok", "version": "local", "checksum": "sha256:test"},
                "logs": [],
            },
        }
    )

    text = module.build_text_report(report)

    assert "tok_" + ("C" * 24) not in text
    assert "<redacted:bearer_token>" in text
