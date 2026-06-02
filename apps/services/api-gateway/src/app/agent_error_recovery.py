"""Agent 自主错误恢复模块。

核心能力：
- 三级恢复策略：retry（重试）→ degrade（降级）→ escalate（升级求助）
- 错误分类：工具错误 / 检索空 / 超时 / 模型错误 / 范围不匹配
- 指数退避重试（Exponential Backoff）
- 降级路径：agent → grounded → common_knowledge → fallback
- 恢复统计：追踪每种恢复策略的成功率

使用方式::

    from .agent_error_recovery import ErrorRecoveryEngine

    engine = ErrorRecoveryEngine()
    result = await engine.execute_with_recovery(
        primary_fn,
        fallback_fns=[degrade_fn, fallback_fn],
        max_retries=2,
    )
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class ErrorType(str, Enum):
    """错误类型分类。"""
    TOOL_ERROR = "tool_error"           # 工具执行失败
    RETRIEVAL_EMPTY = "retrieval_empty" # 检索无结果
    TIMEOUT = "timeout"                 # 超时
    MODEL_ERROR = "model_error"         # 模型调用失败
    SCOPE_MISMATCH = "scope_mismatch"   # 知识范围不匹配
    NETWORK_ERROR = "network_error"     # 网络错误
    UNKNOWN = "unknown"                 # 未知错误


class RecoveryAction(str, Enum):
    """恢复动作。"""
    RETRY = "retry"           # 重试（相同参数）
    RETRY_EXPANDED = "retry_expanded"  # 重试（扩展参数）
    DEGRADE = "degrade"       # 降级到备选方案
    ESCALATE = "escalate"     # 升级到人工
    FALLBACK = "fallback"     # 使用兜底回答
    GIVE_UP = "give_up"       # 放弃


@dataclass
class RecoveryResult:
    """恢复结果。"""
    success: bool = False
    action_taken: str = ""           # 最终采取的动作
    attempts: int = 0                # 总尝试次数
    total_time_ms: float = 0.0       # 总耗时（ms）
    error_chain: list[str] = field(default_factory=list)  # 错误链
    final_data: Any = None           # 最终返回数据
    strategy_stats: dict[str, Any] = field(default_factory=dict)  # 策略统计


# ---------------------------------------------------------------------------
# 错误分类器
# ---------------------------------------------------------------------------


class ErrorClassifier:
    """错误分类器 —— 自动识别错误类型并推荐恢复策略。"""

    @staticmethod
    def classify(exception: Exception) -> ErrorType:
        """分类异常类型。"""
        exc_type = exception.__class__.__name__
        message = str(exception).lower()

        if "timeout" in message or "timed out" in message or "asyncio.TimeoutError" in exc_type:
            return ErrorType.TIMEOUT
        if any(kw in message for kw in ["connection", "network", "dns", "refused"]):
            return ErrorType.NETWORK_ERROR
        if any(kw in message for kw in ["tool", "tool_error"]) or "ToolError" in exc_type:
            return ErrorType.TOOL_ERROR
        if any(kw in message for kw in ["no results", "empty", "no evidence"]):
            return ErrorType.RETRIEVAL_EMPTY
        if any(kw in message for kw in ["model", "llm", "api key", "rate limit", "401", "403", "429"]):
            return ErrorType.MODEL_ERROR
        if any(kw in message for kw in ["scope", "permission", "not found", "404"]):
            return ErrorType.SCOPE_MISMATCH
        return ErrorType.UNKNOWN

    @staticmethod
    def recommend_action(error_type: str, attempt: int) -> RecoveryAction:
        """根据错误类型和重试次数推荐恢复动作。"""
        if attempt <= 2:
            if error_type in {ErrorType.TIMEOUT.value, ErrorType.NETWORK_ERROR.value}:
                return RecoveryAction.RETRY
            if error_type == ErrorType.RETRIEVAL_EMPTY.value:
                return RecoveryAction.RETRY_EXPANDED if attempt == 1 else RecoveryAction.DEGRADE
            if error_type == ErrorType.MODEL_ERROR.value:
                return RecoveryAction.RETRY if attempt <= 2 else RecoveryAction.DEGRADE
            if error_type == ErrorType.TOOL_ERROR.value:
                return RecoveryAction.RETRY if attempt == 1 else RecoveryAction.DEGRADE

        if attempt <= 3:
            return RecoveryAction.DEGRADE
        if attempt <= 4:
            return RecoveryAction.FALLBACK

        return RecoveryAction.GIVE_UP


# ---------------------------------------------------------------------------
# 恢复引擎
# ---------------------------------------------------------------------------


class ErrorRecoveryEngine:
    """自主错误恢复引擎 —— 三级策略 + 指数退避。"""

    # 指数退避配置
    BASE_DELAY_MS = 500          # 基础延迟
    MAX_DELAY_MS = 10_000        # 最大延迟
    BACKOFF_MULTIPLIER = 2.0     # 退避倍率
    JITTER = 0.1                 # 随机抖动比例

    def __init__(self) -> None:
        self._stats: dict[str, dict[str, Any]] = {}  # 策略统计

    async def execute_with_recovery(
        self,
        primary_fn: Any,
        *,
        fallback_fns: list[Any] | None = None,
        max_retries: int = 2,
        error_context: dict[str, Any] | None = None,
    ) -> RecoveryResult:
        """执行 primary_fn，失败时自动恢复。

        参数:
            primary_fn: 主要执行函数 (async callable)
            fallback_fns: 降级备选函数列表 [degrade_fn, fallback_fn, ...]
            max_retries: 最大重试次数
            error_context: 错误上下文（用于日志和策略优化）

        返回:
            RecoveryResult
        """
        fallback_fns = fallback_fns or []
        error_chain: list[str] = []
        started = time.perf_counter()

        # 尝试 1：主函数
        try:
            data = await primary_fn()
            return RecoveryResult(
                success=True,
                action_taken="primary",
                attempts=1,
                total_time_ms=round((time.perf_counter() - started) * 1000, 3),
                error_chain=[],
                final_data=data,
            )
        except Exception as exc:
            error_type = ErrorClassifier.classify(exc)
            error_chain.append(f"primary: {error_type}({str(exc)[:100]})")
            logger.debug("recovery_primary_failed type=%s attempt=1", error_type)

        # 尝试 2-N：重试（指数退避）
        for attempt in range(1, max_retries + 1):
            action = ErrorClassifier.recommend_action(error_type, attempt)
            if action != RecoveryAction.RETRY:
                break  # 不需要再重试

            delay_ms = self._backoff_delay(attempt)
            logger.debug("recovery_retry attempt=%d delay_ms=%d", attempt + 1, delay_ms)
            await asyncio.sleep(delay_ms / 1000.0)

            try:
                data = await primary_fn()
                self._record_success("retry", error_type, attempt)
                return RecoveryResult(
                    success=True,
                    action_taken=f"retry_{attempt}",
                    attempts=attempt + 1,
                    total_time_ms=round((time.perf_counter() - started) * 1000, 3),
                    error_chain=error_chain,
                    final_data=data,
                )
            except Exception as exc2:
                next_error = ErrorClassifier.classify(exc2)
                error_chain.append(f"retry_{attempt}: {next_error}({str(exc2)[:100]})")
                error_type = next_error  # 更新错误类型

        # 尝试：降级到备选方案
        for i, fallback_fn in enumerate(fallback_fns[:-1]):  # 除最后一个都算降级
            try:
                data = await fallback_fn()
                self._record_success("degrade", error_type, max_retries)
                return RecoveryResult(
                    success=True,
                    action_taken=f"degrade_{i}",
                    attempts=max_retries + 1 + i,
                    total_time_ms=round((time.perf_counter() - started) * 1000, 3),
                    error_chain=error_chain,
                    final_data=data,
                )
            except Exception as exc3:
                error_chain.append(f"degrade_{i}: {str(exc3)[:100]}")

        # 最后：兜底
        if fallback_fns:
            try:
                data = await fallback_fns[-1]()
                self._record_success("fallback", error_type, max_retries)
                return RecoveryResult(
                    success=True,
                    action_taken="fallback",
                    attempts=max_retries + len(fallback_fns),
                    total_time_ms=round((time.perf_counter() - started) * 1000, 3),
                    error_chain=error_chain,
                    final_data=data,
                )
            except Exception as exc4:
                error_chain.append(f"fallback: {str(exc4)[:100]}")

        # 完全失败
        self._record_failure(error_type, len(error_chain))
        return RecoveryResult(
            success=False,
            action_taken="give_up",
            attempts=max_retries + len(fallback_fns) + 1,
            total_time_ms=round((time.perf_counter() - started) * 1000, 3),
            error_chain=error_chain,
        )

    def _backoff_delay(self, attempt: int) -> float:
        """计算指数退避延迟（ms）。"""
        import random
        delay = self.BASE_DELAY_MS * (self.BACKOFF_MULTIPLIER ** (attempt - 1))
        delay = min(delay, self.MAX_DELAY_MS)
        # 加随机抖动
        jitter_range = delay * self.JITTER
        delay += random.uniform(-jitter_range, jitter_range)
        return max(delay, 100)

    def _record_success(self, action: str, error_type: str, attempts: int) -> None:
        key = f"{error_type}_{action}"
        stats = self._stats.get(key, {"success": 0, "failure": 0, "avg_attempts": 0})
        stats["success"] += 1
        stats["avg_attempts"] = (stats["avg_attempts"] * (stats["success"] - 1) + attempts) / stats["success"]
        self._stats[key] = stats

    def _record_failure(self, error_type: str, attempts: int) -> None:
        key = f"{error_type}_give_up"
        stats = self._stats.get(key, {"success": 0, "failure": 0, "avg_attempts": 0})
        stats["failure"] += 1
        self._stats[key] = stats

    def stats(self) -> dict[str, Any]:
        """获取恢复统计。"""
        return dict(self._stats)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def recoverable_execute(
    primary_fn: Any,
    *,
    fallback_fns: list[Any] | None = None,
    max_retries: int = 2,
) -> RecoveryResult:
    """便捷函数：执行 primary_fn 并自动恢复。"""
    engine = ErrorRecoveryEngine()
    return await engine.execute_with_recovery(
        primary_fn,
        fallback_fns=fallback_fns,
        max_retries=max_retries,
    )
