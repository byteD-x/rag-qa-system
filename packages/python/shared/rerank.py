from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .retrieval import EvidenceBlock
from .text_search import normalize_text, score_term_overlap


@dataclass(frozen=True)
class RerankDebug:
    unit_id: str
    score: float
    provider: str = "heuristic"


@dataclass(frozen=True)
class RerankSettings:
    provider: str
    api_base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    top_n: int
    extra_body: dict[str, Any]

    @property
    def cross_encoder_configured(self) -> bool:
        return self.provider in {"cross-encoder", "external-cross-encoder"} and bool(
            self.api_base_url and self.api_key and self.model
        )


def _read_env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        candidate = raw.strip()
        if candidate:
            return candidate
    return default


def _read_int(*names: str, default: int) -> int:
    raw = _read_env(*names, default="")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_float(*names: str, default: float) -> float:
    raw = _read_env(*names, default="")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_extra_body(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_rerank_settings() -> RerankSettings:
    return RerankSettings(
        provider=_read_env("RERANK_PROVIDER", default="heuristic").lower(),
        api_base_url=_read_env("RERANK_API_BASE_URL", "LLM_BASE_URL", default="").rstrip("/"),
        api_key=_read_env("RERANK_API_KEY", "LLM_API_KEY", default=""),
        model=_read_env("RERANK_MODEL", default=""),
        timeout_seconds=max(_read_float("RERANK_TIMEOUT_SECONDS", default=20.0), 1.0),
        top_n=max(_read_int("RERANK_TOP_N", default=12), 1),
        extra_body=_parse_extra_body(_read_env("RERANK_EXTRA_BODY_JSON", default="{}")),
    )


def rerank_evidence_blocks(
    question: str,
    items: list[EvidenceBlock],
    *,
    focus_query: str = "",
    limit: int | None = None,
) -> tuple[list[EvidenceBlock], list[RerankDebug]]:
    if not items:
        return [], []

    primary = (focus_query or question or "").strip()
    settings = load_rerank_settings()
    scores, provider = _score_items(primary, items, settings=settings)
    ranked = sorted(items, key=lambda item: scores.get(item.unit_id, 0.0), reverse=True)
    if limit is not None:
        ranked = ranked[:limit]
    debug = [RerankDebug(unit_id=item.unit_id, score=round(scores.get(item.unit_id, 0.0), 6), provider=provider) for item in ranked]
    return ranked, debug


def _score_items(question: str, items: list[EvidenceBlock], *, settings: RerankSettings) -> tuple[dict[str, float], str]:
    heuristic_scores = {item.unit_id: _heuristic_rerank_score(question, item) for item in items}
    if not settings.cross_encoder_configured:
        return heuristic_scores, "heuristic"
    try:
        cross_encoder_scores = _external_cross_encoder_scores(question, items, settings=settings)
    except Exception:
        return heuristic_scores, "heuristic"
    if not cross_encoder_scores:
        return heuristic_scores, "heuristic"
    return cross_encoder_scores, "external-cross-encoder"


def _heuristic_rerank_score(question: str, item: EvidenceBlock) -> float:
    query = normalize_text(question)
    quote_text = f"{item.document_title} {item.section_title} {item.chapter_title} {item.quote or item.raw_text}"
    lexical = score_term_overlap(query, quote_text)
    title_boost = 0.0
    if query and query in normalize_text(f"{item.section_title} {item.chapter_title}"):
        title_boost += 1.5
    structure_boost = 1.0 if item.signal_scores.get("structure") else 0.0
    layout_boost = 0.75 if str(item.source_kind or "").startswith("visual") and any(
        token in query for token in ("table", "chart", "header", "footer", "row", "column", "表", "图", "页眉", "页脚")
    ) else 0.0
    fusion_score = float(item.evidence_path.final_score or 0.0)
    return round((fusion_score * 100.0) + lexical + title_boost + structure_boost + layout_boost, 6)


def _external_cross_encoder_scores(
    question: str,
    items: list[EvidenceBlock],
    *,
    settings: RerankSettings,
) -> dict[str, float]:
    documents = [
        {
            "id": item.unit_id,
            "text": f"{item.document_title}\n{item.section_title}\n{item.quote or item.raw_text}".strip(),
            "metadata": {
                "source_kind": item.source_kind,
                "page_number": item.page_number,
            },
        }
        for item in items[: settings.top_n]
    ]
    request_body: dict[str, Any] = {
        "model": settings.model,
        "query": question,
        "documents": documents,
        "top_n": len(documents),
    }
    if settings.extra_body:
        request_body.update(settings.extra_body)
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = client.post(f"{settings.api_base_url}/rerank", headers=headers, json=request_body)
    if response.status_code >= 400:
        raise RuntimeError(f"rerank provider returned {response.status_code}")
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise RuntimeError("rerank provider returned no results")
    scores: dict[str, float] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        unit_id = str(result.get("id") or result.get("document_id") or "").strip()
        if not unit_id:
            continue
        score = result.get("score")
        if not isinstance(score, (int, float)):
            continue
        scores[unit_id] = float(score)
    return scores
