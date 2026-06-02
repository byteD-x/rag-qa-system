"""多维成本归因引擎。

核心能力：
- 按用户/场景/模型/知识库/日期等多维拆分 LLM 成本
- 成本趋势分析（日/周/月）
- 成本优化建议（识别高成本场景、低效调用）
- 归因数据导出

使用方式::

    from .cost_attribution import CostAttributionEngine

    engine = CostAttributionEngine()
    engine.record(user_id="u1", model="gpt-4", tokens=1000, scene="enterprise_qa")
    report = engine.report(dimension="model", period="7d")
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
class CostRecord:
    """单次调用成本记录。"""
    user_id: str = ""
    session_id: str = ""
    model: str = ""
    scene: str = ""              # 场景：enterprise_qa / tech_support / ...
    execution_mode: str = ""     # grounded / agent
    knowledge_bases: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class AttributionSlice:
    """单个维度切片的归因数据。"""
    key: str = ""                # 维度值（如 "gpt-4"、"用户A"）
    total_cost: float = 0.0
    total_tokens: int = 0
    call_count: int = 0
    avg_cost_per_call: float = 0.0
    avg_latency_ms: float = 0.0
    cached_count: int = 0
    cache_hit_rate: float = 0.0
    cost_percentage: float = 0.0  # 占总成本的百分比


@dataclass
class AttributionReport:
    """归因报告。"""
    dimension: str = ""           # 归因维度
    period: str = ""              # 时间范围
    total_cost: float = 0.0
    total_tokens: int = 0
    total_calls: int = 0
    slices: list[AttributionSlice] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)  # 按日趋势
    generated_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# 成本归因引擎
# ---------------------------------------------------------------------------


class CostAttributionEngine:
    """多维成本归因引擎。"""

    MAX_RECORDS = 100_000  # 最多保存的记录数

    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    def record(
        self,
        *,
        user_id: str = "",
        session_id: str = "",
        model: str = "",
        scene: str = "",
        execution_mode: str = "grounded",
        knowledge_bases: list[str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
        latency_ms: float = 0.0,
        cached: bool = False,
    ) -> None:
        """记录一次调用的成本数据。"""
        record = CostRecord(
            user_id=user_id,
            session_id=session_id,
            model=model,
            scene=scene,
            execution_mode=execution_mode,
            knowledge_bases=knowledge_bases or [],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
            cached=cached,
        )
        self._records.append(record)

        # 超过上限时清理旧记录
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[-self.MAX_RECORDS // 2:]

    def report(
        self,
        dimension: str = "model",
        *,
        period: str = "7d",
        top_n: int = 10,
    ) -> AttributionReport:
        """生成归因报告。

        参数:
            dimension: 归因维度 (model / user / scene / execution_mode / kb)
            period: 时间范围 (1d / 7d / 30d / 90d / all)
            top_n: 返回 Top-N 切片

        返回:
            AttributionReport
        """
        period_seconds = self._parse_period(period)
        cutoff = time.time() - period_seconds if period_seconds > 0 else 0
        filtered = [r for r in self._records if r.timestamp >= cutoff]

        if not filtered:
            return AttributionReport(dimension=dimension, period=period)

        # 按维度聚合
        slices: dict[str, AttributionSlice] = {}
        total_cost = 0.0
        total_tokens = 0

        for r in filtered:
            key = self._extract_key(r, dimension)
            if key not in slices:
                slices[key] = AttributionSlice(key=key)

            s = slices[key]
            s.total_cost += r.estimated_cost
            s.total_tokens += r.input_tokens + r.output_tokens
            s.call_count += 1
            s.avg_latency_ms = (s.avg_latency_ms * (s.call_count - 1) + r.latency_ms) / s.call_count
            if r.cached:
                s.cached_count += 1

            total_cost += r.estimated_cost
            total_tokens += r.input_tokens + r.output_tokens

        # 计算占比和均值
        for s in slices.values():
            s.avg_cost_per_call = round(s.total_cost / max(s.call_count, 1), 6)
            s.cache_hit_rate = round(s.cached_count / max(s.call_count, 1), 4)
            s.cost_percentage = round(s.total_cost / max(total_cost, 0.0001) * 100, 2)

        # 按成本排序取 Top-N
        sorted_slices = sorted(slices.values(), key=lambda s: s.total_cost, reverse=True)[:top_n]

        # 趋势（按日聚合）
        trend = self._daily_trend(filtered)

        return AttributionReport(
            dimension=dimension,
            period=period,
            total_cost=round(total_cost, 6),
            total_tokens=total_tokens,
            total_calls=len(filtered),
            slices=sorted_slices,
            trend=trend,
        )

    def optimization_suggestions(self) -> list[dict[str, Any]]:
        """生成成本优化建议。"""
        suggestions = []

        if not self._records:
            return suggestions

        # 1. 缓存命中率分析
        total = len(self._records)
        cached = sum(1 for r in self._records if r.cached)
        cache_rate = cached / max(total, 1)

        if cache_rate < 0.2 and total > 50:
            suggestions.append({
                "type": "cache_optimization",
                "severity": "medium",
                "message": f"缓存命中率仅 {cache_rate:.1%}，建议启用语义缓存或增加 TTL",
                "potential_savings_pct": round((1 - cache_rate) * 30, 1),
            })

        # 2. 高成本场景
        scene_costs = defaultdict(float)
        for r in self._records:
            scene_costs[r.scene or "unknown"] += r.estimated_cost

        for scene, cost in sorted(scene_costs.items(), key=lambda x: x[1], reverse=True)[:3]:
            if cost > 5.0:
                suggestions.append({
                    "type": "high_cost_scene",
                    "severity": "high" if cost > 20 else "medium",
                    "message": f"场景 '{scene}' 累计成本 ¥{cost:.2f}，考虑使用更经济的模型",
                    "potential_savings_pct": 25,
                })

        # 3. 低效模型使用
        model_stats = defaultdict(lambda: {"count": 0, "tokens": 0, "cost": 0.0})
        for r in self._records:
            ms = model_stats[r.model or "unknown"]
            ms["count"] += 1
            ms["tokens"] += r.input_tokens + r.output_tokens
            ms["cost"] += r.estimated_cost

        for model, stats in model_stats.items():
            if stats["tokens"] > 0:
                avg_cost_per_1k = (stats["cost"] / stats["tokens"]) * 1000
                if avg_cost_per_1k > 0.05:
                    suggestions.append({
                        "type": "expensive_model",
                        "severity": "medium",
                        "message": f"模型 '{model}' 平均成本 ¥{avg_cost_per_1k:.4f}/1k tokens，评估是否可替换为更低成本方案",
                    })

        return suggestions

    def export(self, dimension: str = "model", period: str = "30d") -> list[dict[str, Any]]:
        """导出归因数据（用于前端图表）。"""
        report = self.report(dimension=dimension, period=period)
        return [
            {
                "key": s.key,
                "total_cost": s.total_cost,
                "total_tokens": s.total_tokens,
                "call_count": s.call_count,
                "avg_cost_per_call": s.avg_cost_per_call,
                "cost_percentage": s.cost_percentage,
            }
            for s in report.slices
        ]

    # ---- 内部 ----

    @staticmethod
    def _extract_key(record: CostRecord, dimension: str) -> str:
        mapping = {
            "model": record.model or "unknown",
            "user": record.user_id or "anonymous",
            "scene": record.scene or "unknown",
            "execution_mode": record.execution_mode or "grounded",
            "kb": record.knowledge_bases[0] if record.knowledge_bases else "no_kb",
        }
        return mapping.get(dimension, "unknown")

    @staticmethod
    def _parse_period(period: str) -> float:
        periods = {
            "1d": 86400,
            "7d": 7 * 86400,
            "30d": 30 * 86400,
            "90d": 90 * 86400,
        }
        return periods.get(period, -1)

    def _daily_trend(self, records: list[CostRecord]) -> list[dict[str, Any]]:
        """按日聚合成本趋势。"""
        daily: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0, "calls": 0, "tokens": 0})
        for r in records:
            day = time.strftime("%Y-%m-%d", time.localtime(r.timestamp))
            daily[day]["cost"] += r.estimated_cost
            daily[day]["calls"] += 1
            daily[day]["tokens"] += r.input_tokens + r.output_tokens

        return [
            {"date": day, **{k: round(v, 4) if isinstance(v, float) else v for k, v in stats.items()}}
            for day, stats in sorted(daily.items())
        ]


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

cost_attribution = CostAttributionEngine()
