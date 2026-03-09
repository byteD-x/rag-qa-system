from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser, create_access_token
from shared.tracing import TRACE_ID_HEADER, current_trace_id, ensure_trace_id

from .gateway_config import HOP_BY_HOP_HEADERS
from .gateway_request_support import sanitize_headers
from .gateway_runtime import runtime_settings


async def iter_upstream_bytes(response: httpx.Response) -> AsyncIterator[bytes]:
    async for chunk in response.aiter_bytes():
        yield chunk


async def close_upstream(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


async def proxy_request(request: Request, *, service_base_url: str, service_path: str) -> Response:
    target_url = f"{service_base_url}{service_path}"
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    client = httpx.AsyncClient(timeout=timeout)
    try:
        upstream = await client.send(
            client.build_request(
                method=request.method,
                url=target_url,
                headers=sanitize_headers(request, hop_by_hop_headers=HOP_BY_HOP_HEADERS),
                params=request.query_params,
                content=request.stream(),
            ),
            stream=True,
        )
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        media_type = upstream.headers.get("content-type")
        if media_type and media_type.startswith("text/event-stream"):
            return StreamingResponse(
                iter_upstream_bytes(upstream),
                status_code=upstream.status_code,
                headers=response_headers,
                background=BackgroundTask(close_upstream, upstream, client),
                media_type=media_type,
            )
        try:
            body = await upstream.aread()
        finally:
            await close_upstream(upstream, client)
        return Response(content=body, status_code=upstream.status_code, headers=response_headers, media_type=media_type)
    except Exception:
        await client.aclose()
        raise


def downstream_headers(user: CurrentUser, *, trace_id: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user)}",
        "Content-Type": "application/json",
        TRACE_ID_HEADER: ensure_trace_id(trace_id or current_trace_id(), prefix="gateway-"),
    }


def parse_corpus_id(corpus_id: str) -> tuple[str, str]:
    if ":" not in corpus_id:
        raise_api_error(400, "invalid_corpus_id", f"invalid corpus id: {corpus_id}")
    corpus_type, raw_id = corpus_id.split(":", 1)
    corpus_type = corpus_type.strip().lower()
    raw_id = raw_id.strip()
    if corpus_type != "kb" or not raw_id:
        raise_api_error(400, "invalid_corpus_id", f"invalid corpus id: {corpus_id}")
    return corpus_type, raw_id


async def request_service_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.request(method, url, headers=headers, json=json_body, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": f"upstream service unavailable: {url}", "code": "upstream_unavailable"},
        ) from exc
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        detail = payload.get("detail") if isinstance(payload, dict) else ""
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": str(detail or f"upstream service returned {response.status_code}"), "code": "upstream_request_failed"},
        )
    return response.json()
