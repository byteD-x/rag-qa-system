from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Response

from shared.api_errors import raise_api_error
from shared.metrics import CONTENT_TYPE_LATEST, generate_latest

from .ai_client import load_llm_settings
from .gateway_runtime import gateway_db, runtime_settings
from .governance_metrics import get_governance_metrics
from .semantic_cache import semantic_cache


router = APIRouter()
MAX_UPSTREAM_DETAIL_CHARS = 240


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _short_upstream_detail(value: Any, *, fallback: str) -> str:
    text = str(value or fallback).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= MAX_UPSTREAM_DETAIL_CHARS:
        return text
    return f"{text[:MAX_UPSTREAM_DETAIL_CHARS - 3]}..."


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sanitize_upstream_checks(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    checks: dict[str, dict[str, Any]] = {}
    for name, item in value.items():
        if not isinstance(item, dict):
            continue
        sanitized: dict[str, Any] = {}
        for key, raw in item.items():
            field = str(key)
            sanitized[field] = _short_upstream_detail(raw, fallback="") if field == "detail" else raw
        checks[str(name)] = sanitized
    return checks


def _kb_service_check_from_response(response: httpx.Response) -> dict[str, Any]:
    payload = _response_json(response)
    if response.status_code < 400:
        result: dict[str, Any] = {
            "status": "ok",
            "upstream_status": str(payload.get("status") or "ready"),
        }
        checks = _sanitize_upstream_checks(payload.get("checks"))
        if checks:
            result["checks"] = checks
        return result

    fallback = f"kb-service readiness returned {response.status_code}"
    detail = payload.get("detail") or payload.get("message") or fallback
    return {"status": "failed", "detail": _short_upstream_detail(detail, fallback=fallback)}


async def gateway_readiness_checks() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    try:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "failed", "detail": str(exc)}
    timeout = httpx.Timeout(min(runtime_settings.request_timeout_seconds, 5.0))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{runtime_settings.kb_service_url}/readyz")
        checks["kb_service"] = _kb_service_check_from_response(response)
    except httpx.HTTPError as exc:
        checks["kb_service"] = {"status": "failed", "detail": _short_upstream_detail(exc, fallback="kb-service readiness request failed")}
    settings = load_llm_settings()
    checks["llm"] = {"status": "fallback" if not settings.configured else "ok", "configured": settings.configured}
    return checks


@router.get("/readyz")
async def readyz() -> dict[str, Any]:
    checks = await gateway_readiness_checks()
    failed = [name for name, item in checks.items() if item.get("status") == "failed"]
    if failed:
        raise_api_error(503, "gateway_not_ready", f"gateway dependencies are not ready: {', '.join(failed)}")
    return {"status": "ready", "checks": checks}


def get_metrics_summary() -> dict[str, Any]:
    return {
        "governance_metrics": get_governance_metrics().get_status(),
        "response_cache_summary": semantic_cache.stats(),
    }


@router.get("/api/v1/system/metrics-summary")
async def metrics_summary() -> dict[str, Any]:
    return get_metrics_summary()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
