#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _metric_value(job_report: dict[str, Any], metric_name: str) -> float:
    overall = dict(((job_report.get("report") or {}).get("summary") or {}).get("overall") or {})
    if metric_name == "refusal_precision":
        return float(((overall.get("refusal") or {}).get("precision") or 0.0))
    if metric_name == "refusal_recall":
        return float(((overall.get("refusal") or {}).get("recall") or 0.0))
    return float(overall.get(metric_name) or 0.0)


def _job_versions(job_report: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    overall = dict(((job_report.get("report") or {}).get("summary") or {}).get("overall") or {})
    dataset_versions = [str(item).strip() for item in (overall.get("dataset_versions") or []) if str(item).strip()]
    prompt_versions = [str(item).strip() for item in (overall.get("prompt_versions") or []) if str(item).strip()]
    model_versions = [str(item).strip() for item in (overall.get("model_versions") or []) if str(item).strip()]
    return dataset_versions, prompt_versions, model_versions


def evaluate_report_against_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    required_jobs = dict(baseline.get("jobs") or {})
    job_reports = {str(item.get("name") or ""): item for item in list(report.get("jobs") or [])}
    required_dataset_versions = sorted(
        str(item).strip() for item in list(baseline.get("required_dataset_versions") or []) if str(item).strip()
    )
    observed_dataset_versions: set[str] = set()
    job_results: list[dict[str, Any]] = []

    if str(report.get("suite_version") or "") != str(baseline.get("suite_version") or ""):
        failures.append(
            f"suite_version mismatch: expected {baseline.get('suite_version') or 'unspecified'}, "
            f"got {report.get('suite_version') or 'unspecified'}"
        )

    for job_name, job_baseline in required_jobs.items():
        job_report = job_reports.get(job_name)
        job_failures: list[str] = []
        if job_report is None:
            job_failures.append("missing_job")
            job_results.append({"name": job_name, "status": "failed", "failures": job_failures, "metrics": {}})
            failures.append(f"{job_name}: missing from suite report")
            continue

        dataset_versions, prompt_versions, model_versions = _job_versions(job_report)
        observed_dataset_versions.update(dataset_versions)
        expected_dataset_version = str(job_baseline.get("dataset_version") or "").strip()
        if expected_dataset_version and dataset_versions != [expected_dataset_version]:
            job_failures.append(
                f"dataset_version expected [{expected_dataset_version}] but got {dataset_versions or ['unspecified']}"
            )
        expected_execution_modes = sorted(
            str(item).strip() for item in list(job_baseline.get("execution_modes") or []) if str(item).strip()
        )
        actual_execution_modes = sorted(
            str(item).strip()
            for item in list((((job_report.get("report") or {}).get("summary") or {}).get("overall") or {}).get("execution_modes") or [])
            if str(item).strip()
        )
        if expected_execution_modes and actual_execution_modes != expected_execution_modes:
            job_failures.append(
                f"execution_modes expected {expected_execution_modes} but got {actual_execution_modes or ['unspecified']}"
            )
        if bool(job_baseline.get("prompt_versions_required")) and not prompt_versions:
            job_failures.append("prompt_versions missing")
        if bool(job_baseline.get("model_versions_required")) and not model_versions:
            job_failures.append("model_versions missing")

        metrics: dict[str, float] = {}
        for metric_name, threshold in dict(job_baseline.get("thresholds") or {}).items():
            value = round(_metric_value(job_report, metric_name), 4)
            metrics[metric_name] = value
            if value < float(threshold):
                job_failures.append(f"{metric_name} expected >= {float(threshold):.4f}, got {value:.4f}")

        status = "passed" if not job_failures else "failed"
        job_results.append(
            {
                "name": job_name,
                "status": status,
                "dataset_versions": dataset_versions,
                "prompt_versions": prompt_versions,
                "model_versions": model_versions,
                "metrics": metrics,
                "failures": job_failures,
            }
        )
        failures.extend(f"{job_name}: {detail}" for detail in job_failures)

    if required_dataset_versions:
        observed_sorted = sorted(observed_dataset_versions)
        if observed_sorted != required_dataset_versions:
            failures.append(
                f"required_dataset_versions expected {required_dataset_versions} but got {observed_sorted or ['unspecified']}"
            )

    overall_metrics: dict[str, float] = {}
    suite_metric_failures: list[str] = []
    for metric_name, threshold in dict(baseline.get("overall_thresholds") or {}).items():
        values = [item["metrics"].get(metric_name, 0.0) for item in job_results if item["metrics"]]
        value = round(sum(values) / len(values), 4) if values else 0.0
        overall_metrics[metric_name] = value
        if value < float(threshold):
            suite_metric_failures.append(f"{metric_name} expected >= {float(threshold):.4f}, got {value:.4f}")
    failures.extend(f"suite: {detail}" for detail in suite_metric_failures)

    return {
        "suite_name": str(baseline.get("suite_name") or ""),
        "suite_version": str(report.get("suite_version") or ""),
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "required_dataset_versions": required_dataset_versions,
        "observed_dataset_versions": sorted(observed_dataset_versions),
        "overall_metrics": overall_metrics,
        "jobs": job_results,
        "source_report": str(report.get("config") or ""),
    }


def write_markdown_report(result: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Eval Regression Gate",
        "",
        f"- Suite: `{result.get('suite_name') or 'unspecified'}`",
        f"- Suite version: `{result.get('suite_version') or 'unspecified'}`",
        f"- Status: `{result.get('status') or 'unknown'}`",
        f"- Dataset versions: `{', '.join(result.get('observed_dataset_versions') or []) or 'n/a'}`",
        "",
        "| job | status | dataset versions | prompt versions | model versions | metrics | failures |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in list(result.get("jobs") or []):
        metrics_text = ", ".join(f"{key}={value:.4f}" for key, value in dict(item.get("metrics") or {}).items()) or "n/a"
        failures_text = "; ".join(list(item.get("failures") or [])) or "none"
        lines.append(
            f"| {item.get('name') or 'unnamed'} | {item.get('status') or 'unknown'} | "
            f"{', '.join(item.get('dataset_versions') or []) or 'n/a'} | "
            f"{', '.join(item.get('prompt_versions') or []) or 'n/a'} | "
            f"{', '.join(item.get('model_versions') or []) or 'n/a'} | "
            f"{metrics_text} | {failures_text} |"
        )
    if list(result.get("failures") or []):
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in list(result.get("failures") or []))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a unified eval suite report against repo baselines.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--baseline", default="scripts/evaluation/fixtures/agent_smoke_baseline.json")
    parser.add_argument("--output", default="artifacts/reports/eval_regression_gate.json")
    parser.add_argument("--summary-output", default="artifacts/reports/eval_regression_gate.md")
    args = parser.parse_args()

    report = load_json(args.report)
    baseline = load_json(args.baseline)
    result = evaluate_report_against_baseline(report, baseline)

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
