#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检索质量追踪模块

追踪每次查询的检索质量，包括：
- Query ID 追踪
- 检索文档统计
- 重排序分数分布
- 用户反馈关联
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from uuid import uuid4


@dataclass
class RetrievalRecord:
    """单次检索记录"""
    query_id: str
    question: str
    timestamp: str
    intent: str
    intent_confidence: float
    retrieval_count: int
    rerank_scores: List[float]
    cache_hit: bool
    multi_query_used: bool
    multi_query_variants: int = 0
    latency_ms: float = 0.0
    top_score: float = 0.0
    avg_score: float = 0.0
    feedback_id: Optional[int] = None
    metadata: Dict = field(default_factory=dict)


class RetrievalTracker:
    """检索质量追踪器"""

    def __init__(self, db_path: str = "retrieval_tracking.db"):
        """
        初始化追踪器

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """初始化数据库"""
        with self._get_connection() as conn:
            # 表已经在 _init_schema 中创建，这里不需要重复操作
            pass

    @contextmanager
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # 确保每次连接都初始化表
        self._init_schema(conn)
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self, conn):
        """初始化数据库表结构"""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_records (
                query_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                intent TEXT NOT NULL,
                intent_confidence REAL NOT NULL,
                retrieval_count INTEGER NOT NULL,
                rerank_scores TEXT NOT NULL,
                cache_hit INTEGER NOT NULL,
                multi_query_used INTEGER NOT NULL,
                multi_query_variants INTEGER DEFAULT 0,
                latency_ms REAL NOT NULL,
                top_score REAL NOT NULL,
                avg_score REAL NOT NULL,
                feedback_id INTEGER,
                metadata TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON retrieval_records(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_intent ON retrieval_records(intent)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback ON retrieval_records(feedback_id)
        """)
        conn.commit()

    def generate_query_id(self) -> str:
        """生成唯一的 Query ID"""
        return f"q_{uuid4().hex[:16]}"

    def record_retrieval(
        self,
        question: str,
        intent: str,
        intent_confidence: float,
        retrieval_count: int,
        rerank_scores: List[float],
        cache_hit: bool,
        multi_query_used: bool,
        latency_ms: float,
        multi_query_variants: int = 0,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        记录一次检索

        Args:
            question: 用户问题
            intent: 意图类型
            intent_confidence: 意图置信度
            retrieval_count: 检索文档数量
            rerank_scores: 重排序分数列表
            cache_hit: 是否缓存命中
            multi_query_used: 是否使用多查询
            latency_ms: 延迟（毫秒）
            multi_query_variants: 多查询变体数量
            metadata: 元数据

        Returns:
            query_id
        """
        query_id = self.generate_query_id()
        timestamp = datetime.now().isoformat()

        top_score = max(rerank_scores) if rerank_scores else 0.0
        avg_score = sum(rerank_scores) / len(rerank_scores) if rerank_scores else 0.0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO retrieval_records (
                    query_id, question, timestamp, intent, intent_confidence,
                    retrieval_count, rerank_scores, cache_hit, multi_query_used,
                    multi_query_variants, latency_ms, top_score, avg_score, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query_id,
                question,
                timestamp,
                intent,
                intent_confidence,
                retrieval_count,
                json.dumps(rerank_scores),
                1 if cache_hit else 0,
                1 if multi_query_used else 0,
                multi_query_variants,
                latency_ms,
                top_score,
                avg_score,
                json.dumps(metadata or {}),
            ))
            conn.commit()

        return query_id

    def link_feedback(self, query_id: str, feedback_id: int) -> None:
        """
        关联用户反馈到检索记录

        Args:
            query_id: 查询 ID
            feedback_id: 反馈 ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE retrieval_records
                SET feedback_id = ?
                WHERE query_id = ?
            """, (feedback_id, query_id))
            conn.commit()

    def get_record(self, query_id: str) -> Optional[RetrievalRecord]:
        """
        获取检索记录

        Args:
            query_id: 查询 ID

        Returns:
            检索记录或 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM retrieval_records
                WHERE query_id = ?
            """, (query_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return RetrievalRecord(
                query_id=row["query_id"],
                question=row["question"],
                timestamp=row["timestamp"],
                intent=row["intent"],
                intent_confidence=row["intent_confidence"],
                retrieval_count=row["retrieval_count"],
                rerank_scores=json.loads(row["rerank_scores"]),
                cache_hit=bool(row["cache_hit"]),
                multi_query_used=bool(row["multi_query_used"]),
                multi_query_variants=row["multi_query_variants"],
                latency_ms=row["latency_ms"],
                top_score=row["top_score"],
                avg_score=row["avg_score"],
                feedback_id=row["feedback_id"],
                metadata=json.loads(row["metadata"] or "{}"),
            )

    def get_quality_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取检索质量统计

        Args:
            days: 统计天数

        Returns:
            质量统计字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cutoff_date = datetime.now()
            cutoff_date_str = cutoff_date.isoformat()

            cursor.execute("""
                SELECT 
                    COUNT(*) as total_queries,
                    AVG(retrieval_count) as avg_retrieval_count,
                    AVG(top_score) as avg_top_score,
                    AVG(avg_score) as avg_avg_score,
                    AVG(latency_ms) as avg_latency_ms,
                    SUM(cache_hit) as cache_hits,
                    SUM(multi_query_used) as multi_query_count
                FROM retrieval_records
                WHERE timestamp >= ?
            """, (cutoff_date_str,))
            row = cursor.fetchone()

            cursor.execute("""
                SELECT intent, COUNT(*) as count, AVG(avg_score) as avg_score
                FROM retrieval_records
                WHERE timestamp >= ?
                GROUP BY intent
            """, (cutoff_date_str,))
            intent_stats = [dict(r) for r in cursor.fetchall()]

            return {
                "total_queries": row["total_queries"] or 0,
                "avg_retrieval_count": row["avg_retrieval_count"] or 0.0,
                "avg_top_score": row["avg_top_score"] or 0.0,
                "avg_avg_score": row["avg_avg_score"] or 0.0,
                "avg_latency_ms": row["avg_latency_ms"] or 0.0,
                "cache_hit_count": row["cache_hits"] or 0,
                "multi_query_count": row["multi_query_count"] or 0,
                "cache_hit_rate": (row["cache_hits"] or 0) / max(1, row["total_queries"] or 1),
                "multi_query_rate": (row["multi_query_count"] or 0) / max(1, row["total_queries"] or 1),
                "intent_distribution": intent_stats,
            }

    def export_report(self, output_path: str = "retrieval_quality_report.json") -> str:
        """
        导出检索质量报告

        Args:
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        stats = self.get_quality_stats()
        report = {
            "generated_at": datetime.now().isoformat(),
            "stats": stats,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return output_path


_tracker: Optional[RetrievalTracker] = None


def get_tracker(db_path: str = "retrieval_tracking.db") -> RetrievalTracker:
    """获取全局追踪器实例"""
    global _tracker
    if _tracker is None:
        _tracker = RetrievalTracker(db_path)
    return _tracker


def track_retrieval(
    question: str,
    intent: str,
    intent_confidence: float,
    retrieval_count: int,
    rerank_scores: List[float],
    cache_hit: bool,
    multi_query_used: bool,
    latency_ms: float,
    multi_query_variants: int = 0,
) -> str:
    """
    记录一次检索

    Returns:
        query_id
    """
    return get_tracker().record_retrieval(
        question=question,
        intent=intent,
        intent_confidence=intent_confidence,
        retrieval_count=retrieval_count,
        rerank_scores=rerank_scores,
        cache_hit=cache_hit,
        multi_query_used=multi_query_used,
        latency_ms=latency_ms,
        multi_query_variants=multi_query_variants,
    )


def link_feedback(query_id: str, feedback_id: int) -> None:
    """关联用户反馈"""
    get_tracker().link_feedback(query_id, feedback_id)


def get_retrieval_quality_stats(days: int = 7) -> Dict[str, Any]:
    """获取检索质量统计"""
    return get_tracker().get_quality_stats(days)


if __name__ == "__main__":
    print("=" * 70)
    print("检索质量追踪器测试")
    print("=" * 70)

    tracker = RetrievalTracker(db_path=":memory:")

    print("\n记录测试检索...")
    query_id = tracker.record_retrieval(
        question="如何使用 Python？",
        intent="how_to",
        intent_confidence=0.85,
        retrieval_count=5,
        rerank_scores=[0.9, 0.8, 0.7, 0.6, 0.5],
        cache_hit=False,
        multi_query_used=False,
        latency_ms=150.5,
    )
    print(f"Query ID: {query_id}")

    print("\n获取检索记录...")
    record = tracker.get_record(query_id)
    if record:
        print(f"问题：{record.question}")
        print(f"意图：{record.intent}")
        print(f"检索数量：{record.retrieval_count}")
        print(f"最高分数：{record.top_score}")
        print(f"平均分数：{record.avg_score}")

    print("\n获取质量统计...")
    stats = tracker.get_quality_stats(days=7)
    print(f"总查询数：{stats['total_queries']}")
    print(f"平均检索数量：{stats['avg_retrieval_count']:.2f}")
    print(f"平均最高分数：{stats['avg_top_score']:.2f}")
    print(f"缓存命中率：{stats['cache_hit_rate']:.1%}")
    print(f"多查询使用率：{stats['multi_query_rate']:.1%}")

    print("\n导出报告...")
    report_path = tracker.export_report("test_retrieval_report.json")
    print(f"报告已导出至：{report_path}")
