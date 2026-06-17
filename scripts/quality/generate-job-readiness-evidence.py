#!/usr/bin/env python
"""Generate offline job-readiness evidence and then aggregate it."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = REPO_ROOT / "artifacts" / "reports"
DEFAULT_RETRIEVAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evals" / "retrieval-ablation-fixture.json"


@dataclass(frozen=True)
class EvidenceStep:
    name: str
    command: tuple[str, ...]


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_steps(*, python_executable: str, reports_dir: Path, retrieval_fixture: Path) -> list[EvidenceStep]:
    reports_dir = reports_dir.resolve()
    retrieval_fixture = retrieval_fixture.resolve()
    return [
        EvidenceStep(
            "agent-smoke-evidence",
            (
                python_executable,
                "scripts/evaluation/verify-agent-smoke-evidence.py",
                "--output",
                _display_path(reports_dir / "agent_smoke_evidence_pack.json"),
                "--summary-output",
                _display_path(reports_dir / "agent_smoke_evidence_pack.md"),
            ),
        ),
        EvidenceStep(
            "retrieval-ablation",
            (
                python_executable,
                "scripts/evaluation/run-retrieval-ablation.py",
                "--fixture",
                _display_path(retrieval_fixture),
                "--output",
                _display_path(reports_dir / "job_retrieval_ablation.json"),
                "--summary-output",
                _display_path(reports_dir / "job_retrieval_ablation.md"),
            ),
        ),
        EvidenceStep(
            "job-readiness",
            (
                python_executable,
                "scripts/quality/check-job-readiness.py",
                "--reports-dir",
                _display_path(reports_dir),
            ),
        ),
    ]


def run_steps(steps: list[EvidenceStep], *, cwd: Path = REPO_ROOT) -> int:
    for step in steps:
        print(f"[job-evidence] running {step.name}: {' '.join(step.command)}", flush=True)
        result = subprocess.run(step.command, cwd=cwd, check=False)
        if result.returncode != 0:
            print(f"[job-evidence] failed {step.name}: exit {result.returncode}", file=sys.stderr)
            return result.returncode
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--retrieval-fixture", type=Path, default=DEFAULT_RETRIEVAL_FIXTURE)
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run child scripts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    steps = build_steps(
        python_executable=str(args.python),
        reports_dir=args.reports_dir,
        retrieval_fixture=args.retrieval_fixture,
    )
    return run_steps(steps)


if __name__ == "__main__":
    raise SystemExit(main())
