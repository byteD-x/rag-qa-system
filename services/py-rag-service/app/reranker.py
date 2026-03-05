from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence


def load_cross_encoder(model_name: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


@dataclass(frozen=True)
class RerankResult:
    """重排序结果"""

    chunk_id: str
    document_id: str
    corpus_id: str
    file_name: str
    page_or_loc: str
    text: str
    original_score: float
    rerank_score: float
    hybrid_score: Optional[float]
    rank: int


class Reranker:
    """Cross-Encoder 重排序器"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """
        初始化重排序器

        Args:
            model_name: Cross-Encoder 模型名称
        """
        self._model_name = model_name
        self._model: Optional[Any] = None
        self._lock = threading.Lock()
        self._model_loaded = False

    @property
    def model(self) -> Any:
        """懒加载模型（线程安全）"""
        if not self._model_loaded:
            with self._lock:
                if not self._model_loaded:
                    self._model = load_cross_encoder(self._model_name)
                    self._model_loaded = True
        return self._model

    @property
    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model_loaded

    def rerank(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 8,
    ) -> List[RerankResult]:
        """
        对检索结果进行重排序

        Args:
            query: 查询文本
            documents: 文档列表，每个文档包含 text 字段和元数据
            top_k: 保留的重排序结果数量

        Returns:
            重排序后的结果列表
        """
        if not documents:
            return []

        pairs = [[query, doc.get("text", "")] for doc in documents]
        scores = self.model.predict(pairs)

        scored_results = []
        for idx, score in enumerate(scores):
            doc = documents[idx]
            scored_results.append(
                {
                    "chunk_id": doc.get("chunk_id", ""),
                    "document_id": doc.get("document_id", ""),
                    "corpus_id": doc.get("corpus_id", ""),
                    "file_name": doc.get("file_name", "unknown"),
                    "page_or_loc": doc.get("page_or_loc", "loc:unknown"),
                    "text": doc.get("text", ""),
                    "original_score": doc.get("score", 0.0),
                    "rerank_score": float(score),
                }
            )

        scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        results = []
        for rank, item in enumerate(scored_results[:top_k], start=1):
            results.append(
                RerankResult(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    corpus_id=item["corpus_id"],
                    file_name=item["file_name"],
                    page_or_loc=item["page_or_loc"],
                    text=item["text"],
                    original_score=item["original_score"],
                    rerank_score=item["rerank_score"],
                    hybrid_score=None,
                    rank=rank,
                )
            )

        return results

    def rerank_with_hybrid_score(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 8,
        hybrid_weight: float = 0.5,
        normalization: str = "minmax",
    ) -> List[RerankResult]:
        """
        使用混合分数重排序（结合原始分数和重排序分数）

        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 保留的重排序结果数量
            hybrid_weight: 重排序分数权重（0-1），默认 0.5
            normalization: 归一化方法，支持 "minmax" 或 "max"

        Returns:
            重排序后的结果列表
        """
        if not documents:
            return []

        if not (0.0 <= hybrid_weight <= 1.0):
            raise ValueError("hybrid_weight must be between 0.0 and 1.0")

        pairs = [[query, doc.get("text", "")] for doc in documents]
        rerank_scores = self.model.predict(pairs)

        original_scores = [doc.get("score", 0.0) for doc in documents]

        if normalization == "minmax":
            min_original = min(original_scores)
            max_original = max(original_scores)
            min_rerank = min(rerank_scores)
            max_rerank = max(rerank_scores)

            range_original = max_original - min_original if max_original > min_original else 1.0
            range_rerank = max_rerank - min_rerank if max_rerank > min_rerank else 1.0

            norm_original = [(s - min_original) / range_original for s in original_scores]
            norm_rerank = [(s - min_rerank) / range_rerank for s in rerank_scores]
        else:
            max_original = max(original_scores, default=1.0)
            max_rerank = max(rerank_scores, default=1.0)

            norm_original = [s / max_original if max_original > 0 else 0.0 for s in original_scores]
            norm_rerank = [s / max_rerank if max_rerank > 0 else 0.0 for s in rerank_scores]

        scored_results = []
        for idx in range(len(documents)):
            doc = documents[idx]
            hybrid_score = (
                norm_original[idx] * (1 - hybrid_weight) + norm_rerank[idx] * hybrid_weight
            )

            scored_results.append(
                {
                    "chunk_id": doc.get("chunk_id", ""),
                    "document_id": doc.get("document_id", ""),
                    "corpus_id": doc.get("corpus_id", ""),
                    "file_name": doc.get("file_name", "unknown"),
                    "page_or_loc": doc.get("page_or_loc", "loc:unknown"),
                    "text": doc.get("text", ""),
                    "original_score": original_scores[idx],
                    "rerank_score": float(rerank_scores[idx]),
                    "hybrid_score": hybrid_score,
                }
            )

        scored_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        results = []
        for rank, item in enumerate(scored_results[:top_k], start=1):
            results.append(
                RerankResult(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    corpus_id=item["corpus_id"],
                    file_name=item["file_name"],
                    page_or_loc=item["page_or_loc"],
                    text=item["text"],
                    original_score=item["original_score"],
                    rerank_score=item["rerank_score"],
                    hybrid_score=item["hybrid_score"],
                    rank=rank,
                )
            )

        return results
