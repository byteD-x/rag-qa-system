"""上下文优先级排序引擎。

核心能力：
- 三维评分：相关性 × 时效性 × 重要性
- 相关性评估：与当前问题的语义相似度（基于关键词重叠 + Jaccard 距离）
- 时效性评估：消息时间衰减（越近越高分）
- 重要性评估：消息信号强度（问题/决策/数据/反馈）
- 排序输出：按综合分数降序排列的消息列表

使用方式::

    from .context_prioritizer import ContextPrioritizer

    prioritizer = ContextPrioritizer()
    ranked = prioritizer.rank(history, current_question)
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .context_window import estimate_tokens
from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class PriorityScore:
    """优先级评分明细。"""
    relevance: float = 0.0     # 相关性 0-1
    recency: float = 0.0       # 时效性 0-1
    importance: float = 0.0    # 重要性 0-1
    composite: float = 0.0     # 综合分 0-1


@dataclass
class RankedMessage:
    """排序后的消息。"""
    index: int                          # 原始位置
    message: dict[str, Any]             # 消息内容
    score: PriorityScore = field(default_factory=PriorityScore)
    tokens: int = 0


# ---------------------------------------------------------------------------
# 信号检测
# ---------------------------------------------------------------------------

# 高重要性信号词
_HIGH_IMPORTANCE_KEYWORDS: set[str] = {
    # 决策类
    "决定", "确定", "确认", "批准", "驳回", "拒绝", "通过",
    "选择", "最终方案", "结论", "总结",
    # 问题类
    "报错", "错误", "异常", "失败", "故障", "bug", "error", "crash",
    "无法", "不能", "不支持", "超时", "timeout", "崩了", "挂了",
    # 数据类
    "统计", "数据", "指标", "增长", "下降", "变化", "趋势",
    "多少", "几个", "百分比", "金额", "成本", "预算",
    # 变更类
    "更新", "升级", "修改", "变更", "配置", "部署", "发布",
    "回滚", "迁移", "替换", "新增", "删除",
    # 安全类
    "安全", "漏洞", "权限", "认证", "加密", "脱敏", "合规",
    "审计", "风险", "告警",
    # 用户反馈
    "建议", "反馈", "吐槽", "投诉", "需求", "期望",
    # 版本
    "版本", "version", "v2", "v3", "最新",
}

# 低重要性信号词（寒暄/过渡语）
_LOW_IMPORTANCE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(好的|明白了|知道了|嗯嗯|ok|OK|收到|了解|懂了|行|好)[\s，。.!?]*$"),
    re.compile(r"^(谢谢|多谢|感谢|不客气|客气)[\s，。.!?]*$"),
    re.compile(r"^(你好|您好|hi|hello|嗨|在吗|在不在)[\s，。.!?]*$"),
    re.compile(r"^(有问题|有疑问|随时|再见|拜拜|bye|回头|下次)[\s，。.!?]*$"),
]


@dataclass
class QuestionFeatures:
    """当前问题的特征提取。"""
    tokens: set[str]           # 分词集合
    entities: set[str]         # 实体集合
    keywords: set[str]         # 关键词集合
    has_temporal: bool = False  # 是否包含时间/版本语义
    question_length: int = 0


# ---------------------------------------------------------------------------
# 优先级排序器
# ---------------------------------------------------------------------------


class ContextPrioritizer:
    """上下文优先级排序引擎。

    对历史消息进行三维评分（相关性 × 时效性 × 重要性），
    输出按优先级排序的消息列表，用于在上下文窗口中决定保留哪些消息。
    """

    # 三维权重
    RELEVANCE_WEIGHT = 0.40
    RECENCY_WEIGHT = 0.25
    IMPORTANCE_WEIGHT = 0.35

    # 时效性半衰期（秒）—— 30 分钟
    RECENCY_HALF_LIFE = 1800.0

    def __init__(
        self,
        *,
        relevance_weight: float = 0.40,
        recency_weight: float = 0.25,
        importance_weight: float = 0.35,
        recency_half_life: float = 1800.0,
    ) -> None:
        self.RELEVANCE_WEIGHT = relevance_weight
        self.RECENCY_WEIGHT = recency_weight
        self.IMPORTANCE_WEIGHT = importance_weight
        self.RECENCY_HALF_LIFE = recency_half_life

    def rank(
        self,
        history: list[dict[str, Any]],
        current_question: str,
        *,
        current_time: float | None = None,
    ) -> list[RankedMessage]:
        """对历史消息排序。

        参数:
            history: 历史消息列表
            current_question: 当前用户问题
            current_time: 当前时间戳（用于时效性计算）

        返回:
            按综合分数降序排列的消息列表
        """
        if not history:
            return []

        qf = self._extract_question_features(current_question)
        now = current_time or time.time()

        ranked: list[RankedMessage] = []
        for i, msg in enumerate(history):
            content = str(msg.get("content") or "")
            tokens = estimate_tokens(content)
            score = self._score_message(msg, content, qf, now, index=i, total=len(history))
            ranked.append(RankedMessage(index=i, message=msg, score=score, tokens=tokens))

        ranked.sort(key=lambda x: x.score.composite, reverse=True)
        return ranked

    def rank_and_select(
        self,
        history: list[dict[str, Any]],
        current_question: str,
        token_budget: int,
        *,
        min_turns: int = 2,
    ) -> list[dict[str, Any]]:
        """排序后按 token 预算选取消息。

        参数:
            history: 历史消息列表
            current_question: 当前问题
            token_budget: token 预算上限
            min_turns: 最少保留对话轮数

        返回:
            按原始顺序排列的选中消息
        """
        ranked = self.rank(history, current_question)

        # 强制保留最近 min_turns 轮
        protected_indices = self._protected_indices(history, min_turns)

        selected: set[int] = set(protected_indices)
        token_count = sum(
            estimate_message_tokens(history[i]) for i in protected_indices if i < len(history)
        )

        # 按优先级填充
        for rm in ranked:
            if rm.index in selected:
                continue
            if token_count + rm.tokens > token_budget:
                break
            selected.add(rm.index)
            token_count += rm.tokens

        # 按原始顺序输出
        result = [msg for i, msg in enumerate(history) if i in selected]

        if len(result) < len(history):
            logger.debug(
                "context_priority_selection total=%d selected=%d tokens=%d budget=%d",
                len(history), len(result), token_count, token_budget,
            )

        return result

    def _score_message(
        self,
        msg: dict[str, Any],
        content: str,
        qf: QuestionFeatures,
        now: float,
        *,
        index: int,
        total: int,
    ) -> PriorityScore:
        """对单条消息进行三维评分。"""
        relevance = self._score_relevance(content, qf)
        recency = self._score_recency(msg, now, index=index, total=total)
        importance = self._score_importance(msg, content)
        composite = (
            relevance * self.RELEVANCE_WEIGHT
            + recency * self.RECENCY_WEIGHT
            + importance * self.IMPORTANCE_WEIGHT
        )
        return PriorityScore(
            relevance=round(relevance, 4),
            recency=round(recency, 4),
            importance=round(importance, 4),
            composite=round(composite, 4),
        )

    # ---- 相关性评分 ----

    def _score_relevance(self, content: str, qf: QuestionFeatures) -> float:
        """评估消息与当前问题的相关性（基于关键词重叠 + Jaccard）。"""
        if not content.strip() or not qf.keywords:
            return 0.1

        content_lower = content.lower()
        content_tokens = set(self._tokenize(content_lower))

        # 关键词命中率
        keyword_hits = sum(1 for kw in qf.keywords if kw in content_lower)
        keyword_score = keyword_hits / max(len(qf.keywords), 1)

        # 实体命中率
        entity_hits = sum(1 for ent in qf.entities if ent in content_lower)
        entity_score = entity_hits / max(len(qf.entities), 1) if qf.entities else 0.0

        # Jaccard 相似度
        if qf.tokens and content_tokens:
            intersection = len(qf.tokens & content_tokens)
            union = len(qf.tokens | content_tokens)
            jaccard = intersection / max(union, 1)
        else:
            jaccard = 0.0

        return round(keyword_score * 0.5 + entity_score * 0.3 + jaccard * 0.2, 4)

    # ---- 时效性评分 ----

    def _score_recency(
        self,
        msg: dict[str, Any],
        now: float,
        *,
        index: int,
        total: int,
    ) -> float:
        """评估消息的时效性（指数衰减 + 位置权重）。"""
        # 优先使用时间戳
        created_at = msg.get("created_at") or msg.get("timestamp")
        if isinstance(created_at, (int, float)) and created_at > 0:
            age_seconds = max(now - float(created_at), 0)
            time_score = math.exp(-age_seconds * math.log(2) / self.RECENCY_HALF_LIFE)
        else:
            # Fallback: 使用位置信息
            position_score = (index + 1) / max(total, 1)
            # 越靠后越新，分数越高
            time_score = 0.3 + 0.7 * position_score

        return round(min(time_score, 1.0), 4)

    # ---- 重要性评分 ----

    def _score_importance(self, msg: dict[str, Any], content: str) -> float:
        """评估消息的重要性（信号强度分析）。"""
        if not content.strip():
            return 0.0

        role = str(msg.get("role") or "").strip()
        content_lower = content.lower()
        score = 0.0

        # 用户消息通常比系统/助手消息更重要
        if role == "user":
            score += 0.15

        # 高重要性关键词命中
        high_importance_hits = sum(1 for kw in _HIGH_IMPORTANCE_KEYWORDS if kw in content_lower)
        if high_importance_hits > 0:
            # 对数增长 —— 命中越多越高，但边际递减
            score += min(0.15 + 0.08 * math.log2(high_importance_hits + 1), 0.45)

        # 低重要性模式减分
        for pattern in _LOW_IMPORTANCE_PATTERNS:
            if pattern.match(content.strip()):
                score -= 0.40
                break

        # 长度信号
        length = len(content)
        if length < 10:
            score -= 0.15  # 太短可能是寒暄
        elif length > 200:
            score += 0.10  # 长消息通常包含更多信息

        # 包含代码块/结构化数据加分
        if "```" in content or "|" in content:
            score += 0.08

        # 数字数据密度（包含多个数字可能意味着具体数据）
        numbers = len(re.findall(r"\d+", content))
        if numbers >= 3:
            score += 0.10

        return round(min(max(score, 0.0), 1.0), 4)

    # ---- 特征提取 ----

    def _extract_question_features(self, question: str) -> QuestionFeatures:
        """从当前问题提取特征。"""
        if not question.strip():
            return QuestionFeatures(tokens=set(), entities=set(), keywords=set())

        lower = question.lower()
        tokens = set(self._tokenize(lower))
        entities = self._extract_entities(question)
        keywords = {kw for kw in _HIGH_IMPORTANCE_KEYWORDS if kw in lower}
        has_temporal = any(kw in lower for kw in {"版本", "时间", "日期", "最近", "当前", "历史", "之前", "之后", "上次", "下次"})

        return QuestionFeatures(
            tokens=tokens,
            entities=entities,
            keywords=keywords,
            has_temporal=has_temporal,
            question_length=len(question),
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单的中文+英文分词。"""
        # 按非字母数字字符切分
        tokens = re.findall(r"[a-zA-Z0-9_]+|[一-鿿]+", text.lower())
        # 对于过长的中文词按 2-gram 拆分
        result: list[str] = []
        for token in tokens:
            if re.match(r"^[一-鿿]+$", token) and len(token) > 3:
                # 中文 2-gram
                for i in range(len(token) - 1):
                    result.append(token[i:i+2])
                result.append(token)  # 也保留原词
            else:
                result.append(token)
        return result

    @staticmethod
    def _extract_entities(text: str) -> set[str]:
        """从文本中提取简单实体。"""
        entities: set[str] = set()
        # 数字序列
        for m in re.finditer(r"\d{2,}", text):
            entities.add(m.group())
        # 大写英文缩写
        for m in re.finditer(r"[A-Z]{2,6}", text):
            entities.add(m.group())
        # 中文引号内容
        for m in re.finditer(r"[「「]([^」」]+)[」」]", text):
            entities.add(m.group(1))
        return entities

    @staticmethod
    def _protected_indices(history: list[dict[str, Any]], min_turns: int) -> list[int]:
        """获取最少保留的对话轮次对应的索引。"""
        if min_turns <= 0 or not history:
            return []
        protected: list[int] = []
        turn_count = 0
        user_seen = False
        for i in range(len(history) - 1, -1, -1):
            role = str(history[i].get("role") or "")
            protected.append(i)
            if role == "user":
                if user_seen:
                    turn_count += 1
                user_seen = True
            elif role == "assistant" and user_seen:
                turn_count += 1
                user_seen = False
            if turn_count >= min_turns:
                break
        return protected


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """估算单条消息的 token 数。"""
    return estimate_tokens(str(message.get("content") or "")) + 4
