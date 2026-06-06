#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR_CANDIDATES = (
    "artifacts/reports",
)
REPORT_SPECS = {
    "ingest": {"file": "local_ingest_benchmark.json", "required": True},
    "retrieval": {"file": "retrieval_ablation_report.json", "required": True},
    "embedding": {"file": "embedding_retrieval_benchmark.json", "required": True},
    "evidence_pack": {"file": "agent_smoke_evidence_pack.json", "required": True},
    "eval_suite": {"file": "eval_suite_report.json", "required": False},
    "regression_gate": {"file": "eval_regression_gate.json", "required": False},
    "agent_smoke_regression_gate": {"file": "agent_smoke_regression_gate.json", "required": False},
    "multipart_resume": {"file": "multipart_resume_report.json", "required": False},
    "pytest_groups": {"file": "pytest-groups-summary.json", "required": False},
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_reports_dir(value: str | None) -> Path:
    if value:
        return (REPO_ROOT / value).resolve()
    for candidate in DEFAULT_REPORT_DIR_CANDIDATES:
        resolved = (REPO_ROOT / candidate).resolve()
        if resolved.exists():
            return resolved
    return (REPO_ROOT / DEFAULT_REPORT_DIR_CANDIDATES[0]).resolve()


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_report(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = load_json(path)
    except json.JSONDecodeError as exc:
        return {}, f"invalid_json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "invalid_json: root must be an object"
    return payload, "present"


def _status_from_payload(key: str, payload: dict[str, Any]) -> str:
    if not payload:
        return "missing"
    if key in {"evidence_pack", "regression_gate", "agent_smoke_regression_gate"}:
        return str(payload.get("status") or "unknown")
    if key == "multipart_resume":
        return "passed" if bool(payload.get("resume_verified")) else "failed"
    if key == "pytest_groups":
        return str(payload.get("status") or "unknown")
    return "present"


def _summarize_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    kb = dict(payload.get("kb") or {})
    return {
        "file_count": _int(kb.get("file_count")),
        "throughput_mib_per_s": round(_float(kb.get("throughput_mib_per_s")), 4),
        "chunks": _int(kb.get("chunks")),
        "sections": _int(kb.get("sections")),
        "mean_parse_ms": round(_float(kb.get("mean_parse_ms")), 4),
    }


def _summarize_retrieval(payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload.get("summary") or {})
    best_name, best_metrics = max(
        summary.items(),
        key=lambda item: _float(dict(item[1] or {}).get("mrr")),
        default=("", {}),
    )
    best_metrics = dict(best_metrics or {})
    return {
        "best_config": str(best_name),
        "best_mrr": round(_float(best_metrics.get("mrr")), 4),
        "best_recall_at_1": round(_float(best_metrics.get("recall_at_1")), 4),
        "best_recall_at_3": round(_float(best_metrics.get("recall_at_3")), 4),
        "best_ndcg_at_3": round(_float(best_metrics.get("ndcg_at_3")), 4),
    }


def _summarize_eval_suite(payload: dict[str, Any]) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    for item in list(payload.get("jobs") or []):
        overall = dict(((item.get("report") or {}).get("summary") or {}).get("overall") or {})
        jobs.append(
            {
                "name": str(item.get("name") or ""),
                "accuracy": round(_float(overall.get("accuracy")), 4),
                "correctness": round(_float(overall.get("correctness")), 4),
                "faithfulness": round(_float(overall.get("faithfulness")), 4),
                "citation_alignment": round(_float(overall.get("citation_alignment")), 4),
                "p95_latency_ms": round(_float((overall.get("latency") or {}).get("p95_ms")), 2),
                "execution_modes": list(overall.get("execution_modes") or []),
                "dataset_versions": list(overall.get("dataset_versions") or []),
            }
        )
    return {"suite_version": str(payload.get("suite_version") or ""), "jobs": jobs}


def _summarize_embedding(payload: dict[str, Any]) -> dict[str, Any]:
    backends: list[dict[str, Any]] = []
    for item in list(payload.get("backends") or []):
        summary = dict(item.get("summary") or {})
        backends.append(
            {
                "label": str(item.get("label") or ""),
                "skipped": bool(item.get("skipped")),
                "reason": str(item.get("reason") or ""),
                "recall_at_1": round(_float(summary.get("recall_at_1")), 4),
                "mrr": round(_float(summary.get("mrr")), 4),
            }
        )
    eligible = [item for item in backends if not item["skipped"]]
    best = max(eligible, key=lambda item: _float(item.get("mrr")), default={})
    return {"best_backend": best, "backends": backends}


def _summarize_evidence_pack(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "suite_name": str(payload.get("suite_name") or ""),
        "suite_version": str(payload.get("suite_version") or ""),
        "status": str(payload.get("status") or "unknown"),
        "eval_case_count": sum(_int(item.get("case_count")) for item in list(payload.get("eval_fixtures") or [])),
        "corpus_fixture_count": len(list(payload.get("corpus_fixtures") or [])),
        "failures": list(payload.get("failures") or []),
    }


def _summarize_regression_gate(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "suite_name": str(payload.get("suite_name") or ""),
        "suite_version": str(payload.get("suite_version") or ""),
        "status": str(payload.get("status") or "unknown"),
        "failures": list(payload.get("failures") or []),
        "overall_metrics": dict(payload.get("overall_metrics") or {}),
    }


def _summarize_multipart_resume(payload: dict[str, Any]) -> dict[str, Any]:
    timings = dict(payload.get("timings_seconds") or {})
    return {
        "resume_verified": bool(payload.get("resume_verified")),
        "total_parts": _int(payload.get("total_parts")),
        "ready_seconds": timings.get("ready"),
    }


def _summarize_pytest_groups(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(payload.get("status") or "unknown"),
        "scheduled_groups": _int(payload.get("scheduled_groups")),
        "completed_groups": _int(payload.get("completed_groups")),
        "failed_groups": _int(payload.get("failed_groups")),
        "timed_out_groups": _int(payload.get("timed_out_groups")),
        "elapsed_seconds": round(_float(payload.get("elapsed_seconds")), 4),
        "slowest_groups": list(payload.get("slowest_groups") or [])[:5],
    }


def build_daily_report(reports_dir: Path) -> dict[str, Any]:
    resolved_dir = reports_dir.resolve()
    reports: dict[str, dict[str, Any]] = {}
    report_index: list[dict[str, Any]] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    failures: list[str] = []

    for key, spec in REPORT_SPECS.items():
        path = resolved_dir / str(spec["file"])
        payload, load_status = _load_report(path)
        payload_status = _status_from_payload(key, payload)
        required = bool(spec["required"])
        reports[key] = payload
        item = {
            "key": key,
            "file": str(spec["file"]),
            "required": required,
            "load_status": load_status,
            "status": payload_status,
        }
        report_index.append(item)

        if load_status == "missing":
            if required:
                missing_required.append(str(spec["file"]))
            else:
                missing_optional.append(str(spec["file"]))
            continue
        if load_status != "present":
            failures.append(f"{spec['file']}: {load_status}")
            continue
        if key == "pytest_groups" and payload_status != "passed":
            failures.append(f"{spec['file']}: status {payload_status}")
            continue
        if payload_status in {"failed", "unknown"}:
            failures.append(f"{spec['file']}: status {payload_status}")

    metrics: dict[str, Any] = {}
    if reports["ingest"]:
        metrics["ingest"] = _summarize_ingest(reports["ingest"])
    if reports["retrieval"]:
        metrics["retrieval"] = _summarize_retrieval(reports["retrieval"])
    if reports["eval_suite"]:
        metrics["eval_suite"] = _summarize_eval_suite(reports["eval_suite"])
    if reports["embedding"]:
        metrics["embedding"] = _summarize_embedding(reports["embedding"])
    if reports["evidence_pack"]:
        metrics["evidence_pack"] = _summarize_evidence_pack(reports["evidence_pack"])
    if reports["regression_gate"]:
        metrics["regression_gate"] = _summarize_regression_gate(reports["regression_gate"])
    if reports["agent_smoke_regression_gate"]:
        metrics["agent_smoke_regression_gate"] = _summarize_regression_gate(reports["agent_smoke_regression_gate"])
    if reports["multipart_resume"]:
        metrics["multipart_resume"] = _summarize_multipart_resume(reports["multipart_resume"])
    if reports["pytest_groups"]:
        metrics["pytest_groups"] = _summarize_pytest_groups(reports["pytest_groups"])

    status = "passed"
    if failures:
        status = "failed"
    elif missing_required:
        status = "partial"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(resolved_dir),
        "status": status,
        "missing_required_reports": missing_required,
        "missing_optional_reports": missing_optional,
        "failures": failures,
        "reports": report_index,
        "metrics": metrics,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = dict(report.get("metrics") or {})
    lines = [
        "# RAG Daily Report",
        "",
        f"- Source dir: `{report.get('source_dir')}`",
        f"- Status: `{report.get('status')}`",
        f"- Missing required reports: `{', '.join(report.get('missing_required_reports') or []) or 'none'}`",
        f"- Missing optional reports: `{', '.join(report.get('missing_optional_reports') or []) or 'none'}`",
        "",
        "## Report Inventory",
        "",
        "| report | required | load status | status |",
        "| --- | --- | --- | --- |",
    ]
    for item in list(report.get("reports") or []):
        lines.append(
            f"| `{item.get('file')}` | {str(bool(item.get('required'))).lower()} | "
            f"{item.get('load_status') or 'unknown'} | {item.get('status') or 'unknown'} |"
        )
    lines.append("")

    ingest = dict(metrics.get("ingest") or {})
    if ingest:
        lines.extend(
            [
                "## Ingest",
                "",
                f"- KB throughput: `{_float(ingest.get('throughput_mib_per_s')):.2f} MiB/s`",
                f"- KB chunks: `{_int(ingest.get('chunks'))}`",
                f"- KB sections: `{_int(ingest.get('sections'))}`",
                f"- Mean parse ms: `{_float(ingest.get('mean_parse_ms')):.2f}`",
                "",
            ]
        )

    retrieval = dict(metrics.get("retrieval") or {})
    if retrieval:
        lines.extend(
            [
                "## Retrieval",
                "",
                f"- Best config: `{retrieval.get('best_config') or 'n/a'}`",
                f"- Best MRR: `{_float(retrieval.get('best_mrr')):.4f}`",
                f"- Best recall@1: `{_float(retrieval.get('best_recall_at_1')):.4f}`",
                f"- Best recall@3: `{_float(retrieval.get('best_recall_at_3')):.4f}`",
                "",
            ]
        )

    evidence_pack = dict(metrics.get("evidence_pack") or {})
    if evidence_pack:
        lines.extend(
            [
                "## Evidence Pack",
                "",
                f"- Suite: `{evidence_pack.get('suite_name') or 'n/a'}`",
                f"- Suite version: `{evidence_pack.get('suite_version') or 'n/a'}`",
                f"- Status: `{evidence_pack.get('status') or 'unknown'}`",
                f"- Eval cases: `{_int(evidence_pack.get('eval_case_count'))}`",
                f"- Corpus fixtures: `{_int(evidence_pack.get('corpus_fixture_count'))}`",
                "",
            ]
        )

    eval_suite = dict(metrics.get("eval_suite") or {})
    if eval_suite:
        lines.extend(["## Eval Jobs", ""])
        for item in list(eval_suite.get("jobs") or []):
            lines.append(
                f"- `{item.get('name')}`: accuracy `{_float(item.get('accuracy')):.4f}`, "
                f"correctness `{_float(item.get('correctness')):.4f}`, "
                f"faithfulness `{_float(item.get('faithfulness')):.4f}`, "
                f"p95 latency `{_float(item.get('p95_latency_ms')):.2f} ms`"
            )
        lines.append("")

    embedding = dict(metrics.get("embedding") or {})
    if embedding:
        lines.extend(["## Embeddings", ""])
        for item in list(embedding.get("backends") or []):
            if item.get("skipped"):
                lines.append(f"- `{item.get('label')}`: skipped ({item.get('reason')})")
                continue
            lines.append(
                f"- `{item.get('label')}`: recall@1 `{_float(item.get('recall_at_1')):.4f}`, "
                f"MRR `{_float(item.get('mrr')):.4f}`"
            )
        lines.append("")

    regression_gate = dict(metrics.get("regression_gate") or metrics.get("agent_smoke_regression_gate") or {})
    if regression_gate:
        lines.extend(
            [
                "## Regression Gate",
                "",
                f"- Suite: `{regression_gate.get('suite_name') or 'n/a'}`",
                f"- Status: `{regression_gate.get('status') or 'unknown'}`",
                f"- Failures: `{'; '.join(regression_gate.get('failures') or []) or 'none'}`",
                "",
            ]
        )

    multipart_resume = dict(metrics.get("multipart_resume") or {})
    if multipart_resume:
        lines.extend(
            [
                "## Resilience",
                "",
                f"- Multipart resume verified: `{bool(multipart_resume.get('resume_verified'))}`",
                f"- Total parts: `{_int(multipart_resume.get('total_parts'))}`",
                f"- Ready after resume: `{multipart_resume.get('ready_seconds')}` s",
                "",
            ]
        )

    pytest_groups = dict(metrics.get("pytest_groups") or {})
    if pytest_groups:
        lines.extend(
            [
                "## Pytest Groups",
                "",
                f"- Status: `{pytest_groups.get('status') or 'unknown'}`",
                f"- Scheduled groups: `{_int(pytest_groups.get('scheduled_groups'))}`",
                f"- Completed groups: `{_int(pytest_groups.get('completed_groups'))}`",
                f"- Failed groups: `{_int(pytest_groups.get('failed_groups'))}`",
                f"- Timed out groups: `{_int(pytest_groups.get('timed_out_groups'))}`",
                f"- Elapsed seconds: `{_float(pytest_groups.get('elapsed_seconds')):.2f}`",
                "",
            ]
        )
        slowest = list(pytest_groups.get("slowest_groups") or [])
        if slowest:
            lines.extend(
                [
                    "| group | status | elapsed seconds | stdout | stderr |",
                    "| --- | --- | ---: | --- | --- |",
                ]
            )
            for item in slowest:
                lines.append(
                    f"| `{item.get('group') or 'unknown'}` | {item.get('status') or 'unknown'} | "
                    f"{_float(item.get('elapsed_seconds')):.2f} | `{item.get('stdout_log') or ''}` | "
                    f"`{item.get('stderr_log') or ''}` |"
                )
            lines.append("")

    if list(report.get("failures") or []):
        lines.extend(["## Failures", ""])
        lines.extend(f"- {item}" for item in list(report.get("failures") or []))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a compact daily RAG engineering report from local report artifacts.")
    parser.add_argument("--reports-dir", default="")
    parser.add_argument("--output", default="", help="Optional Markdown output path.")
    parser.add_argument("--json-output", default="", help="Optional machine-readable JSON output path.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required reports are missing or failed.")
    args = parser.parse_args()

    reports_dir = resolve_reports_dir(args.reports_dir or None)
    report = build_daily_report(reports_dir)
    markdown = render_markdown_report(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    if args.json_output:
        json_output_path = Path(args.json_output)
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(markdown)
    if args.strict and report["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
