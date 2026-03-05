#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检索质量评估模块

收集用户反馈，分析 Bad Case，生成质量报告。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager


@dataclass
class Feedback:
    """用户反馈"""
    id: int
    question: str
    answer_id: str
    rating: int  # 1=无用，2=有用
    comment: Optional[str]
    created_at: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class QualityMetrics:
    """质量指标"""
    total_feedbacks: int
    positive_feedbacks: int
    negative_feedbacks: int
    satisfaction_rate: float  # 满意度
    avg_rating: float
    bad_cases: List[Dict]
    top_improvement_areas: List[str]


class QualityAssessor:
    """质量评估器"""

    def __init__(self, db_path: str = "quality_feedback.db"):
        """
        初始化质量评估器

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """初始化数据库"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rating ON feedbacks(rating)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON feedbacks(created_at)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_feedback(
        self,
        question: str,
        answer_id: str,
        rating: int,
        comment: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        添加用户反馈

        Args:
            question: 用户问题
            answer_id: 答案 ID
            rating: 评分 (1=无用，2=有用)
            comment: 评论 (可选)
            metadata: 元数据 (可选)

        Returns:
            反馈 ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedbacks (question, answer_id, rating, comment, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                question,
                answer_id,
                rating,
                comment,
                datetime.now().isoformat(),
                json.dumps(metadata or {})
            ))
            conn.commit()
            return cursor.lastrowid

    def get_metrics(self, days: int = 30) -> QualityMetrics:
        """
        获取质量指标

        Args:
            days: 统计天数

        Returns:
            质量指标
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 计算时间范围
            cutoff_date = datetime.now()
            cutoff_date_str = cutoff_date.isoformat()

            # 总反馈数
            cursor.execute("""
                SELECT COUNT(*) FROM feedbacks
                WHERE created_at >= ?
            """, (cutoff_date_str,))
            total = cursor.fetchone()[0]

            # 正面反馈
            cursor.execute("""
                SELECT COUNT(*) FROM feedbacks
                WHERE rating = 2 AND created_at >= ?
            """, (cutoff_date_str,))
            positive = cursor.fetchone()[0]

            # 负面反馈
            cursor.execute("""
                SELECT COUNT(*) FROM feedbacks
                WHERE rating = 1 AND created_at >= ?
            """, (cutoff_date_str,))
            negative = cursor.fetchone()[0]

            # 平均评分
            cursor.execute("""
                SELECT AVG(rating) FROM feedbacks
                WHERE created_at >= ?
            """, (cutoff_date_str,))
            avg_rating = cursor.fetchone()[0] or 0.0

            # Bad Cases (负面反馈的问题)
            cursor.execute("""
                SELECT question, answer_id, comment, created_at
                FROM feedbacks
                WHERE rating = 1 AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 20
            """, (cutoff_date_str,))
            bad_cases = [dict(row) for row in cursor.fetchall()]

            # 计算满意度
            satisfaction_rate = positive / (positive + negative) if (positive + negative) > 0 else 0.0

            # 改进建议 (基于评论关键词)
            improvement_areas = self._analyze_improvement_areas(negative)

            return QualityMetrics(
                total_feedbacks=total,
                positive_feedbacks=positive,
                negative_feedbacks=negative,
                satisfaction_rate=satisfaction_rate,
                avg_rating=avg_rating,
                bad_cases=bad_cases,
                top_improvement_areas=improvement_areas
            )

    def _analyze_improvement_areas(self, negative_count: int) -> List[str]:
        """分析改进领域"""
        if negative_count == 0:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT comment FROM feedbacks
                WHERE rating = 1 AND comment IS NOT NULL
            """)

            comments = [row[0] for row in cursor.fetchall()]
            if not comments:
                return ["需要更多用户反馈"]

            # 简单的关键词分析
            keywords = {
                "不准确": 0,
                "不相关": 0,
                "不完整": 0,
                "太慢": 0,
                "错误": 0,
            }

            for comment in comments:
                for keyword in keywords:
                    if keyword in comment:
                        keywords[keyword] += 1

            # 排序并返回 top 3
            sorted_keywords = sorted(
                keywords.items(),
                key=lambda x: x[1],
                reverse=True
            )

            return [kw for kw, count in sorted_keywords[:3] if count > 0]

    def get_feedback_history(
        self,
        limit: int = 50,
        rating_filter: Optional[int] = None
    ) -> List[Feedback]:
        """
        获取反馈历史

        Args:
            limit: 返回数量限制
            rating_filter: 评分过滤 (可选)

        Returns:
            反馈列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if rating_filter:
                cursor.execute("""
                    SELECT id, question, answer_id, rating, comment, created_at, metadata
                    FROM feedbacks
                    WHERE rating = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (rating_filter, limit))
            else:
                cursor.execute("""
                    SELECT id, question, answer_id, rating, comment, created_at, metadata
                    FROM feedbacks
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))

            feedbacks = []
            for row in cursor.fetchall():
                feedbacks.append(Feedback(
                    id=row[0],
                    question=row[1],
                    answer_id=row[2],
                    rating=row[3],
                    comment=row[4],
                    created_at=row[5],
                    metadata=json.loads(row[6] or "{}")
                ))

            return feedbacks

    def export_report(self, output_path: str = "quality_report.json") -> str:
        """
        导出质量报告

        Args:
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        metrics = self.get_metrics()

        report = {
            "generated_at": datetime.now().isoformat(),
            "metrics": {
                "total_feedbacks": metrics.total_feedbacks,
                "positive_feedbacks": metrics.positive_feedbacks,
                "negative_feedbacks": metrics.negative_feedbacks,
                "satisfaction_rate": metrics.satisfaction_rate,
                "avg_rating": metrics.avg_rating,
            },
            "bad_cases": metrics.bad_cases,
            "improvement_areas": metrics.top_improvement_areas,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return output_path


# 全局评估器实例
_assessor: Optional[QualityAssessor] = None


def get_assessor(db_path: str = "quality_feedback.db") -> QualityAssessor:
    """获取全局评估器实例"""
    global _assessor
    if _assessor is None:
        _assessor = QualityAssessor(db_path)
    return _assessor


def add_feedback(
    question: str,
    answer_id: str,
    rating: int,
    comment: Optional[str] = None
) -> int:
    """添加用户反馈"""
    return get_assessor().add_feedback(question, answer_id, rating, comment)


def get_quality_metrics(days: int = 30) -> QualityMetrics:
    """获取质量指标"""
    return get_assessor().get_metrics(days)


def export_quality_report(output_path: str = "quality_report.json") -> str:
    """导出质量报告"""
    return get_assessor().export_report(output_path)


if __name__ == "__main__":
    # 测试示例
    print("=" * 70)
    print("质量评估器测试")
    print("=" * 70)

    assessor = QualityAssessor(db_path=":memory:")  # 使用内存数据库测试

    # 添加测试反馈
    print("\n添加测试反馈...")
    assessor.add_feedback(
        question="如何使用 Python？",
        answer_id="ans_001",
        rating=2,
        comment="很有帮助"
    )
    assessor.add_feedback(
        question="Docker 怎么用？",
        answer_id="ans_002",
        rating=1,
        comment="回答不准确"
    )
    assessor.add_feedback(
        question="机器学习是什么？",
        answer_id="ans_003",
        rating=2,
        comment="解释清晰"
    )

    # 获取指标
    print("\n获取质量指标...")
    metrics = assessor.get_metrics(days=30)
    print(f"总反馈数：{metrics.total_feedbacks}")
    print(f"正面反馈：{metrics.positive_feedbacks}")
    print(f"负面反馈：{metrics.negative_feedbacks}")
    print(f"满意度：{metrics.satisfaction_rate:.1%}")
    print(f"平均评分：{metrics.avg_rating:.2f}")
    print(f"改进建议：{metrics.top_improvement_areas}")

    # 导出报告
    print("\n导出质量报告...")
    report_path = assessor.export_report("test_quality_report.json")
    print(f"报告已导出至：{report_path}")
