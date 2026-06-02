"""问题复杂度分类器 —— 快速评估问题复杂度以驱动智能模型路由。

评估维度（不调用LLM，延迟 < 1ms）：
1. 问题长度与结构（短问候 vs 长段落）
2. 关键词信号（多步推理、比较、条件判断）
3. 实体密度（专有名词、数字、日期）
4. 句式复杂度（嵌套结构、问句数量）

输出：
- 1: 极简（问候、确认）→ 使用经济模型或缓存
- 2: 简单（单事实查询）→ 标准模型
- 3: 中等（多条件查询）→ 标准模型
- 4: 复杂（比较、推理）→ 高级模型
- 5: 极复杂（多步推理+计算）→ 最强模型

集成方式::

    from .complexity_classifier import classify_complexity, ComplexityLevel

    level = classify_complexity("请比较v2和v3的差异并计算影响范围")
    # level.score = 4, level.recommended_route = "grounded", level.recommended_model_tier = "premium"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ComplexityLevel:
    """复杂度评估结果"""

    score: int  # 1-5
    label: str  # trivial / simple / moderate / complex / very_complex
    features: list[str] = field(default_factory=list)  # 触发复杂度评估的特征
    recommended_route: str = "grounded"  # 推荐的路由键
    recommended_model_tier: str = "standard"  # economy / standard / premium
    should_cache: bool = False  # 是否建议缓存
    can_use_small_model: bool = False  # 是否可用小模型


# ---------------------------------------------------------------------------
# 特征信号
# ---------------------------------------------------------------------------

# 极简模式
_TRIVIAL_PATTERNS = [
    r"^(你好|hello|hi|hey)\s*$",
    r"^(谢谢|thanks|thank you|再见|bye)\s*$",
    r"^(好的|ok|okay|yes|no|对|不对)\s*$",
    r"^(继续|go on|next)\s*$",
]

# 低复杂度关键词
_SIMPLE_INDICATORS = [
    "什么是", "是谁", "哪个", "多少", "什么时候",
    "哪里", "怎么拼", "怎么读", "是什么",
    "定义", "含义",
]

# 高复杂度信号
_COMPLEX_KW = {
    "compare": ["比较", "对比", "差异", "区别", "vs", "versus", "哪个更好", "优缺点"],
    "multi_step": ["第一步", "第二步", "然后", "接着", "最后", "先", "再", "之后", "首先", "其次", "然后"],
    "conditional": ["如果", "假如", "假设", "条件", "取决于", "根据", "按"],
    "reasoning": ["为什么", "原因", "怎么计算", "如何得出", "分析", "评估", "判断", "推理"],
    "aggregation": ["总结", "归纳", "汇总", "统计", "列出所有", "找出所有", "计算"],
    "temporal": ["历史", "版本", "变更", "时间线", "之前", "之后", "旧", "新"],
}

# 高实体密度指标（专有名词、代码、数字）
_ENTITY_DENSITY_RE = re.compile(
    r"[A-Z][a-z]+|[0-9]{2,}|\b(v|V)\d+\.?\d*\b|[A-Z_]{3,}"
)

# 问题分割（多个问号）
_MULTI_QUESTION_RE = re.compile(r"[？?]")


# ---------------------------------------------------------------------------
# 分类器
# ---------------------------------------------------------------------------


def classify_complexity(
    question: str,
    *,
    context: dict[str, Any] | None = None,
) -> ComplexityLevel:
    """快速评估问题复杂度（不调用 LLM），返回 ComplexityLevel。

    参数:
        question: 用户原始问题
        context: 可选上下文（多知识库、版本冲突等）
    """
    q = str(question or "").strip()
    features: list[str] = []
    score = 1

    # 1. 极简模式检测
    for pattern in _TRIVIAL_PATTERNS:
        if re.match(pattern, q, re.IGNORECASE):
            return ComplexityLevel(
                score=1,
                label="trivial",
                features=["greeting_pattern"],
                recommended_route="common_knowledge",
                recommended_model_tier="economy",
                should_cache=True,
                can_use_small_model=True,
            )

    # 2. 长度维度
    q_len = len(q)
    if q_len <= 15:
        score += 0
        features.append("very_short")
    elif q_len <= 60:
        score += 1
        features.append("short")
    elif q_len <= 200:
        score += 2
        features.append("medium_length")
    else:
        score += 3
        features.append("long")

    # 3. 高复杂度信号计数
    complex_signals = 0
    for category, keywords in _COMPLEX_KW.items():
        found = [kw for kw in keywords if kw in q]
        if found:
            complex_signals += 1
            features.append(f"complex_{category}")

    if complex_signals >= 3:
        score += 3
    elif complex_signals >= 2:
        score += 2
    elif complex_signals >= 1:
        score += 1

    # 4. 低复杂度信号降权
    if q_len <= 60 and complex_signals == 0:
        simple_count = sum(1 for kw in _SIMPLE_INDICATORS if kw in q)
        if simple_count >= 1:
            score = max(1, score - 1)
            features.append("simple_query")

    # 5. 实体密度
    entities = _ENTITY_DENSITY_RE.findall(q)
    if len(entities) >= 5:
        score += 1
        features.append("high_entity_density")

    # 6. 多问题检测
    question_marks = len(_MULTI_QUESTION_RE.findall(q))
    if question_marks >= 3:
        score += 1
        features.append("multi_question")

    # 7. 上下文信号
    ctx = context or {}
    if len(list(ctx.get("corpus_ids") or [])) > 3:
        score += 1
        features.append("multi_corpus")
    if ctx.get("has_version_conflict") or ctx.get("time_ambiguity"):
        score += 1
        features.append("version_context")

    # 8. 规划分数
    score = min(5, max(1, score))

    # 标签映射
    label_map = {1: "trivial", 2: "simple", 3: "moderate", 4: "complex", 5: "very_complex"}
    label = label_map.get(score, "moderate")

    # 推荐路由和模型层级
    if score <= 1:
        route = "common_knowledge"
        tier = "economy"
        should_cache = True
        can_small = True
    elif score <= 2:
        route = "grounded"
        tier = "economy"
        should_cache = True
        can_small = True
    elif score <= 3:
        route = "grounded"
        tier = "standard"
        should_cache = False
        can_small = False
    else:
        route = "agent" if "complex_multi_step" in features or "complex_reasoning" in features else "grounded"
        tier = "premium"
        should_cache = False
        can_small = False

    return ComplexityLevel(
        score=score,
        label=label,
        features=features,
        recommended_route=route,
        recommended_model_tier=tier,
        should_cache=should_cache,
        can_use_small_model=can_small,
    )


# ---------------------------------------------------------------------------
# 模型层级定义
# ---------------------------------------------------------------------------

# 模型层级与候选模型映射（可通过环境变量覆盖）
MODEL_TIERS: dict[str, list[str]] = {
    "economy": ["qwen-turbo", "gpt-4o-mini"],
    "standard": ["qwen-plus", "gpt-4o"],
    "premium": ["qwen-max", "gpt-4o", "claude-sonnet-4-6"],
}


def resolve_model_for_complexity(
    complexity: ComplexityLevel,
    *,
    available_models: list[str] | None = None,
    tier_mapping: dict[str, list[str]] | None = None,
) -> str | None:
    """根据复杂度等级推荐具体模型。

    参数:
        complexity: 复杂度评估结果
        available_models: 当前可用的模型列表（不传则用默认层级）
        tier_mapping: 自定义层级映射

    返回:
        推荐模型名，或 None
    """
    tiers = tier_mapping or MODEL_TIERS
    candidates = tiers.get(complexity.recommended_model_tier, [])

    if available_models:
        # 交集：取候选和可用模型的重叠
        matching = [m for m in candidates if m in available_models]
        return matching[0] if matching else (available_models[0] if available_models else None)

    return candidates[0] if candidates else None
