from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import httpx


CHUNK_SIZE_BYTES = 5 * 1024 * 1024
QUERYABLE_STATUSES = {"fast_index_ready", "hybrid_ready", "ready"}


def login(base_url: str, email: str, password: str) -> str:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{base_url.rstrip('/')}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def list_kb_bases(client: httpx.Client, *, base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get(f"{base_url.rstrip('/')}/kb/bases", headers=headers)
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("items", []) or [])


def create_kb_base(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    name: str,
    description: str,
    category: str,
) -> dict[str, Any]:
    response = client.post(
        f"{base_url.rstrip('/')}/kb/bases",
        headers=headers,
        json={"name": name, "description": description, "category": category},
    )
    response.raise_for_status()
    return response.json()


def list_corpus_documents(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    corpus_id: str,
) -> list[dict[str, Any]]:
    response = client.get(
        f"{base_url.rstrip('/')}/kb/bases/{corpus_id}/documents",
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("items", []) or [])


def get_upload_session(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    upload_id: str,
) -> dict[str, Any]:
    response = client.get(
        f"{base_url.rstrip('/')}/kb/uploads/{upload_id}",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


def create_upload(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    corpus_id: str,
    file_path: Path,
    category: str,
) -> dict[str, Any]:
    file_type = file_path.suffix.lstrip(".").lower()
    response = client.post(
        f"{base_url.rstrip('/')}/kb/uploads",
        headers=headers,
        json={
            "base_id": corpus_id,
            "file_name": file_path.name,
            "file_type": file_type or "txt",
            "size_bytes": file_path.stat().st_size,
            "category": category,
        },
    )
    response.raise_for_status()
    return response.json()


def build_part_numbers(file_path: Path, *, chunk_size_bytes: int = CHUNK_SIZE_BYTES) -> list[int]:
    total_parts = max(1, math.ceil(file_path.stat().st_size / float(chunk_size_bytes)))
    return list(range(1, total_parts + 1))


def presign_parts(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    upload_id: str,
    part_numbers: list[int],
) -> dict[str, Any]:
    response = client.post(
        f"{base_url.rstrip('/')}/kb/uploads/{upload_id}/parts/presign",
        headers=headers,
        json={"part_numbers": part_numbers},
    )
    response.raise_for_status()
    return response.json()


def upload_parts(
    client: httpx.Client,
    *,
    file_path: Path,
    presign_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    uploaded_parts = list(presign_payload.get("uploaded_parts", []) or [])
    chunk_size = int(presign_payload.get("chunk_size_bytes") or CHUNK_SIZE_BYTES)
    with file_path.open("rb") as handle:
        for item in presign_payload.get("presigned_parts", []) or []:
            part_number = int(item["part_number"])
            start = (part_number - 1) * chunk_size
            handle.seek(start)
            data = handle.read(chunk_size)
            response = client.put(str(item["url"]), content=data, headers={"Content-Type": "application/octet-stream"})
            response.raise_for_status()
            etag = response.headers.get("etag") or response.headers.get("ETag") or ""
            if not etag:
                raise RuntimeError(f"missing etag for uploaded part {part_number}")
            uploaded_parts.append(
                {
                    "part_number": part_number,
                    "etag": etag,
                    "size_bytes": len(data),
                }
            )
    uploaded_parts.sort(key=lambda item: int(item["part_number"]))
    return uploaded_parts


def complete_upload(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    upload_id: str,
    parts: list[dict[str, Any]],
    content_hash: str = "",
) -> dict[str, Any]:
    response = client.post(
        f"{base_url.rstrip('/')}/kb/uploads/{upload_id}/complete",
        headers=headers,
        json={"parts": parts, "content_hash": content_hash},
    )
    response.raise_for_status()
    return response.json()


def poll_job(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    timeout_seconds: int,
    poll_seconds: float,
    upload_ack_seconds: float,
) -> dict[str, Any]:
    started = time.time()
    query_ready_at: float | None = None
    hybrid_ready_at: float | None = None
    ready_at: float | None = None
    last_payload: dict[str, Any] = {}

    while time.time() - started < timeout_seconds:
        response = client.get(
            f"{base_url.rstrip('/')}/kb/ingest-jobs/{job_id}",
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        document_status = str(payload.get("document_status") or payload.get("status") or "")
        if payload.get("query_ready") and query_ready_at is None:
            query_ready_at = time.time()
        if str(payload.get("document_enhancement_status") or payload.get("enhancement_status") or "") in {
            "summary_vectors_ready",
            "hybrid_ready",
        } and hybrid_ready_at is None:
            hybrid_ready_at = time.time()
        if document_status in {"ready", "failed"} and ready_at is None:
            ready_at = time.time()
        if document_status in {"ready", "failed"}:
            break
        time.sleep(poll_seconds)

    finished = time.time()
    return {
        "job": last_payload,
        "timings_seconds": {
            "upload_ack": round(upload_ack_seconds, 3),
            "fast_index_ready": round((query_ready_at - started), 3) if query_ready_at else None,
            "hybrid_ready": round((hybrid_ready_at - started), 3) if hybrid_ready_at else None,
            "ready": round((ready_at - started), 3) if ready_at else None,
            "total_polling": round(finished - started, 3),
        },
    }


def upload_and_wait(
    client: httpx.Client,
    *,
    base_url: str,
    headers: dict[str, str],
    corpus_id: str,
    file_path: Path,
    title: str,
    category: str = "",
    timeout_seconds: int = 900,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    upload_started = time.time()
    session = create_upload(
        client,
        base_url=base_url,
        headers=headers,
        corpus_id=corpus_id,
        file_path=file_path,
        category=category,
    )
    upload_id = str(session.get("id") or session.get("upload_id") or "")
    presign_payload = presign_parts(
        client,
        base_url=base_url,
        headers=headers,
        upload_id=upload_id,
        part_numbers=build_part_numbers(file_path),
    )
    parts = upload_parts(client, file_path=file_path, presign_payload=presign_payload)
    complete_payload = complete_upload(
        client,
        base_url=base_url,
        headers=headers,
        upload_id=upload_id,
        parts=parts,
    )
    upload_ack_seconds = time.time() - upload_started
    result = poll_job(
        client,
        base_url=base_url,
        headers=headers,
        job_id=str(complete_payload["job_id"]),
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        upload_ack_seconds=upload_ack_seconds,
    )
    return {
        "service": "kb",
        "corpus_id": corpus_id,
        "file": str(file_path),
        "upload_id": upload_id,
        "job_id": complete_payload["job_id"],
        "document_id": complete_payload.get("document_id"),
        **result,
    }
