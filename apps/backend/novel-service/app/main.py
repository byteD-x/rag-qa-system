from __future__ import annotations

import hashlib
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.auth import CurrentUser
from shared.logging import setup_logging
from shared.tracing import TRACE_ID_HEADER, current_trace_id, ensure_trace_id, reset_trace_id, set_trace_id
from shared.sse import iter_query_sse_messages

from .db import to_json
from .query import build_refusal_response, compact_quote, detect_strategy
from .retrieve import retrieve_novel_result
from .runtime import db, ensure_runtime, storage


logger = setup_logging("novel-service")
UPLOAD_PART_EXPIRES_SECONDS = int(os.getenv("UPLOAD_PART_EXPIRES_SECONDS", "3600"))

app = FastAPI(title="RAG-QA 2.0 Novel Service", version="3.0.0")


class CreateLibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class CreateUploadRequest(BaseModel):
    library_id: str
    title: str = Field(min_length=1, max_length=255)
    volume_label: str = Field(default="", max_length=120)
    spoiler_ack: bool = True
    file_name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=16)
    size_bytes: int = Field(gt=0)


class PresignPartsRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=1000)


class UploadPartItem(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1, max_length=256)
    size_bytes: int = Field(default=0, ge=0)


class CompleteUploadRequest(BaseModel):
    parts: list[UploadPartItem] = Field(default_factory=list)
    content_hash: str = Field(default="", max_length=128)


class RetrieveRequest(BaseModel):
    library_id: str
    question: str = Field(min_length=1, max_length=12000)
    document_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)


class NovelQueryRequest(BaseModel):
    library_id: str
    question: str = Field(min_length=1, max_length=12000)
    document_ids: list[str] = Field(default_factory=list)
    debug: bool = False


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime()


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = ensure_trace_id(request.headers.get(TRACE_ID_HEADER), prefix="novel-")
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
    finally:
        reset_trace_id(token)
    response.headers[TRACE_ID_HEADER] = trace_id
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/novel/libraries")
def create_library(payload: CreateLibraryRequest, user: CurrentUser) -> dict[str, Any]:
    library_id = str(uuid4())
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO novel_libraries (id, name, description, created_by)
                VALUES (%s, %s, %s, %s)
                """,
                (library_id, payload.name.strip(), payload.description.strip(), user.user_id),
            )
        conn.commit()
    return {
        "id": library_id,
        "name": payload.name.strip(),
        "description": payload.description.strip(),
    }


@app.get("/api/v1/novel/libraries")
def list_libraries(user: CurrentUser) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM novel_libraries ORDER BY created_at DESC")
            rows = cur.fetchall()
    return {"items": rows}


@app.get("/api/v1/novel/libraries/{library_id}/documents")
def list_library_documents(library_id: str, user: CurrentUser) -> dict[str, Any]:
    return {"items": _fetch_library_documents(library_id)}


@app.get("/api/v1/novel/documents/{document_id}")
def get_document(document_id: str, user: CurrentUser) -> dict[str, Any]:
    return _load_document(document_id)


@app.get("/api/v1/novel/documents/{document_id}/events")
def get_document_events(document_id: str, user: CurrentUser) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM novel_document_events
                WHERE document_id = %s
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            rows = cur.fetchall()
    return {"items": rows}


@app.post("/api/v1/novel/uploads")
def create_upload(payload: CreateUploadRequest, user: CurrentUser) -> dict[str, Any]:
    file_type = payload.file_type.lower().lstrip(".")
    if file_type != "txt":
        raise HTTPException(status_code=400, detail="novel upload currently supports txt only")
    _ensure_library_exists(payload.library_id)

    upload_id = str(uuid4())
    storage_key = storage.build_storage_key(service="novel", document_id=upload_id, file_name=payload.file_name)
    s3_upload_id = storage.create_multipart_upload(
        storage_key,
        metadata={
            "upload_id": upload_id,
            "library_id": payload.library_id,
            "created_by": user.user_id,
        },
    )
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO novel_upload_sessions (
                    id, library_id, title, volume_label, file_name, file_type, size_bytes,
                    storage_key, s3_upload_id, status, created_by, spoiler_ack, expires_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, 'pending_upload', %s, %s, NOW() + INTERVAL '1 hour'
                )
                """,
                (
                    upload_id,
                    payload.library_id,
                    payload.title.strip(),
                    payload.volume_label.strip(),
                    payload.file_name,
                    file_type,
                    payload.size_bytes,
                    storage_key,
                    s3_upload_id,
                    user.user_id,
                    payload.spoiler_ack,
                ),
            )
        conn.commit()
    return _serialize_upload_session(_load_upload_session(upload_id))


