"""模型健康监控 —— 实时追踪各模型性能，驱动智能路由决策。

核心能力：
- 实时延迟追踪（P50/P95/P99）
- 错误率统计（按错误类型分类）
- 滑动窗口健康评分（0-1）
- 自动熔断（连续失败超过阈值时摘除）
- 动态权重调整（健康模型权重更高）

集成方式::

    from .model_health import ModelHealthMonitor

    monitor = ModelHealthMonitor()
    monitor.record_success("qwen-plus", latency_ms=350, tokens=500)
    monitor.record_failure("gpt-4o", error_type="timeout")

    # 选择最佳模型
    best = monitor.pick_best(["qwen-turbo", "qwen-plus", "gpt-4o"], prefer="cost")
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ModelStats:
    """单个模型的运行时统计"""

    model_name: str
    route_key: str = ""

    # 调用统计
    total_calls: int = 0
    total_success: int = 0
    total_failures: int = 0

    # 延迟（毫秒）
    latency_samples: list[float] = field(default_factory=list)  # 滑动窗口
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0

    # 错误分类
    error_counts: dict[str, int] = field(default_factory=dict)

    # 健康评分 0-1（越高越好）
    health_score: float = 1.0

    # 熔断
    circuit_open: bool = False
    circuit_open_at: float = 0.0
    consecutive_failures: int = 0
    max_consecutive_failures: int = 5

    # Token 消耗
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost: float = 0.0

    # 最后活动时间
    last_success_at: float = 0.0
    last_failure_at: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.total_success / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return sum(self.latency_samples) / len(self.latency_samples)


# ---------------------------------------------------------------------------
# 模型健康监控
# ---------------------------------------------------------------------------


class ModelHealthMonitor:
    """全局模型健康监控器（单例模式）。

    自动记录每个模型的调用结果，实时计算健康评分。
    """

    def __init__(
        self,
        *,
        window_size: int = 100,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown: float = 30.0,
        health_decay_rate: float = 0.1,
    ) -> None:
        self._models: dict[str, ModelStats] = {}
        self._window_size = window_size
        self._circuit_threshold = circuit_breaker_threshold
        self._circuit_cooldown = circuit_breaker_cooldown
        self._decay_rate = health_decay_rate

    # ---- 记录 ---------------------------------------------------------------

    def record_success(
        self,
        model_name: str,
        *,
        latency_ms: float = 0.0,
        route_key: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """记录一次成功的模型调用。"""
        stats = self._get_or_create(model_name, route_key)
        stats.total_calls += 1
        stats.total_success += 1
        stats.consecutive_failures = 0
        stats.last_success_at = time.time()
        stats.total_input_tokens += input_tokens
        stats.total_output_tokens += output_tokens
        stats.estimated_cost += cost

        # 滑动窗口延迟
        if latency_ms > 0:
            stats.latency_samples.append(latency_ms)
            if len(stats.latency_samples) > self._window_size:
                stats.latency_samples.pop(0)
            self._recalc_latency_percentiles(stats)

        # 关闭熔断（如果之前开了）
        if stats.circuit_open:
            stats.circuit_open = False
            logger.info("model_circuit_closed model=%s", model_name)

        # 更新健康评分
        self._update_health(stats)

    def record_failure(
        self,
        model_name: str,
        *,
        error_type: str = "unknown",
        route_key: str = "",
    ) -> None:
        """记录一次失败的模型调用。"""
        stats = self._get_or_create(model_name, route_key)
        stats.total_calls += 1
        stats.total_failures += 1
        stats.consecutive_failures += 1
        stats.last_failure_at = time.time()
        stats.error_counts[error_type] = stats.error_counts.get(error_type, 0) + 1

        # 熔断检查
        if stats.consecutive_failures >= self._circuit_threshold:
            stats.circuit_open = True
            stats.circuit_open_at = time.time()
            logger.warning(
                "model_circuit_opened model=%s consecutive=%d",
                model_name,
                stats.consecutive_failures,
            )

        self._update_health(stats)

    # ---- 查询 ---------------------------------------------------------------

    def pick_best(
        self,
        candidates: list[str],
        *,
        prefer: str = "balanced",
        min_health: float = 0.5,
    ) -> str | None:
        """从候选模型中选择最佳模型。

        参数:
            candidates: 候选模型名列表
            prefer: 偏好策略 — "speed" / "cost" / "balanced" / "health"
            min_health: 最低健康评分，低于此分的模型被排除
        返回:
            最佳模型名，或 None（无可用模型）
        """
        available = []
        for name in candidates:
            stats = self._models.get(name)
            if stats is None:
                # 无历史数据，视为可用
                available.append((name, 1.0, 0.0, 0.0))
                continue
            if stats.circuit_open:
                if time.time() - stats.circuit_open_at < self._circuit_cooldown:
                    continue
                # 冷却期过，尝试恢复
                stats.circuit_open = False
            if stats.health_score < min_health:
                continue
            available.append((name, stats.health_score, stats.avg_latency_ms, stats.estimated_cost))

        if not available:
            return None

        if prefer == "speed":
            available.sort(key=lambda x: x[2])  # 延迟最低
        elif prefer == "cost":
            available.sort(key=lambda x: x[3])  # 成本最低
        elif prefer == "health":
            available.sort(key=lambda x: x[1], reverse=True)  # 健康度最高
        else:  # balanced
            # 综合评分：健康度 * 0.4 + 延迟倒数归一化 * 0.3 + 成本倒数归一化 * 0.3
            max_lat = max((a[2] for a in available), default=1)
            max_cost = max((a[3] for a in available), default=1)
            available.sort(
                key=lambda x: (
                    x[1] * 0.4
                    + (1 - x[2] / max(max_lat, 1)) * 0.3
                    + (1 - x[3] / max(max_cost, 1)) * 0.3
                ),
                reverse=True,
            )

        return available[0][0] if available else None

    def get_stats(self, model_name: str) -> ModelStats | None:
        """获取指定模型的统计数据。"""
        return self._models.get(model_name)

    def all_stats(self) -> dict[str, ModelStats]:
        """获取所有模型的统计数据。"""
        return dict(self._models)

    def summary(self) -> dict[str, Any]:
        """获取全局健康摘要。"""
        models_summary = {}
        for name, stats in self._models.items():
            models_summary[name] = {
                "health_score": round(stats.health_score, 3),
                "success_rate": round(stats.success_rate, 3),
                "total_calls": stats.total_calls,
                "p50_ms": round(stats.latency_p50, 1),
                "p95_ms": round(stats.latency_p95, 1),
                "avg_latency_ms": round(stats.avg_latency_ms, 1),
                "circuit_open": stats.circuit_open,
                "consecutive_failures": stats.consecutive_failures,
                "estimated_cost": round(stats.estimated_cost, 6),
            }
        return {
            "models": models_summary,
            "total_models": len(self._models),
            "healthy_models": sum(
                1 for s in self._models.values() if s.health_score >= 0.5 and not s.circuit_open
            ),
            "circuit_open_models": sum(1 for s in self._models.values() if s.circuit_open),
        }

    # ---- 内部 ---------------------------------------------------------------

    def _get_or_create(self, model_name: str, route_key: str) -> ModelStats:
        if model_name not in self._models:
            self._models[model_name] = ModelStats(model_name=model_name, route_key=route_key)
        return self._models[model_name]

    def _recalc_latency_percentiles(self, stats: ModelStats) -> None:
        """重新计算延迟百分位。"""
        if not stats.latency_samples:
            return
        sorted_lat = sorted(stats.latency_samples)
        n = len(sorted_lat)
        stats.latency_p50 = sorted_lat[int(n * 0.5)] if n > 0 else 0
        stats.latency_p95 = sorted_lat[min(int(n * 0.95), n - 1)] if n > 1 else sorted_lat[0]
        stats.latency_p99 = sorted_lat[min(int(n * 0.99), n - 1)] if n > 1 else sorted_lat[0]

    def _update_health(self, stats: ModelStats) -> None:
        """更新健康评分（指数移动平均）。"""
        # 基础分：成功率
        success_score = stats.success_rate

        # 惩罚：连续失败
        failure_penalty = min(stats.consecutive_failures * 0.15, 0.75)

        # 惩罚：高错误率
        error_rate = stats.total_failures / max(stats.total_calls, 1)
        error_penalty = error_rate * 0.5

        raw_score = max(0.0, success_score - failure_penalty - error_penalty)

        # 指数移动平均平滑
        stats.health_score = stats.health_score * (1 - self._decay_rate) + raw_score * self._decay_rate
        stats.health_score = round(max(0.0, min(1.0, stats.health_score)), 4)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

model_health_monitor = ModelHealthMonitor()
