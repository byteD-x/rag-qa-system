from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Body, Query, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import can_manage_everything, require_kb_permission
from .kb_batch_dry_run import KnowledgeBatchPayloadError
from .kb_job_queue import KnowledgeBaseJobQueue, KnowledgeJobQueueError, build_knowledge_job_result, knowledge_job_queue
from .kb_rebuild import KnowledgeRebuildPayloadError
from .kb_runtime import KB_READ_PERMISSION, KB_WRITE_PERMISSION


router = APIRouter()


@router.post("/api/knowledge_base/jobs")
async def post_knowledge_job(request: Request, user: CurrentUser, body: Any = Body(...)) -> dict[str, Any]:
    require_kb_permission(request, user, KB_WRITE_PERMISSION, action="kb.job.enqueue", resource_type="knowledge_base")
    try:
        mode, payload = _parse_job_request(body)
        request_snapshot = _request_snapshot(request)

        async def runner(job_mode: str, job_payload: dict[str, Any]) -> dict[str, Any]:
            return await asyncio.to_thread(build_knowledge_job_result, job_mode, job_payload, request=request_snapshot, user=user)

        return await knowledge_job_queue.enqueue(mode=mode, payload=payload, runner=runner, owner_user_id=user.user_id)
    except KnowledgeJobQueueError as exc:
        status_code = 409 if exc.code == "knowledge_job_queue_full" else 400
        raise_api_error(status_code, exc.code, exc.detail)
    except (KnowledgeBatchPayloadError, KnowledgeRebuildPayloadError) as exc:
        raise_api_error(400, exc.code, exc.detail)


@router.get("/api/knowledge_base/jobs/{job_id}")
async def get_knowledge_job(job_id: str, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.job.get", resource_type="knowledge_base")
    snapshot = await knowledge_job_queue.get(
        job_id,
        owner_user_id=user.user_id,
        include_all=can_manage_everything(user),
    )
    if snapshot is None:
        raise_api_error(404, "knowledge_job_not_found", "knowledge job not found")
    return snapshot


@router.get("/api/knowledge_base/status")
async def get_knowledge_status(
    request: Request,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.status.get", resource_type="knowledge_base")
    return {
        "success": True,
        "queue": await knowledge_job_queue.summary(
            limit=limit,
            owner_user_id=user.user_id,
            include_all=can_manage_everything(user),
        ),
    }


def _parse_job_request(body: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(body, dict):
        raise KnowledgeJobQueueError("knowledge_job_payload_invalid", "request body must be an object")
    mode = str(body.get("mode") or "").strip().lower()
    payload = body.get("payload")
    if isinstance(payload, dict):
        return mode, dict(payload)
    return mode, {key: value for key, value in body.items() if key != "mode"}


def _request_snapshot(request: Request) -> Request:
    return SimpleNamespace(url=SimpleNamespace(path=str(request.url.path)))  # type: ignore[return-value]


def set_knowledge_job_queue(queue: KnowledgeBaseJobQueue) -> None:
    global knowledge_job_queue
    knowledge_job_queue = queue
