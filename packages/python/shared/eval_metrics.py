from __future__ import annotations

import math
from statistics import mean


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    rank = max(0.0, min(1.0, p / 100.0)) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[lower], 4)
    weight = rank - lower
    return round((ordered[lower] * (1.0 - weight)) + (ordered[upper] * weight), 4)


def recall_at_k(relevance: list[int], k: int) -> float:
    if not relevance or k <= 0:
        return 0.0
    positives = sum(1 for item in relevance if item > 0)
    if positives <= 0:
        return 0.0
    hits = sum(1 for item in relevance[:k] if item > 0)
    return round(hits / positives, 4)


def reciprocal_rank(relevance: list[int]) -> float:
    for index, item in enumerate(relevance, start=1):
        if item > 0:
            return round(1.0 / float(index), 4)
    return 0.0


def ndcg_at_k(relevance: list[int], k: int) -> float:
    if not relevance or k <= 0:
        return 0.0
    dcg = 0.0
    for index, item in enumerate(relevance[:k], start=1):
        if item <= 0:
            continue
        dcg += float(item) / math.log2(index + 1)
    ideal = sorted((item for item in relevance if item > 0), reverse=True)[:k]
    if not ideal:
        return 0.0
    idcg = 0.0
    for index, item in enumerate(ideal, start=1):
        idcg += float(item) / math.log2(index + 1)
    if idcg <= 0:
        return 0.0
    return round(dcg / idcg, 4)


def precision(relevant_hits: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(relevant_hits) / float(total), 4)


def summarize_latencies(latencies_ms: list[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"count": 0.0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": float(len(latencies_ms)),
        "mean_ms": round(mean(latencies_ms), 4),
        "p50_ms": percentile(latencies_ms, 50),
        "p95_ms": percentile(latencies_ms, 95),
        "max_ms": round(max(latencies_ms), 4),
    }


def refusal_scores(*, true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    return {
        "precision": precision(true_positive, true_positive + false_positive),
        "recall": precision(true_positive, true_positive + false_negative),
    }
