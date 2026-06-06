"""语义缓存 —— 三层缓存体系降低推理成本与延迟。

L1 精确缓存：相同问题+相同知识库版本 → 直接返回（0 Token消耗）
L2 语义缓存：基于问题 embedding 相似度匹配 → 返回缓存答案
L3 Prompt Cache：利用 LLM API 的 prompt caching 缓存 system prompt 前缀

缓存失效策略：
- 知识库文档更新时主动失效相关缓存
- TTL 时间过期自动失效
- 用户反馈点踩时失效对应缓存

集成方式::

    from .semantic_cache import SemanticCache

    cache = SemanticCache(qdrant_client, embedding_fn)
    hit = await cache.lookup(question="退款流程是什么？", corpus_ids=["kb:abc"])
    if hit:
        return hit.cached_answer  # 跳过 LLM 调用
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class CacheHit:
    """缓存命中结果"""

    cache_level: str  # exact / semantic / prompt
    cached_answer: str
    cached_answer_mode: str
    cached_citations: list[dict[str, Any]] = field(default_factory=list)
    cached_usage: dict[str, Any] = field(default_factory=dict)
    similarity_score: float = 1.0  # 语义缓存的相似度
    original_question: str = ""  # 命中缓存的原始问题
    age_seconds: float = 0.0  # 缓存条目年龄


@dataclass
class CacheEntry:
    """缓存条目"""

    cache_key: str  # 精确缓存键
    question_embedding: list[float]  # 问题 embedding
    question: str  # 原始问题
    answer: str
    answer_mode: str
    citations: list[dict[str, Any]]
    usage: dict[str, Any]
    corpus_ids: list[str]  # 关联的知识库 ID（用于失效）
    model_name: str
    created_at: float
    ttl_seconds: float
    hit_count: int = 0


# ---------------------------------------------------------------------------
# 语义缓存
# ---------------------------------------------------------------------------


class SemanticCache:
    """三层语义缓存，集成 Qdrant 向量检索。

    缓存键 = sha256(问题 + 知识库版本 + 模型名)
    语义匹配 = embedding 余弦相似度
    """

    def __init__(
        self,
        *,
        qdrant_client: Any = None,
        embedding_fn: Any = None,
        semantic_threshold: float = 0.92,
        default_ttl: float = 3600.0,  # 默认 1 小时
        max_entries: int = 10000,
        cache_collection: str = "answer-cache",
    ) -> None:
        self._qdrant = qdrant_client
        self._embed_fn = embedding_fn
        self._semantic_threshold = semantic_threshold
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._collection = cache_collection

        # 内存 LRU（fallback，当 Qdrant 不可用时）
        self._memory_cache: dict[str, CacheEntry] = {}
        self._lru_order: list[str] = []
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._expired = 0
        self._clears = 0

    # ---- 查询 ---------------------------------------------------------------

    async def lookup(
        self,
        *,
        question: str,
        corpus_ids: list[str] | None = None,
        model_name: str = "",
        bypass_cache: bool = False,
    ) -> CacheHit | None:
        """查三层缓存，返回命中结果或 None。

        查找顺序: L1 精确 → L2 语义 → L3 Prompt（调用方处理）
        """
        if bypass_cache:
            return None

        corpus_key = ",".join(sorted(corpus_ids or []))
        exact_key = _exact_cache_key(question, corpus_key, model_name)

        # L1: 精确缓存
        hit = await self._lookup_exact(exact_key)
        if hit is not None:
            logger.debug("cache_hit_exact key=%s", exact_key[:32])
            return hit

        # L2: 语义缓存
        if self._embed_fn is not None:
            hit = await self._lookup_semantic(question, corpus_key, model_name)
            if hit is not None:
                logger.debug("cache_hit_semantic similarity=%.3f q=%s", hit.similarity_score, question[:60])
                return hit

        self._misses += 1
        return None

    async def store(
        self,
        *,
        question: str,
        answer: str,
        answer_mode: str,
        citations: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        corpus_ids: list[str] | None = None,
        model_name: str = "",
        ttl_seconds: float | None = None,
    ) -> None:
        """存储缓存条目。"""
        corpus_key = ",".join(sorted(corpus_ids or []))
        exact_key = _exact_cache_key(question, corpus_key, model_name)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        entry = CacheEntry(
            cache_key=exact_key,
            question_embedding=await self._embed(question) if self._embed_fn else [],
            question=question,
            answer=answer,
            answer_mode=answer_mode,
            citations=list(citations or []),
            usage=dict(usage or {}),
            corpus_ids=sorted(corpus_ids or []),
            model_name=model_name,
            created_at=time.time(),
            ttl_seconds=ttl,
        )

        # 写入内存
        self._remove_memory_entry(exact_key)
        self._memory_cache[exact_key] = entry
        self._lru_order.append(exact_key)
        self._writes += 1
        self._evict_lru()

        # 写入 Qdrant（如果有）
        if self._qdrant is not None and self._embed_fn is not None and entry.question_embedding:
            await self._qdrant_store(entry)

        logger.debug("cache_store key=%s ttl=%.0fs", exact_key[:32], ttl)

    async def invalidate(
        self,
        *,
        corpus_id: str = "",
        question: str = "",
        model_name: str = "",
    ) -> int:
        """失效缓存。返回失效的条目数。"""
        removed = 0
        to_remove: list[str] = []

        for key, entry in self._memory_cache.items():
            if corpus_id and corpus_id in entry.corpus_ids:
                to_remove.append(key)
            elif question and entry.question == question:
                to_remove.append(key)
            elif model_name and entry.model_name == model_name:
                to_remove.append(key)

        for key in to_remove:
            self._remove_memory_entry(key)
            removed += 1

        self._clears += removed
        logger.info("cache_invalidated count=%d corpus=%s", removed, corpus_id or "all")
        return removed

    def stats(self) -> dict[str, Any]:
        """缓存统计。"""
        now = time.time()
        expired_entries = self._prune_expired_entries(now)
        entries = list(self._memory_cache.values())
        total_lookups = self._hits + self._misses
        hit_rate = round(self._hits / max(total_lookups, 1), 4)
        return {
            "enabled": True,
            "ttl_seconds": round(float(self._default_ttl), 3),
            "size": len(entries),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "writes": self._writes,
            "expired": self._expired,
            "clears": self._clears,
            "hit_rate": hit_rate,
            "expired_entries": expired_entries,
            "total_entries": len(entries),
            "total_hits": self._hits,
            "hit_rate_estimate": hit_rate,
            "avg_age_seconds": round(
                sum(now - e.created_at for e in entries) / max(len(entries), 1), 1
            ),
            "memory_usage_estimate": len(entries) * 2048,  # 粗略估计
        }

    # ---- 内部 ---------------------------------------------------------------

    async def _lookup_exact(self, exact_key: str) -> CacheHit | None:
        """L1 精确匹配。"""
        entry = self._memory_cache.get(exact_key)
        if entry is None:
            return None
        if time.time() - entry.created_at > entry.ttl_seconds:
            self._remove_memory_entry(exact_key)
            self._expired += 1
            return None
        entry.hit_count += 1
        self._hits += 1
        # LRU 刷新
        if exact_key in self._lru_order:
            self._lru_order.remove(exact_key)
        self._lru_order.append(exact_key)
        return CacheHit(
            cache_level="exact",
            cached_answer=entry.answer,
            cached_answer_mode=entry.answer_mode,
            cached_citations=list(entry.citations),
            cached_usage=dict(entry.usage),
            similarity_score=1.0,
            original_question=entry.question,
            age_seconds=time.time() - entry.created_at,
        )

    async def _lookup_semantic(self, question: str, corpus_key: str, model_name: str) -> CacheHit | None:
        """L2 语义匹配 —— 基于问题 embedding 相似度。"""
        if self._embed_fn is None:
            return None

        query_embedding = await self._embed(question)
        if not query_embedding:
            return None

        best_score = 0.0
        best_entry: CacheEntry | None = None
        expired_keys: list[str] = []

        for entry in self._memory_cache.values():
            if time.time() - entry.created_at > entry.ttl_seconds:
                expired_keys.append(entry.cache_key)
                continue
            if model_name and entry.model_name != model_name:
                continue
            if not entry.question_embedding:
                continue
            score = _cosine_similarity(query_embedding, entry.question_embedding)
            if score > best_score and score >= self._semantic_threshold:
                best_score = score
                best_entry = entry

        if best_entry is not None:
            best_entry.hit_count += 1
            self._hits += 1
            self._remove_expired_keys(expired_keys)
            return CacheHit(
                cache_level="semantic",
                cached_answer=best_entry.answer,
                cached_answer_mode=best_entry.answer_mode,
                cached_citations=list(best_entry.citations),
                cached_usage=dict(best_entry.usage),
                similarity_score=best_score,
                original_question=best_entry.question,
                age_seconds=time.time() - best_entry.created_at,
            )

        self._remove_expired_keys(expired_keys)
        return None

    async def _embed(self, text: str) -> list[float]:
        """生成 text embedding。"""
        if self._embed_fn is None:
            return []
        try:
            result = await self._embed_fn(text)
            if isinstance(result, list):
                return result
            return list(result)
        except Exception as exc:
            logger.warning("semantic_cache_embed_failed err=%s", exc)
            return []

    async def _qdrant_store(self, entry: CacheEntry) -> None:
        """将缓存条目写入 Qdrant。"""
        try:
            import uuid

            point_id = str(uuid.uuid4())
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[{
                    "id": point_id,
                    "vector": entry.question_embedding,
                    "payload": {
                        "cache_key": entry.cache_key,
                        "question": entry.question,
                        "corpus_ids": entry.corpus_ids,
                        "model_name": entry.model_name,
                        "created_at": entry.created_at,
                    },
                }],
            )
        except Exception as exc:
            logger.warning("qdrant_cache_store_failed err=%s", exc)

    def _evict_lru(self) -> None:
        """LRU 淘汰，超过最大条目数时驱逐最旧的。"""
        while len(self._memory_cache) > self._max_entries:
            if not self._lru_order:
                break
            oldest_key = self._lru_order.pop(0)
            self._memory_cache.pop(oldest_key, None)
            logger.debug("cache_lru_evict key=%s", oldest_key[:32])

    def _remove_memory_entry(self, key: str) -> None:
        self._memory_cache.pop(key, None)
        self._lru_order = [item for item in self._lru_order if item != key]

    def _remove_expired_keys(self, keys: list[str]) -> int:
        unique_keys = list(dict.fromkeys(keys))
        for key in unique_keys:
            self._remove_memory_entry(key)
        self._expired += len(unique_keys)
        return len(unique_keys)

    def _prune_expired_entries(self, now: float | None = None) -> int:
        current_time = time.time() if now is None else now
        expired_keys = [
            key
            for key, entry in self._memory_cache.items()
            if current_time - entry.created_at > entry.ttl_seconds
        ]
        return self._remove_expired_keys(expired_keys)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _exact_cache_key(question: str, corpus_key: str, model_name: str) -> str:
    """生成精确缓存键。"""
    raw = json.dumps(
        {"q": question.strip(), "c": corpus_key, "m": model_name},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = (sum(x * x for x in a)) ** 0.5
    norm_b = (sum(y * y for y in b)) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


semantic_cache = SemanticCache()
