from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RAGOptimizationConfig:
    """RAG 优化配置"""

    # 混合检索配置
    hybrid_search_dense_weight: float = 0.7
    hybrid_search_sparse_weight: float = 0.3

    # 重排序配置
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 8

    # 查询缓存配置
    query_cache_enabled: bool = True
    query_cache_ttl_hours: int = 24
    query_cache_max_size: int = 10000

    # 分块策略配置
    default_chunk_size: int = 1024
    default_chunk_overlap: int = 100

    # 意图分类配置
    intent_classification_enabled: bool = True

    # 元数据增强配置
    metadata_enhancement_enabled: bool = True
    max_keywords: int = 5

    @classmethod
    def from_env(cls) -> "RAGOptimizationConfig":
        """从环境变量加载配置"""
        return cls(
            # 混合检索配置
            hybrid_search_dense_weight=getenv_float(
                "HYBRID_SEARCH_DENSE_WEIGHT", 0.7
            ),
            hybrid_search_sparse_weight=getenv_float(
                "HYBRID_SEARCH_SPARSE_WEIGHT", 0.3
            ),
            # 重排序配置
            reranker_model=os.getenv(
                "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            reranker_top_k=getenv_int("RERANKER_TOP_K", 8),
            # 查询缓存配置
            query_cache_enabled=getenv_bool("QUERY_CACHE_ENABLED", True),
            query_cache_ttl_hours=getenv_int("QUERY_CACHE_TTL_HOURS", 24),
            query_cache_max_size=getenv_int("QUERY_CACHE_MAX_SIZE", 10000),
            # 分块策略配置
            default_chunk_size=getenv_int("DEFAULT_CHUNK_SIZE", 1024),
            default_chunk_overlap=getenv_int("DEFAULT_CHUNK_OVERLAP", 100),
            # 意图分类配置
            intent_classification_enabled=getenv_bool(
                "INTENT_CLASSIFICATION_ENABLED", True
            ),
            # 元数据增强配置
            metadata_enhancement_enabled=getenv_bool(
                "METADATA_ENHANCEMENT_ENABLED", True
            ),
            max_keywords=getenv_int("MAX_KEYWORDS", 5),
        )


def getenv_bool(name: str, fallback: bool) -> bool:
    """获取布尔类型环境变量"""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return fallback
    return raw in ("true", "1", "yes", "on")


def getenv_int(name: str, fallback: int) -> int:
    """获取整数类型环境变量"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def getenv_float(name: str, fallback: float) -> float:
    """获取浮点数类型环境变量"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback
