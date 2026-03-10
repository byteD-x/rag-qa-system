from __future__ import annotations

import inspect
import json
import os
from dataclasses import dataclass, field
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
            detail="LLM_EXTRA_BODY_JSON 不是有效的 JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM_EXTRA_BODY_JSON 必须为 JSON 对象",
        )
    return payload


def _parse_model_routing(raw: str) -> dict[str, dict[str, Any]]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM_MODEL_ROUTING_JSON 涓嶆槸鏈夋晥鐨?JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM_MODEL_ROUTING_JSON 蹇呴』涓?JSON 瀵硅薄",
        )
    routes: dict[str, dict[str, Any]] = {}
    for route_key, raw_definition in payload.items():
        if not isinstance(route_key, str) or not isinstance(raw_definition, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key in ("provider", "base_url", "api_key", "model"):
            value = raw_definition.get(key)
            if isinstance(value, str) and value.strip():
                cleaned[key] = value.strip()
        for key in ("temperature", "timeout_seconds"):
            value = raw_definition.get(key)
            if isinstance(value, (int, float)):
                cleaned[key] = float(value)
        value = raw_definition.get("max_tokens")
        if isinstance(value, (int, float)):
            cleaned["max_tokens"] = max(int(value), 1)
        extra_body = raw_definition.get("extra_body")
        if isinstance(extra_body, dict):
            cleaned["extra_body"] = extra_body
        if cleaned:
            routes[route_key.strip()] = cleaned
    return routes


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


def _extract_text_delta(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value:
                parts.append(text_value)
                continue
            if item.get("type") == "text":
                nested_text = item.get("text")
                if isinstance(nested_text, str) and nested_text:
                    parts.append(nested_text)
        return "".join(parts)
    return ""


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    model: str
    common_knowledge_model: str
    timeout_seconds: float
    default_temperature: float
    default_max_tokens: int
    common_knowledge_max_tokens: int
    common_knowledge_history_messages: int
    common_knowledge_history_chars: int
    system_prompt: str
    extra_body: dict[str, Any]
    model_routing: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.base_url and self.api_key and self.model)

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def load_llm_settings() -> LLMSettings:
    api_key = _read_env("LLM_API_KEY", "AI_API_KEY", "DASHSCOPE_API_KEY")
    default_max_tokens = max(_read_int("LLM_MAX_TOKENS", "AI_DEFAULT_MAX_TOKENS", default=2048), 128)
    common_knowledge_max_tokens = max(
        _read_int("LLM_COMMON_KNOWLEDGE_MAX_TOKENS", default=min(default_max_tokens, 512)),
        64,
    )
    return LLMSettings(
        enabled=_read_bool("LLM_ENABLED", "AI_CHAT_ENABLED", default=True),
        provider=_read_env("LLM_PROVIDER", "AI_PROVIDER", default="openai-compatible"),
        base_url=_read_env("LLM_BASE_URL", "AI_BASE_URL").rstrip("/"),
        api_key=api_key,
        model=_read_env("LLM_MODEL", "AI_MODEL"),
        common_knowledge_model=_read_env("LLM_COMMON_KNOWLEDGE_MODEL", default=""),
        timeout_seconds=max(_read_float("LLM_TIMEOUT_SECONDS", "AI_CHAT_TIMEOUT_SECONDS", default=120.0), 10.0),
        default_temperature=min(max(_read_float("LLM_TEMPERATURE", "AI_DEFAULT_TEMPERATURE", default=0.7), 0.0), 2.0),
        default_max_tokens=default_max_tokens,
        common_knowledge_max_tokens=min(common_knowledge_max_tokens, default_max_tokens),
        common_knowledge_history_messages=max(_read_int("LLM_COMMON_KNOWLEDGE_HISTORY_MESSAGES", default=4), 0),
        common_knowledge_history_chars=max(_read_int("LLM_COMMON_KNOWLEDGE_HISTORY_CHARS", default=400), 80),
        system_prompt=_read_env("LLM_SYSTEM_PROMPT", "AI_SYSTEM_PROMPT"),
        extra_body=_parse_extra_body(_read_env("LLM_EXTRA_BODY_JSON", "AI_EXTRA_BODY_JSON", default="{}")),
        model_routing=_parse_model_routing(_read_env("LLM_MODEL_ROUTING_JSON", "AI_MODEL_ROUTING_JSON", default="{}")),
    )


async def create_llm_completion(
    *,
    settings: LLMSettings,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 回答生成已禁用",
        )
    if not settings.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 回答生成未配置",
        )

    request_body: dict[str, Any] = {
        "model": (model or settings.model).strip(),
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
                detail="上游 LLM 服务不可用",
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
        detail = provider_error or f"上游 LLM 服务返回状态码 {response.status_code}"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="上游 LLM 服务未返回有效结果",
        )

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    message = message if isinstance(message, dict) else {}
    answer = _extract_text_content(message.get("content"))
    reasoning = _extract_text_content(message.get("reasoning_content"))
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="上游 LLM 服务返回了空回答",
        )

    return {
        "answer": answer,
        "reasoning": reasoning,
        "model": str(payload.get("model") or model or settings.model),
        "provider": settings.provider,
        "finish_reason": str(choice.get("finish_reason", "") or ""),
        "usage": payload.get("usage") if isinstance(payload, dict) else {},
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def create_llm_completion_stream(
    *,
    settings: LLMSettings,
    messages: list[dict[str, str]],
    on_text_delta: Any,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 回答生成已禁用",
        )
    if not settings.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 回答生成未配置",
        )

    request_body: dict[str, Any] = {
        "model": (model or settings.model).strip(),
        "messages": messages,
        "temperature": settings.default_temperature if temperature is None else temperature,
        "max_tokens": settings.default_max_tokens if max_tokens is None else max_tokens,
        "stream": True,
    }
    if settings.extra_body:
        request_body.update(settings.extra_body)
        request_body["stream"] = True

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(settings.timeout_seconds)
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict[str, Any] = {}
    resolved_model = (model or settings.model).strip()
    finish_reason = ""

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream("POST", settings.chat_url, headers=headers, json=request_body) as response:
                if response.status_code >= 400:
                    provider_error = ""
                    try:
                        data = await response.aread()
                        payload = json.loads(data.decode("utf-8")) if data else {}
                    except (ValueError, UnicodeDecodeError):
                        payload = {}
                    if isinstance(payload, dict):
                        if isinstance(payload.get("error"), dict):
                            provider_error = str(payload["error"].get("message", "")).strip()
                        elif payload.get("message"):
                            provider_error = str(payload["message"]).strip()
                    detail = provider_error or f"上游 LLM 服务返回状态码 {response.status_code}"
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

                content_type = (response.headers.get("content-type") or "").lower()
                if not content_type.startswith("text/event-stream"):
                    payload = json.loads((await response.aread()).decode("utf-8"))
                    choices = payload.get("choices") if isinstance(payload, dict) else None
                    if not isinstance(choices, list) or not choices:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="上游 LLM 服务未返回有效结果",
                        )
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    message_payload = choice.get("message") if isinstance(choice, dict) else {}
                    message_payload = message_payload if isinstance(message_payload, dict) else {}
                    answer = _extract_text_content(message_payload.get("content"))
                    reasoning = _extract_text_content(message_payload.get("reasoning_content"))
                    if not answer:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="上游 LLM 服务返回了空回答",
                        )
                    await _maybe_await(on_text_delta(answer, answer))
                    return {
                        "answer": answer,
                        "reasoning": reasoning,
                        "model": str(payload.get("model") or resolved_model),
                        "provider": settings.provider,
                        "finish_reason": str(choice.get("finish_reason", "") or ""),
                        "usage": payload.get("usage") if isinstance(payload, dict) else {},
                    }

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if isinstance(payload.get("usage"), dict):
                        usage = dict(payload["usage"])
                    resolved_model = str(payload.get("model") or resolved_model)
                    choices = payload.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice.get("delta") if isinstance(choice, dict) else {}
                    if not isinstance(delta, dict):
                        delta = {}
                    text_delta = _extract_text_delta(delta.get("content"))
                    reasoning_delta = _extract_text_delta(delta.get("reasoning_content"))
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                    if text_delta:
                        answer_parts.append(text_delta)
                        await _maybe_await(on_text_delta(text_delta, "".join(answer_parts)))
                    finish_reason = str(choice.get("finish_reason", "") or finish_reason)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="上游 LLM 服务不可用",
            ) from exc

    answer = "".join(answer_parts).strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="上游 LLM 服务返回了空回答",
        )

    return {
        "answer": answer,
        "reasoning": "".join(reasoning_parts).strip(),
        "model": resolved_model or settings.model,
        "provider": settings.provider,
        "finish_reason": finish_reason,
        "usage": usage,
    }
