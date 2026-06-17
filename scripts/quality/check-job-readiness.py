#!/usr/bin/env python
"""Aggregate job-alignment readiness signals into one local gate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = REPO_ROOT / "artifacts" / "reports"
DEFAULT_OUTPUT = DEFAULT_REPORTS_DIR / "job_readiness_summary.json"
DEFAULT_SUMMARY_OUTPUT = DEFAULT_REPORTS_DIR / "job_readiness_summary.md"


@dataclass(frozen=True)
class ReportSpec:
    key: str
    file_name: str
    required: bool
    expected_statuses: tuple[str, ...] = ("passed",)


REPORT_SPECS = (
    ReportSpec("agent_smoke_evidence", "agent_smoke_evidence_pack.json", True),
    ReportSpec("retrieval_ablation", "job_retrieval_ablation.json", True, expected_statuses=()),
    ReportSpec("pytest_eval_pipeline", "job_eval_pipeline_pytest_summary.json", False),
    ReportSpec("agent_smoke_regression_gate", "agent_smoke_regression_gate.json", False),
)


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"invalid_json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "invalid_json: root must be an object"
    return payload, "present"


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _status_from_payload(spec: ReportSpec, payload: dict[str, Any]) -> str:
    if not payload:
        return "missing"
    if spec.key == "retrieval_ablation":
        summary = payload.get("summary")
        return "passed" if isinstance(summary, dict) and bool(summary) else "failed"
    return str(payload.get("status") or "unknown")


def _summarize_retrieval(payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload.get("summary") or {})
    best_name = ""
    best_metrics: dict[str, Any] = {}
    for name, metrics in summary.items():
        current = dict(metrics or {})
        if not best_metrics or _float(current.get("mrr")) > _float(best_metrics.get("mrr")):
            best_name = str(name)
            best_metrics = current
    return {
        "best_config": best_name,
        "recall_at_1": round(_float(best_metrics.get("recall_at_1")), 4),
        "recall_at_3": round(_float(best_metrics.get("recall_at_3")), 4),
        "mrr": round(_float(best_metrics.get("mrr")), 4),
        "ndcg_at_3": round(_float(best_metrics.get("ndcg_at_3")), 4),
    }


def _summarize_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "suite_name": str(payload.get("suite_name") or ""),
        "suite_version": str(payload.get("suite_version") or ""),
        "job_count": len(list(payload.get("jobs") or [])),
        "eval_case_count": sum(int(item.get("case_count") or 0) for item in list(payload.get("eval_fixtures") or [])),
        "corpus_fixture_count": len(list(payload.get("corpus_fixtures") or [])),
    }


def _summarize_pytest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scheduled_groups": int(payload.get("scheduled_groups") or 0),
        "completed_groups": int(payload.get("completed_groups") or 0),
        "failed_groups": int(payload.get("failed_groups") or 0),
        "timed_out_groups": int(payload.get("timed_out_groups") or 0),
        "elapsed_seconds": round(_float(payload.get("elapsed_seconds")), 4),
    }


def _summarize_report(spec: ReportSpec, payload: dict[str, Any]) -> dict[str, Any]:
    if spec.key == "retrieval_ablation":
        return _summarize_retrieval(payload)
    if spec.key == "agent_smoke_evidence":
        return _summarize_evidence(payload)
    if spec.key == "pytest_eval_pipeline":
        return _summarize_pytest(payload)
    if spec.key == "agent_smoke_regression_gate":
        return {
            "suite_name": str(payload.get("suite_name") or ""),
            "suite_version": str(payload.get("suite_version") or ""),
            "failures": list(payload.get("failures") or []),
        }
    return {}


def build_job_readiness_report(reports_dir: Path) -> dict[str, Any]:
    reports_dir = reports_dir.resolve()
    items: list[dict[str, Any]] = []
    failures: list[str] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for spec in REPORT_SPECS:
        path = reports_dir / spec.file_name
        payload, load_status = _load_json(path)
        status = _status_from_payload(spec, payload)
        item = {
            "key": spec.key,
            "file": spec.file_name,
            "required": spec.required,
            "load_status": load_status,
            "status": status,
            "summary": _summarize_report(spec, payload) if load_status == "present" else {},
        }
        items.append(item)

        if load_status == "missing":
            if spec.required:
                missing_required.append(spec.file_name)
            else:
                missing_optional.append(spec.file_name)
            continue
        if load_status != "present":
            failures.append(f"{spec.file_name}: {load_status}")
            continue
        if spec.expected_statuses and status not in spec.expected_statuses:
            failures.append(f"{spec.file_name}: status {status}")
        if spec.key == "retrieval_ablation" and status == "passed":
            retrieval_summary = dict(item.get("summary") or {})
            if _float(retrieval_summary.get("recall_at_1")) <= 0 or _float(retrieval_summary.get("mrr")) <= 0:
                failures.append(f"{spec.file_name}: retrieval metrics are empty")

    overall = "passed"
    if failures:
        overall = "failed"
    elif missing_required:
        overall = "partial"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(reports_dir),
        "status": overall,
        "missing_required_reports": missing_required,
        "missing_optional_reports": missing_optional,
        "failures": failures,
        "reports": items,
    }


def write_json_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Job Readiness Summary",
        "",
        f"- Status: `{report.get('status') or 'unknown'}`",
        f"- Source dir: `{report.get('source_dir') or ''}`",
        f"- Missing required: `{len(list(report.get('missing_required_reports') or []))}`",
        f"- Missing optional: `{len(list(report.get('missing_optional_reports') or []))}`",
        f"- Failures: `{len(list(report.get('failures') or []))}`",
        "",
        "## Reports",
        "",
        "| key | required | load | status | summary |",
        "|---|---:|---|---|---|",
    ]
    for item in list(report.get("reports") or []):
        summary = json.dumps(item.get("summary") or {}, ensure_ascii=False, sort_keys=True)
        lines.append(
            f"| `{item.get('key')}` | {bool(item.get('required'))} | "
            f"`{item.get('load_status')}` | `{item.get('status')}` | `{summary}` |"
        )
    failures = list(report.get("failures") or [])
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in failures)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--no-write", action="store_true", help="Print JSON only; do not write report files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_job_readiness_report(args.reports_dir)
    if not args.no_write:
        write_json_report(report, args.output)
        write_markdown_report(report, args.summary_output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
