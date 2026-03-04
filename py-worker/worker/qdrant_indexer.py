from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)


@dataclass(frozen=True)
class IndexPoint:
    point_id: str
    vector: List[float]
    payload: dict


class QdrantIndexer:
    def __init__(self, url: str, collection: str, embedding_dim: int):
        self._collection = collection
        self._client = QdrantClient(url=url)
        self._ensure_collection(embedding_dim)

    def _ensure_collection(self, embedding_dim: int) -> None:
        existing = [item.name for item in self._client.get_collections().collections]
        if self._collection in existing:
            current_dim = self._current_collection_dim()
            if current_dim is not None and current_dim != embedding_dim:
                raise ValueError(
                    f"qdrant collection '{self._collection}' vector size mismatch: "
                    f"expected={embedding_dim}, current={current_dim}"
                )
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
        )

    def _current_collection_dim(self) -> int | None:
        detail = self._client.get_collection(collection_name=self._collection)
        vectors = detail.config.params.vectors
        if hasattr(vectors, "size"):
            return int(vectors.size)

        if isinstance(vectors, dict) and vectors:
            first = next(iter(vectors.values()))
            if hasattr(first, "size"):
                return int(first.size)

        return None

    def replace_document_points(self, document_id: str, points: Iterable[IndexPoint]) -> None:
        selector = FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            )
        )
        self._client.delete(
            collection_name=self._collection,
            points_selector=selector,
            wait=True,
        )

        batch: List[PointStruct] = []
        for item in points:
            batch.append(PointStruct(id=item.point_id, vector=item.vector, payload=item.payload))

        if batch:
            self._client.upsert(collection_name=self._collection, points=batch, wait=True)
