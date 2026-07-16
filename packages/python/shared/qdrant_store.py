from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models


DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "langchain-sparse"


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    api_key: str
    collection: str
    prefer_grpc: bool
    timeout_seconds: float
    fastembed_model_name: str
    fastembed_sparse_model_name: str
    fastembed_vector_size: int
    fastembed_threads: int
    fastembed_cache_dir: str
    index_batch_size: int


def load_qdrant_settings(prefix: str = "QDRANT") -> QdrantSettings:
    timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "10").strip()
    try:
        timeout_seconds = max(float(timeout_raw), 1.0)
    except ValueError:
        timeout_seconds = 10.0

    threads_raw = os.getenv("FASTEMBED_THREADS", "4").strip()
    try:
        fastembed_threads = max(int(threads_raw), 1)
    except ValueError:
        fastembed_threads = 4

    vector_size_raw = os.getenv("FASTEMBED_VECTOR_SIZE", "").strip()
    try:
        fastembed_vector_size = max(int(vector_size_raw), 0) if vector_size_raw else 0
    except ValueError:
        fastembed_vector_size = 0

    batch_size_raw = os.getenv("FASTEMBED_BATCH_SIZE", "64").strip()
    try:
        index_batch_size = max(int(batch_size_raw), 1)
    except ValueError:
        index_batch_size = 64

    return QdrantSettings(
        url=os.getenv(f"{prefix}_URL", "http://qdrant:6333").strip() or "http://qdrant:6333",
        api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
        collection=os.getenv(f"{prefix}_COLLECTION", "kb-evidence").strip() or "kb-evidence",
        prefer_grpc=os.getenv(f"{prefix}_PREFER_GRPC", "false").strip().lower() in {"1", "true", "yes", "on"},
        timeout_seconds=timeout_seconds,
        fastembed_model_name=os.getenv("FASTEMBED_MODEL_NAME", "BAAI/bge-small-zh-v1.5").strip() or "BAAI/bge-small-zh-v1.5",
        fastembed_sparse_model_name=os.getenv("FASTEMBED_SPARSE_MODEL_NAME", "Qdrant/bm25").strip() or "Qdrant/bm25",
        fastembed_vector_size=fastembed_vector_size,
        fastembed_threads=fastembed_threads,
        fastembed_cache_dir=os.getenv("FASTEMBED_CACHE_DIR", "").strip(),
        index_batch_size=index_batch_size,
    )


def check_qdrant_runtime_config(*, settings: QdrantSettings | None = None, prefix: str = "QDRANT") -> dict[str, Any]:
    config = settings or load_qdrant_settings(prefix=prefix)
    return {
        "status": "ok",
        "endpoint": _safe_endpoint(config.url),
        "collection": config.collection,
        "prefer_grpc": config.prefer_grpc,
        "timeout_seconds": config.timeout_seconds,
        "api_key_configured": bool(config.api_key),
        "fastembed_model": config.fastembed_model_name,
        "fastembed_sparse_model": config.fastembed_sparse_model_name,
        "fastembed_vector_size": config.fastembed_vector_size,
        "fastembed_threads": config.fastembed_threads,
        "fastembed_cache_dir_configured": bool(config.fastembed_cache_dir),
        "index_batch_size": config.index_batch_size,
    }


def _safe_endpoint(url: str) -> str:
    cleaned = str(url or "").strip()
    if not cleaned:
        return ""
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return cleaned.split("@", 1)[-1]
    if not parts.scheme or not parts.netloc:
        return cleaned.split("@", 1)[-1]
    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def qdrant_point_id(*, unit_type: str, unit_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"qdrant-point:{unit_type}:{unit_id}"))


def dense_vector_size(settings: QdrantSettings | None = None) -> int:
    config = settings or load_qdrant_settings()
    if config.fastembed_vector_size > 0:
        return config.fastembed_vector_size
    for item in TextEmbedding.list_supported_models():
        if str(item.get("model") or "") == config.fastembed_model_name:
            return int(item.get("dim") or 0)
    raise RuntimeError(f"unsupported FASTEMBED_MODEL_NAME: {config.fastembed_model_name}")


def get_qdrant_client(settings: QdrantSettings | None = None) -> QdrantClient:
    config = settings or load_qdrant_settings()
    return _get_qdrant_client_cached(
        config.url,
        config.api_key,
        config.prefer_grpc,
        config.timeout_seconds,
    )


@lru_cache(maxsize=2)
def _get_qdrant_client_cached(url: str, api_key: str, prefer_grpc: bool, timeout_seconds: float) -> QdrantClient:
    return QdrantClient(
        url=url,
        api_key=api_key or None,
        prefer_grpc=prefer_grpc,
        timeout=timeout_seconds,
    )


def ensure_qdrant_collection(
    *,
    client: QdrantClient | None = None,
    settings: QdrantSettings | None = None,
) -> dict[str, Any]:
    config = settings or load_qdrant_settings()
    qdrant = client or get_qdrant_client(config)
    size = dense_vector_size(config)
    if not qdrant.collection_exists(config.collection):
        qdrant.create_collection(
            collection_name=config.collection,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(),
            },
        )
        # 载荷索引只在集合新建时建一次;后续查询不再重复建,避免每查多次往返。
        for field_name in (
            "base_id",
            "document_id",
            "unit_type",
            "source_kind",
            "metadata.base_id",
            "metadata.document_id",
            "metadata.unit_type",
            "metadata.source_kind",
        ):
            qdrant.create_payload_index(
                config.collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
    return {
        "url": config.url,
        "collection": config.collection,
        "vector_name": DENSE_VECTOR_NAME,
        "sparse_vector_name": SPARSE_VECTOR_NAME,
        "vector_size": size,
        "model": config.fastembed_model_name,
        "sparse_model": config.fastembed_sparse_model_name,
    }


def check_qdrant_access(
    *,
    client: QdrantClient | None = None,
    settings: QdrantSettings | None = None,
) -> dict[str, Any]:
    config = settings or load_qdrant_settings()
    qdrant = client or get_qdrant_client(config)
    info = qdrant.get_collection(config.collection)
    return {
        "collection": config.collection,
        "status": str(getattr(info, "status", "") or "ok"),
    }
