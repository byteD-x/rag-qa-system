#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
KB_SERVICE_SRC_DIR = REPO_ROOT / "apps/services/knowledge-base/src"
DEFAULT_KB_PATTERNS = [
    "datasets/demo/documents/doc_*.txt",
    "README.md",
    "docs/reference/api-specification.md",
    "docs/operations/runbook.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
]

KB_INLINE = """
import json, sys, time
from pathlib import Path
from app.parsing import parse_document

paths = [Path(item) for item in sys.argv[1:]]
items = []
for path in paths:
    started = time.perf_counter()
    parsed = parse_document(path, "txt")
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    items.append({
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "sections": len(parsed.sections),
        "chunks": len(parsed.chunks),
        "parse_ms": round(elapsed_ms, 3),
    })
print(json.dumps({"items": items}, ensure_ascii=False))
"""


def run_inline(command: list[str], *, cwd: Path) -> dict[str, Any]:
    env = dict(os.environ)
    pythonpath_parts = [str(cwd), str(REPO_ROOT / "packages/python")]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    result = subprocess.run(command, cwd=str(cwd), check=True, capture_output=True, text=True, env=env)
    return json.loads(result.stdout.strip())


def resolve_kb_files(patterns: list[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(REPO_ROOT.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            candidates.append(resolved)
    return candidates


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    kb = report["kb"]
    lines = [
        "# Local KB Ingest Benchmark",
        "",
        "## KB",
        "",
        "| file count | total MiB | total sections | total chunks | mean parse ms | throughput MiB/s |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {kb['file_count']} | {kb['size_mib']:.2f} | {kb['sections']} | {kb['chunks']} | "
        f"{kb['mean_parse_ms']:.2f} | {kb['throughput_mib_per_s']:.2f} |",
        "",
        f"- Input patterns: `{', '.join(kb['input_patterns'])}`",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local KB parsing throughput without running the full stack.")
    parser.add_argument("--kb-path", action="append", default=[], help="repeatable glob or file path; defaults cover demo docs plus repo docs")
    parser.add_argument("--output", default="artifacts/reports/local_ingest_benchmark.json")
    parser.add_argument("--summary-output", default="artifacts/reports/local_ingest_benchmark.md")
    args = parser.parse_args()

    kb_patterns = args.kb_path or list(DEFAULT_KB_PATTERNS)
    kb_files = resolve_kb_files(kb_patterns)
    kb_raw = run_inline(
        [sys.executable, "-c", KB_INLINE, *[str(path.resolve()) for path in kb_files]],
        cwd=KB_SERVICE_SRC_DIR,
    )

    kb_items = list(kb_raw.get("items", []))
    kb_total_bytes = sum(int(item["size_bytes"]) for item in kb_items)
    kb_total_ms = sum(float(item["parse_ms"]) for item in kb_items)
    kb_seconds = max(kb_total_ms / 1000.0, 0.001)

    report = {
        "kb": {
            "file_count": len(kb_items),
            "input_patterns": kb_patterns,
            "size_mib": round(kb_total_bytes / (1024.0 * 1024.0), 4),
            "sections": sum(int(item["sections"]) for item in kb_items),
            "chunks": sum(int(item["chunks"]) for item in kb_items),
            "mean_parse_ms": round((kb_total_ms / len(kb_items)), 4) if kb_items else 0.0,
            "throughput_mib_per_s": round((kb_total_bytes / (1024.0 * 1024.0)) / kb_seconds, 4),
            "items": kb_items,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_report(report, summary_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
