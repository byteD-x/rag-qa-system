#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "scripts" / "evaluation" / "fixtures"
DEFAULT_BASELINE = FIXTURE_DIR / "agent_smoke_baseline.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "reports" / "agent_smoke_evidence_pack.json"
DEFAULT_SUMMARY_OUTPUT = REPO_ROOT / "artifacts" / "reports" / "agent_smoke_evidence_pack.md"

EVAL_FIXTURES = {
    "grounded_single": "agent_smoke_grounded.json",
    "agent_multi": "agent_smoke_agent.json",
    "strict_refusal": "agent_smoke_refusal.json",
}
CORPUS_FIXTURES = ["agent_smoke_policy.txt", "agent_smoke_travel.txt"]
REQUIRED_CASE_FIELDS = ["id", "category", "question", "min_citations", "must_refuse_without_evidence"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _append_failure(failures: list[str], message: str) -> None:
    failures.append(message)


def _validate_case(case: Any, *, fixture_name: str, index: int, expected_category: str) -> list[str]:
    failures: list[str] = []
    prefix = f"{fixture_name}[{index}]"
    if not isinstance(case, dict):
        return [f"{prefix}: case must be an object"]

    for field in REQUIRED_CASE_FIELDS:
        if field not in case:
            _append_failure(failures, f"{prefix}: missing required field `{field}`")

    for field in ["id", "category", "question"]:
        value = case.get(field)
        if not isinstance(value, str) or not value.strip():
            _append_failure(failures, f"{prefix}: `{field}` must be a non-empty string")

    if case.get("category") != expected_category:
        _append_failure(
            failures,
            f"{prefix}: category expected `{expected_category}` but got `{case.get('category') or 'unspecified'}`",
        )

    min_citations = case.get("min_citations")
    if type(min_citations) is not int or min_citations < 0:
        _append_failure(failures, f"{prefix}: `min_citations` must be a non-negative integer")

    if type(case.get("must_refuse_without_evidence")) is not bool:
        _append_failure(failures, f"{prefix}: `must_refuse_without_evidence` must be a boolean")

    return failures


def validate_evidence_pack(*, baseline_path: Path = DEFAULT_BASELINE, fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    failures: list[str] = []
    jobs: list[dict[str, Any]] = []
    eval_fixtures: list[dict[str, Any]] = []
    corpus_fixtures: list[dict[str, Any]] = []

    baseline: dict[str, Any] = {}
    if not baseline_path.exists():
        _append_failure(failures, f"baseline missing: {_display_path(baseline_path)}")
    else:
        loaded = load_json(baseline_path)
        if not isinstance(loaded, dict):
            _append_failure(failures, f"baseline must be an object: {_display_path(baseline_path)}")
        else:
            baseline = loaded

    suite_name = str(baseline.get("suite_name") or "").strip()
    suite_version = str(baseline.get("suite_version") or "").strip()
    if not suite_name:
        _append_failure(failures, "baseline suite_name missing")
    if not suite_version:
        _append_failure(failures, "baseline suite_version missing")

    required_dataset_versions = sorted(
        str(item).strip() for item in list(baseline.get("required_dataset_versions") or []) if str(item).strip()
    )
    if not required_dataset_versions:
        _append_failure(failures, "baseline required_dataset_versions missing")

    baseline_jobs = baseline.get("jobs") or {}
    if not isinstance(baseline_jobs, dict) or not baseline_jobs:
        _append_failure(failures, "baseline jobs missing")
        baseline_jobs = {}

    job_dataset_versions: list[str] = []
    for job_name, job_config in baseline_jobs.items():
        job_config = job_config if isinstance(job_config, dict) else {}
        dataset_version = str(job_config.get("dataset_version") or "").strip()
        execution_modes = [
            str(item).strip() for item in list(job_config.get("execution_modes") or []) if str(item).strip()
        ]
        thresholds = dict(job_config.get("thresholds") or {})
        job_failures: list[str] = []

        if not dataset_version:
            job_failures.append("dataset_version missing")
        else:
            job_dataset_versions.append(dataset_version)
            if required_dataset_versions and dataset_version not in required_dataset_versions:
                job_failures.append(f"dataset_version `{dataset_version}` is not listed in required_dataset_versions")
        if not execution_modes:
            job_failures.append("execution_modes missing")
        if not thresholds:
            job_failures.append("thresholds missing")

        jobs.append(
            {
                "name": str(job_name),
                "dataset_version": dataset_version,
                "execution_modes": execution_modes,
                "thresholds": sorted(thresholds.keys()),
                "status": "passed" if not job_failures else "failed",
                "failures": job_failures,
            }
        )
        failures.extend(f"{job_name}: {item}" for item in job_failures)

    if required_dataset_versions and sorted(job_dataset_versions) != required_dataset_versions:
        _append_failure(
            failures,
            "baseline required_dataset_versions must match jobs dataset_version values: "
            f"required={required_dataset_versions}, jobs={sorted(job_dataset_versions)}",
        )

    for job_name, file_name in EVAL_FIXTURES.items():
        path = fixture_dir / file_name
        fixture_failures: list[str] = []
        case_count = 0
        if not path.exists():
            fixture_failures.append("missing")
        else:
            cases = load_json(path)
            if not isinstance(cases, list) or not cases:
                fixture_failures.append("must be a non-empty case array")
            else:
                case_count = len(cases)
                for index, case in enumerate(cases):
                    fixture_failures.extend(
                        _validate_case(case, fixture_name=file_name, index=index, expected_category=job_name)
                    )

        eval_fixtures.append(
            {
                "job": job_name,
                "path": _display_path(path),
                "case_count": case_count,
                "status": "passed" if not fixture_failures else "failed",
                "failures": fixture_failures,
            }
        )
        failures.extend(f"{file_name}: {item}" for item in fixture_failures)

    for file_name in CORPUS_FIXTURES:
        path = fixture_dir / file_name
        corpus_failures: list[str] = []
        size_bytes = 0
        if not path.exists():
            corpus_failures.append("missing")
        else:
            content = path.read_text(encoding="utf-8")
            size_bytes = len(content.encode("utf-8"))
            if not content.strip():
                corpus_failures.append("empty")

        corpus_fixtures.append(
            {
                "path": _display_path(path),
                "size_bytes": size_bytes,
                "status": "passed" if not corpus_failures else "failed",
                "failures": corpus_failures,
            }
        )
        failures.extend(f"{file_name}: {item}" for item in corpus_failures)

    return {
        "suite_name": suite_name,
        "suite_version": suite_version,
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "baseline": _display_path(baseline_path),
        "required_dataset_versions": required_dataset_versions,
        "job_dataset_versions": sorted(job_dataset_versions),
        "jobs": jobs,
        "eval_fixtures": eval_fixtures,
        "corpus_fixtures": corpus_fixtures,
    }


def write_markdown_report(result: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Agent Smoke Evidence Pack",
        "",
        f"- Suite: `{result.get('suite_name') or 'unspecified'}`",
        f"- Suite version: `{result.get('suite_version') or 'unspecified'}`",
        f"- Status: `{result.get('status') or 'unknown'}`",
        f"- Baseline: `{result.get('baseline') or 'unspecified'}`",
        "",
        "## Jobs",
        "",
        "| job | status | dataset version | execution modes | thresholds | failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in list(result.get("jobs") or []):
        lines.append(
            f"| {item.get('name') or 'unnamed'} | {item.get('status') or 'unknown'} | "
            f"{item.get('dataset_version') or 'n/a'} | "
            f"{', '.join(item.get('execution_modes') or []) or 'n/a'} | "
            f"{', '.join(item.get('thresholds') or []) or 'n/a'} | "
            f"{'; '.join(item.get('failures') or []) or 'none'} |"
        )

    lines.extend(
        [
            "",
            "## Eval Fixtures",
            "",
            "| job | status | path | cases | failures |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for item in list(result.get("eval_fixtures") or []):
        lines.append(
            f"| {item.get('job') or 'unnamed'} | {item.get('status') or 'unknown'} | "
            f"`{item.get('path') or 'n/a'}` | {int(item.get('case_count') or 0)} | "
            f"{'; '.join(item.get('failures') or []) or 'none'} |"
        )

    lines.extend(
        [
            "",
            "## Corpus Fixtures",
            "",
            "| status | path | size bytes | failures |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for item in list(result.get("corpus_fixtures") or []):
        lines.append(
            f"| {item.get('status') or 'unknown'} | `{item.get('path') or 'n/a'}` | "
            f"{int(item.get('size_bytes') or 0)} | {('; '.join(item.get('failures') or []) or 'none')} |"
        )

    if list(result.get("failures") or []):
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in list(result.get("failures") or []))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the offline agent smoke eval evidence pack.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--fixture-dir", default=str(FIXTURE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_OUTPUT))
    args = parser.parse_args()

    result = validate_evidence_pack(baseline_path=Path(args.baseline), fixture_dir=Path(args.fixture_dir))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_report(result, summary_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