@app.get("/api/v1/novel/uploads/{upload_id}")
def get_upload(upload_id: str, user: CurrentUser) -> dict[str, Any]:
    return _serialize_upload_session(_load_upload_session(upload_id))


@app.post("/api/v1/novel/uploads/{upload_id}/parts/presign")
def presign_upload_parts(upload_id: str, payload: PresignPartsRequest, user: CurrentUser) -> dict[str, Any]:
    session = _load_upload_session(upload_id)
    uploaded_parts = _list_uploaded_parts(session)
    uploaded_numbers = {item["part_number"] for item in uploaded_parts}

    urls = []
    for part_number in payload.part_numbers:
        if part_number in uploaded_numbers:
            continue
        urls.append(
            {
                "part_number": int(part_number),
                "url": storage.presign_upload_part(
                    str(session["storage_key"]),
                    str(session["s3_upload_id"]),
                    int(part_number),
                    expires_in=UPLOAD_PART_EXPIRES_SECONDS,
                ),
            }
        )

    _update_upload_status(upload_id, "uploading")
    return {
        "upload_id": upload_id,
        "uploaded_parts": uploaded_parts,
        "presigned_parts": urls,
        "chunk_size_bytes": 5 * 1024 * 1024,
    }


@app.post("/api/v1/novel/uploads/{upload_id}/complete")
def complete_upload(upload_id: str, payload: CompleteUploadRequest, user: CurrentUser) -> dict[str, Any]:
    session = _load_upload_session(upload_id)
    if session.get("document_id"):
        return _complete_payload(str(session["document_id"]))

    parts = [
        {
            "PartNumber": int(item.part_number),
            "ETag": item.etag,
            "size_bytes": int(item.size_bytes),
        }
        for item in payload.parts
    ]
    if not parts:
        parts = _list_uploaded_parts(session, internal_shape=True)
    if not parts:
        raise HTTPException(status_code=400, detail="no uploaded parts found")

    storage.complete_multipart_upload(
        str(session["storage_key"]),
        str(session["s3_upload_id"]),
        [{"PartNumber": item["PartNumber"], "ETag": item["ETag"]} for item in sorted(parts, key=lambda row: row["PartNumber"])],
    )
    _persist_upload_parts(upload_id, parts)
    object_meta = storage.stat_object(str(session["storage_key"]))

    document_id = str(uuid4())
    job_id = str(uuid4())
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO novel_documents (
                    id, library_id, title, volume_label, file_name, content_hash, storage_path,
                    storage_key, size_bytes, status, query_ready, enhancement_status,
                    created_by, stats_json, upload_session_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, '',
                    %s, %s, 'uploaded', FALSE, '', %s, %s::jsonb, %s
                )
                """,
                (
                    document_id,
                    session["library_id"],
                    session["title"],
                    session["volume_label"],
                    session["file_name"],
                    payload.content_hash.strip(),
                    session["storage_key"],
                    int(object_meta.get("ContentLength") or session["size_bytes"]),
                    user.user_id,
                    to_json({"spoiler_ack": bool(session.get("spoiler_ack")), "upload_mode": "multipart"}),
                    upload_id,
                ),
            )
            cur.execute(
                """
                INSERT INTO novel_ingest_jobs (
                    id, document_id, status, phase, query_ready, enhancement_status, checkpoint_json
                )
                VALUES (%s, %s, 'queued', 'uploaded', FALSE, '', '{}'::jsonb)
                """,
                (job_id, document_id),
            )
            cur.execute(
                """
                UPDATE novel_upload_sessions
                SET status = 'completed',
                    content_hash = %s,
                    document_id = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (payload.content_hash.strip(), document_id, upload_id),
            )
            cur.execute(
                """
                INSERT INTO novel_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'uploaded', 'multipart upload completed', %s::jsonb)
                """,
                (document_id, to_json({"job_id": job_id, "size_bytes": int(object_meta.get("ContentLength") or 0)})),
            )
        conn.commit()
    return _complete_payload(document_id)


