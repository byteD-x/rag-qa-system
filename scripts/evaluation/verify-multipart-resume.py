#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from http_helpers import (
    auth_headers,
    build_part_numbers,
    complete_upload,
    create_upload,
    get_upload_session,
    login,
    poll_job,
    presign_parts,
    upload_parts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify KB multipart upload resume behavior against the live stack.")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--email", default="admin@local")
    parser.add_argument("--password", required=True)
    parser.add_argument("--corpus-id", required=True, help="KB base id")
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", default="Resume Verification")
    parser.add_argument("--category", default="resume-check")
    parser.add_argument("--initial-parts", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--output", default="artifacts/reports/multipart_resume_report.json")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    token = login(args.base_url, args.email, args.password)
    headers = auth_headers(token)

    with httpx.Client(timeout=120.0) as client:
        upload_started = time.time()
        session = create_upload(
            client,
            base_url=args.base_url,
            headers=headers,
            corpus_id=args.corpus_id,
            file_path=file_path,
            title=args.title,
            category=args.category,
        )
        upload_id = str(session.get("id") or session.get("upload_id") or "")
        all_part_numbers = build_part_numbers(file_path)
        initial_part_numbers = all_part_numbers[: max(1, min(args.initial_parts, len(all_part_numbers)))]
        initial_presign = presign_parts(
            client,
            base_url=args.base_url,
            headers=headers,
            upload_id=upload_id,
            part_numbers=all_part_numbers,
        )

        uploaded_after_first_pass = upload_parts(
            client,
            file_path=file_path,
            presign_payload={
                **initial_presign,
                "presigned_parts": [
                    item for item in initial_presign.get("presigned_parts", []) or []
                    if int(item["part_number"]) in initial_part_numbers
                ],
            },
        )
        session_after_first_pass = get_upload_session(
            client,
            base_url=args.base_url,
            headers=headers,
            upload_id=upload_id,
        )

        resume_presign = presign_parts(
            client,
            base_url=args.base_url,
            headers=headers,
            upload_id=upload_id,
            part_numbers=all_part_numbers,
        )
        resumed_part_numbers = [
            int(item["part_number"]) for item in resume_presign.get("presigned_parts", []) or []
        ]
        completed_parts = upload_parts(client, file_path=file_path, presign_payload=resume_presign)
        complete_payload = complete_upload(
            client,
            base_url=args.base_url,
            headers=headers,
            upload_id=upload_id,
            parts=completed_parts,
        )
        upload_ack_seconds = time.time() - upload_started
        polling = poll_job(
            client,
            base_url=args.base_url,
            headers=headers,
            job_id=str(complete_payload["job_id"]),
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            upload_ack_seconds=upload_ack_seconds,
        )

    uploaded_parts_from_session = list(session_after_first_pass.get("uploaded_parts", []) or [])
    report = {
        "service": "kb",
        "corpus_id": args.corpus_id,
        "file": str(file_path),
        "upload_id": upload_id,
        "job_id": str(complete_payload["job_id"]),
        "document_id": str(complete_payload.get("document_id") or ""),
        "total_parts": len(all_part_numbers),
        "initial_part_numbers": initial_part_numbers,
        "initial_uploaded_part_count": len(uploaded_after_first_pass),
        "session_uploaded_part_count": len(uploaded_parts_from_session),
        "resumed_part_numbers": resumed_part_numbers,
        "resume_verified": len(uploaded_parts_from_session) == len(initial_part_numbers)
        and sorted(resumed_part_numbers) == [part for part in all_part_numbers if part not in initial_part_numbers],
        **polling,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
