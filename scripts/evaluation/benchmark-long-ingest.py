#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from http_helpers import auth_headers, login, upload_and_wait


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark enterprise KB multipart upload and staged ingest.")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--email", default="admin@local")
    parser.add_argument("--password", required=True)
    parser.add_argument("--corpus-id", required=True, help="KB base id")
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", default="Benchmark KB Document")
    parser.add_argument("--category", default="benchmark")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--output", default="artifacts/reports/long_ingest_report.json")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    token = login(args.base_url, args.email, args.password)
    headers = auth_headers(token)

    with httpx.Client(timeout=120.0) as client:
        report = upload_and_wait(
            client,
            base_url=args.base_url,
            headers=headers,
            corpus_id=args.corpus_id,
            file_path=file_path,
            title=args.title,
            category=args.category,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