@app.get("/api/v1/novel/ingest-jobs/{job_id}")
def get_ingest_job(job_id: str, user: CurrentUser) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT jobs.*, documents.status AS document_status, documents.query_ready,
                       documents.enhancement_status AS document_enhancement_status,
                       documents.query_ready_at, documents.hybrid_ready_at, documents.ready_at,
                       documents.query_ready_until_chapter
                FROM novel_ingest_jobs jobs
                JOIN novel_documents documents ON documents.id = jobs.document_id
                WHERE jobs.id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="ingest job not found")
    return row


@app.post("/api/v1/novel/retrieve")
def retrieve_novel(payload: RetrieveRequest, user: CurrentUser) -> dict[str, Any]:
    result = retrieve_novel_result(
        library_id=payload.library_id,
        question=payload.question,
        document_ids=payload.document_ids,
        limit=payload.limit,
    )
    return {
        "items": [_serialize_evidence(item, corpus_id=f"novel:{payload.library_id}") for item in result.items],
        "retrieval": result.stats.as_dict(),
        "trace_id": current_trace_id(),
    }


@app.post("/api/v1/novel/query")
def query_novel(payload: NovelQueryRequest, user: CurrentUser) -> dict[str, Any]:
    return _build_query_response(payload)


@app.post("/api/v1/novel/query/stream")
def stream_query_novel(payload: NovelQueryRequest, user: CurrentUser) -> StreamingResponse:
    result = _build_query_response(payload)

    def generate() -> Any:
        yield from iter_query_sse_messages(result)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/v1/novel/documents/upload")
