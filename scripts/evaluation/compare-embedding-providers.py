#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages/python"))

from shared.embeddings import EmbeddingSettings, cosine_similarity, embed_texts
from shared.eval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank


def _build_local_settings(backend: str) -> EmbeddingSettings:
    return EmbeddingSettings(
        provider="local",
        api_url="",
        api_key="",
        model=f"local-{backend}-512",
        timeout_seconds=60.0,
        batch_size=64,
        local_backend=backend,
    )


def _build_external_settings(args: argparse.Namespace) -> EmbeddingSettings | None:
    api_url = args.external_api_url.strip()
    model = args.external_model.strip()
    if not api_url or not model:
        return None
    return EmbeddingSettings(
        provider="external",
        api_url=api_url,
        api_key=args.external_api_key,
        model=model,
        timeout_seconds=max(args.external_timeout_seconds, 10.0),
        batch_size=max(args.external_batch_size, 1),
        local_backend="projection",
    )


def _score_metrics(expected_unit_ids: set[str], ranked_unit_ids: list[str]) -> dict[str, float]:
    relevance = [1 if unit_id in expected_unit_ids else 0 for unit_id in ranked_unit_ids]
    return {
        "recall_at_1": recall_at_k(relevance, 1),
        "recall_at_3": recall_at_k(relevance, 3),
        "mrr": reciprocal_rank(relevance),
        "ndcg_at_3": ndcg_at_k(relevance, 3),
    }


def _average(rows: list[dict[str, float]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(item[key]) for item in rows) / len(rows), 4)


def _candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        part.strip()
        for part in (
            str(candidate.get("document_title") or ""),
            str(candidate.get("section_title") or ""),
            str(candidate.get("chapter_title") or ""),
            str(candidate.get("quote") or candidate.get("raw_text") or ""),
        )
        if part and part.strip()
    )


def _rank_case(case: dict[str, Any], *, settings: EmbeddingSettings) -> dict[str, Any]:
    candidates = list(case.get("candidates", []) or [])
    texts = [str(case.get("question") or ""), *[_candidate_text(item) for item in candidates]]
    vectors = embed_texts(texts, settings=settings)
    question_vector = vectors[0]
    ranked = sorted(
        (
            {
                "unit_id": str(candidate["unit_id"]),
                "score": round(cosine_similarity(question_vector, vectors[index + 1]), 6),
            }
            for index, candidate in enumerate(candidates)
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    metrics = _score_metrics({str(item) for item in case.get("expected_unit_ids", [])}, [item["unit_id"] for item in ranked])
    return {
        "id": str(case.get("id") or ""),
        "question": str(case.get("question") or ""),
        "top_units": [item["unit_id"] for item in ranked[:3]],
        "top_scores": [item["score"] for item in ranked[:3]],
        **metrics,
    }


def _evaluate_backend(cases: list[dict[str, Any]], *, settings: EmbeddingSettings, label: str) -> dict[str, Any]:
    details = [_rank_case(case, settings=settings) for case in cases]
    summary = {
        "recall_at_1": _average(details, "recall_at_1"),
        "recall_at_3": _average(details, "recall_at_3"),
        "mrr": _average(details, "mrr"),
        "ndcg_at_3": _average(details, "ndcg_at_3"),
    }
    return {
        "label": label,
        "settings": asdict(settings),
        "summary": summary,
        "details": details,
    }


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Embedding Retrieval Benchmark",
        "",
        "| backend | recall@1 | recall@3 | mrr | ndcg@3 | notes |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["backends"]:
        if item.get("skipped"):
            lines.append(
                f"| {item['label']} | 0.0000 | 0.0000 | 0.0000 | 0.0000 | skipped: {item['reason']} |"
            )
            continue
        summary = item["summary"]
        lines.append(
            f"| {item['label']} | {summary['recall_at_1']:.4f} | {summary['recall_at_3']:.4f} | "
            f"{summary['mrr']:.4f} | {summary['ndcg_at_3']:.4f} | provider `{item['settings']['provider']}` model `{item['settings']['model']}` |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare embedding backends with an embedding-only retrieval ranking benchmark.")
    parser.add_argument("--fixture", default="tests/fixtures/evals/retrieval-ablation-fixture.json")
    parser.add_argument("--output", default="artifacts/reports/embedding_retrieval_benchmark.json")
    parser.add_argument("--summary-output", default="artifacts/reports/embedding_retrieval_benchmark.md")
    parser.add_argument("--skip-local-hash", action="store_true")
    parser.add_argument("--with-external", action="store_true")
    parser.add_argument("--external-api-url", default="")
    parser.add_argument("--external-api-key", default="")
    parser.add_argument("--external-model", default="")
    parser.add_argument("--external-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--external-batch-size", type=int, default=32)
    args = parser.parse_args()

    cases = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    backends: list[dict[str, Any]] = []
    backends.append(_evaluate_backend(cases, settings=_build_local_settings("projection"), label="local-projection"))
    if not args.skip_local_hash:
        backends.append(_evaluate_backend(cases, settings=_build_local_settings("hash"), label="local-hash"))

    if args.with_external:
        external_settings = _build_external_settings(args)
        if external_settings is None:
            backends.append(
                {
                    "label": "external",
                    "skipped": True,
                    "reason": "missing --external-api-url or --external-model",
                }
            )
        else:
            try:
                backends.append(_evaluate_backend(cases, settings=external_settings, label=f"external:{external_settings.model}"))
            except Exception as exc:  # pragma: no cover - network/config failure path
                backends.append(
                    {
                        "label": f"external:{external_settings.model}",
                        "skipped": True,
                        "reason": str(exc),
                    }
                )

    report = {
        "fixture": str(Path(args.fixture).resolve()),
        "backends": backends,
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
