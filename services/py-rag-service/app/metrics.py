from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

rag_query_count = Counter(
    "rag_query_count",
    "Total number of RAG queries",
    ["status", "intent"],
)

rag_retrieval_latency_seconds = Histogram(
    "rag_retrieval_latency_seconds",
    "RAG retrieval latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

rag_cache_hits_total = Counter(
    "rag_cache_hits_total",
    "Total number of cache hits",
)

rag_cache_misses_total = Counter(
    "rag_cache_misses_total",
    "Total number of cache misses",
)

rag_rerank_scores = Histogram(
    "rag_rerank_scores",
    "RAG rerank scores distribution",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
)

rag_cache_hit_rate = Gauge(
    "rag_cache_hit_rate",
    "Current cache hit rate",
)

rag_active_requests = Gauge(
    "rag_active_requests",
    "Number of active RAG requests",
)

rag_intent_classification = Counter(
    "rag_intent_classification",
    "RAG intent classification distribution",
    ["intent", "confidence_bucket"],
)

rag_multi_query_usage = Counter(
    "rag_multi_query_usage",
    "RAG multi-query usage count",
    ["variant_count"],
)

rag_retrieval_stats = Histogram(
    "rag_retrieval_stats",
    "RAG retrieval statistics",
    ["stat_type"],
    buckets=[1, 2, 5, 10, 20, 50, 100],
)

rag_query_quality_score = Histogram(
    "rag_query_quality_score",
    "RAG query quality score",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryMetrics:
    """单次查询的性能指标"""

    latency_seconds: float
    cache_hit: bool
    retrieval_count: int
    rerank_score_avg: Optional[float] = None
    status: str = "success"
    intent: str = "unknown"
    intent_confidence: Optional[float] = None
    multi_query_used: bool = False
    multi_query_variants: int = 0
    cache_size: int = 0
    query_id: Optional[str] = None


class MetricsCollector:
    """性能指标收集器"""

    def __init__(self):
        self._request_count = 0

    def start_request(self) -> float:
        """记录请求开始时间"""
        rag_active_requests.inc()
        return time.time()

    def end_request(self, start_time: float) -> None:
        """记录请求结束"""
        rag_active_requests.dec()
        latency = time.time() - start_time
        rag_retrieval_latency_seconds.observe(latency)
        return None

    def record_cache_hit(self) -> None:
        """记录缓存命中"""
        rag_cache_hits_total.inc()

    def record_cache_miss(self) -> None:
        """记录缓存未命中"""
        rag_cache_misses_total.inc()

    def update_cache_metrics(self, hit_rate: float) -> None:
        """更新缓存命中率"""
        rag_cache_hit_rate.set(hit_rate)

    def record_rerank_scores(self, scores: list[float]) -> None:
        """记录重排序分数"""
        for score in scores:
            rag_rerank_scores.observe(score)

    def record_intent_classification(self, intent: str, confidence: float) -> None:
        """记录意图分类结果"""
        confidence_bucket = self._get_confidence_bucket(confidence)
        rag_intent_classification.labels(intent=intent, confidence_bucket=confidence_bucket).inc()

    def record_multi_query_usage(self, variant_count: int) -> None:
        """记录多查询使用情况"""
        rag_multi_query_usage.labels(variant_count=str(variant_count)).inc()

    def record_retrieval_stats(self, stat_type: str, value: int) -> None:
        """记录检索统计"""
        rag_retrieval_stats.labels(stat_type=stat_type).observe(value)

    def record_query_quality_score(self, score: float) -> None:
        """记录查询质量分数"""
        rag_query_quality_score.observe(score)

    def _get_confidence_bucket(self, confidence: float) -> str:
        """获取置信度桶"""
        if confidence >= 0.9:
            return "high"
        elif confidence >= 0.7:
            return "medium"
        else:
            return "low"

    def record_query(self, metrics: QueryMetrics) -> None:
        """记录完整查询指标"""
        rag_query_count.labels(status=metrics.status, intent=metrics.intent).inc()

        if not metrics.cache_hit:
            latency = metrics.latency_seconds
            rag_retrieval_latency_seconds.observe(latency)

            if metrics.retrieval_count > 0:
                self.record_retrieval_stats("retrieved_docs", metrics.retrieval_count)

            if metrics.rerank_score_avg is not None:
                self.record_rerank_scores([metrics.rerank_score_avg])
                self.record_query_quality_score(metrics.rerank_score_avg)

        if metrics.intent and metrics.intent_confidence is not None:
            self.record_intent_classification(metrics.intent, metrics.intent_confidence)

        if metrics.multi_query_used:
            self.record_multi_query_usage(metrics.multi_query_variants)

        logger.info(
            f"Query metrics: latency={metrics.latency_seconds:.3f}s "
            f"cache_hit={metrics.cache_hit} retrieval_count={metrics.retrieval_count} "
            f"status={metrics.status} intent={metrics.intent} "
            f"multi_query={metrics.multi_query_used} query_id={metrics.query_id}"
        )


metrics_collector = MetricsCollector()

create_metrics_endpoint = make_asgi_app
