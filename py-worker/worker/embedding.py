from __future__ import annotations

import hashlib
import time
from typing import List

import httpx

from worker.config import WorkerConfig


PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "ollama": "http://host.docker.internal:11434/v1",
}


def resolve_provider_base_url(provider: str, explicit_base_url: str) -> str:
    explicit = explicit_base_url.strip()
    if explicit:
        return explicit.rstrip("/")

    normalized = provider.strip().lower()
    if normalized == "custom":
        return ""

    return PROVIDER_BASE_URLS.get(normalized, PROVIDER_BASE_URLS["openai"])


class EmbeddingClient:
    def __init__(self, cfg: WorkerConfig):
        self._cfg = cfg
        self._base_url = resolve_provider_base_url(cfg.llm_provider, cfg.llm_base_url)
        self._client = httpx.Client(timeout=cfg.llm_timeout_seconds)

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.llm_api_key and self._cfg.llm_embedding_model and self._base_url)

    def embed(self, text: str) -> List[float]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be empty")

        if not self.enabled:
            return hash_embedding(normalized, self._cfg.embedding_dim)

        return self._request_embedding(normalized)

    def _request_embedding(self, text: str) -> List[float]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._cfg.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._cfg.llm_embedding_model,
            "input": text,
        }

        attempts = self._cfg.llm_max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    self._sleep_between_retries()
                    continue
                raise RuntimeError(f"embedding request failed: {exc}") from exc

            if resp.status_code >= 500 and attempt < attempts:
                self._sleep_between_retries()
                continue

            if resp.status_code >= 400:
                body = (resp.text or "").strip().replace("\n", " ")
                if len(body) > 300:
                    body = body[:300] + "..."
                raise RuntimeError(f"embedding request rejected: status={resp.status_code} body={body}")

            try:
                data = resp.json()
                vector_raw = data["data"][0]["embedding"]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise RuntimeError("embedding response format invalid") from exc

            if not isinstance(vector_raw, list) or len(vector_raw) == 0:
                raise RuntimeError("embedding response contains empty vector")

            try:
                return [float(v) for v in vector_raw]
            except (TypeError, ValueError) as exc:
                raise RuntimeError("embedding response contains non-numeric vector values") from exc

        raise RuntimeError("embedding request exhausted retries")

    def _sleep_between_retries(self) -> None:
        delay_ms = self._cfg.llm_retry_delay_milliseconds
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)


def hash_embedding(text: str, dim: int) -> List[float]:
    # Deterministic fallback embedding when no external model is configured.
    seed = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    values: List[float] = []
    counter = 0
    while len(values) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for b in block:
            values.append((b / 127.5) - 1.0)
            if len(values) >= dim:
                break
        counter += 1

    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return [0.0 for _ in values]
    return [v / norm for v in values]

