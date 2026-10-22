from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .retrieval import EvidenceBlock
from .text_search import normalize_text


_EXACT_TOKEN_RE = re.compile(r"(?<![a-z0-9])[a-z0-9][a-z0-9_.:/-]{2,}(?![a-z0-9])")


@dataclass(frozen=True)
class JEVSettings:
    enabled: bool
    api_url: str
    api_key: str
    model: str
    timeout_seconds: float
    batch_size: int
    high_threshold: float
    low_threshold: float

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.api_url and self.api_key)


@dataclass(frozen=True)
class GateDebug:
    unit_id: str
    probability: float | None
    action: str
    provider: str


@dataclass(frozen=True)
class GateMeta:
    evaluated_candidates: int = 0
    kept_candidates: int = 0
    dropped_candidates: int = 0
    remote_calls: int = 0
    provider: str = "disabled"
    warning: str = ""


def _read_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _read_bool(name: str, *, default: bool) -> bool:
    value = _read_env(name, default="")
    return default if not value else value.lower() in {"1", "true", "yes", "on"}


def _read_float(name: str, *, default: float) -> float:
    try:
        return float(_read_env(name, default=str(default)))
    except ValueError:
        return default


def _read_int(name: str, *, default: int) -> int:
    try:
        return int(_read_env(name, default=str(default)))
    except ValueError:
        return default


def load_jev_settings() -> JEVSettings:
    low_threshold = min(max(_read_float("JEV_LOW_THRESHOLD", default=0.35), 0.0), 1.0)
    high_threshold = min(max(_read_float("JEV_HIGH_THRESHOLD", default=0.75), 0.0), 1.0)
    if high_threshold < low_threshold:
        high_threshold = low_threshold
    return JEVSettings(
        enabled=_read_bool("JEV_ENABLED", default=False),
        api_url=_read_env("JEV_API_URL", "JEV_API_BASE_URL"),
        api_key=_read_env("JEV_API_KEY"),
        model=_read_env("JEV_MODEL", default="system-one"),
        timeout_seconds=max(_read_float("JEV_TIMEOUT_SECONDS", default=2.0), 0.1),
        batch_size=max(_read_int("JEV_BATCH_SIZE", default=30), 1),
        high_threshold=high_threshold,
        low_threshold=low_threshold,
    )


def gate_evidence_blocks(
    question: str,
    items: list[EvidenceBlock],
    *,
    settings: JEVSettings | None = None,
) -> tuple[list[EvidenceBlock], list[GateDebug], GateMeta]:
    """Gate reranked evidence with deterministic checks and optional JEV scoring."""
    if not items:
        return [], [], GateMeta()
    resolved_settings = settings or load_jev_settings()
    if not resolved_settings.enabled:
        return (
            list(items),
            [GateDebug(item.unit_id, None, "disabled", "disabled") for item in items],
            GateMeta(evaluated_candidates=len(items), kept_candidates=len(items)),
        )
    if not resolved_settings.configured:
        return (
            list(items),
            [GateDebug(item.unit_id, None, "fallback", "disabled") for item in items],
            GateMeta(
                evaluated_candidates=len(items),
                kept_candidates=len(items),
                provider="disabled",
                warning="jev_not_configured",
            ),
        )

    probabilities: dict[str, float] = {}
    debug: dict[str, GateDebug] = {}
    unresolved: list[EvidenceBlock] = []
    deterministic_matches = {
        item.unit_id for item in items if _deterministic_probability(question, item) is not None
    }
    unique_exact_match = len(deterministic_matches) == 1
    for item in items:
        deterministic = _deterministic_probability(question, item)
        if deterministic is not None:
            probabilities[item.unit_id] = deterministic
            debug[item.unit_id] = GateDebug(item.unit_id, deterministic, "keep", "deterministic")
        elif unique_exact_match:
            probabilities[item.unit_id] = 0.0
            debug[item.unit_id] = GateDebug(item.unit_id, 0.0, "drop", "deterministic")
        else:
            unresolved.append(item)

    remote_calls = 0
    warning = ""
    if unresolved:
        try:
            for start in range(0, len(unresolved), resolved_settings.batch_size):
                batch = unresolved[start : start + resolved_settings.batch_size]
                probabilities.update(_request_scores(question, batch, resolved_settings))
                remote_calls += 1
        except Exception:
            warning = "jev_unavailable"
            for item in unresolved:
                debug[item.unit_id] = GateDebug(item.unit_id, None, "fallback", "fallback")

    kept: list[EvidenceBlock] = []
    for item in items:
        if item.unit_id in debug and debug[item.unit_id].action == "fallback":
            kept.append(item)
            continue
        probability = probabilities.get(item.unit_id)
        if probability is None:
            debug[item.unit_id] = GateDebug(item.unit_id, None, "fallback", "fallback")
            kept.append(item)
            warning = warning or "jev_missing_score"
            continue
        probability = min(max(float(probability), 0.0), 1.0)
        action = "keep" if probability >= resolved_settings.high_threshold else "deprioritize"
        if probability < resolved_settings.low_threshold:
            action = "drop"
        debug[item.unit_id] = GateDebug(item.unit_id, round(probability, 6), action, "jev")
        if action != "drop":
            kept.append(item)

    provider = "jev" if remote_calls else "deterministic"
    return (
        kept,
        [debug[item.unit_id] for item in items],
        GateMeta(
            evaluated_candidates=len(items),
            kept_candidates=len(kept),
            dropped_candidates=len(items) - len(kept),
            remote_calls=remote_calls,
            provider=provider,
            warning=warning,
        ),
    )


