#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages/python"))

from shared.eval_metrics import ndcg_at_k, recall_at_k_ids, reciprocal_rank
from shared.query_rewrite import rewrite_query
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath, weighted_rrf
from shared.text_search import score_term_overlap


FUSION_WEIGHTS = {
    "baseline": {"structure": 1.3, "fts": 1.0, "vector": 0.9},
    "rewrite": {"structure": 1.3, "fts": 1.0, "vector": 0.9, "rewrite": 0.6},
}


def build_blocks(case: dict[str, Any]) -> list[EvidenceBlock]:
    blocks: list[EvidenceBlock] = []
    for item in case.get("candidates", []):
        blocks.append(
            EvidenceBlock(
                unit_id=str(item["unit_id"]),
                document_id=str(item["unit_id"]),
                document_title=str(item.get("document_title") or ""),
                section_title=str(item.get("section_title") or ""),
                chapter_title=str(item.get("chapter_title") or ""),
                quote=str(item.get("quote") or ""),
                raw_text=str(item.get("raw_text") or ""),
                signal_scores={key: float(value) for key, value in dict(item.get("signal_scores") or {}).items()},
                evidence_path=EvidencePath(),
            )
        )
    return blocks


def rank_case(case: dict[str, Any], *, enable_rewrite: bool, enable_rerank: bool) -> list[EvidenceBlock]:
    blocks = build_blocks(case)
    rewrite = rewrite_query(str(case["question"]))
    ranked_lists: dict[str, list[str]] = {}

    for signal in ("structure", "fts", "vector"):
        ranked_lists[signal] = [
            block.unit_id
            for block in sorted(blocks, key=lambda item: item.signal_scores.get(signal, 0.0), reverse=True)
            if block.signal_scores.get(signal, 0.0) > 0
        ]

    if enable_rewrite:
        ranked_lists["rewrite"] = [
            block.unit_id
            for block in sorted(
                blocks,
                key=lambda item: score_term_overlap(rewrite.focus_query or rewrite.retrieval_query, f"{item.section_title} {item.raw_text}"),
                reverse=True,
            )
            if score_term_overlap(rewrite.focus_query or rewrite.retrieval_query, f"{block.section_title} {block.raw_text}") > 0
        ]

    weights = FUSION_WEIGHTS["rewrite" if enable_rewrite else "baseline"]
    fused = weighted_rrf(ranked_lists, weights=weights)
    ordered = [
        block
        for block in sorted(
            blocks,
            key=lambda item: fused.get(item.unit_id, 0.0),
            reverse=True,
        )
        if block.unit_id in fused
    ]

    with_scores = [
        EvidenceBlock(
            unit_id=block.unit_id,
            document_id=block.document_id,
            document_title=block.document_title,
            section_title=block.section_title,
            chapter_title=block.chapter_title,
            quote=block.quote,
            raw_text=block.raw_text,
            signal_scores={**block.signal_scores, "fusion": round(fused.get(block.unit_id, 0.0), 6)},
            evidence_path=EvidencePath(final_score=round(fused.get(block.unit_id, 0.0), 6)),
        )
        for block in ordered
    ]

    if not enable_rerank:
        return with_scores

    reranked, _ = rerank_evidence_blocks(
        str(case["question"]),
        with_scores[: max(3, len(with_scores))],
        focus_query=rewrite.focus_query,
        limit=len(with_scores),
    )
    return reranked


def score_ranking(case: dict[str, Any], ranked: list[EvidenceBlock]) -> dict[str, Any]:
    expected = {str(item) for item in case.get("expected_unit_ids", [])}
    relevance = [1 if block.unit_id in expected else 0 for block in ranked]
    ranked_ids = [block.unit_id for block in ranked]
    return {
        "recall_at_1": recall_at_k_ids(expected, ranked_ids, 1),
        "recall_at_3": recall_at_k_ids(expected, ranked_ids, 3),
        "mrr": reciprocal_rank(relevance),
        "ndcg_at_3": ndcg_at_k(relevance, 3),
    }


