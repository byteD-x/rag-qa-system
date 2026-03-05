#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
意图分类器模块

根据问题类型自动分类，路由到不同的检索策略。
支持的意图类型：
- factual: 查找具体事实/信息
- how_to: 查找操作指南/步骤
- troubleshooting: 排查错误/问题
- conceptual: 理解概念/原理
- code: 查找代码示例
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class IntentType(str, Enum):
    """意图类型枚举"""
    FACTUAL = "factual"  # 事实性问题
    HOW_TO = "how_to"  # 操作指南
    TROUBLESHOOTING = "troubleshooting"  # 故障排查
    CONCEPTUAL = "conceptual"  # 概念理解
    CODE = "code"  # 代码相关
    UNKNOWN = "unknown"  # 未知类型


class IntentClassifier:
    """意图分类器"""

    def __init__(self):
        # 关键词模式匹配
        self.patterns: Dict[IntentType, List[str]] = {
            IntentType.FACTUAL: [
                r"是什么", r"什么是", r"什么时候", r"在哪里", r"谁",
                r"which", r"what is", r"when", r"where", r"who",
                r"定义", r"含义", r"意思",
            ],
            IntentType.HOW_TO: [
                r"如何", r"怎么", r"怎样", r"怎么做", r"怎么做",
                r"how to", r"how do", r"how can",
                r"步骤", r"方法", r"流程", r"教程",
                r"使用", r"创建", r"实现", r"安装", r"配置",
            ],
            IntentType.TROUBLESHOOTING: [
                r"错误", r"问题", r"失败", r"异常", r"不行",
                r"error", r"failed", r"issue", r"problem", r"bug",
                r"解决", r"排查", r"调试", r"修复",
                r"无法", r"不能", r"为什么.*不",
            ],
            IntentType.CONCEPTUAL: [
                r"为什么", r"原理", r"机制", r"工作方式", r"工作原理",
                r"why", r"principle", r"mechanism",
                r"解释", r"理解", r"说明",
                r"区别", r"差异", r"对比", r"vs", r"和.*有什么不同",
            ],
            IntentType.CODE: [
                r"代码", r"示例", r"demo", r"example",
                r"python", r"java", r"javascript", r"sql",
                r"函数", r"类", r"方法", r"接口", r"API",
                r"怎么写代码", r"如何实现.*代码",
            ],
        }

        # 意图对应的检索策略
        self.retrieval_strategies: Dict[IntentType, Dict] = {
            IntentType.FACTUAL: {
                "top_k": 5,
                "rerank_top_k": 3,
                "dense_weight": 0.8,
                "sparse_weight": 0.2,
            },
            IntentType.HOW_TO: {
                "top_k": 8,
                "rerank_top_k": 5,
                "dense_weight": 0.6,
                "sparse_weight": 0.4,
            },
            IntentType.TROUBLESHOOTING: {
                "top_k": 10,
                "rerank_top_k": 6,
                "dense_weight": 0.5,
                "sparse_weight": 0.5,
            },
            IntentType.CONCEPTUAL: {
                "top_k": 6,
                "rerank_top_k": 4,
                "dense_weight": 0.9,
                "sparse_weight": 0.1,
            },
            IntentType.CODE: {
                "top_k": 8,
                "rerank_top_k": 5,
                "dense_weight": 0.7,
                "sparse_weight": 0.3,
            },
            IntentType.UNKNOWN: {
                "top_k": 8,
                "rerank_top_k": 5,
                "dense_weight": 0.7,
                "sparse_weight": 0.3,
            },
        }

    def classify(self, question: str) -> Tuple[IntentType, float, str]:
        """
        分类问题意图

        Args:
            question: 用户问题

        Returns:
            (intent_type, confidence, reason)
            - intent_type: 意图类型
            - confidence: 置信度 (0-1)
            - reason: 分类原因
        """
        question_lower = question.lower()

        # 统计每个意图的匹配分数
        scores: Dict[IntentType, int] = {intent: 0 for intent in IntentType}
        matched_patterns: Dict[IntentType, List[str]] = {intent: [] for intent in IntentType}

        for intent, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, question_lower):
                    scores[intent] += 1
                    matched_patterns[intent].append(pattern)

        # 找出得分最高的意图
        max_score = max(scores.values())
        if max_score == 0:
            return IntentType.UNKNOWN, 0.5, "未匹配到明显模式，使用默认策略"

        # 获取所有最高分的意图
        top_intents = [
            intent for intent, score in scores.items()
            if score == max_score
        ]

        # 如果平局，使用优先级：troubleshooting > how_to > code > factual > conceptual
        priority_order = [
            IntentType.TROUBLESHOOTING,
            IntentType.HOW_TO,
            IntentType.FACTUAL,
            IntentType.CODE,
            IntentType.CONCEPTUAL,
        ]

        selected_intent = None
        for intent in priority_order:
            if intent in top_intents:
                selected_intent = intent
                break

        if selected_intent is None:
            selected_intent = top_intents[0]

        # 计算置信度
        total_matches = sum(scores.values())
        confidence = min(1.0, max_score / total_matches) if total_matches > 0 else 0.5

        # 生成原因
        reason = f"匹配到 {max_score} 个特征: {', '.join(matched_patterns[selected_intent][:3])}"

        return selected_intent, confidence, reason

    def get_retrieval_strategy(self, intent: IntentType) -> Dict:
        """
        获取意图对应的检索策略

        Args:
            intent: 意图类型

        Returns:
            检索策略配置
        """
        return self.retrieval_strategies.get(
            intent,
            self.retrieval_strategies[IntentType.UNKNOWN]
        )

    def classify_and_get_strategy(self, question: str) -> Dict:
        """
        分类问题并获取检索策略

        Args:
            question: 用户问题

        Returns:
            包含意图、置信度、策略的字典
        """
        intent, confidence, reason = self.classify(question)
        strategy = self.get_retrieval_strategy(intent)

        return {
            "intent": intent.value,
            "confidence": confidence,
            "reason": reason,
            "strategy": strategy,
        }


# 全局分类器实例
_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    """获取全局分类器实例"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def classify_intent(question: str) -> Dict:
    """
    分类问题意图并返回策略

    Args:
        question: 用户问题

    Returns:
        分类结果和策略配置
    """
    return get_classifier().classify_and_get_strategy(question)


if __name__ == "__main__":
    # 测试示例
    test_questions = [
        "什么是 RAG 技术？",
        "如何使用 Python 读取文件？",
        "Docker 容器无法启动怎么办？",
        "机器学习和深度学习有什么区别？",
        "请给我一个 Python 读取文件的代码示例",
        "北京是中国的首都吗？",
        "如何配置 Kubernetes 集群？",
        "API 返回 500 错误如何解决？",
    ]

    print("=" * 70)
    print("意图分类器测试")
    print("=" * 70)

    for question in test_questions:
        result = classify_intent(question)
        print(f"\n问题：{question}")
        print(f"意图：{result['intent']}")
        print(f"置信度：{result['confidence']:.2f}")
        print(f"原因：{result['reason']}")
        print(f"策略：top_k={result['strategy']['top_k']}, "
              f"dense_weight={result['strategy']['dense_weight']}")