def _deterministic_probability(question: str, item: EvidenceBlock) -> float | None:
    query = normalize_text(question)
    target = normalize_text(
        f"{item.document_title} {item.section_title} {item.quote or item.raw_text}"
    )
    if query and query in target:
        return 1.0
    exact_tokens = [token.strip("._:/-") for token in _EXACT_TOKEN_RE.findall(query)]
    exact_tokens = [token for token in exact_tokens if token]
    if exact_tokens and all(token in target for token in exact_tokens):
        return 1.0
    return None


def _request_scores(
    question: str,
    items: list[EvidenceBlock],
    settings: JEVSettings,
) -> dict[str, float]:
    body: dict[str, Any] = {
        "model": settings.model,
        "state": {"query": question},
        "questions": [
            {
                "id": item.unit_id,
                "question": "这段内容是否能够直接帮助回答用户问题？",
                "candidate": {
                    "title": item.document_title,
                    "section": item.section_title,
                    "text": item.raw_text or item.quote,
                },
            }
            for item in items
        ],
    }
    with httpx.Client(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = client.post(
            settings.api_url,
            headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
            json=body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"JEV provider returned {response.status_code}")
    payload = response.json()
    return _parse_scores(payload)


def _parse_scores(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise RuntimeError("JEV provider returned an invalid payload")
    raw_results = payload.get("results") or payload.get("questions") or payload.get("scores")
    scores: dict[str, float] = {}
    if isinstance(raw_results, dict):
        for unit_id, raw_score in raw_results.items():
            probability = _probability_from_value(raw_score)
            if probability is not None:
                scores[str(unit_id)] = probability
    elif isinstance(raw_results, list):
        for result in raw_results:
            if not isinstance(result, dict):
                continue
            unit_id = str(result.get("id") or result.get("unit_id") or result.get("question_id") or "").strip()
            probability = _probability_from_value(result)
            if unit_id and probability is not None:
                scores[unit_id] = probability
    if not scores:
        raise RuntimeError("JEV provider returned no scores")
    return scores


def _probability_from_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None
    for key in ("yes_probability", "probability", "score", "yes_prob"):
        candidate = value.get(key)
        if isinstance(candidate, (int, float)):
            return float(candidate)
    judgment = str(value.get("judgment") or value.get("answer") or "").strip().lower()
    if judgment in {"yes", "y", "true", "是", "相关", "relevant"}:
        return 1.0
    if judgment in {"no", "n", "false", "否", "不相关", "irrelevant"}:
        return 0.0
    return None
