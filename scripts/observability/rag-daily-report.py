#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR_CANDIDATES = (
    "artifacts/reports",
)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a compact daily RAG engineering report from local report artifacts.")
    parser.add_argument("--reports-dir", default="")
    args = parser.parse_args()

    reports_dir = resolve_reports_dir(args.reports_dir or None)
    ingest = load_json(reports_dir / "local_ingest_benchmark.json")
    ablation = load_json(reports_dir / "retrieval_ablation_report.json")
    eval_suite = load_json(reports_dir / "eval_suite_report.json")
    embedding_benchmark = load_json(reports_dir / "embedding_retrieval_benchmark.json")
    multipart_resume = load_json(reports_dir / "multipart_resume_report.json")

    lines = ["# RAG Daily Report", "", f"- Source dir: `{reports_dir}`", ""]
    if ingest:
        kb = ingest.get("kb", {})
        lines.extend(
            [
                "## Ingest",
                "",
                f"- KB throughput: `{kb.get('throughput_mib_per_s', 0):.2f} MiB/s`",
                f"- KB chunks: `{kb.get('chunks', 0)}`",
                "",
            ]
        )
    if ablation:
        best_name = max(
            ablation.get("summary", {}).items(),
            key=lambda item: float(item[1].get("mrr", 0.0)),
            default=("", {}),
        )
        lines.extend(
            [
                "## Retrieval",
                "",
                f"- Best config: `{best_name[0]}`",
                f"- Best MRR: `{float(best_name[1].get('mrr', 0.0)):.4f}`",
                f"- Best recall@1: `{float(best_name[1].get('recall_at_1', 0.0)):.4f}`",
                "",
            ]
        )
    if eval_suite:
        lines.extend(["## Eval Jobs", ""])
        for item in eval_suite.get("jobs", []):
            overall = item.get("report", {}).get("summary", {}).get("overall", {})
            lines.append(
                f"- `{item.get('name')}`: accuracy `{float(overall.get('accuracy', 0.0)):.4f}`, "
                f"p95 latency `{float(overall.get('latency', {}).get('p95_ms', 0.0)):.2f} ms`"
            )
        lines.append("")
    if embedding_benchmark:
        lines.extend(["## Embeddings", ""])
        for item in embedding_benchmark.get("backends", []):
            if item.get("skipped"):
                lines.append(f"- `{item.get('label')}`: skipped ({item.get('reason')})")
                continue
            summary = item.get("summary", {})
            lines.append(
                f"- `{item.get('label')}`: recall@1 `{float(summary.get('recall_at_1', 0.0)):.4f}`, "
                f"MRR `{float(summary.get('mrr', 0.0)):.4f}`"
            )
        lines.append("")
    if multipart_resume:
        timings = multipart_resume.get("timings_seconds", {})
        lines.extend(
            [
                "## Resilience",
                "",
                f"- Multipart resume verified: `{bool(multipart_resume.get('resume_verified'))}`",
                f"- Total parts: `{int(multipart_resume.get('total_parts', 0) or 0)}`",
                f"- Ready after resume: `{timings.get('ready')}` s",
                "",
            ]
        )

    output = "\n".join(lines).strip() + "\n"
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
