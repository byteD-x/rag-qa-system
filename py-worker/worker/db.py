from __future__ import annotations

from dataclasses import dataclass
from typing import List

import psycopg


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    document_id: str
    status: str
    retry_count: int


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    corpus_id: str
    file_name: str
    file_type: str
    storage_key: str


class DB:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def load_job_with_document(self, conn: psycopg.Connection, job_id: str) -> tuple[JobRecord, DocumentRecord]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.id, j.document_id, j.status, j.retry_count,
                       d.id, d.corpus_id, d.file_name, d.file_type, d.storage_key
                FROM ingest_jobs j
                JOIN documents d ON d.id = j.document_id
                WHERE j.id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"job not found: {job_id}")

        job = JobRecord(
            job_id=str(row[0]),
            document_id=str(row[1]),
            status=str(row[2]),
            retry_count=int(row[3]),
        )
        doc = DocumentRecord(
            id=str(row[4]),
            corpus_id=str(row[5]),
            file_name=str(row[6]),
            file_type=str(row[7]),
            storage_key=str(row[8]),
        )
        return job, doc

    def mark_running(self, conn: psycopg.Connection, job_id: str, progress: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET status = 'running', progress = %s, error_message = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (progress, job_id),
            )
            cur.execute(
                """
                UPDATE documents
                SET status = 'indexing'
                WHERE id = (SELECT document_id FROM ingest_jobs WHERE id = %s)
                """,
                (job_id,),
            )

    def update_progress(self, conn: psycopg.Connection, job_id: str, progress: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET progress = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (progress, job_id),
            )

    def replace_chunks(
        self,
        conn: psycopg.Connection,
        document_id: str,
        chunks: List[tuple[int, str, str, int, str]],
    ) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM doc_chunks WHERE document_id = %s", (document_id,))
            if not chunks:
                return
            cur.executemany(
                """
                INSERT INTO doc_chunks (id, document_id, chunk_index, chunk_text, page_or_loc, token_count, qdrant_point_id)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
                """,
                [(document_id, idx, text, loc, token_count, point_id) for idx, text, loc, token_count, point_id in chunks],
            )

    def mark_done(self, conn: psycopg.Connection, job_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET status = 'done', progress = 100, error_message = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            cur.execute(
                """
                UPDATE documents
                SET status = 'ready'
                WHERE id = (SELECT document_id FROM ingest_jobs WHERE id = %s)
                """,
                (job_id,),
            )

    def mark_failed(self, conn: psycopg.Connection, job_id: str, error_message: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET status = 'failed', error_message = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (error_message[:3000], job_id),
            )
            cur.execute(
                """
                UPDATE documents
                SET status = 'failed'
                WHERE id = (SELECT document_id FROM ingest_jobs WHERE id = %s)
                """,
                (job_id,),
            )

    def increase_retry(self, conn: psycopg.Connection, job_id: str) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET retry_count = retry_count + 1, updated_at = NOW()
                WHERE id = %s
                RETURNING retry_count
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"job not found for retry: {job_id}")
            return int(row[0])
    def mark_queued_for_retry(self, conn: psycopg.Connection, job_id: str, error_message: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_jobs
                SET status = 'queued', progress = 0, error_message = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (error_message[:3000], job_id),
            )
