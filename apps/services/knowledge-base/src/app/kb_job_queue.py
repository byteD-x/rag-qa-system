from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request

from shared.auth import CurrentUser

from .kb_batch_ingest import build_knowledge_batch_ingest_payload, parse_knowledge_batch_ingest_payload
from .kb_rebuild import build_knowledge_rebuild_payload, parse_knowledge_rebuild_payload


JobRunner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]

DEFAULT_KB_JOB_QUEUE_MAX_JOBS = 100
TERMINAL_JOB_STATUSES = {"completed", "failed"}
SUPPORTED_JOB_MODES = {"ingest", "rebuild"}
FORBIDDEN_PUBLIC_KEYS = {
    "chunk_text",
    "chunk_texts",
    "chunks",
    "content",
    "content_path",
    "embedding",
    "embeddings",
    "path",
    "raw_text",
    "source_path",
    "storage_path",
    "storage_key",
    "text",
    "text_content",
}
PATH_PATTERN = re.compile(r"([A-Za-z]:[\\/][^\s]+|/[^\s]+)")


class KnowledgeJobQueueError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _KnowledgeJob:
    job_id: str
    mode: str
    payload: dict[str, Any]
    documents: list[dict[str, Any]]
    runner: JobRunner
    owner_user_id: str = ""
    status: str = "queued"
    created_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class KnowledgeBaseJobQueue:
    def __init__(
        self,
        *,
        max_jobs: int = DEFAULT_KB_JOB_QUEUE_MAX_JOBS,
        job_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.max_jobs = max(int(max_jobs or DEFAULT_KB_JOB_QUEUE_MAX_JOBS), 1)
        self._job_id_factory = job_id_factory or (lambda: str(uuid4()))
        self._lock = asyncio.Lock()
        self._jobs: dict[str, _KnowledgeJob] = {}
        self._order: list[str] = []
        self._drain_task: asyncio.Task[None] | None = None

    async def enqueue(self, *, mode: str, payload: Any, runner: JobRunner, owner_user_id: str = "") -> dict[str, Any]:
        normalized_mode = _normalize_mode(mode)
        normalized_payload, documents = normalize_knowledge_job_payload(normalized_mode, payload)
        job = _KnowledgeJob(
            job_id=self._job_id_factory(),
            mode=normalized_mode,
            payload=normalized_payload,
            documents=documents,
            runner=runner,
            owner_user_id=str(owner_user_id or "").strip(),
        )
        async with self._lock:
            self._prune_locked(target_size=self.max_jobs - 1)
            if len(self._order) >= self.max_jobs:
                raise KnowledgeJobQueueError("knowledge_job_queue_full", "knowledge job queue is full")
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            self._ensure_drain_task_locked()
            return self._snapshot_locked(job)

    async def get(self, job_id: str, *, owner_user_id: str = "", include_all: bool = False) -> dict[str, Any] | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            if job and owner_user_id and not include_all and job.owner_user_id and job.owner_user_id != owner_user_id:
                return None
            return self._snapshot_locked(job) if job else None

    async def summary(self, *, limit: int = 20, owner_user_id: str = "", include_all: bool = False) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 20), self.max_jobs))
        async with self._lock:
            counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
            by_mode = {mode: 0 for mode in sorted(SUPPORTED_JOB_MODES)}
            visible_jobs = [job for job in self._jobs.values() if _can_view_job(job, owner_user_id=owner_user_id, include_all=include_all)]
            for job in visible_jobs:
                counts[job.status] = int(counts.get(job.status, 0)) + 1
                by_mode[job.mode] = int(by_mode.get(job.mode, 0)) + 1
            visible_job_ids = [job_id for job_id in reversed(self._order) if job_id in self._jobs and _can_view_job(self._jobs[job_id], owner_user_id=owner_user_id, include_all=include_all)]
            job_ids = visible_job_ids[:safe_limit]
            return {
                "max_jobs": self.max_jobs,
                "total_jobs": len(visible_jobs),
                "counts": counts,
                "modes": by_mode,
                "jobs": [self._snapshot_locked(self._jobs[job_id]) for job_id in job_ids if job_id in self._jobs],
            }

    async def wait_idle(self) -> None:
        while True:
            async with self._lock:
                drain_task = self._drain_task
            if drain_task is None:
                return
            await asyncio.shield(drain_task)

    def _ensure_drain_task_locked(self) -> None:
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while True:
            async with self._lock:
                job = self._next_queued_locked()
                if job is None:
                    self._drain_task = None
                    return
                job.status = "running"
                job.started_at = _utcnow()
            try:
                result = job.runner(job.mode, job.payload)
                if inspect.isawaitable(result):
                    result = await result
                public_result = _sanitize_public_value(result if isinstance(result, dict) else {"result": result})
                async with self._lock:
                    job.status = "completed"
                    job.result = public_result if isinstance(public_result, dict) else {"result": public_result}
                    job.finished_at = _utcnow()
                    self._prune_locked()
            except Exception as exc:
                async with self._lock:
                    job.status = "failed"
                    job.error = _serialize_error(exc)
                    job.finished_at = _utcnow()
                    self._prune_locked()

    def _next_queued_locked(self) -> _KnowledgeJob | None:
        for job_id in self._order:
            job = self._jobs.get(job_id)
            if job and job.status == "queued":
                return job
        return None

    def _prune_locked(self, *, target_size: int | None = None) -> None:
        limit = self.max_jobs if target_size is None else max(int(target_size), 0)
        while len(self._order) > limit:
            removable_id = next(
                (job_id for job_id in self._order if self._jobs.get(job_id) and self._jobs[job_id].status in TERMINAL_JOB_STATUSES),
                None,
            )
            if removable_id is None:
                return
            self._jobs.pop(removable_id, None)
            self._order.remove(removable_id)

    def _snapshot_locked(self, job: _KnowledgeJob) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "mode": job.mode,
            "status": job.status,
            "document_count": len(job.documents),
            "documents": [dict(item) for item in job.documents],
            "created_at": _iso_timestamp(job.created_at),
            "started_at": _iso_timestamp(job.started_at),
            "finished_at": _iso_timestamp(job.finished_at),
            "result": dict(job.result) if job.result is not None else None,
            "error": dict(job.error) if job.error is not None else None,
        }


