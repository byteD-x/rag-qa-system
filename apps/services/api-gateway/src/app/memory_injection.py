"""记忆注入策略引擎。

核心能力：
- 智能决策：何时注入记忆、注入什么、注入多少
- 当前问题 → 语义检索相关记忆 → 按相关度 + 重要度排序
- 注入预算控制：记忆块不超出 Token 预算的 15%
- 注入格式：结构化记忆块嵌入系统 prompt

使用方式::

    from .memory_injection import MemoryInjector

    injector = MemoryInjector(memory_store)
    injection_text = await injector.inject(user_id, question, max_tokens=600)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .context_window import estimate_tokens
from .gateway_runtime import logger
from .memory_importance import MemoryImportanceScorer


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class InjectionDecision:
    """注入决策。"""
    should_inject: bool = False
    reason: str = ""
    memories_to_inject: list[Any] = field(default_factory=list)
    injected_tokens: int = 0
    injection_text: str = ""
    relevance_scores: list[float] = field(default_factory=list)


@dataclass
class InjectionConfig:
    """注入配置。"""
    max_inject_tokens: int = 600  # 注入记忆的最大 token 数
    max_memories: int = 8  # 最多注入几条记忆
    min_relevance: float = 0.2  # 最低相关性阈值
    min_importance: float = 0.15  # 最低重要性阈值（衰减后）
    enable_auto_inject: bool = True  # 是否启用自动注入


# ---------------------------------------------------------------------------
# 记忆注入器
# ---------------------------------------------------------------------------


class MemoryInjector:
    """记忆注入策略引擎。

    决策流程：
    1. 问题是否与已存记忆相关？→ 语义检索
    2. 哪些记忆值得注入？→ 相关性 + 重要性排序
    3. 注入多少？→ Token 预算控制
    4. 生成注入文本 → 嵌入到系统 prompt
    """

    DEFAULT_INJECTION_TEMPLATE = """## 用户记忆与偏好
以下是该用户的历史偏好和已知信息，请在回答时优先参考：

{memories}

