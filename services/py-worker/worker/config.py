from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    postgres_dsn: str
    redis_url: str
    ingest_queue_key: str
    poll_interval_seconds: int
    worker_max_retries: int

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_use_ssl: bool

    qdrant_url: str
    qdrant_collection: str
    embedding_dim: int

    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_embedding_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_retry_delay_milliseconds: int

    metadata_enhancement_enabled: bool
    metadata_max_keywords: int


def build_worker_config() -> WorkerConfig:
    poll_interval = int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5"))
    max_retries = int(os.getenv("WORKER_MAX_RETRIES", "3"))
    embedding_dim = int(os.getenv("EMBEDDING_DIM", "256"))
    llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
    llm_retry_delay_milliseconds = int(os.getenv("LLM_RETRY_DELAY_MILLISECONDS", "600"))
    metadata_enhancement_enabled = os.getenv("METADATA_ENHANCEMENT_ENABLED", "true").lower() == "true"
    metadata_max_keywords = int(os.getenv("METADATA_MAX_KEYWORDS", "5"))

    if poll_interval <= 0:
        poll_interval = 5
    if max_retries < 0:
        max_retries = 0
    if embedding_dim <= 0:
        embedding_dim = 256
    if llm_timeout_seconds <= 0:
        llm_timeout_seconds = 30
    if llm_max_retries < 0:
        llm_max_retries = 0
    if llm_retry_delay_milliseconds < 0:
        llm_retry_delay_milliseconds = 0
    if metadata_max_keywords <= 0:
        metadata_max_keywords = 5

    return WorkerConfig(
        postgres_dsn=os.getenv("POSTGRES_DSN", "postgres://rag:rag@postgres:5432/rag?sslmode=disable"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        ingest_queue_key=os.getenv("INGEST_QUEUE_KEY", "ingest_jobs"),
        poll_interval_seconds=poll_interval,
        worker_max_retries=max_retries,
        s3_endpoint=os.getenv("S3_ENDPOINT", "minio:9000"),
        s3_access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        s3_bucket=os.getenv("S3_BUCKET", "rag-raw"),
        s3_use_ssl=os.getenv("S3_USE_SSL", "false").lower() == "true",
        qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "rag_chunks"),
        embedding_dim=embedding_dim,
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower() or "openai",
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_embedding_model=os.getenv("LLM_EMBEDDING_MODEL", "").strip(),
        llm_timeout_seconds=llm_timeout_seconds,
        llm_max_retries=llm_max_retries,
        llm_retry_delay_milliseconds=llm_retry_delay_milliseconds,
        metadata_enhancement_enabled=metadata_enhancement_enabled,
        metadata_max_keywords=metadata_max_keywords,
    )
