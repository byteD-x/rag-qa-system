from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status


def _read_env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        candidate = raw.strip()
        if candidate:
            return candidate
    return default


def _read_bool(*names: str, default: bool) -> bool:
    raw = _read_env(*names, default="")
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _read_float(*names: str, default: float) -> float:
    raw = _read_env(*names, default="")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_int(*names: str, default: int) -> int:
    raw = _read_env(*names, default="")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_extra_body(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM_EXTRA_BODY_JSON is not valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM_EXTRA_BODY_JSON must be a JSON object",
        )
    return payload


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    parts.append(cleaned)
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
                continue
            if item.get("type") == "text":
                nested_text = item.get("text")
                if isinstance(nested_text, str) and nested_text.strip():
                    parts.append(nested_text.strip())
        return "\n".join(parts).strip()
    return ""


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    default_temperature: float
    default_max_tokens: int
    system_prompt: str
    extra_body: dict[str, Any]

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.base_url and self.api_key and self.model)

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def load_llm_settings() -> LLMSettings:
    api_key = _read_env("LLM_API_KEY", "AI_API_KEY", "DASHSCOPE_API_KEY")
    return LLMSettings(
        enabled=_read_bool("LLM_ENABLED", "AI_CHAT_ENABLED", default=True),
        provider=_read_env("LLM_PROVIDER", "AI_PROVIDER", default="openai-compatible"),
        base_url=_read_env("LLM_BASE_URL", "AI_BASE_URL").rstrip("/"),
        api_key=api_key,
        model=_read_env("LLM_MODEL", "AI_MODEL"),
        timeout_seconds=max(_read_float("LLM_TIMEOUT_SECONDS", "AI_CHAT_TIMEOUT_SECONDS", default=120.0), 10.0),
        default_temperature=min(max(_read_float("LLM_TEMPERATURE", "AI_DEFAULT_TEMPERATURE", default=0.7), 0.0), 2.0),
        default_max_tokens=max(_read_int("LLM_MAX_TOKENS", "AI_DEFAULT_MAX_TOKENS", default=2048), 128),
        system_prompt=_read_env("LLM_SYSTEM_PROMPT", "AI_SYSTEM_PROMPT"),
        extra_body=_parse_extra_body(_read_env("LLM_EXTRA_BODY_JSON", "AI_EXTRA_BODY_JSON", default="{}")),
    )


async def create_llm_completion(
    *,
    settings: LLMSettings,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM answer generation is disabled",
        )
    if not settings.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM answer generation is not configured",
        )

    request_body: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "temperature": settings.default_temperature if temperature is None else temperature,
        "max_tokens": settings.default_max_tokens if max_tokens is None else max_tokens,
    }
    if settings.extra_body:
        request_body.update(settings.extra_body)

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(settings.timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(settings.chat_url, headers=headers, json=request_body)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="upstream LLM provider is unavailable",
            ) from exc

    if response.status_code >= 400:
        provider_error = ""
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict):
            if isinstance(data.get("error"), dict):
                provider_error = str(data["error"].get("message", "")).strip()
            elif data.get("message"):
                provider_error = str(data["message"]).strip()
        detail = provider_error or f"upstream LLM provider returned {response.status_code}"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="upstream LLM provider returned no choices",
        )

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    message = message if isinstance(message, dict) else {}
    answer = _extract_text_content(message.get("content"))
    reasoning = _extract_text_content(message.get("reasoning_content"))
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="upstream LLM provider returned an empty answer",
        )

    return {
        "answer": answer,
        "reasoning": reasoning,
        "model": str(payload.get("model") or settings.model),
        "provider": settings.provider,
        "finish_reason": str(choice.get("finish_reason", "") or ""),
        "usage": payload.get("usage") if isinstance(payload, dict) else {},
    }
