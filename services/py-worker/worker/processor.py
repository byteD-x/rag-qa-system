from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import psycopg

from worker.chunking import chunk_segments
from worker.config import WorkerConfig
from worker.db import DB
from worker.embedding import EmbeddingClient
from worker.metadata_enhancer import MetadataEnhancer
from worker.parser import parse_document
from worker.qdrant_indexer import IndexPoint, QdrantIndexer
from worker.storage import S3Store


class IngestProcessor:
    def __init__(self, cfg: WorkerConfig):
        self._cfg = cfg
        self._db = DB(cfg.postgres_dsn)
        self._s3 = S3Store(
            endpoint=cfg.s3_endpoint,
            access_key=cfg.s3_access_key,
            secret_key=cfg.s3_secret_key,
            bucket=cfg.s3_bucket,
            use_ssl=cfg.s3_use_ssl,
        )
        self._embedding_client = EmbeddingClient(cfg)
        self._metadata_enhancer = MetadataEnhancer(max_keywords=cfg.metadata_max_keywords)

    def process_job(self, job_id: str) -> tuple[bool, str]:
        try:
            with self._db.connect() as conn:
                conn.autocommit = False
                job, doc = self._db.load_job_with_document(conn, job_id)
                self._db.mark_running(conn, job.job_id, progress=5)
                conn.commit()

            with tempfile.TemporaryDirectory(prefix="ragp-ingest-") as tmp_dir:
                file_path = Path(tmp_dir) / f"source.{doc.file_type}"
                self._s3.download_to(doc.storage_key, file_path)

                with self._db.connect() as conn:
                    conn.autocommit = False
                    self._db.update_progress(conn, job.job_id, progress=20)
                    conn.commit()

                segments = parse_document(file_path, doc.file_type)
                
                full_text = " ".join(seg.text for seg in segments)
                metadata = None
                if self._cfg.metadata_enhancement_enabled:
                    metadata = self._metadata_enhancer.enhance(full_text)
                
                chunks = chunk_segments(segments, chunk_tokens=800, overlap_tokens=120)
                if not chunks:
                    raise ValueError("document parse succeeded but no text chunks generated")

                with self._db.connect() as conn:
                    conn.autocommit = False
                    self._db.update_progress(conn, job.job_id, progress=55)
                    conn.commit()

                import pickle
                
                # Simple local checkpointing to prevent full-recalculation on transient errors
                chk_path = Path(tmp_dir) / f"{job.job_id}_checkpoint.pkl"
                processed_chunk_cache = {}
                if chk_path.exists():
                    try:
                        with open(chk_path, "rb") as f:
                            processed_chunk_cache = pickle.load(f)
                    except Exception:
                        pass

                vector_points: list[IndexPoint] = []
                db_chunks: list[tuple[int, str, str, int, str]] = []
                for chunk in chunks:
                    point_id = str(uuid.uuid4())
                    
                    # Only embed if not processed already during a previous retry attempt
                    vector = None
                    if chunk.chunk_index not in processed_chunk_cache:
                        vector = self._embedding_client.embed(chunk.text)
                        processed_chunk_cache[chunk.chunk_index] = vector
                        with open(chk_path, "wb") as f:
                            pickle.dump(processed_chunk_cache, f)
                    else:
                        vector = processed_chunk_cache[chunk.chunk_index]
                    
                    payload = {
                        "document_id": doc.id,
                        "corpus_id": doc.corpus_id,
                        "file_name": doc.file_name,
                        "file_type": doc.file_type,
                        "page_or_loc": chunk.page_or_loc,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                    }
                    db_chunks.append((chunk.chunk_index, chunk.text, chunk.page_or_loc, chunk.token_count, point_id))

                embedding_dim = len(vector_points[0].vector)
                indexer = QdrantIndexer(
                    url=self._cfg.qdrant_url,
                    collection=self._cfg.qdrant_collection,
                    embedding_dim=embedding_dim,
                )
                indexer.replace_document_points(document_id=doc.id, points=vector_points)

                with self._db.connect() as conn:
                    conn.autocommit = False
                    self._db.update_progress(conn, job.job_id, progress=85)
                    self._db.replace_chunks(conn, doc.id, db_chunks)
                    self._db.mark_done(conn, job.job_id)
                    conn.commit()

            return True, "indexed"

        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            with self._db.connect() as conn:
                conn.autocommit = False
                retry_count = self._db.increase_retry(conn, job_id)
                if retry_count <= self._cfg.worker_max_retries:
                    self._db.mark_queued_for_retry(conn, job_id, f"retrying after error: {msg}")
                    conn.commit()
                    return False, "retry"

                self._db.mark_failed(conn, job_id, f"ingest failed permanently: {msg}")
                conn.commit()
            return False, "failed"
