from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, status

from .ai_client import LLMSettings, load_llm_settings


DEFAULT_MAX_MODELS = 200


def llm_config_summary(settings: LLMSettings | None = None) -> dict[str, Any]:
    effective = settings or load_llm_settings()
    return {
        "enabled": effective.enabled,
        "configured": effective.configured,
        "provider": effective.provider,
        "base_url": effective.base_url,
        "api_key_configured": bool(effective.api_key),
        "current_model": effective.model,
        "common_knowledge_model": effective.common_knowledge_model,
        "model_routing": _summarize_model_routing(effective.model_routing),
    }


def _summarize_model_routing(routes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for route_key, route in (routes or {}).items():
        if not isinstance(route, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key in ("provider", "base_url", "model", "fallback_route_key", "temperature", "max_tokens", "timeout_seconds"):
            if route.get(key) not in ("", None):
                cleaned[key] = route[key]
        cleaned["api_key_configured"] = bool(route.get("api_key"))
        if cleaned:
            summary[str(route_key)] = cleaned
    return summary


def _normalize_base_url(raw_base_url: str) -> str:
    value = str(raw_base_url or "").strip().rstrip("/")
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LLM base_url is required")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LLM base_url must be an http(s) URL")

    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _models_url(base_url: str) -> str:
    return f"{_normalize_base_url(base_url)}/models"


def _provider_error_detail(response: httpx.Response) -> str:
    provider_error = ""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            provider_error = str(error.get("message") or "").strip()
        elif isinstance(payload.get("message"), str):
            provider_error = str(payload["message"]).strip()
    return provider_error or f"upstream model discovery returned status {response.status_code}"


def _normalize_model_item(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        model_id = raw.strip()
        return {"id": model_id, "object": "model", "owned_by": "", "created": None} if model_id else None
    if not isinstance(raw, dict):
        return None
    model_id = str(raw.get("id") or raw.get("name") or "").strip()
    if not model_id:
        return None
    created = raw.get("created")
    if not isinstance(created, int):
        created = None
    return {
        "id": model_id,
        "object": str(raw.get("object") or "model"),
        "owned_by": str(raw.get("owned_by") or raw.get("owner") or ""),
        "created": created,
    }


def _extract_models(payload: Any, *, max_models: int) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw_items = payload.get("data")
        if not isinstance(raw_items, list):
            raw_items = payload.get("models")
    else:
        raw_items = payload
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="upstream model discovery returned an invalid payload")

    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = _normalize_model_item(raw)
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        models.append(item)
        if len(models) >= max_models:
            break
    return models


async def discover_openai_compatible_models(
    *,
    provider: str = "",
    base_url: str = "",
    credential: str = "",
    max_models: int = DEFAULT_MAX_MODELS,
    settings: LLMSettings | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    effective = settings or load_llm_settings()
    resolved_provider = (provider or effective.provider or "openai-compatible").strip()
    resolved_base_url = (base_url or effective.base_url).strip()
    resolved_credential = (credential or effective.api_key).strip()
    if not resolved_credential:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LLM credential is required for model discovery")

    normalized_base_url = _normalize_base_url(resolved_base_url)
    url = _models_url(normalized_base_url)
    headers = {"Authorization": "Bearer " + resolved_credential, "Accept": "application/json"}
    max_items = min(max(int(max_models or DEFAULT_MAX_MODELS), 1), 1000)

    timeout = httpx.Timeout(min(max(float(effective.timeout_seconds or 30.0), 5.0), 30.0))
    client_context = client_factory() if client_factory is not None else httpx.AsyncClient(timeout=timeout)
    async with client_context as client:
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="upstream model discovery is unavailable") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_provider_error_detail(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="upstream model discovery returned non-JSON data") from exc

    models = _extract_models(payload, max_models=max_items)
    return {
        "provider": resolved_provider,
        "base_url": normalized_base_url,
        "models_url": url,
        "api_key_configured": True,
        "current_model": effective.model,
        "models": models,
        "count": len(models),
    }
