from __future__ import annotations

from typing import Any

from fastapi import Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import audit_event, can_manage_everything
from .kb_resource_store import load_document_unscoped, serialize_ingest_job
from .kb_runtime import db, logger, storage


def load_upload_session(
    upload_id: str,
    *,
    user: CurrentUser,
    request: Request | None = None,
    action: str = "kb.upload.get",
) -> dict[str, Any]:
    row = load_upload_session_unscoped(upload_id)
    owner_id = str(row.get("created_by") or "")
    if owner_id != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="upload_session",
                resource_id=upload_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "upload session is outside your scope")
    return row


def load_upload_session_unscoped(upload_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_upload_sessions WHERE id = %s", (upload_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "upload_session_not_found", "upload session not found")
    return row


def update_upload_status(upload_id: str, status: str) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_upload_sessions
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, upload_id),
            )
        conn.commit()


def list_uploaded_parts(session: dict[str, Any], *, internal_shape: bool = False) -> list[dict[str, Any]]:
    parts = storage.list_parts(str(session["storage_key"]), str(session["s3_upload_id"]))
    normalized = []
    for item in parts:
        if internal_shape:
            normalized.append(
                {
                    "PartNumber": int(item["PartNumber"]),
                    "ETag": str(item["ETag"]),
                    "size_bytes": int(item.get("Size") or 0),
                }
            )
        else:
            normalized.append(
                {
                    "part_number": int(item["PartNumber"]),
                    "etag": str(item["ETag"]),
                    "size_bytes": int(item.get("Size") or 0),
                }
            )
    return normalized


def persist_upload_parts(upload_id: str, parts: list[dict[str, Any]]) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO kb_upload_parts (upload_session_id, part_number, etag, size_bytes, status)
                VALUES (%s, %s, %s, %s, 'uploaded')
                ON CONFLICT (upload_session_id, part_number)
                DO UPDATE SET etag = EXCLUDED.etag, size_bytes = EXCLUDED.size_bytes, status = EXCLUDED.status
                """,
                [
                    (
                        upload_id,
                        int(item["PartNumber"]),
                        str(item["ETag"]),
                        int(item.get("size_bytes") or 0),
                    )
                    for item in parts
                ],
            )
        conn.commit()


def list_base_upload_sessions(base_id: str, *, user: CurrentUser, cur=None) -> list[dict[str, Any]]:
    if cur is not None:
        return list_base_upload_sessions_with_cursor(cur, base_id, user=user)
    with db.connect() as conn:
        with conn.cursor() as next_cur:
            return list_base_upload_sessions_with_cursor(next_cur, base_id, user=user)


def list_base_upload_sessions_with_cursor(cur, base_id: str, *, user: CurrentUser) -> list[dict[str, Any]]:
    if can_manage_everything(user):
        cur.execute(
            """
            SELECT *
            FROM kb_upload_sessions
            WHERE base_id = %s
            """,
            (base_id,),
        )
    else:
        cur.execute(
            """
            SELECT *
            FROM kb_upload_sessions
            WHERE base_id = %s
              AND created_by = %s
            """,
            (base_id, user.user_id),
        )
    return cur.fetchall()


def list_document_upload_sessions(document_id: str, upload_session_id: Any, *, user: CurrentUser, cur=None) -> list[dict[str, Any]]:
    if cur is not None:
        rows = list_document_upload_sessions_with_cursor(cur, document_id, upload_session_id, user=user)
    else:
        with db.connect() as conn:
            with conn.cursor() as next_cur:
                rows = list_document_upload_sessions_with_cursor(next_cur, document_id, upload_session_id, user=user)
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row.get("id") or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        unique_rows.append(row)
    return unique_rows


def list_document_upload_sessions_with_cursor(cur, document_id: str, upload_session_id: Any, *, user: CurrentUser) -> list[dict[str, Any]]:
    if upload_session_id:
        if can_manage_everything(user):
            cur.execute(
                """
                SELECT *
                FROM kb_upload_sessions
                WHERE document_id = %s OR id = %s
                ORDER BY created_at DESC
                """,
                (document_id, upload_session_id),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM kb_upload_sessions
                WHERE created_by = %s
                  AND (document_id = %s OR id = %s)
                ORDER BY created_at DESC
                """,
                (user.user_id, document_id, upload_session_id),
            )
    else:
        if can_manage_everything(user):
            cur.execute(
                """
                SELECT *
                FROM kb_upload_sessions
                WHERE document_id = %s
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM kb_upload_sessions
                WHERE document_id = %s
                  AND created_by = %s
                ORDER BY created_at DESC
                """,
                (document_id, user.user_id),
            )
    return cur.fetchall()


def cleanup_upload_session_storage(session: dict[str, Any]) -> None:
    status_value = str(session.get("status") or "")
    storage_key = str(session.get("storage_key") or "")
    upload_id = str(session.get("s3_upload_id") or "")
    if status_value in {"pending_upload", "uploading"} and storage_key and upload_id:
        storage.abort_multipart_upload(storage_key, upload_id)
    delete_storage_key_if_present(storage_key)


def delete_storage_key_if_present(storage_key: str) -> None:
    candidate = storage_key.strip()
    if not candidate:
        return
    storage.delete_object(candidate)


def cleanup_deleted_resources(*, upload_sessions: list[dict[str, Any]], storage_keys: list[str]) -> None:
    for session in upload_sessions:
        try:
            cleanup_upload_session_storage(session)
        except Exception:
            logger.exception("failed to cleanup upload session storage upload_id=%s", session.get("id"))
    for storage_key in storage_keys:
        try:
            delete_storage_key_if_present(storage_key)
        except Exception:
            logger.exception("failed to cleanup storage key storage_key=%s", storage_key)


def complete_payload(*, document_id: str, upload_id: str) -> dict[str, Any]:
    document = load_document_unscoped(document_id)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT jobs.*, documents.status AS document_status, documents.query_ready,
                       documents.enhancement_status AS document_enhancement_status,
                       documents.query_ready_at, documents.hybrid_ready_at, documents.ready_at
                FROM kb_ingest_jobs jobs
                JOIN kb_documents documents ON documents.id = jobs.document_id
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            job = cur.fetchone()
    serialized_job = serialize_ingest_job(job) if job else {}
    return {
        "upload_id": upload_id,
        "document_id": document_id,
        "job_id": str(job["id"]) if job else "",
        "document": document,
        "job": serialized_job,
    }


def serialize_upload_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        **session,
        "upload_id": str(session.get("id") or ""),
        "uploaded_parts": list_uploaded_parts(session),
    }
