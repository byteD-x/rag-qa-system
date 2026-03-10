from __future__ import annotations

import inspect
from dataclasses import is_dataclass, replace
from typing import Any

from fastapi import HTTPException, status


class RouteDecision(dict):
    @property
    def route_key(self) -> str:
        return str(self.get("route_key") or "")

    @property
    def fallback_route_key(self) -> str:
        return str(self.get("fallback_route_key") or "")


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
        fallback_route_key=str(route.get("fallback_route_key") or ""),
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


def resolve_model_route_plan(
    settings: Any,
    route_key: str,
    *,
    default_model: str | None = None,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> list[RouteDecision]:
    primary = resolve_model_route(
        settings,
        route_key,
        default_model=default_model,
        default_temperature=default_temperature,
        default_max_tokens=default_max_tokens,
    )
    plan = [primary]
    seen = {primary.route_key}
    current = primary
    while current.fallback_route_key and current.fallback_route_key not in seen:
        seen.add(current.fallback_route_key)
        fallback = resolve_model_route(
            settings,
            current.fallback_route_key,
            default_model=default_model,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
        )
        if not bool(fallback.get("applied")):
            break
        plan.append(fallback)
        current = fallback
    return plan


def _apply_route_decision(settings: Any, decision: RouteDecision) -> Any:
    if is_dataclass(settings):
        return replace(
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
    return proxy


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
    return _apply_route_decision(settings, decision), decision


def settings_with_model_route_plan(
    settings: Any,
    route_key: str,
    *,
    default_model: str | None = None,
    default_temperature: float | None = None,
    default_max_tokens: int | None = None,
) -> list[tuple[Any, RouteDecision]]:
    return [
        (
            _apply_route_decision(settings, decision),
            decision,
        )
        for decision in resolve_model_route_plan(
            settings,
            route_key,
            default_model=default_model,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
        )
    ]


async def execute_with_model_route_fallback(
    route_plan: list[tuple[Any, RouteDecision]],
    *,
    call: Any,
) -> tuple[Any, RouteDecision, list[str]]:
    if not route_plan:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No model route is available",
        )
    attempted_routes: list[str] = []
    last_error: HTTPException | None = None
    last_index = len(route_plan) - 1
    for index, (candidate_settings, decision) in enumerate(route_plan):
        attempted_routes.append(decision.route_key)
        try:
            result = call(candidate_settings, decision)
            if inspect.isawaitable(result):
                result = await result
            return result, decision, attempted_routes
        except HTTPException as exc:
            last_error = exc
            if exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR or index >= last_index:
                raise
    if last_error is not None:
        raise last_error
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No model route completed successfully",
    )


__all__ = [
    "RouteDecision",
    "execute_with_model_route_fallback",
    "resolve_model_route",
    "resolve_model_route_plan",
    "settings_with_model_route",
    "settings_with_model_route_plan",
]
