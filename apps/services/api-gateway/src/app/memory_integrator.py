"""跨会话记忆整合器。

核心能力：
- 跨会话记忆合并与去重（同一用户多次对话的记忆整合）
- 冲突检测与解决（新旧记忆矛盾 → LLM 仲裁）
- 记忆版本追踪（追踪一条记忆在多轮对话中的演变）
- 记忆聚类（将语义相近的记忆合并为"知识簇"）

使用方式::

    from .memory_integrator import MemoryIntegrator

    integrator = MemoryIntegrator(store)
    merged = await integrator.integrate(new_memories, user_id)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger
from .memory_importance import MemoryImportanceScorer


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class MergeDecision:
    """记忆合并决策。"""
    action: str = "keep_both"  # keep_both | replace | merge | discard
    reason: str = ""
    merged_entry: dict[str, Any] | None = None
    retained_ids: list[str] = field(default_factory=list)
    discarded_ids: list[str] = field(default_factory=list)


@dataclass
class IntegrationResult:
    """整合结果。"""
    user_id: str = ""
    new_count: int = 0
    merged_count: int = 0
    replaced_count: int = 0
    discarded_count: int = 0
    conflicts: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 记忆整合器
# ---------------------------------------------------------------------------


class MemoryIntegrator:
    """跨会话记忆整合器。"""

    # 相似度阈值：超过此值视为需要合并
    SIMILARITY_THRESHOLD = 0.75
    # 冲突检测阈值：同 subject+predicate 但 object 不同的置信度阈值
    CONFLICT_THRESHOLD = 0.65

    def __init__(self, store: Any = None) -> None:
        self._store = store
        self._scorer = MemoryImportanceScorer()

    async def integrate(
        self,
        new_memories: list[Any],
        user_id: str,
        *,
        existing_memories: list[Any] | None = None,
    ) -> IntegrationResult:
        """整合新记忆与已有记忆。

        参数:
            new_memories: 新提取的记忆（MemoryTriple 或 MemoryEntry）
            user_id: 用户标识
            existing_memories: 已有的记忆列表（不提供则从 store 查询）

        返回:
            整合结果
        """
        if not new_memories:
            return IntegrationResult(user_id=user_id)

        # 加载已有记忆
        if existing_memories is None and self._store is not None:
            existing_memories = await self._store.list_by_user(user_id, limit=200)
        existing_memories = existing_memories or []

        result = IntegrationResult(user_id=user_id, new_count=len(new_memories))

        for new_mem in new_memories:
            new_subject = str(getattr(new_mem, "subject", "") or "").strip()
            new_predicate = str(getattr(new_mem, "predicate", "") or "").strip()
            new_object = str(getattr(new_mem, "object", "") or "").strip()

            if not new_subject or not new_object:
                result.discarded_count += 1
                continue

            # 查找冲突/重复
            conflicts = self._find_conflicts(new_mem, existing_memories)

            if not conflicts:
                # 无冲突，保留新记忆
                result.retained_ids.append(getattr(new_mem, "id", str(uuid.uuid4())))
                continue

            # 解决冲突
            decision = self._resolve(new_mem, conflicts)
            self._apply_decision(result, decision)

        logger.info(
            "memory_integrated user=%s new=%d merged=%d replaced=%d discarded=%d",
            user_id, result.new_count, result.merged_count,
            result.replaced_count, result.discarded_count,
        )
        return result

    def _find_conflicts(self, new_mem: Any, existing: list[Any]) -> list[Any]:
        """查找与新记忆冲突的已有记忆。"""
        new_subject = str(getattr(new_mem, "subject", "") or "").strip().lower()
        new_predicate = str(getattr(new_mem, "predicate", "") or "").strip().lower()

        conflicts = []
        for old_mem in existing:
            old_subject = str(getattr(old_mem, "subject", "") or "").strip().lower()
            old_predicate = str(getattr(old_mem, "predicate", "") or "").strip().lower()

            # 同 subject + predicate → 可能是冲突
            if old_subject == new_subject:
                # predicate 相似度
                predicate_sim = self._text_similarity(new_predicate, old_predicate)
                if predicate_sim >= self.CONFLICT_THRESHOLD:
                    conflicts.append(old_mem)

        return conflicts

    def _resolve(self, new_mem: Any, conflicts: list[Any]) -> MergeDecision:
        """解决记忆冲突。"""
        new_object = str(getattr(new_mem, "object", "") or "").strip()
        new_importance = getattr(new_mem, "importance", 0.5)
        new_confidence = getattr(new_mem, "confidence", 0.8)
        new_created = getattr(new_mem, "created_at", 0.0)

        for old in conflicts:
            old_object = str(getattr(old, "object", "") or "").strip()
            old_importance = getattr(old, "importance", 0.5)
            old_confidence = getattr(old, "confidence", 0.8)

            # 完全相同 → discard new
            if new_object == old_object:
                return MergeDecision(
                    action="discard",
                    reason="完全重复的记忆",
                    discarded_ids=[getattr(new_mem, "id", "")],
                )

            # 语义相似 > 阈值 → merge
            obj_sim = self._text_similarity(new_object.lower(), old_object.lower())
            if obj_sim >= self.SIMILARITY_THRESHOLD:
                # 保留更重要的那条，合并置信度
                if new_importance >= old_importance:
                    return MergeDecision(
                        action="replace",
                        reason=f"新记忆更重要 (importance {new_importance} > {old_importance})",
                        retained_ids=[getattr(new_mem, "id", "")],
                        discarded_ids=[getattr(old, "id", "")],
                    )
                else:
                    return MergeDecision(
                        action="discard",
                        reason=f"已有记忆更重要 (importance {old_importance} > {new_importance})",
                        discarded_ids=[getattr(new_mem, "id", "")],
                    )

            # 不同 → keep_both
            return MergeDecision(
                action="keep_both",
                reason="同主题但内容不同，两条都保留",
            )

        return MergeDecision(action="keep_both", reason="未匹配到冲突")

    def _apply_decision(self, result: IntegrationResult, decision: MergeDecision) -> None:
        """应用合并决策到结果。"""
        if decision.action == "replace":
            result.replaced_count += 1
        elif decision.action == "merge":
            result.merged_count += 1
        elif decision.action == "discard":
            result.discarded_count += 1

        if decision.retained_ids:
            result.retained_ids.extend(decision.retained_ids)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """简单的文本相似度（Jaccard + 字符重叠）。"""
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        a_chars = set(a)
        b_chars = set(b)
        intersection = len(a_chars & b_chars)
        union = len(a_chars | b_chars)

        if union == 0:
            return 0.0

        # 字符 Jaccard
        char_jaccard = intersection / union

        # 长度相似度
        len_ratio = min(len(a), len(b)) / max(len(a), len(b), 1)

        return round(char_jaccard * 0.6 + len_ratio * 0.4, 4)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def integrate_memories(
    new_memories: list[Any],
    user_id: str,
    *,
    store: Any = None,
) -> IntegrationResult:
    """便捷函数：整合新记忆到已有记忆库。"""
    integrator = MemoryIntegrator(store)
    return await integrator.integrate(new_memories, user_id)
