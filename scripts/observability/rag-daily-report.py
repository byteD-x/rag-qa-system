#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a compact daily RAG engineering report from local report artifacts.")
    parser.add_argument("--reports-dir", default="docs/reports")
    args = parser.parse_args()

    reports_dir = (REPO_ROOT / args.reports_dir).resolve()
    ingest = load_json(reports_dir / "local_ingest_benchmark.json")
    ablation = load_json(reports_dir / "retrieval_ablation_report.json")
    eval_suite = load_json(reports_dir / "eval_suite_report.json")

    lines = ["# RAG Daily Report", ""]
    if ingest:
        novel = ingest.get("novel", {})
        kb = ingest.get("kb", {})
        lines.extend(
            [
                "## Ingest",
                "",
                f"- Novel throughput: `{novel.get('throughput_mib_per_s', 0):.2f} MiB/s`",
                f"- Novel passages: `{novel.get('passages', 0)}`",
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

    output = "\n".join(lines).strip() + "\n"
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
