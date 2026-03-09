from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Response

from shared.api_errors import raise_api_error
from shared.metrics import CONTENT_TYPE_LATEST, generate_latest

from .ai_client import load_llm_settings
from .gateway_runtime import gateway_db, runtime_settings


router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


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
        checks["kb_service"] = {"status": "ok"} if response.status_code < 400 else {"status": "failed", "detail": f"kb-service readiness returned {response.status_code}"}
    except httpx.HTTPError as exc:
        checks["kb_service"] = {"status": "failed", "detail": str(exc)}
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


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
