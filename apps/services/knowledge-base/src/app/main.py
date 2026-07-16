from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from shared.api_errors import (
    http_exception_response,
    unexpected_exception_response,
    validation_exception_response,
)
from shared.auth import ensure_auth_configuration_ready
from shared.tracing import TRACE_ID_HEADER, ensure_trace_id, reset_trace_id, set_trace_id

from .kb_api_support import check_readiness as _kb_readiness_checks
from .kb_analytics_routes import router as kb_analytics_router
from .kb_auto_index_routes import router as kb_auto_index_router
from .kb_batch_dry_run_routes import router as kb_batch_dry_run_router
from .kb_batch_ingest_routes import router as kb_batch_ingest_router
from .kb_base_routes import router as kb_base_router
from .kb_chunk_routes import router as kb_chunk_router
from .kb_connector_routes import (
    has_active_scheduled_connectors,
    router as kb_connector_router,
    run_due_connectors_batch,
    set_connector_scheduler_reconciler,
)
from .kb_connector_scheduler import ConnectorSchedulerManager
from .kb_ingest_routes import router as kb_ingest_router
from .kb_index_routes import router as kb_index_router
from .kb_job_queue_routes import router as kb_job_queue_router
from .kb_query_routes import router as kb_query_router
from .kb_rebuild_routes import router as kb_rebuild_router
from .kb_runtime import db, logger, prepare_runtime, storage
from .kb_sync_routes import router as kb_sync_router
from .kb_system_routes import router as kb_system_router
from .kb_upload_routes import router as kb_upload_router
from .kb_object_store_routes import router as kb_object_store_router
from .kb_visual_routes import router as kb_visual_router
from .worker import run_worker_loop


CONNECTOR_SCHEDULER = ConnectorSchedulerManager(
    has_active_schedules=has_active_scheduled_connectors,
    run_due_batch=run_due_connectors_batch,
)


def _worker_enabled() -> bool:
    """是否在 kb-service 进程内跑 ingest worker(默认关闭,保持独立 kb-worker 进程原行为)。

    单机形态可设 KB_RUN_WORKER=true 让 service 进程内后台线程跑 worker,省一个容器。
    """
    return os.getenv("KB_RUN_WORKER", "").strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    warnings = ensure_auth_configuration_ready()
    for warning in warnings:
        logger.warning("kb-service auth configuration warning: %s", warning)
    prepare_runtime()
    loop = asyncio.get_running_loop()
    CONNECTOR_SCHEDULER.bind_loop(loop)
    set_connector_scheduler_reconciler(CONNECTOR_SCHEDULER.reconcile)
    CONNECTOR_SCHEDULER.reconcile()
    app.state.connector_scheduler = CONNECTOR_SCHEDULER

    worker_stop: threading.Event | None = None
    worker_thread: threading.Thread | None = None
    if _worker_enabled():
        worker_stop = threading.Event()
        # 进程内后台线程跑 worker;enable_metrics=False 避免与 service 抢指标端口。
        # 领取用 FOR UPDATE SKIP LOCKED + 租约,与独立 kb-worker 并存也安全。
        worker_thread = threading.Thread(
            target=run_worker_loop,
            kwargs={"stop_event": worker_stop, "enable_metrics": False},
            name="kb-ingest-worker",
            daemon=True,
        )
        worker_thread.start()
        logger.info("kb-service in-process ingest worker started (KB_RUN_WORKER enabled)")

    yield

    if worker_stop is not None:
        worker_stop.set()
    if worker_thread is not None:
        worker_thread.join(timeout=10)
    await CONNECTOR_SCHEDULER.shutdown()


app = FastAPI(title="RAG-QA 2.0 KB Service", version="3.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    return http_exception_response(exc)


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    return validation_exception_response(exc)


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.exception("kb-service unexpected error path=%s", request.url.path)
    return unexpected_exception_response()


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = ensure_trace_id(request.headers.get(TRACE_ID_HEADER), prefix="kb-")
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
    finally:
        reset_trace_id(token)
    response.headers[TRACE_ID_HEADER] = trace_id
    return response


app.include_router(kb_system_router)
app.include_router(kb_analytics_router)
app.include_router(kb_auto_index_router)
app.include_router(kb_batch_dry_run_router)
app.include_router(kb_batch_ingest_router)
app.include_router(kb_index_router)
app.include_router(kb_job_queue_router)
app.include_router(kb_rebuild_router)
app.include_router(kb_base_router)
app.include_router(kb_chunk_router)
app.include_router(kb_connector_router)
app.include_router(kb_sync_router)
app.include_router(kb_upload_router)
app.include_router(kb_ingest_router)
app.include_router(kb_query_router)
app.include_router(kb_visual_router)
app.include_router(kb_object_store_router)


__all__ = ["_kb_readiness_checks", "app", "db", "storage"]
