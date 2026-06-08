"""Token-aware 滑动窗口管理器。

核心能力：
- 基于 token 数量而非消息条数的滑动窗口
- 支持中英文混合的 token 估算（无需外部 tokenizer 依赖）
- 关键消息标记（不可淘汰的系统消息、重要用户消息）
- 双向窗口：系统消息固定保留 + 最近 N token 滑动窗口
- Token 预算分配：系统消息、历史、证据各占比例可配置

使用方式::

    from .context_window import ContextWindowManager

    mgr = ContextWindowManager(max_tokens=4000)
    managed = mgr.manage(history, system_prompt, evidence_block)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.token_estimation import estimate_tokens

from .gateway_runtime import logger


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """估算单条消息的 token 数（包含角色标记开销约 4 token）。"""
    role = str(message.get("role") or "")
    content = str(message.get("content") or "")
    # 角色标记 + 格式化开销
    overhead = 4
    return overhead + estimate_tokens(role) + estimate_tokens(content)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class WindowConfig:
    """滑动窗口配置。"""

    max_tokens: int = 4000  # 窗口最大 token 数
    system_reserve_ratio: float = 0.15  # 系统消息保留 token 比例
    history_ratio: float = 0.50  # 历史消息分配比例
    evidence_ratio: float = 0.35  # 证据文本分配比例
    min_history_turns: int = 2  # 最少保留的对话轮数（1轮=user+assistant）
    reserved_message_ids: set[str] = field(default_factory=set)  # 不可淘汰的消息 ID


@dataclass
class WindowStats:
    """窗口使用统计。"""

    total_tokens: int = 0
    system_tokens: int = 0
    history_tokens: int = 0
    evidence_tokens: int = 0
    messages_kept: int = 0
    messages_dropped: int = 0
    budget_limit: int = 0
    overflow: bool = False


# ---------------------------------------------------------------------------
# 滑动窗口管理器
# ---------------------------------------------------------------------------


class ContextWindowManager:
    """Token-aware 滑动窗口管理器。

    按 token 预算分配系统消息、历史对话和证据文本的比例，
    超出预算时从最早的消息开始淘汰，保留关键消息。
    """

    def __init__(
        self,
        max_tokens: int = 4000,
        *,
        system_reserve_ratio: float = 0.15,
        history_ratio: float = 0.50,
        evidence_ratio: float = 0.35,
        min_history_turns: int = 2,
    ) -> None:
        self._config = WindowConfig(
            max_tokens=max_tokens,
            system_reserve_ratio=system_reserve_ratio,
            history_ratio=history_ratio,
            evidence_ratio=evidence_ratio,
            min_history_turns=min_history_turns,
        )

    @property
    def config(self) -> WindowConfig:
        return self._config

    def manage(
        self,
        history: list[dict[str, Any]],
        system_prompt: str = "",
        evidence_block: str = "",
        *,
        reserved_message_ids: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], WindowStats]:
        """管理上下文窗口。

        参数:
            history: 历史消息列表（按时间正序）
            system_prompt: 系统级提示词
            evidence_block: 证据文本块
            reserved_message_ids: 不可被淘汰的消息 ID 集合

        返回:
            (裁剪后的消息列表, 窗口统计)
        """
        reserved = reserved_message_ids or set()
        config = self._config

        # 计算各区域 token 预算
        system_budget = int(config.max_tokens * config.system_reserve_ratio)
        history_budget = int(config.max_tokens * config.history_ratio)
        evidence_budget = int(config.max_tokens * config.evidence_ratio)

        # 1. 处理 evidence block
        truncated_evidence = self._truncate_text(evidence_block, evidence_budget)
        evidence_tokens = estimate_tokens(truncated_evidence)

        # 2. 处理系统提示词（不可淘汰）
        truncated_system = self._truncate_text(system_prompt, system_budget)
        system_tokens = estimate_tokens(truncated_system)

        # 3. 滑动窗口处理历史消息
        kept, dropped, history_tokens = self._slide_window(
            history,
            history_budget,
            reserved=reserved,
            min_turns=config.min_history_turns,
        )

        total = system_tokens + history_tokens + evidence_tokens
        stats = WindowStats(
            total_tokens=total,
            system_tokens=system_tokens,
            history_tokens=history_tokens,
            evidence_tokens=evidence_tokens,
            messages_kept=len(kept),
            messages_dropped=dropped,
            budget_limit=config.max_tokens,
            overflow=total > config.max_tokens,
        )

        if stats.overflow:
            logger.warning(
                "context_window_overflow total=%d budget=%d kept=%d dropped=%d",
                total, config.max_tokens, len(kept), dropped,
            )

        return kept, stats

    def _slide_window(
        self,
        history: list[dict[str, Any]],
        budget: int,
        *,
        reserved: set[str],
        min_turns: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """从历史消息中执行滑动窗口裁剪。

        策略：从最新消息向前累计 token，超出预算后裁剪。
        保留至少 min_turns 轮完整对话。
        """
        if not history:
            return [], 0, 0

        # 标记每条消息是否受保护
        protected = self._mark_protected(history, reserved, min_turns)

        # 从最新消息向前累计
        kept: list[dict[str, Any]] = []
        token_count = 0
        dropped = 0
        budget_breached = False

        for msg in reversed(history):
            msg_id = str(msg.get("id") or msg.get("message_id") or "")
            is_protected = msg_id in reserved or msg in protected
            msg_tokens = estimate_message_tokens(msg)

            if not budget_breached and (is_protected or token_count + msg_tokens <= budget):
                kept.insert(0, msg)
                token_count += msg_tokens
            else:
                budget_breached = True
                dropped += 1

        if dropped > 0:
            logger.debug(
                "context_window_slide kept=%d dropped=%d tokens=%d budget=%d",
                len(kept), dropped, token_count, budget,
            )

        return kept, dropped, token_count

    def _mark_protected(
        self,
        history: list[dict[str, Any]],
        reserved_ids: set[str],
        min_turns: int,
    ) -> list[dict[str, Any]]:
        """标记最少保留的对话轮次。"""
        if min_turns <= 0 or not history:
            return []

        protected: list[dict[str, Any]] = []
        turn_count = 0
        user_seen = False

        for msg in reversed(history):
            role = str(msg.get("role") or "")
            if role == "user":
                if user_seen:
                    turn_count += 1
                user_seen = True
            elif role == "assistant" and user_seen:
                turn_count += 1
                user_seen = False
            protected.append(msg)
            if turn_count >= min_turns:
                break

        return protected

    @staticmethod
    def _truncate_text(text: str, max_tokens: int) -> str:
        """按 token 预算截断文本。"""
        if not text:
            return ""
        tokens = estimate_tokens(text)
        if tokens <= max_tokens:
            return text
        # 按比例截断字符
        ratio = max_tokens / max(tokens, 1)
        target_chars = max(int(len(text) * ratio * 1.15), 50)  # 略多留一些空间
        return text[:target_chars] + "\n...（内容已截断）"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def manage_context_window(
    history: list[dict[str, Any]],
    system_prompt: str = "",
    evidence_block: str = "",
    *,
    max_tokens: int = 4000,
    min_history_turns: int = 2,
) -> tuple[list[dict[str, Any]], WindowStats]:
    """便捷函数：一键管理上下文窗口。"""
    mgr = ContextWindowManager(max_tokens=max_tokens, min_history_turns=min_history_turns)
    return mgr.manage(history, system_prompt, evidence_block)
