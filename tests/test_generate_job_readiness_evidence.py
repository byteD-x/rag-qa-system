from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    module_path = REPO_ROOT / "scripts" / "quality" / "generate-job-readiness-evidence.py"
    spec = importlib.util.spec_from_file_location("generate_job_readiness_evidence_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_job_readiness_evidence_test"] = module
    spec.loader.exec_module(module)
    return module


def test_build_steps_uses_expected_default_commands() -> None:
    script = _load_script_module()
    steps = script.build_steps(
        python_executable="python",
        reports_dir=REPO_ROOT / "artifacts" / "reports",
        retrieval_fixture=REPO_ROOT / "tests" / "fixtures" / "evals" / "retrieval-ablation-fixture.json",
    )

    assert [step.name for step in steps] == ["agent-smoke-evidence", "retrieval-ablation", "job-readiness"]
    assert steps[0].command[:2] == ("python", "scripts/evaluation/verify-agent-smoke-evidence.py")
    assert steps[1].command[:2] == ("python", "scripts/evaluation/run-retrieval-ablation.py")
    assert steps[2].command[:2] == ("python", "scripts/quality/check-job-readiness.py")
    assert "--output" in steps[2].command
    assert "--summary-output" in steps[2].command


def test_build_completion_summary_reports_key_artifacts(tmp_path: Path) -> None:
    script = _load_script_module()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "job_readiness_summary.json").write_text(
        """
        {"status":"passed","missing_required_reports":[],"failures":[]}
        """.strip(),
        encoding="utf-8",
    )

    lines = script.build_completion_summary(reports_dir)

    assert lines[0] == "[job-evidence] completed offline evidence chain"
    assert any("readiness status: passed" in line for line in lines)
    assert any("job_readiness_summary.md" in line for line in lines)
    assert any("agent_smoke_evidence_pack.md" in line for line in lines)
    assert any("interview next steps" in line for line in lines)
    assert any("job-interview-demo-runbook.md" in line for line in lines)
    assert any("job-production-boundary.md" in line for line in lines)
    assert any("README.md#最快验证路径" in line for line in lines)


def test_run_steps_stops_on_first_failure(monkeypatch) -> None:
    script = _load_script_module()
    executed: list[tuple[str, ...]] = []

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(command, cwd, check):  # noqa: ANN001
        executed.append(tuple(command))
        return Result(1 if len(executed) == 1 else 0)

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    exit_code = script.run_steps([script.EvidenceStep("step1", ("one",)), script.EvidenceStep("step2", ("two",))])

    assert exit_code == 1
    assert executed == [("one",)]


def test_run_steps_executes_all_steps_when_successful(monkeypatch, capsys) -> None:
    script = _load_script_module()
    executed: list[tuple[str, ...]] = []

    class Result:
        returncode = 0

    def fake_run(command, cwd, check):  # noqa: ANN001
        executed.append(tuple(command))
        return Result()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(script, "build_completion_summary", lambda reports_dir: ["summary line"])

    exit_code = script.run_steps([script.EvidenceStep("step1", ("one",)), script.EvidenceStep("step2", ("two",))])

    assert exit_code == 0
    assert executed == [("one",), ("two",)]
    assert "summary line" in capsys.readouterr().out


def test_run_steps_skips_completion_summary_on_failure(monkeypatch, tmp_path: Path) -> None:
    script = _load_script_module()
    executed: list[tuple[str, ...]] = []

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(command, cwd, check):  # noqa: ANN001
        executed.append(tuple(command))
        return Result(1 if len(executed) == 1 else 0)

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(script, "build_completion_summary", lambda reports_dir: (_ for _ in ()).throw(AssertionError("should not build summary on failure")))

    exit_code = script.run_steps([script.EvidenceStep("step1", ("one",)), script.EvidenceStep("step2", ("two",))], reports_dir=tmp_path / "reports")

    assert exit_code == 1
    assert executed == [("one",)]