def average_metric(rows: list[dict[str, float]], name: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(item[name]) for item in rows) / len(rows), 4)


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Retrieval Ablation Report",
        "",
        "| config | recall@1 | recall@3 | mrr | ndcg@3 | notes |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, metrics in report["summary"].items():
        if metrics.get("skipped"):
            lines.append(f"| {name} | - | - | - | - | skipped: {metrics['reason']} |")
            continue
        lines.append(
            f"| {name} | {metrics['recall_at_1']:.4f} | {metrics['recall_at_3']:.4f} | "
            f"{metrics['mrr']:.4f} | {metrics['ndcg_at_3']:.4f} | - |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evaluate_config(
    cases: list[dict[str, Any]],
    *,
    enable_rewrite: bool,
    enable_rerank: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        ranked = rank_case(case, enable_rewrite=enable_rewrite, enable_rerank=enable_rerank)
        metrics = score_ranking(case, ranked)
        rows.append(
            {
                "id": str(case["id"]),
                "question": str(case["question"]),
                "top_units": [block.unit_id for block in ranked[:3]],
                **metrics,
            }
        )
    return (
        {
            "recall_at_1": average_metric(rows, "recall_at_1"),
            "recall_at_3": average_metric(rows, "recall_at_3"),
            "mrr": average_metric(rows, "mrr"),
            "ndcg_at_3": average_metric(rows, "ndcg_at_3"),
        },
        rows,
    )


def _with_rerank_environment(
    *,
    api_url: str,
    api_key: str,
    model: str,
) -> dict[str, str | None]:
    names = ("RERANK_PROVIDER", "RERANK_API_BASE_URL", "RERANK_API_KEY", "RERANK_MODEL")
    previous = {name: os.environ.get(name) for name in names}
    os.environ["RERANK_PROVIDER"] = "external-cross-encoder"
    os.environ["RERANK_API_BASE_URL"] = api_url.rstrip("/")
    os.environ["RERANK_API_KEY"] = api_key
    os.environ["RERANK_MODEL"] = model
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline retrieval ablation against a deterministic fixture dataset.")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output", default="artifacts/reports/retrieval_ablation_report.json")
    parser.add_argument("--summary-output", default="artifacts/reports/retrieval_ablation_report.md")
    parser.add_argument("--with-cross-encoder", action="store_true")
    parser.add_argument("--cross-encoder-api-url", default="")
    parser.add_argument("--cross-encoder-api-key", default="")
    parser.add_argument("--cross-encoder-model", default="qwen3-rerank")
    args = parser.parse_args()

    cases = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    configs = {
        "fusion_only": {"enable_rewrite": False, "enable_rerank": False},
        "rewrite_plus_fusion": {"enable_rewrite": True, "enable_rerank": False},
        "rewrite_plus_fusion_plus_rerank": {"enable_rewrite": True, "enable_rerank": True},
    }
    details: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, dict[str, Any]] = {}

    baseline_env = {name: os.environ.get(name) for name in ("RERANK_PROVIDER", "RERANK_API_BASE_URL", "RERANK_API_KEY", "RERANK_MODEL")}
    os.environ["RERANK_PROVIDER"] = "heuristic"
    try:
        for name, config in configs.items():
            metrics, rows = _evaluate_config(cases, **config)
            details[name] = rows
            summary[name] = metrics
    finally:
        _restore_environment(baseline_env)

    if args.with_cross_encoder:
        cross_name = f"rewrite_plus_fusion_plus_cross_encoder:{args.cross_encoder_model}"
        if not args.cross_encoder_api_url or not args.cross_encoder_api_key:
            summary[cross_name] = {"skipped": True, "reason": "missing cross-encoder API URL or API key"}
            details[cross_name] = []
        else:
            previous_env = _with_rerank_environment(
                api_url=args.cross_encoder_api_url,
                api_key=args.cross_encoder_api_key,
                model=args.cross_encoder_model,
            )
            try:
                metrics, rows = _evaluate_config(
                    cases,
                    enable_rewrite=True,
                    enable_rerank=True,
                )
            except Exception as exc:  # pragma: no cover - external service failure path
                summary[cross_name] = {"skipped": True, "reason": str(exc)}
                details[cross_name] = []
            else:
                summary[cross_name] = metrics
                details[cross_name] = rows
            finally:
                _restore_environment(previous_env)

    baseline = summary.get("fusion_only")
    if isinstance(baseline, dict) and not baseline.get("skipped"):
        for metrics in summary.values():
            if metrics.get("skipped"):
                continue
            metrics["delta_vs_fusion_only"] = {
                key: round(float(metrics[key]) - float(baseline[key]), 4)
                for key in ("recall_at_1", "recall_at_3", "mrr", "ndcg_at_3")
            }

    report = {
        "fixture": str(Path(args.fixture).resolve()),
        "summary": summary,
        "details": details,
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
