from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any


class RouteDecision(dict):
    @property
    def route_key(self) -> str:
        return str(self.get("route_key") or "")


def resolve_model_route(
    settings: Any,
    route_key: str,
    *,
    default_model: str | None = None,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> RouteDecision:
    routes = getattr(settings, "model_routing", {}) or {}
    route = dict(routes.get(route_key, {}) or {})
    extra_body = route.get("extra_body")
    return RouteDecision(
        route_key=route_key,
        applied=bool(route),
        provider=str(route.get("provider") or getattr(settings, "provider", "")),
        base_url=str(route.get("base_url") or getattr(settings, "base_url", "")),
        api_key=str(route.get("api_key") or getattr(settings, "api_key", "")),
        model=str(route.get("model") or default_model or getattr(settings, "model", "")),
        temperature=float(
            route["temperature"]
            if route.get("temperature") is not None
            else default_temperature
            if default_temperature is not None
            else getattr(settings, "default_temperature", 0.0)
        ),
        max_tokens=int(
            route["max_tokens"]
            if route.get("max_tokens") is not None
            else default_max_tokens
            if default_max_tokens is not None
            else getattr(settings, "default_max_tokens", 0)
        ),
        timeout_seconds=float(route.get("timeout_seconds") or getattr(settings, "timeout_seconds", 0.0)),
        extra_body=dict(extra_body) if isinstance(extra_body, dict) else dict(getattr(settings, "extra_body", {}) or {}),
    )


def settings_with_model_route(
    settings: Any,
    route_key: str,
    *,
    default_model: str | None = None,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> tuple[Any, RouteDecision]:
    decision = resolve_model_route(
        settings,
        route_key,
        default_model=default_model,
        default_temperature=default_temperature,
        default_max_tokens=default_max_tokens,
    )
    if is_dataclass(settings):
        routed_settings = replace(
            settings,
            provider=decision["provider"],
            base_url=decision["base_url"],
            api_key=decision["api_key"],
            model=decision["model"],
            timeout_seconds=decision["timeout_seconds"],
            default_temperature=decision["temperature"],
            default_max_tokens=decision["max_tokens"],
            extra_body=decision["extra_body"],
        )
    else:
        proxy = type("RoutedSettings", (), {})()
        for key, value in vars(settings).items():
            setattr(proxy, key, value)
        for key in dir(settings):
            if key.startswith("_") or hasattr(proxy, key):
                continue
            setattr(proxy, key, getattr(settings, key))
        proxy.provider = decision["provider"]
        proxy.base_url = decision["base_url"]
        proxy.api_key = decision["api_key"]
        proxy.model = decision["model"]
        proxy.timeout_seconds = decision["timeout_seconds"]
        proxy.default_temperature = decision["temperature"]
        proxy.default_max_tokens = decision["max_tokens"]
        proxy.extra_body = decision["extra_body"]
        routed_settings = proxy
    return routed_settings, decision


__all__ = ["RouteDecision", "resolve_model_route", "settings_with_model_route"]
