#!/usr/bin/env python
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_SCRIPT = REPO_ROOT / "scripts/evaluation/run-retrieval-ablation.py"
ONLINE_EVAL_SCRIPT = REPO_ROOT / "scripts/evaluation/eval-long-rag.py"
DEFAULT_RETRIEVAL_FIXTURE = REPO_ROOT / "tests/fixtures/evals/enterprise-policy-poc-retrieval.json"
DEFAULT_ONLINE_FIXTURE = REPO_ROOT / "tests/fixtures/evals/enterprise-policy-poc-online.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "artifacts/reports"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_retrieval_ablation(*, fixture: Path, output: Path, summary_output: Path) -> dict[str, Any]:
    retrieval = _load_module("enterprise_policy_poc_retrieval", RETRIEVAL_SCRIPT)
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    configs = {
        "fusion_only": {"enable_rewrite": False, "enable_rerank": False},
        "rewrite_plus_fusion": {"enable_rewrite": True, "enable_rerank": False},
        "rewrite_plus_fusion_plus_rerank": {"enable_rewrite": True, "enable_rerank": True},
    }
    details: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, dict[str, float]] = {}

    for name, config in configs.items():
        rows: list[dict[str, Any]] = []
        for case in cases:
            ranked = retrieval.rank_case(case, **config)
            metrics = retrieval.score_ranking(case, ranked)
            rows.append(
                {
                    "id": str(case["id"]),
                    "question": str(case["question"]),
                    "top_units": [block.unit_id for block in ranked[:3]],
                    **metrics,
                }
            )
        details[name] = rows
        summary[name] = {
            "recall_at_1": retrieval.average_metric(rows, "recall_at_1"),
            "recall_at_3": retrieval.average_metric(rows, "recall_at_3"),
            "mrr": retrieval.average_metric(rows, "mrr"),
            "ndcg_at_3": retrieval.average_metric(rows, "ndcg_at_3"),
        }

    report = {
        "fixture": str(fixture.resolve()),
        "summary": summary,
        "details": details,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    retrieval.write_markdown_report(report, summary_output)
    return report


def run_online_eval(
    *,
    base_url: str,
    email: str,
    password: str,
    eval_file: Path,
    corpus_ids: list[str],
    output: Path,
    summary_output: Path,
    execution_mode: str,
) -> dict[str, Any]:
    online_eval = _load_module("enterprise_policy_poc_online_eval", ONLINE_EVAL_SCRIPT)
    report = online_eval.run_eval_job(
        base_url=base_url,
        email=email,
        password=password,
        eval_file=str(eval_file),
        scope_mode="single",
        corpus_ids=corpus_ids,
        document_ids=[],
        execution_mode=execution_mode,
        dataset_version="enterprise-policy-poc-2026-07-08",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    online_eval.write_markdown_report(report, summary_output)
    return report


def write_poc_summary(
    *,
    output: Path,
    retrieval_report: dict[str, Any],
    retrieval_summary_path: Path,
    online_report: dict[str, Any] | None,
    online_summary_path: Path,
) -> None:
    lines = [
        "# Enterprise Policy PoC Summary",
        "",
        "## Offline Retrieval",
        "",
        f"- Report: `{retrieval_summary_path.as_posix()}`",
        "",
        "| config | recall@1 | recall@3 | mrr | ndcg@3 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in retrieval_report["summary"].items():
        lines.append(
            f"| {name} | {metrics['recall_at_1']:.4f} | {metrics['recall_at_3']:.4f} | "
            f"{metrics['mrr']:.4f} | {metrics['ndcg_at_3']:.4f} |"
        )

    lines.extend(["", "## Online Grounded Eval", ""])
    if online_report is None:
        lines.extend(
            [
                "- Status: `skipped`",
                "- Reason: run with `--online --corpus-id kb:<KB_ID> --password <ADMIN_PASSWORD>` after uploading the PoC corpus.",
            ]
        )
    else:
        overall = online_report["summary"]["overall"]
        lines.extend(
            [
                f"- Report: `{online_summary_path.as_posix()}`",
                "",
                "| metric | value |",
                "| --- | ---: |",
                f"| correctness | {overall['correctness']:.4f} |",
                f"| citation alignment | {overall['citation_alignment']:.4f} |",
                f"| faithfulness | {overall['faithfulness']:.4f} |",
                f"| refusal precision | {overall['refusal']['precision']:.4f} |",
                f"| refusal recall | {overall['refusal']['recall']:.4f} |",
            ]
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the enterprise policy trusted-QA PoC checks.")
    parser.add_argument("--retrieval-fixture", type=Path, default=DEFAULT_RETRIEVAL_FIXTURE)
    parser.add_argument("--online-fixture", type=Path, default=DEFAULT_ONLINE_FIXTURE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--online", action="store_true", help="also run online grounded eval against an existing KB")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--email", default="admin@local")
    parser.add_argument("--password", default="")
    parser.add_argument("--corpus-id", action="append", default=[], help="repeatable; expected format: kb:<uuid>")
    parser.add_argument("--execution-mode", choices=["grounded", "agent"], default="grounded")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_dir = args.report_dir
    retrieval_json = report_dir / "enterprise_policy_poc_retrieval.json"
    retrieval_md = report_dir / "enterprise_policy_poc_retrieval.md"
    online_json = report_dir / "enterprise_policy_poc_online.json"
    online_md = report_dir / "enterprise_policy_poc_online.md"
    summary_md = report_dir / "enterprise_policy_poc_summary.md"

    retrieval_report = run_retrieval_ablation(
        fixture=args.retrieval_fixture,
        output=retrieval_json,
        summary_output=retrieval_md,
    )
    online_report = None
    if args.online:
        if not args.password:
            raise RuntimeError("--password is required when --online is set")
        if not args.corpus_id:
            raise RuntimeError("--corpus-id kb:<KB_ID> is required when --online is set")
        online_report = run_online_eval(
            base_url=args.base_url,
            email=args.email,
            password=args.password,
            eval_file=args.online_fixture,
            corpus_ids=list(args.corpus_id),
            output=online_json,
            summary_output=online_md,
            execution_mode=args.execution_mode,
        )

    write_poc_summary(
        output=summary_md,
        retrieval_report=retrieval_report,
        retrieval_summary_path=retrieval_md,
        online_report=online_report,
        online_summary_path=online_md,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "offline_retrieval_report": str(retrieval_json.resolve()),
                "offline_retrieval_summary": str(retrieval_md.resolve()),
                "online_eval_report": str(online_json.resolve()) if online_report else "",
                "online_eval_summary": str(online_md.resolve()) if online_report else "",
                "summary": str(summary_md.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

