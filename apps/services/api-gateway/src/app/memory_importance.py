"""记忆重要性评分与 Ebbinghaus 遗忘曲线。

核心能力：
- 多维度记忆重要性评分（来源/频率/类型/情感）
- Ebbinghaus 遗忘曲线建模（指数衰减 + 复习强化）
- 自适应遗忘速率（基于记忆类型和重要性动态调整）
- 记忆健康度评估（是否需要复习/加强）

Ebbinghaus 遗忘曲线：
- 公式: R = e^(-t/S)，其中 S 是记忆强度
- 复习效应：每次成功检索 → 强度翻倍（spacing effect）
- 半衰期模型：
  - 高重要性偏好：半衰期 30 天
  - 中等事实：半衰期 7 天
  - 低重要性知识：半衰期 3 天

使用方式::

    from .memory_importance import MemoryImportanceScorer

    scorer = MemoryImportanceScorer()
    score = scorer.score(memory_entry)
    health = scorer.memory_health(memory_entry)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ImportanceScoreDetail:
    """重要性评分明细。"""
    source_quality: float = 0.0    # 来源质量（用户明确表达 vs 推断）
    frequency: float = 0.0         # 提及频率
    memory_type_weight: float = 0.0 # 类型权重
    recency_bonus: float = 0.0     # 近期提及加分
    composite: float = 0.5         # 综合重要性


@dataclass
class MemoryHealth:
    """记忆健康度评估。"""
    effective_importance: float = 0.5  # 衰减后的有效重要性
    needs_review: bool = False         # 是否需要复习
    risk_of_forgetting: float = 0.0    # 遗忘风险 0-1
    suggested_review_interval_hours: float = 168.0  # 建议复习间隔（小时）
    estimated_half_life_hours: float = 168.0  # 估算半衰期（小时）


# ---------------------------------------------------------------------------
# 记忆类型权重
# ---------------------------------------------------------------------------

# 不同类型记忆的基础权重（preference > fact > knowledge）
MEMORY_TYPE_BASE_IMPORTANCE = {
    "preference": 0.70,   # 用户偏好最重要
    "fact": 0.55,         # 事实信息中等
    "knowledge": 0.40,    # 知识性信息稍低
}

# 不同类型记忆的默认半衰期（小时）
MEMORY_TYPE_HALF_LIFE_HOURS = {
    "preference": 720.0,   # 30 天
    "fact": 168.0,          # 7 天
    "knowledge": 72.0,      # 3 天
}


# ---------------------------------------------------------------------------
# 重要性评分器
# ---------------------------------------------------------------------------


class MemoryImportanceScorer:
    """记忆重要性评分器 —— 多维度评估 + Ebbinghaus 遗忘建模。"""

    def __init__(
        self,
        *,
        base_importance: dict[str, float] | None = None,
        half_life_hours: dict[str, float] | None = None,
    ) -> None:
        self._base_importance = base_importance or MEMORY_TYPE_BASE_IMPORTANCE
        self._half_life_hours = half_life_hours or MEMORY_TYPE_HALF_LIFE_HOURS

    # ---- 重要性评分 ----

    def score(self, memory: Any, *, access_count: int = 0, mention_count: int = 1) -> ImportanceScoreDetail:
        """多维度重要性评分。

        参数:
            memory: MemoryTriple 或 MemoryEntry
            access_count: 被检索次数
            mention_count: 在对话中被提及的次数

        返回:
            评分明细
        """
        memory_type = getattr(memory, "memory_type", "fact")
        confidence = getattr(memory, "confidence", 0.8)
        existing_importance = getattr(memory, "importance", 0.5)

        # 1. 来源质量：置信度 × 现有重要性
        source_quality = round(confidence * existing_importance, 4)

        # 2. 频率因子：通过使用频率评估重要性（对数增长）
        total_hits = max(access_count + mention_count, 1)
        frequency = round(min(math.log2(total_hits + 1) * 0.2, 0.5), 4)

        # 3. 类型权重
        memory_type_weight = round(self._base_importance.get(memory_type, 0.5), 4)

        # 4. 近期加分：最近访问在 24h 内加分
        last_accessed = getattr(memory, "last_accessed_at", 0.0)
        now = time.time()
        if last_accessed > 0 and (now - last_accessed) < 86400:
            recency_bonus = 0.10
        else:
            recency_bonus = 0.0

        # 综合评分：加权平均
        composite = round(
            source_quality * 0.45
            + frequency * 0.20
            + memory_type_weight * 0.25
            + recency_bonus * 0.10,
            4,
        )

        return ImportanceScoreDetail(
            source_quality=source_quality,
            frequency=frequency,
            memory_type_weight=memory_type_weight,
            recency_bonus=recency_bonus,
            composite=min(composite, 1.0),
        )

    # ---- Ebbinghaus 遗忘曲线 ----

    def decay_factor(self, memory: Any, *, current_time: float | None = None) -> float:
        """计算 Ebbinghaus 遗忘衰减因子。

        公式: R = e^(-t / S)
        - R: 记忆保留率
        - t: 经过时间（小时）
        - S: 记忆强度（半衰期 / ln(2)）
        """
        now = current_time or time.time()
        reference_time = (
            getattr(memory, "last_accessed_at", 0.0)
            or getattr(memory, "created_at", 0.0)
            or now
        )
        elapsed_hours = max((now - reference_time) / 3600.0, 0.0)

        # 半衰期：考虑记忆类型 + 重要性
        memory_type = getattr(memory, "memory_type", "fact")
        base_half_life = self._half_life_hours.get(memory_type, 168.0)
        importance = getattr(memory, "importance", 0.5)
        decay_rate = getattr(memory, "decay_rate", 0.1)

        # 复习效应：每次成功访问 -> 半衰期翻倍（间隔效应）
        access_count = getattr(memory, "access_count", 0)
        spacing_multiplier = 2.0 ** min(access_count, 5)  # 最大 32x

        # 综合半衰期
        effective_half_life = base_half_life * (0.3 + importance * 1.5) * spacing_multiplier

        # 遗忘速率调整
        adjusted_decay = decay_rate * (1.0 - importance * 0.7)

        # Ebbinghaus 曲线: R = e^(-decay * t / half_life)
        decay_factor = math.exp(-adjusted_decay * elapsed_hours / effective_half_life)

        return round(max(decay_factor, 0.01), 6)

    def effective_importance(self, memory: Any, *, current_time: float | None = None) -> float:
        """计算衰减后的有效重要性。"""
        importance = getattr(memory, "importance", 0.5)
        decay = self.decay_factor(memory, current_time=current_time)
        return round(importance * (0.3 + 0.7 * decay), 4)

    # ---- 记忆健康度 ----

    def memory_health(self, memory: Any, *, current_time: float | None = None) -> MemoryHealth:
        """评估记忆的健康度。

        返回:
            MemoryHealth: 包含是否需要复习、遗忘风险等信息
        """
        effective = self.effective_importance(memory, current_time=current_time)
        importance = getattr(memory, "importance", 0.5)
        memory_type = getattr(memory, "memory_type", "fact")

        # 遗忘风险：importance 与 effective 的差距
        risk = round(max(importance - effective, 0.0), 4)

        # 需要复习：有效重要性低于阈值
        threshold = self._base_importance.get(memory_type, 0.5) * 0.5
        needs_review = effective < threshold

        # 建议复习间隔：基于半衰期
        base_half_life = self._half_life_hours.get(memory_type, 168.0)
        suggested_interval = base_half_life * (0.5 + importance * 0.5)

        return MemoryHealth(
            effective_importance=effective,
            needs_review=needs_review,
            risk_of_forgetting=risk,
            suggested_review_interval_hours=round(suggested_interval, 1),
            estimated_half_life_hours=round(base_half_life * (0.3 + importance * 1.5), 1),
        )

    # ---- 复习记录 ----

    def record_access(self, memory: Any, *, current_time: float | None = None) -> None:
        """记录一次记忆检索（触发复习强化效应）。

        更新 last_accessed_at 和 access_count。
        """
        now = current_time or time.time()
        try:
            memory.last_accessed_at = now
            memory.access_count = getattr(memory, "access_count", 0) + 1
        except (AttributeError, TypeError):
            pass  # memory 对象可能是只读的

    def record_review(self, memory: Any, *, current_time: float | None = None) -> None:
        """记录一次主动复习（比被动访问强化效果更强）。"""
        now = current_time or time.time()
        try:
            memory.last_accessed_at = now
            # 主动复习：access_count 至少 +2
            memory.access_count = getattr(memory, "access_count", 0) + 2
            # 提升重要性
            current_importance = getattr(memory, "importance", 0.5)
            memory.importance = min(current_importance + 0.05, 1.0)
            # 降低遗忘速率
            current_decay = getattr(memory, "decay_rate", 0.1)
            memory.decay_rate = max(current_decay - 0.02, 0.02)
        except (AttributeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def estimate_half_life(
    importance: float,
    memory_type: str = "fact",
    *,
    access_count: int = 0,
) -> float:
    """估算记忆半衰期（小时）。"""
    base = MEMORY_TYPE_HALF_LIFE_HOURS.get(memory_type, 168.0)
    spacing_multiplier = 2.0 ** min(access_count, 5)
    return round(base * (0.3 + importance * 1.5) * spacing_multiplier, 1)


def forgetting_retention(
    elapsed_hours: float,
    importance: float = 0.5,
    memory_type: str = "fact",
    *,
    access_count: int = 0,
) -> float:
    """估算经过 elapsed_hours 后的记忆保留率。"""
    half_life = estimate_half_life(importance, memory_type, access_count=access_count)
    decay_rate = 0.3 * (1.0 - importance) + 0.02
    return round(math.exp(-decay_rate * elapsed_hours / half_life), 6)
