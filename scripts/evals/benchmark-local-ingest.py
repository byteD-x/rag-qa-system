#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
NOVEL_SERVICE_DIR = REPO_ROOT / "apps/backend/novel-service"
KB_SERVICE_DIR = REPO_ROOT / "apps/backend/kb-service"

NOVEL_INLINE = """
import json, sys, time
from pathlib import Path
from app.streaming_ingest import build_streaming_parse, iter_chapter_blocks

path = Path(sys.argv[1])
started = time.perf_counter()
blocks = list(iter_chapter_blocks(path))
block_ms = (time.perf_counter() - started) * 1000.0
parse_started = time.perf_counter()
parsed = build_streaming_parse(blocks)
parse_ms = (time.perf_counter() - parse_started) * 1000.0
payload = {
    "file": str(path),
    "size_bytes": path.stat().st_size,
    "chapter_blocks": len(blocks),
    "chapters": len(parsed.chapters),
    "scenes": len(parsed.scenes),
    "passages": len(parsed.passages),
    "aliases": len(parsed.aliases),
    "relation_edges": len(parsed.relation_edges),
    "block_scan_ms": round(block_ms, 3),
    "parse_ms": round(parse_ms, 3),
}
print(json.dumps(payload, ensure_ascii=False))
"""

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
    result = subprocess.run(command, cwd=str(cwd), check=True, capture_output=True, text=True)
    return json.loads(result.stdout.strip())


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    novel = report["novel"]
    kb = report["kb"]
    lines = [
        "# Local Ingest Benchmark",
        "",
        "## Novel",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| size (MiB) | {novel['size_mib']:.2f} |",
        f"| chapter blocks | {novel['chapter_blocks']} |",
        f"| scenes | {novel['scenes']} |",
        f"| passages | {novel['passages']} |",
        f"| scan ms | {novel['block_scan_ms']:.2f} |",
        f"| parse ms | {novel['parse_ms']:.2f} |",
        f"| throughput MiB/s | {novel['throughput_mib_per_s']:.2f} |",
        "",
        "## KB",
        "",
        "| file count | total MiB | total sections | total chunks | mean parse ms | throughput MiB/s |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {kb['file_count']} | {kb['size_mib']:.2f} | {kb['sections']} | {kb['chunks']} | "
        f"{kb['mean_parse_ms']:.2f} | {kb['throughput_mib_per_s']:.2f} |",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local parsing throughput without running the full stack.")
    parser.add_argument("--novel-file", default="docs/呢喃诗章(咸鱼飞行家).txt")
    parser.add_argument("--kb-glob", default="docs/demo-dataset/doc_*.txt")
    parser.add_argument("--output", default="docs/reports/local_ingest_benchmark.json")
    parser.add_argument("--summary-output", default="docs/reports/local_ingest_benchmark.md")
    args = parser.parse_args()

    novel_file = (REPO_ROOT / args.novel_file).resolve()
    kb_files = sorted(REPO_ROOT.glob(args.kb_glob))
    novel_raw = run_inline([sys.executable, "-c", NOVEL_INLINE, str(novel_file)], cwd=NOVEL_SERVICE_DIR)
    kb_raw = run_inline([sys.executable, "-c", KB_INLINE, *[str(path.resolve()) for path in kb_files]], cwd=KB_SERVICE_DIR)

    novel_seconds = max((float(novel_raw["block_scan_ms"]) + float(novel_raw["parse_ms"])) / 1000.0, 0.001)
    novel_size_mib = float(novel_raw["size_bytes"]) / (1024.0 * 1024.0)
    kb_items = list(kb_raw.get("items", []))
    kb_total_bytes = sum(int(item["size_bytes"]) for item in kb_items)
    kb_total_ms = sum(float(item["parse_ms"]) for item in kb_items)
    kb_seconds = max(kb_total_ms / 1000.0, 0.001)

    report = {
        "novel": {
            **novel_raw,
            "size_mib": round(novel_size_mib, 4),
            "throughput_mib_per_s": round(novel_size_mib / novel_seconds, 4),
        },
        "kb": {
            "file_count": len(kb_items),
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
