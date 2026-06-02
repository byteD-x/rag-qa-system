"""成本预算控制与预警模块。

核心能力：
- 用户级 / 会话级 / 日级三级预算体系
- Token 消耗实时追踪
- 预算耗尽预警（80%/95%/100% 三级预警）
- 超额拦截（硬预算）或降级路由（软预算）
- 成本预估模型（输入 token → 预估成本）

使用方式::

    from .cost_budget import CostBudgetController

    ctrl = CostBudgetController()
    ctrl.check(user_id, session_id, estimated_tokens)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class BudgetLevel(str, Enum):
    """预算层级。"""
    USER = "user"           # 用户级（月度总预算）
    SESSION = "session"     # 会话级（单次对话预算）
    DAILY = "daily"         # 日级（每日预算）


class BudgetStatus(str, Enum):
    """预算状态。"""
    HEALTHY = "healthy"           # 正常 (< 80%)
    WARNING = "warning"           # 预警 (80%-95%)
    CRITICAL = "critical"         # 临界 (95%-100%)
    EXCEEDED = "exceeded"         # 超额 (> 100%)
    DISABLED = "disabled"         # 预算已禁用


@dataclass
class BudgetConfig:
    """预算配置。"""
    level: str = "session"     # 预算层级
    max_tokens: int = 100_000  # 最大 token 数
    max_cost: float = 0.0      # 最大成本（货币单位），0 表示不限制
    hard_limit: bool = True    # 硬限制（超支拒绝） vs 软限制（降级路由）
    alert_thresholds: list[float] = field(default_factory=lambda: [0.8, 0.95])


@dataclass
class BudgetState:
    """预算当前状态。"""
    level: str = ""
    status: str = "healthy"
    tokens_used: int = 0
    tokens_limit: int = 0
    cost_used: float = 0.0
    cost_limit: float = 0.0
    usage_ratio: float = 0.0       # 使用比例 0-1
    alert_level: int = 0            # 0=healthy, 1=warning, 2=critical
    estimated_remaining: int = 0
    next_reset_at: float = 0.0


# ---------------------------------------------------------------------------
# 成本预估
# ---------------------------------------------------------------------------


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_price_per_1k: float = 0.015,
    output_price_per_1k: float = 0.06,
    model_name: str = "",
) -> dict[str, Any]:
    """估算 LLM 调用成本。

    参数:
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        input_price_per_1k: 每千输入 token 价格
        output_price_per_1k: 每千输出 token 价格
        model_name: 模型名（用于价格查询）

    返回:
        包含 cost、input_cost、output_cost 的字典
    """
    # 模型价格表（每千 token，CNY）
    MODEL_PRICES = {
        "gpt-4": (0.218, 0.436),
        "gpt-4o": (0.036, 0.109),
        "gpt-3.5-turbo": (0.0036, 0.0145),
        "claude-opus": (0.109, 0.436),
        "claude-sonnet": (0.0218, 0.109),
        "qwen-plus": (0.014, 0.014),
        "qwen-max": (0.028, 0.084),
        "deepseek-v3": (0.007, 0.014),
    }

    if model_name:
        for key, (in_price, out_price) in MODEL_PRICES.items():
            if key in model_name.lower():
                input_price_per_1k = in_price
                output_price_per_1k = out_price
                break

    input_cost = (input_tokens / 1000.0) * input_price_per_1k
    output_cost = (output_tokens / 1000.0) * output_price_per_1k

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_price_per_1k": input_price_per_1k,
        "output_price_per_1k": output_price_per_1k,
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6),
        "model": model_name,
    }


def estimate_tokens_to_cost(
    estimated_input_tokens: int,
    estimated_output_tokens: int | None = None,
    *,
    model_name: str = "",
    input_price_per_1k: float = 0.015,
    output_price_per_1k: float = 0.06,
) -> float:
    """快速估算：预估 token 数 → 预估成本。"""
    out_tokens = estimated_output_tokens or estimated_input_tokens // 3
    result = estimate_cost(
        estimated_input_tokens, out_tokens,
        input_price_per_1k=input_price_per_1k,
        output_price_per_1k=output_price_per_1k,
        model_name=model_name,
    )
    return float(result["total_cost"])


# ---------------------------------------------------------------------------
# 成本预算控制器
# ---------------------------------------------------------------------------


class CostBudgetController:
    """成本预算控制器 —— 多级预算体系 + 实时追踪 + 预警拦截。"""

    def __init__(self) -> None:
        # 内存存储（生产应替换为数据库）
        self._budgets: dict[str, dict[str, BudgetState]] = {}

    def configure(
        self,
        user_id: str,
        session_id: str = "",
        *,
        level: str = "session",
        max_tokens: int = 100_000,
        max_cost: float = 0.0,
        hard_limit: bool = True,
    ) -> None:
        """配置预算。

        参数:
            user_id: 用户标识
            session_id: 会话标识（session 级时需要）
            level: 预算层级
            max_tokens: 最大 token 数
            max_cost: 最大成本（0 表示不限制）
            hard_limit: 超支后拒绝还是降级
        """
        key = self._budget_key(user_id, session_id, level)
        self._budgets[key] = {
            "config": BudgetConfig(
                level=level,
                max_tokens=max_tokens,
                max_cost=max_cost,
                hard_limit=hard_limit,
            ),
            "state": BudgetState(
                level=level,
                status=BudgetStatus.HEALTHY.value,
                tokens_limit=max_tokens,
                cost_limit=max_cost,
                next_reset_at=time.time() + 86400 * (30 if level == "user" else 1),
            ),
        }

    def check(
        self,
        user_id: str,
        session_id: str,
        estimated_tokens: int,
        *,
        estimated_cost: float = 0.0,
    ) -> tuple[bool, BudgetState]:
        """检查预算是否充足。

        返回:
            (是否允许, 预算状态)
        """
        last_state: BudgetState | None = None
        # 按优先级检查：session → daily → user
        for level in [BudgetLevel.SESSION.value, BudgetLevel.DAILY.value, BudgetLevel.USER.value]:
            key = self._budget_key(user_id, session_id, level)
            entry = self._budgets.get(key)
            if entry is None:
                continue

            config = entry["config"]
            state = entry["state"]
            last_state = state

            # 检查 token 预算
            if config.max_tokens > 0:
                new_tokens = state.tokens_used + estimated_tokens
                state.usage_ratio = new_tokens / config.max_tokens
                state.estimated_remaining = max(config.max_tokens - state.tokens_used, 0)

                if state.usage_ratio >= 1.0:
                    state.status = BudgetStatus.EXCEEDED.value
                    if config.hard_limit:
                        logger.warning(
                            "budget_exceeded level=%s user=%s used=%d limit=%d",
                            level, user_id, state.tokens_used, config.max_tokens,
                        )
                        return False, state
                elif state.usage_ratio >= 0.95:
                    state.status = BudgetStatus.CRITICAL.value
                    state.alert_level = 2
                elif state.usage_ratio >= 0.80:
                    state.status = BudgetStatus.WARNING.value
                    state.alert_level = 1

            # 检查成本预算
            if config.max_cost > 0 and estimated_cost > 0:
                new_cost = state.cost_used + estimated_cost
                if new_cost >= config.max_cost and config.hard_limit:
                    return False, state

        return True, last_state or BudgetState(status=BudgetStatus.HEALTHY.value)

    def record(
        self,
        user_id: str,
        session_id: str,
        tokens_used: int,
        *,
        cost: float = 0.0,
    ) -> None:
        """记录实际消耗。"""
        for level in [BudgetLevel.SESSION.value, BudgetLevel.DAILY.value, BudgetLevel.USER.value]:
            key = self._budget_key(user_id, session_id, level)
            entry = self._budgets.get(key)
            if entry is None:
                continue

            state = entry["state"]
            state.tokens_used += tokens_used
            state.cost_used += cost

    def status(self, user_id: str, session_id: str) -> dict[str, BudgetState]:
        """查询所有层级的预算状态。"""
        result = {}
        for level in [BudgetLevel.SESSION.value, BudgetLevel.DAILY.value, BudgetLevel.USER.value]:
            key = self._budget_key(user_id, session_id, level)
            entry = self._budgets.get(key)
            if entry is not None:
                result[level] = entry["state"]
        return result

    def reset(self, user_id: str, session_id: str = "", *, level: str = "") -> None:
        """重置预算。"""
        if level:
            key = self._budget_key(user_id, session_id, level)
            entry = self._budgets.get(key)
            if entry:
                entry["state"].tokens_used = 0
                entry["state"].cost_used = 0.0
                entry["state"].status = BudgetStatus.HEALTHY.value
        else:
            for level in [BudgetLevel.SESSION.value, BudgetLevel.DAILY.value, BudgetLevel.USER.value]:
                key = self._budget_key(user_id, session_id, level)
                self._budgets.pop(key, None)

    @staticmethod
    def _budget_key(user_id: str, session_id: str, level: str) -> str:
        if level == BudgetLevel.USER.value:
            return f"user:{user_id}"
        elif level == BudgetLevel.SESSION.value:
            return f"session:{session_id}"
        return f"daily:{user_id}:{time.strftime('%Y-%m-%d')}"