def normalize_knowledge_job_payload(mode: str, raw: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "ingest":
        documents = parse_knowledge_batch_ingest_payload(raw)
        return {"documents": [dict(document) for document in documents]}, [_ingest_document_snapshot(document, index=index) for index, document in enumerate(documents)]
    payload = parse_knowledge_rebuild_payload(raw)
    return dict(payload), [_rebuild_document_snapshot(payload)]


def build_knowledge_job_result(mode: str, payload: dict[str, Any], *, request: Request, user: CurrentUser) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "ingest":
        return build_knowledge_batch_ingest_payload(payload, request=request, user=user)
    return build_knowledge_rebuild_payload(payload, request=request, user=user)


def _can_view_job(job: _KnowledgeJob, *, owner_user_id: str, include_all: bool) -> bool:
    return include_all or not owner_user_id or not job.owner_user_id or job.owner_user_id == owner_user_id


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in SUPPORTED_JOB_MODES:
        raise KnowledgeJobQueueError("knowledge_job_mode_invalid", "knowledge job mode must be ingest or rebuild")
    return normalized


def _ingest_document_snapshot(document: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "doc_id": str(document.get("doc_id") or ""),
        "file_name": _safe_leaf_name(document.get("file_name"), fallback=str(document.get("doc_id") or "document")),
        "base_id": str(document.get("base_id") or ""),
        "category": str(document.get("category") or ""),
        "content_chars": len(str(document.get("content") or "")),
    }


def _rebuild_document_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": 0,
        "doc_id": str(payload.get("doc_id") or ""),
        "dry_run": bool(payload.get("dry_run")),
        "signature": str(payload.get("signature") or ""),
    }


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.lower()
            if normalized_key in FORBIDDEN_PUBLIC_KEYS:
                continue
            if isinstance(item, str) and normalized_key in {"file_name", "source_file"}:
                sanitized[key_text] = _safe_leaf_name(item, fallback="")
                continue
            if isinstance(item, str) and any(token in normalized_key for token in ("path", "uri", "url")):
                sanitized[key_text] = _safe_reference(item)
                continue
            sanitized[key_text] = _sanitize_public_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, str):
        return _safe_error_text(value)
    return value


def _serialize_error(exc: Exception) -> dict[str, str]:
    code = str(getattr(exc, "code", "") or exc.__class__.__name__ or "knowledge_job_failed")
    return {"code": code, "detail": "knowledge job failed"}


def _safe_reference(raw: Any) -> str:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return ""
    normalized = cleaned.replace("\\", "/")
    if len(normalized) > 1 and normalized[1] == ":":
        return _safe_leaf_name(normalized, fallback="")
    if "://" not in normalized:
        return _safe_leaf_name(normalized, fallback="")
    try:
        parts = urlsplit(normalized)
    except ValueError:
        return _safe_leaf_name(normalized, fallback="")
    if parts.scheme in {"http", "https"}:
        return parts.netloc
    return parts.scheme


def _safe_error_text(raw: str) -> str:
    return PATH_PATTERN.sub(lambda match: _safe_reference(match.group(0)), raw)


def _safe_leaf_name(raw: Any, *, fallback: str) -> str:
    cleaned = str(raw or "").strip().replace("\\", "/")
    leaf = PurePosixPath(cleaned).name.strip()
    if not leaf or leaf in {".", ".."}:
        leaf = fallback
    return leaf[:160]


def _iso_timestamp(value: datetime | None) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


knowledge_job_queue = KnowledgeBaseJobQueue()