---
"""

    def __init__(self, memory_store: Any = None, *, config: InjectionConfig | None = None) -> None:
        self._store = memory_store
        self._config = config or InjectionConfig()
        self._scorer = MemoryImportanceScorer()

    async def inject(
        self,
        user_id: str,
        question: str,
        *,
        max_tokens: int | None = None,
    ) -> InjectionDecision:
        """决定是否注入记忆以及注入什么。

        参数:
            user_id: 用户标识
            question: 当前问题
            max_tokens: 注入的 token 预算（覆盖配置）

        返回:
            注入决策
        """
        budget = max_tokens or self._config.max_inject_tokens

        if not self._config.enable_auto_inject or self._store is None:
            return InjectionDecision(should_inject=False, reason="注入已禁用")

        # 1. 语义检索相关记忆
        try:
            candidate_memories = await self._store.search(
                user_id,
                question,
                limit=self._config.max_memories * 2,  # 多取一些做筛选
            )
        except Exception as exc:
            logger.warning("memory_inject_search_failed user=%s err=%s", user_id, exc)
            return InjectionDecision(should_inject=False, reason=f"检索失败: {exc}")

        if not candidate_memories:
            return InjectionDecision(should_inject=False, reason="无相关记忆")

        # 2. 过滤：相关性 + 重要性
        scored = self._score_candidates(candidate_memories, question)
        scored = [
            (mem, rel, imp)
            for mem, rel, imp in scored
            if rel >= self._config.min_relevance
            and imp >= self._config.min_importance
        ]

        if not scored:
            return InjectionDecision(
                should_inject=False,
                reason=f"候选记忆未通过阈值 (relevance<{self._config.min_relevance} or importance<{self._config.min_importance})",
            )

        # 3. 按综合分数排序，选取 top-k
        scored.sort(key=lambda x: x[1] * 0.6 + x[2] * 0.4, reverse=True)
        selected = []
        relevance_scores = []
        token_count = 0

        for mem, rel, imp in scored[:self._config.max_memories]:
            mem_text = self._format_memory(mem)
            mem_tokens = estimate_tokens(mem_text)
            if token_count + mem_tokens > budget:
                break
            selected.append(mem)
            relevance_scores.append(rel)
            token_count += mem_tokens

        if not selected:
            return InjectionDecision(should_inject=False, reason="Token 预算不足以注入任何记忆")

        # 4. 生成注入文本
        injection_text = self._build_injection_text(selected)
        actual_tokens = estimate_tokens(injection_text)

        logger.debug(
            "memory_injected user=%s count=%d tokens=%d relevance_avg=%.2f",
            user_id, len(selected), actual_tokens,
            sum(relevance_scores) / max(len(relevance_scores), 1),
        )

        return InjectionDecision(
            should_inject=True,
            reason=f"注入 {len(selected)} 条记忆",
            memories_to_inject=selected,
            injected_tokens=actual_tokens,
            injection_text=injection_text,
            relevance_scores=relevance_scores,
        )

    def _score_candidates(
        self,
        memories: list[Any],
        question: str,
    ) -> list[tuple[Any, float, float]]:
        """对候选记忆评分（相关性 + 有效重要性）。"""
        question_lower = question.lower()
        results = []

        for mem in memories:
            mem_text = (
                f"{getattr(mem, 'subject', '')} "
                f"{getattr(mem, 'predicate', '')} "
                f"{getattr(mem, 'object', '')}"
            ).lower()

            # 相关性：关键词命中率
            relevance = self._compute_relevance(question_lower, mem_text)

            # 有效重要性：考虑衰减
            effective_imp = getattr(mem, "effective_importance", None)
            if effective_imp is None or not callable(effective_imp):
                effective_imp = self._scorer.effective_importance(mem)

            results.append((mem, relevance, float(effective_imp)))

        return results

    @staticmethod
    def _compute_relevance(question: str, memory_text: str) -> float:
        """计算问题与记忆的相关性。"""
        if not question or not memory_text:
            return 0.0

        # 分词
        q_tokens = set(question.replace(" ", ""))
        m_tokens = set(memory_text.replace(" ", ""))

        if not q_tokens or not m_tokens:
            return 0.0

        intersection = len(q_tokens & m_tokens)
        # 命中率相对于问题 token 数（问题越短，命中率要求越高）
        q_ratio = intersection / max(len(q_tokens), 1)

        # 双向 Jaccard
        union = len(q_tokens | m_tokens)
        jaccard = intersection / max(union, 1)

        return round(q_ratio * 0.6 + jaccard * 0.4, 4)

    def _build_injection_text(self, memories: list[Any]) -> str:
        """构建注入文本。"""
        memory_lines = []
        for mem in memories:
            memory_lines.append(self._format_memory(mem))

        formatted = "\n".join(
            f"- {line}" for line in memory_lines if line
        )
        return self.DEFAULT_INJECTION_TEMPLATE.format(memories=formatted)

    @staticmethod
    def _format_memory(memory: Any) -> str:
        """格式化单条记忆为文本。"""
        subject = str(getattr(memory, "subject", "") or "").strip()
        predicate = str(getattr(memory, "predicate", "") or "").strip()
        obj = str(getattr(memory, "object", "") or "").strip()
        memory_type = str(getattr(memory, "memory_type", "") or "").strip()
        importance = getattr(memory, "importance", 0.5)

        type_map = {
            "preference": "偏好",
            "fact": "事实",
            "knowledge": "知识",
        }
        type_label = type_map.get(memory_type, memory_type)

        # 重要性星级
        stars = "★" * max(int(importance * 5), 1)

        if predicate in {"是", "为", "="}:
            return f"[{type_label} | {stars}] {subject}: {obj}"
        return f"[{type_label} | {stars}] {subject} {predicate} {obj}"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def inject_user_memories(
    user_id: str,
    question: str,
    *,
    memory_store: Any = None,
    max_tokens: int = 600,
) -> InjectionDecision:
    """便捷函数：根据当前问题注入相关用户记忆。"""
    injector = MemoryInjector(memory_store)
    return await injector.inject(user_id, question, max_tokens=max_tokens)
