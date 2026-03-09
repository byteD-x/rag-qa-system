from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import httpx

from .text_search import tokenize_text


EMBEDDING_DIM = 512


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    api_url: str
    api_key: str
    model: str
    timeout_seconds: float
    batch_size: int
    local_backend: str


def load_embedding_settings(prefix: str = "EMBEDDING") -> EmbeddingSettings:
    """Load embedding configuration from environment variables."""
    provider = (os.getenv(f"{prefix}_PROVIDER", "local").strip() or "local").lower()
    timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "60").strip()
    batch_raw = os.getenv(f"{prefix}_BATCH_SIZE", "64").strip()
    try:
        timeout_seconds = max(float(timeout_raw), 5.0)
    except ValueError:
        timeout_seconds = 60.0
    try:
        batch_size = max(int(batch_raw), 1)
    except ValueError:
        batch_size = 64
    return EmbeddingSettings(
        provider=provider,
        api_url=os.getenv(f"{prefix}_API_URL", "").strip(),
        api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
        model=os.getenv(f"{prefix}_MODEL", "local-projection-512").strip() or "local-projection-512",
        timeout_seconds=timeout_seconds,
        batch_size=batch_size,
        local_backend=(os.getenv(f"{prefix}_LOCAL_BACKEND", "projection").strip() or "projection").lower(),
    )


def vector_literal(values: Iterable[float]) -> str:
    """Convert a vector to pgvector literal syntax."""
    return "[" + ",".join(f"{float(item):.8f}" for item in values) + "]"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for two dense vectors."""
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for index in range(min(len(left), len(right))):
        l_value = float(left[index])
        r_value = float(right[index])
        dot += l_value * r_value
        left_norm += l_value * l_value
        right_norm += r_value * r_value
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


def stable_content_key(*parts: str) -> str:
    """Build a stable cache key from content and provider metadata."""
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update((part or "").encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def _settings_cache_key(settings: EmbeddingSettings) -> tuple[str, str, str, str, float, int]:
    return (
        settings.provider,
        settings.api_url,
        settings.model,
        settings.local_backend,
        float(settings.timeout_seconds),
        int(settings.batch_size),
    )


def embed_texts(texts: list[str], *, settings: EmbeddingSettings | None = None) -> list[list[float]]:
    """Embed a batch of texts using local or external providers.

    Input:
    - texts: Ordered text batch.
    - settings: Optional embedding configuration.

    Output:
    - Dense vector list aligned with the input order.

    Failure:
    - Raises RuntimeError when the external provider returns an invalid payload.
    """
    config = settings or load_embedding_settings()
    if config.provider == "external":
        return _embed_external(texts, config)
    return [_embed_local(text, config) for text in texts]


def embed_query_text(text: str, *, settings: EmbeddingSettings | None = None) -> list[float]:
    config = settings or load_embedding_settings()
    if not text.strip():
        return [0.0] * EMBEDDING_DIM
    cached = _embed_query_text_cached(_settings_cache_key(config), text)
    return list(cached)


def clear_query_embedding_cache() -> None:
    _embed_query_text_cached.cache_clear()


@lru_cache(maxsize=512)
def _embed_query_text_cached(settings_key: tuple[str, str, str, str, float, int], text: str) -> tuple[float, ...]:
    provider, api_url, model, local_backend, timeout_seconds, batch_size = settings_key
    settings = EmbeddingSettings(
        provider=provider,
        api_url=api_url,
        api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        model=model,
        timeout_seconds=timeout_seconds,
        batch_size=batch_size,
        local_backend=local_backend,
    )
    return tuple(embed_texts([text], settings=settings)[0])


def _embed_external(texts: list[str], settings: EmbeddingSettings) -> list[list[float]]:
    if not settings.api_url:
        raise RuntimeError("external embedding provider requires EMBEDDING_API_URL")
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    body = {
        "model": settings.model,
        "input": texts,
    }
    with httpx.Client(timeout=settings.timeout_seconds) as client:
        response = client.post(settings.api_url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("external embedding provider returned invalid payload")
    vectors: list[list[float]] = []
    for item in data:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list):
            raise RuntimeError("external embedding provider returned invalid embedding")
        values = [float(value) for value in vector[:EMBEDDING_DIM]]
        if len(values) < EMBEDDING_DIM:
            values.extend([0.0] * (EMBEDDING_DIM - len(values)))
        vectors.append(_normalize_vector(values))
    return vectors


def _embed_local(text: str, settings: EmbeddingSettings) -> list[float]:
    if settings.local_backend == "hash":
        return _embed_local_hash(text)
    if settings.local_backend == "projection":
        return _embed_local_projection(text)
    return _embed_local_hash(text)


def _embed_local_hash(text: str) -> list[float]:
    values = [0.0] * EMBEDDING_DIM
    tokens = tokenize_text(text, dedupe=False)
    if not tokens:
        return values
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:2], byteorder="big") % EMBEDDING_DIM
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        values[bucket] += sign
    return _normalize_vector(values)


def _embed_local_projection(text: str) -> list[float]:
    values = [0.0] * EMBEDDING_DIM
    tokens = tokenize_text(text, dedupe=False)
    if not tokens:
        return values
    token_count = float(len(tokens))
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for index in range(EMBEDDING_DIM):
            byte = digest[index % len(digest)]
            values[index] += ((float(byte) / 255.0) * 2.0 - 1.0) / math.sqrt(token_count)
    return _normalize_vector(values)


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]
