from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CachedQuery:
    """缓存的查询结果"""

    query_hash: str
    question: str
    result: Any
    created_at: float
    ttl_seconds: int
    hit_count: int = 0

    def is_expired(self) -> bool:
        """检查是否已过期"""
        return time.time() - self.created_at > self.ttl_seconds


class QueryCache:
    """查询缓存：LRU 策略 + TTL 过期"""

    def __init__(
        self,
        max_size: int = 10000,
        ttl_hours: int = 24,
    ):
        """
        初始化查询缓存

        Args:
            max_size: 最大缓存条目数
            ttl_hours: 缓存存活时间（小时）
        """
        self._max_size = max_size
        self._ttl_seconds = ttl_hours * 3600
        self._cache: OrderedDict[str, CachedQuery] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, question: str) -> Optional[Any]:
        """
        从缓存获取结果

        Args:
            question: 查询问题

        Returns:
            缓存的结果，如果不存在或已过期则返回 None
        """
        query_hash = self._hash_query(question)

        if query_hash not in self._cache:
            self._misses += 1
            return None

        cached = self._cache[query_hash]

        if cached.is_expired():
            self._cache.pop(query_hash)
            self._misses += 1
            return None

        self._cache.move_to_end(query_hash)
        object.__setattr__(cached, "hit_count", cached.hit_count + 1)
        self._hits += 1

        return cached.result

    def set(self, question: str, result: Any) -> None:
        """
        缓存查询结果

        Args:
            question: 查询问题
            result: 查询结果
        """
        query_hash = self._hash_query(question)

        if query_hash in self._cache:
            self._cache.pop(query_hash)

        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        cached = CachedQuery(
            query_hash=query_hash,
            question=question,
            result=result,
            created_at=time.time(),
            ttl_seconds=self._ttl_seconds,
        )

        self._cache[query_hash] = cached

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def invalidate(self, question: str) -> bool:
        """
        使特定查询的缓存失效

        Args:
            question: 查询问题

        Returns:
            如果成功删除返回 True，否则返回 False
        """
        query_hash = self._hash_query(question)
        if query_hash in self._cache:
            self._cache.pop(query_hash)
            return True
        return False

    @property
    def size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def stats(self) -> Dict[str, Any]:
        """缓存统计信息"""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }

    def _hash_query(self, question: str) -> str:
        """生成查询哈希"""
        normalized = question.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