def upload_document(
    user: CurrentUser,
    library_id: str = Form(...),
    title: str = Form(...),
    volume_label: str = Form(""),
    spoiler_ack: bool = Form(True),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    file_type = (file.filename or "").split(".")[-1].lower()
    if file_type != "txt":
        raise HTTPException(status_code=400, detail="novel upload currently supports txt only")

    raw = file.file.read()
    content_hash = hashlib.sha256(raw).hexdigest()
    document_id = str(uuid4())
    job_id = str(uuid4())
    storage_key = storage.build_storage_key(service="novel-legacy", document_id=document_id, file_name=file.filename or "source.txt")
    storage.put_bytes(storage_key, raw, metadata={"document_id": document_id, "legacy": "true"})

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO novel_documents (
                    id, library_id, title, volume_label, file_name, content_hash, storage_path,
                    storage_key, size_bytes, status, query_ready, enhancement_status,
                    created_by, stats_json
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, '',
                    %s, %s, 'uploaded', FALSE, '', %s, %s::jsonb
                )
                """,
                (
                    document_id,
                    library_id,
                    title.strip(),
                    volume_label.strip(),
                    file.filename or "source.txt",
                    content_hash,
                    storage_key,
                    len(raw),
                    user.user_id,
                    to_json({"spoiler_ack": bool(spoiler_ack), "legacy_upload": True}),
                ),
            )
            cur.execute(
                """
                INSERT INTO novel_ingest_jobs (id, document_id, status, phase, checkpoint_json)
                VALUES (%s, %s, 'queued', 'uploaded', '{}'::jsonb)
                """,
                (job_id, document_id),
            )
            cur.execute(
                """
                INSERT INTO novel_document_events (document_id, stage, message, details_json)
                VALUES (%s, 'uploaded', 'legacy direct upload completed', %s::jsonb)
                """,
                (document_id, to_json({"job_id": job_id})),
            )
        conn.commit()
    return {
        "id": document_id,
        "job_id": job_id,
        "status": "uploaded",
    }


def _build_query_response(payload: NovelQueryRequest) -> dict[str, Any]:
    strategy = detect_strategy(payload.question)
    retrieval = retrieve_novel_result(
        library_id=payload.library_id,
        question=payload.question,
        document_ids=payload.document_ids,
        limit=8,
    )
    evidence = retrieval.items
    if not evidence:
        result = build_refusal_response(strategy=strategy, reason="no_relevant_evidence")
        result["answer_mode"] = "refusal"
        result["evidence_path"] = []
        result["retrieval"] = retrieval.stats.as_dict()
        result["trace_id"] = current_trace_id()
        return result

    top_score = float(evidence[0].evidence_path.final_score)
    strong_items = [item for item in evidence if float(item.evidence_path.final_score) >= 0.02]
    if len(strong_items) >= 2 and top_score >= 0.02:
        answer_mode = "grounded"
        evidence_status = "grounded"
        grounding_score = min(0.95, 0.62 + (len(strong_items) * 0.05) + top_score)
        answer = _grounded_answer(evidence[:2])
        refusal_reason = ""
    elif top_score >= 0.01:
        answer_mode = "weak_grounded"
        evidence_status = "partial"
        grounding_score = min(0.72, 0.46 + top_score)
        answer = (
            f"根据当前证据，我只能保守确认：{compact_quote(evidence[0].raw_text, 160)}。"
            "现有证据不足以支持更强结论。 [1]"
        )
        refusal_reason = "partial_evidence"
    else:
        answer_mode = "refusal"
        evidence_status = "insufficient"
        grounding_score = 0.0
        answer = "当前小说证据不足，无法给出可靠回答。"
        refusal_reason = "insufficient_evidence"

    citations = [_serialize_evidence(item, corpus_id=f"novel:{payload.library_id}") for item in evidence]
    return {
        "answer": answer,
        "answer_mode": answer_mode,
        "strategy_used": strategy,
        "evidence_status": evidence_status,
        "grounding_score": grounding_score,
        "refusal_reason": refusal_reason,
        "citations": citations,
        "evidence_path": [item["evidence_path"] for item in citations],
        "retrieval": retrieval.stats.as_dict(),
        "trace_id": current_trace_id(),
    }


def _grounded_answer(evidence: list[Any]) -> str:
    first = evidence[0]
    answer = f"最直接的证据来自《{first.document_title}》的 {first.section_title}：{compact_quote(first.raw_text, 130)} [1]"
    if len(evidence) > 1:
        second = evidence[1]
        answer += f"；补充证据见 {second.section_title}：{compact_quote(second.raw_text, 90)} [2]"
    return answer


def _ensure_library_exists(library_id: str) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM novel_libraries WHERE id = %s", (library_id,))
            exists = cur.fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="novel library not found")


def _fetch_library_documents(library_id: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM novel_documents
                WHERE library_id = %s
                ORDER BY created_at DESC
                """,
                (library_id,),
            )
            return cur.fetchall()


def _load_document(document_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM novel_documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return row


def _load_upload_session(upload_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM novel_upload_sessions WHERE id = %s", (upload_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    return row


def _update_upload_status(upload_id: str, status: str) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE novel_upload_sessions
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, upload_id),
            )
        conn.commit()


def _list_uploaded_parts(session: dict[str, Any], *, internal_shape: bool = False) -> list[dict[str, Any]]:
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


def _persist_upload_parts(upload_id: str, parts: list[dict[str, Any]]) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO novel_upload_parts (upload_session_id, part_number, etag, size_bytes, status)
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


def _complete_payload(document_id: str) -> dict[str, Any]:
    document = _load_document(document_id)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text
                FROM novel_ingest_jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            job = cur.fetchone()
    return {
        "document_id": document_id,
        "job_id": str(job["id"]) if job else "",
        "document": document,
    }


def _serialize_upload_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        **session,
        "uploaded_parts": _list_uploaded_parts(session),
    }


def _serialize_evidence(item: Any, *, corpus_id: str) -> dict[str, Any]:
    payload = item.as_dict()
    payload["corpus_id"] = corpus_id
    payload["service_type"] = "novel"
    return payload
