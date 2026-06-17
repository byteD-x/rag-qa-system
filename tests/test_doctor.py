from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    module_path = REPO_ROOT / "scripts" / "quality" / "doctor.py"
    spec = importlib.util.spec_from_file_location("doctor_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["doctor_test"] = module
    spec.loader.exec_module(module)
    return module


def test_doctor_report_passes_with_warnings(monkeypatch) -> None:
    script = _load_script_module()

    monkeypatch.setattr(script.shutil, "which", lambda name: "cmd" if name != "docker" else None)
    original_exists = script.Path.exists

    def fake_exists(self):
        if str(self).endswith(".env"):
            return True
        return original_exists(self)

    monkeypatch.setattr(script.Path, "exists", fake_exists)
    original_read_text = script.Path.read_text

    def fake_read_text(self, encoding="utf-8"):
        if str(self).endswith(".env"):
            return "JWT_SECRET=x\nADMIN_EMAIL=a@b.com\nADMIN_PASSWORD=secret\nLLM_API_KEY=key\n"
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(script.Path, "read_text", fake_read_text)
    monkeypatch.setattr(script, "_status_for_port", lambda port: script.CheckResult(f"port:{port}", "ok", "free"))

    report = script.build_report()

    assert report["status"] == "passed_with_warnings"
    assert report["errors"] == []
    docker_warning = next(item for item in report["warnings"] if item["name"] == "command:docker")
    assert "make demo-offline" in docker_warning["detail"]
    assert any("make demo-offline" in step for step in report["next_steps"])
    json.dumps(report, ensure_ascii=False)


def test_doctor_report_fails_when_required_command_missing(monkeypatch) -> None:
    script = _load_script_module()

    monkeypatch.setattr(script.shutil, "which", lambda name: None if name == "node" else "cmd")
    monkeypatch.setattr(script.Path, "exists", lambda self: True)
    monkeypatch.setattr(script, "_status_for_port", lambda port: script.CheckResult(f"port:{port}", "ok", "free"))

    report = script.build_report()

    assert report["status"] == "failed"
    assert any(item["name"] == "command:node" for item in report["errors"])
    assert report["next_steps"] == ["先修复上面的 Errors，再重新运行 `make doctor`。"]


def test_doctor_strict_returns_nonzero_for_warnings(monkeypatch, capsys) -> None:
    script = _load_script_module()

    monkeypatch.setattr(
        script,
        "build_report",
        lambda: {
            "repo_root": str(REPO_ROOT),
            "status": "passed_with_warnings",
            "errors": [],
            "warnings": [
                {
                    "name": "command:docker",
                    "status": "warn",
                    "detail": "not found; run `make demo-offline` for offline evidence before full Docker stack checks",
                }
            ],
            "next_steps": ["如果暂时没有 Docker CLI，先运行 `make demo-offline` 验证离线证据链。"],
            "checks": [
                {
                    "name": "command:docker",
                    "status": "warn",
                    "detail": "not found; run `make demo-offline` for offline evidence before full Docker stack checks",
                }
            ],
        },
    )

    assert script.main(["--json", "--strict"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "passed_with_warnings"
    assert any("make demo-offline" in step for step in payload["next_steps"])


def test_doctor_warns_when_env_missing(monkeypatch) -> None:
    script = _load_script_module()

    monkeypatch.setattr(script.shutil, "which", lambda name: "cmd")
    monkeypatch.setattr(script.Path, "exists", lambda self: False if str(self).endswith(".env") else True)
    monkeypatch.setattr(script, "_status_for_port", lambda port: script.CheckResult(f"port:{port}", "ok", "free"))

    report = script.build_report()

    assert any(item["name"] == "env:.env" for item in report["warnings"])
    assert any(".env.example" in step for step in report["next_steps"])


def test_doctor_human_report_prints_next_steps(capsys) -> None:
    script = _load_script_module()
    report = {
        "repo_root": str(REPO_ROOT),
        "status": "passed_with_warnings",
        "errors": [],
        "warnings": [{"name": "command:docker", "status": "warn", "detail": "not found"}],
        "next_steps": ["如果暂时没有 Docker CLI，先运行 `make demo-offline` 验证离线证据链。"],
        "checks": [{"name": "command:docker", "status": "warn", "detail": "not found"}],
    }

    script.write_human_report(report)

    captured = capsys.readouterr()
    assert "Next steps:" in captured.out
    assert "make demo-offline" in captured.out
