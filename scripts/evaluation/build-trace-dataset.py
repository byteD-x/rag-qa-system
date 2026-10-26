#!/usr/bin/env python
"""Convert sanitized retrieval traces into a versioned evaluation dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_dataset(input_path: Path, *, dataset_version: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or not str(raw.get("question") or "").strip():
            continue
        evidence = list(raw.get("evidence") or raw.get("items") or [])
        records.append(
            {
                "case_id": str(raw.get("case_id") or raw.get("trace_id") or f"trace-{len(records) + 1}"),
                "question": str(raw.get("question") or "").strip(),
                "expected_behavior": str(raw.get("expected_behavior") or "answer_with_citation"),
                "expected_unit_ids": [str(item) for item in (raw.get("expected_unit_ids") or []) if str(item)],
                "source_trace_id": str(raw.get("trace_id") or ""),
                "retrieval": dict(raw.get("retrieval") or {}),
                "evidence": [
                    {
                        "unit_id": str(item.get("unit_id") or ""),
                        "document_id": str(item.get("document_id") or ""),
                        "quote": str(item.get("quote") or "")[:500],
                        "gate_action": str(item.get("gate_action") or ""),
                        "signal_scores": dict(item.get("signal_scores") or {}),
                    }
                    for item in evidence
                    if isinstance(item, dict)
                ],
                "safety": dict(raw.get("safety") or {}),
            }
        )
    return {"dataset_version": dataset_version, "record_count": len(records), "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a RAG evaluation dataset from JSONL traces.")
    parser.add_argument("--input", required=True, help="Sanitized JSONL trace file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset-version", default="trace-derived-v1")
    args = parser.parse_args()
    dataset = build_dataset(Path(args.input), dataset_version=args.dataset_version)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "record_count": dataset["record_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
