from __future__ import annotations

from fastapi import APIRouter, Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .db import to_json
from .kb_api_support import audit_event, require_kb_permission
from .kb_resource_store import load_ingest_job, serialize_ingest_job
from .kb_runtime import KB_MANAGE_PERMISSION, KB_READ_PERMISSION, db


router = APIRouter()


@router.get("/api/v1/kb/ingest-jobs/{job_id}")
def get_ingest_job(job_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.ingest.get", resource_type="ingest_job", resource_id=job_id)
    row = load_ingest_job(job_id, user=user, request=request, action="kb.ingest.get")
    if row is None:
        raise_api_error(404, "ingest_job_not_found", "ingest job not found")
    return serialize_ingest_job(row)


@router.post("/api/v1/kb/ingest-jobs/{job_id}/retry")
def retry_ingest_job(job_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_kb_permission(request, user, KB_MANAGE_PERMISSION, action="kb.ingest.retry", resource_type="ingest_job", resource_id=job_id)
    row = load_ingest_job(job_id, user=user, request=request, action="kb.ingest.retry")
    if row is None:
        raise_api_error(404, "ingest_job_not_found", "ingest job not found")
    status_value = str(row.get("status") or "")
    if status_value not in {"failed", "dead_letter"}:
        raise_api_error(400, "ingest_job_not_retryable", "only failed or dead-letter jobs can be retried")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_ingest_jobs
                SET status = 'queued',
                    phase = 'uploaded',
                    query_ready = FALSE,
                    enhancement_status = '',
                    error_message = '',
                    last_error_code = '',
                    next_retry_at = NOW(),
                    lease_token = '',
                    lease_expires_at = NULL,
                    dead_lettered_at = NULL,
                    finished_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            cur.execute(
                """
                UPDATE kb_documents
                SET status = 'uploaded',
                    query_ready = FALSE,
                    enhancement_status = '',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (row["document_id"],),
            )
            cur.execute(
                """
                INSERT INTO kb_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'uploaded', 'manual ingest retry queued', %s::jsonb)
                """,
                (row["document_id"], to_json({"job_id": job_id, "manual_retry": True})),
            )
        conn.commit()
    audit_event(
        action="kb.ingest.manual_retry",
        outcome="success",
        request=request,
        user=user,
        resource_type="ingest_job",
        resource_id=job_id,
        scope="managed",
        details={"document_id": str(row.get("document_id") or "")},
    )
    refreshed = load_ingest_job(job_id, user=user, request=request, action="kb.ingest.get")
    return serialize_ingest_job(refreshed or row)
