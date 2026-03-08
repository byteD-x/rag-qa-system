#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from http_helpers import (
    QUERYABLE_STATUSES,
    auth_headers,
    create_kb_base,
    list_corpus_documents,
    list_kb_bases,
    login,
    upload_and_wait,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_GLOB = "datasets/demo/documents/doc_*.txt"
KB_CONTEXT_SOURCES = [
    ("repo_overview", REPO_ROOT / "README.md"),
    ("api_spec", REPO_ROOT / "docs/reference/api-specification.md"),
    ("runbook", REPO_ROOT / "docs/operations/runbook.md"),
    ("contributing", REPO_ROOT / "CONTRIBUTING.md"),
    ("security", REPO_ROOT / "SECURITY.md"),
]


def _queryable_document(documents: list[dict[str, Any]], file_name: str) -> dict[str, Any] | None:
    for item in documents:
        status_value = str(item.get("status") or "")
        if str(item.get("file_name") or item.get("title") or "") != file_name:
            continue
        if bool(item.get("query_ready")) or status_value in QUERYABLE_STATUSES:
            return item
    return None


def _ensure_kb_base(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    reuse_existing: bool,
) -> dict[str, Any]:
    target_name = "Demo KB Eval Base"
    if reuse_existing:
        for item in list_kb_bases(client, base_url=base_url, headers=headers):
            if str(item.get("name") or "") == target_name:
                return {"id": str(item["id"]), "name": target_name, "reused": True}
    created = create_kb_base(
        client,
        base_url=base_url,
        headers=headers,
        name=target_name,
        description="Provisioned by scripts/evaluation/run-demo-eval-suite.py for repeatable enterprise RAG evals.",
        category="demo-eval",
    )
    return {**created, "reused": False}


def _materialize_kb_context_files(temp_dir: Path) -> list[Path]:
    files: list[Path] = []
    for stem, source in KB_CONTEXT_SOURCES:
        target = temp_dir / f"{stem}.txt"
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        files.append(target)
    return files


def _resolve_kb_sources(kb_glob: str, temp_dir: Path) -> list[Path]:
    demo_docs = sorted(REPO_ROOT.glob(kb_glob))
    mirrored_context = _materialize_kb_context_files(temp_dir)
    return [*demo_docs, *mirrored_context]


def _ensure_kb_documents(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    base_id: str,
    source_files: list[Path],
    timeout_seconds: int,
    poll_seconds: float,
    reuse_existing: bool,
) -> list[dict[str, Any]]:
    existing_docs = list_corpus_documents(
        client,
        base_url=base_url,
        headers=headers,
        corpus_id=base_id,
    ) if reuse_existing else []
    results: list[dict[str, Any]] = []

    for file_path in source_files:
        if reuse_existing:
            existing = _queryable_document(existing_docs, file_path.name)
            if existing is not None:
                results.append(
                    {
                        "file_name": file_path.name,
                        "document_id": str(existing.get("id") or ""),
                        "status": str(existing.get("status") or ""),
                        "query_ready": bool(existing.get("query_ready")),
                        "reused": True,
                    }
                )
                continue

        upload_report = upload_and_wait(
            client,
            base_url=base_url,
            headers=headers,
            corpus_id=base_id,
            file_path=file_path,
            title=file_path.stem,
            category="demo-eval",
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        results.append(
            {
                "file_name": file_path.name,
                "document_id": str(upload_report.get("document_id") or ""),
                "status": str(upload_report.get("job", {}).get("document_status") or ""),
                "query_ready": bool(upload_report.get("job", {}).get("query_ready")),
                "reused": False,
                "job_id": str(upload_report.get("job_id") or ""),
                "timings_seconds": upload_report.get("timings_seconds", {}),
            }
        )
    return results


def _write_suite_config(*, kb_corpus_id: str, output_path: Path) -> Path:
    payload = {
        "jobs": [
            {
                "name": "kb",
                "eval_file": "tests/fixtures/evals/kb-smoke-eval.json",
                "scope_mode": "single",
                "corpus_ids": [kb_corpus_id],
                "document_ids": [],
            },
            {
                "name": "adversarial",
                "eval_file": "tests/fixtures/evals/adversarial-refusal-eval.json",
                "scope_mode": "all",
                "corpus_ids": [],
                "document_ids": [],
            },
        ]
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _run_eval_suite(
    *,
    password: str,
    config_path: Path,
    report_output: Path,
    summary_output: Path,
    base_url: str,
    email: str,
) -> None:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts/evaluation/run-eval-suite.py"),
        "--base-url",
        base_url,
        "--email",
        email,
        "--password",
        password,
        "--config",
        str(config_path),
        "--output",
        str(report_output),
        "--summary-output",
        str(summary_output),
    ]
    subprocess.run(command, cwd=str(REPO_ROOT), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision demo KB corpora and run a repeatable unified eval suite.")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--email", default="admin@local")
    parser.add_argument("--password", required=True)
    parser.add_argument("--kb-glob", default=DEFAULT_KB_GLOB)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--config-output", default="artifacts/evals/demo_eval_suite_config.json")
    parser.add_argument("--asset-output", default="artifacts/evals/demo_eval_assets.json")
    parser.add_argument("--report-output", default="artifacts/reports/eval_suite_report.json")
    parser.add_argument("--summary-output", default="artifacts/reports/eval_suite_report.md")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-reuse-existing", action="store_true")
    args = parser.parse_args()

    reuse_existing = not args.no_reuse_existing
    token = login(args.base_url, args.email, args.password)
    headers = auth_headers(token)

    with tempfile.TemporaryDirectory(prefix="rag-demo-eval-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        kb_sources = _resolve_kb_sources(args.kb_glob, temp_dir)

        with httpx.Client(timeout=120.0) as client:
            kb_base = _ensure_kb_base(
                client,
                base_url=args.base_url,
                headers=headers,
                reuse_existing=reuse_existing,
            )
            kb_results = _ensure_kb_documents(
                client,
                base_url=args.base_url,
                headers=headers,
                base_id=str(kb_base["id"]),
                source_files=kb_sources,
                timeout_seconds=args.timeout_seconds,
                poll_seconds=args.poll_seconds,
                reuse_existing=reuse_existing,
            )

    config_path = _write_suite_config(
        kb_corpus_id=f"kb:{kb_base['id']}",
        output_path=(REPO_ROOT / args.config_output).resolve(),
    )
    asset_output = (REPO_ROOT / args.asset_output).resolve()
    asset_output.parent.mkdir(parents=True, exist_ok=True)
    asset_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "kb": {
            "corpus_id": f"kb:{kb_base['id']}",
            "base_id": str(kb_base["id"]),
            "base_name": str(kb_base["name"]),
            "documents": kb_results,
        },
        "suite_config": str(config_path),
    }
    asset_output.write_text(json.dumps(asset_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.prepare_only:
        _run_eval_suite(
            password=args.password,
            config_path=config_path,
            report_output=(REPO_ROOT / args.report_output).resolve(),
            summary_output=(REPO_ROOT / args.summary_output).resolve(),
            base_url=args.base_url,
            email=args.email,
        )

    print(json.dumps(asset_manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
