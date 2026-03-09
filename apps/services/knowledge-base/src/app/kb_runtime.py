from __future__ import annotations

import os

from shared.logging import setup_logging
from shared.metrics import Counter, Gauge, Histogram

from .runtime import db, prepare_runtime, storage


logger = setup_logging("kb-service")
UPLOAD_PART_EXPIRES_SECONDS = int(os.getenv("UPLOAD_PART_EXPIRES_SECONDS", "3600"))
IDEMPOTENCY_TTL_HOURS = max(int(os.getenv("KB_IDEMPOTENCY_TTL_HOURS", "24")), 1)
DEFAULT_INGEST_MAX_ATTEMPTS = max(int(os.getenv("KB_INGEST_MAX_ATTEMPTS", "5")), 1)
KB_READ_PERMISSION = "kb.read"
KB_WRITE_PERMISSION = "kb.write"
KB_MANAGE_PERMISSION = "kb.manage"
CHAT_PERMISSION = "chat.use"
AUDIT_PERMISSION = "audit.read"

KB_UPLOAD_REQUESTS_TOTAL = Counter(
    "rag_kb_upload_requests_total",
    "KB upload requests.",
    labelnames=("result",),
)
KB_RETRIEVE_REQUESTS_TOTAL = Counter(
    "rag_kb_retrieve_requests_total",
    "KB retrieve and query requests.",
    labelnames=("result", "degraded"),
)
KB_RETRIEVE_LATENCY_MS = Histogram(
    "rag_kb_retrieve_latency_ms",
    "KB retrieval latency in milliseconds.",
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)
KB_INGEST_JOBS_GAUGE = Gauge(
    "rag_kb_ingest_jobs_total",
    "Current KB ingest jobs by status.",
    labelnames=("status",),
)
KB_DEAD_LETTER_GAUGE = Gauge(
    "rag_kb_dead_letter_total",
    "Current KB dead-letter ingest jobs.",
)
KB_IDEMPOTENCY_TOTAL = Counter(
    "rag_kb_idempotency_total",
    "KB idempotency outcomes.",
    labelnames=("result", "scope"),
)


__all__ = [
    "AUDIT_PERMISSION",
    "CHAT_PERMISSION",
    "DEFAULT_INGEST_MAX_ATTEMPTS",
    "IDEMPOTENCY_TTL_HOURS",
    "KB_DEAD_LETTER_GAUGE",
    "KB_IDEMPOTENCY_TOTAL",
    "KB_INGEST_JOBS_GAUGE",
    "KB_MANAGE_PERMISSION",
    "KB_READ_PERMISSION",
    "KB_RETRIEVE_LATENCY_MS",
    "KB_RETRIEVE_REQUESTS_TOTAL",
    "KB_UPLOAD_REQUESTS_TOTAL",
    "KB_WRITE_PERMISSION",
    "UPLOAD_PART_EXPIRES_SECONDS",
    "db",
    "logger",
    "prepare_runtime",
    "storage",
]
