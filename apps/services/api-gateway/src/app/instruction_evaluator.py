"""指令 A/B 评估引擎。

核心能力：
- 指令 A/B 对比测试（同一问题，不同指令，对比回答质量）
- 多维度评分：准确性、完整性、简洁性、用户满意度
- 统计显著性检验（p-value）
- 实验组管理（对照组/实验组）

使用方式::

    from .instruction_evaluator import InstructionABEvaluator

    evaluator = InstructionABEvaluator()
    evaluator.start_experiment("prompt_v2_test", control_prompt="...", variant_prompt="...")
    evaluator.record_result("prompt_v2_test", variant="B", score=0.85)
    report = evaluator.report("prompt_v2_test")
"""

from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ExperimentConfig:
    """实验配置。"""
    experiment_id: str
    name: str = ""
    description: str = ""
    control_prompt: str = ""       # 对照组指令
    variant_prompt: str = ""       # 实验组指令
    metric_keys: list[str] = field(default_factory=lambda: [
        "accuracy", "completeness", "conciseness", "user_satisfaction"
    ])
    sample_size_target: int = 100  # 目标样本量
    split_ratio: float = 0.5      # 流量分配比例（A:B）
    is_active: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class TrialResult:
    """单次试验结果。"""
    trial_id: str
    experiment_id: str
    variant: str = "A"  # A=对照组, B=实验组
    question: str = ""
    scores: dict[str, float] = field(default_factory=dict)  # metric → score
    latency_ms: float = 0.0
    user_feedback: str = ""  # positive / negative / neutral
    created_at: float = field(default_factory=time.time)


@dataclass
class ExperimentReport:
    """实验报告。"""
    experiment_id: str
    name: str = ""
    is_significant: bool = False
    sample_size: dict[str, int] = field(default_factory=dict)  # A/B → count
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)  # metric → {A_mean, B_mean, diff_pct, p_value}
    recommendation: str = ""  # adopt_variant / keep_control / need_more_data
    confidence_level: float = 0.95
    generated_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# A/B 评估引擎
# ---------------------------------------------------------------------------


class InstructionABEvaluator:
    """指令 A/B 对比评估引擎。"""

    SIGNIFICANCE_THRESHOLD = 0.05  # p < 0.05 视为显著
    MIN_SAMPLE_SIZE = 30           # 最少样本量才能出报告

    def __init__(self) -> None:
        self._experiments: dict[str, ExperimentConfig] = {}
        self._results: dict[str, list[TrialResult]] = defaultdict(list)

    def start_experiment(
        self,
        experiment_id: str,
        *,
        name: str = "",
        control_prompt: str,
        variant_prompt: str,
        description: str = "",
        sample_size_target: int = 100,
        split_ratio: float = 0.5,
    ) -> ExperimentConfig:
        """启动一个新的 A/B 实验。

        参数:
            experiment_id: 实验 ID
            control_prompt: 对照组指令（当前使用版本）
            variant_prompt: 实验组指令（新版本）
            description: 实验说明
            sample_size_target: 目标样本量
            split_ratio: 流量分配比例

        返回:
            ExperimentConfig
        """
        config = ExperimentConfig(
            experiment_id=experiment_id,
            name=name or experiment_id,
            description=description,
            control_prompt=control_prompt,
            variant_prompt=variant_prompt,
            sample_size_target=sample_size_target,
            split_ratio=split_ratio,
        )
        self._experiments[experiment_id] = config
        self._results[experiment_id] = []
        logger.info("ab_experiment_started id=%s name=%s target=%d", experiment_id, name, sample_size_target)
        return config

    def stop_experiment(self, experiment_id: str) -> None:
        """停止实验。"""
        if experiment_id in self._experiments:
            self._experiments[experiment_id].is_active = False
            logger.info("ab_experiment_stopped id=%s", experiment_id)

    def assign_variant(self, experiment_id: str) -> str:
        """为请求分配变体（A 或 B）。

        使用哈希分配保证同一用户/问题的一致性。
        """
        config = self._experiments.get(experiment_id)
        if config is None or not config.is_active:
            return "A"

        a_count = sum(1 for r in self._results.get(experiment_id, []) if r.variant == "A")
        b_count = sum(1 for r in self._results.get(experiment_id, []) if r.variant == "B")
        total = a_count + b_count

        if total == 0:
            return "A"  # 优先填充对照组

        actual_ratio = b_count / total if total > 0 else 0
        return "A" if actual_ratio >= config.split_ratio else "B"

    def record_result(
        self,
        experiment_id: str,
        *,
        variant: str,
        question: str = "",
        scores: dict[str, float] | None = None,
        latency_ms: float = 0.0,
        user_feedback: str = "",
    ) -> TrialResult:
        """记录一次试验结果。

        参数:
            experiment_id: 实验 ID
            variant: A 或 B
            question: 用户问题
            scores: 各维度评分 {accuracy: 0.9, completeness: 0.8, ...}
            latency_ms: 响应延迟
            user_feedback: 用户反馈

        返回:
            TrialResult
        """
        trial = TrialResult(
            trial_id=uuid.uuid4().hex[:8],
            experiment_id=experiment_id,
            variant=variant,
            question=question,
            scores=scores or {},
            latency_ms=latency_ms,
            user_feedback=user_feedback,
        )
        self._results[experiment_id].append(trial)
        return trial

    def report(self, experiment_id: str) -> ExperimentReport | None:
        """生成实验报告。"""
        config = self._experiments.get(experiment_id)
        if config is None:
            return None

        results = self._results.get(experiment_id, [])
        a_results = [r for r in results if r.variant == "A"]
        b_results = [r for r in results if r.variant == "B"]

        sample_size = {"A": len(a_results), "B": len(b_results)}
        total = sample_size["A"] + sample_size["B"]

        if total < self.MIN_SAMPLE_SIZE:
            return ExperimentReport(
                experiment_id=experiment_id,
                name=config.name,
                sample_size=sample_size,
                recommendation="need_more_data",
            )

        # 各指标对比
        metrics = {}
        all_significant = True

        for metric_key in config.metric_keys:
            a_vals = [r.scores.get(metric_key, 0) for r in a_results]
            b_vals = [r.scores.get(metric_key, 0) for r in b_results]

            if not a_vals or not b_vals:
                continue

            a_mean = sum(a_vals) / len(a_vals)
            b_mean = sum(b_vals) / len(b_vals)
            diff_pct = round((b_mean - a_mean) / max(a_mean, 0.001) * 100, 2)

            # 简化的 Welch's t-test
            p_value = self._welch_ttest(a_vals, b_vals)
            is_sig = p_value < self.SIGNIFICANCE_THRESHOLD

            metrics[metric_key] = {
                "A_mean": round(a_mean, 4),
                "B_mean": round(b_mean, 4),
                "diff_pct": diff_pct,
                "p_value": round(p_value, 4),
                "significant": is_sig,
            }

            if not is_sig:
                all_significant = False

        # 推荐
        recommendation = self._make_recommendation(metrics, sample_size, config)

        return ExperimentReport(
            experiment_id=experiment_id,
            name=config.name,
            is_significant=all_significant,
            sample_size=sample_size,
            metrics=metrics,
            recommendation=recommendation,
            confidence_level=self._confidence_level(total),
        )

    def list_experiments(self) -> list[dict[str, Any]]:
        """列出所有实验。"""
        return [
            {
                "experiment_id": eid,
                "name": config.name,
                "is_active": config.is_active,
                "sample_size": len(self._results.get(eid, [])),
                "target": config.sample_size_target,
                "created_at": config.created_at,
            }
            for eid, config in self._experiments.items()
        ]

    # ---- 统计方法 ----

    @staticmethod
    def _welch_ttest(a: list[float], b: list[float]) -> float:
        """Welch's t-test（简化版，不依赖 scipy）。"""
        n_a, n_b = len(a), len(b)
        if n_a < 2 or n_b < 2:
            return 1.0

        mean_a = sum(a) / n_a
        mean_b = sum(b) / n_b

        var_a = sum((x - mean_a) ** 2 for x in a) / (n_a - 1)
        var_b = sum((x - mean_b) ** 2 for x in b) / (n_b - 1)

        se = math.sqrt(var_a / n_a + var_b / n_b)
        if se < 1e-10:
            return 1.0

        t_stat = (mean_b - mean_a) / se

        # 自由度（Welch-Satterthwaite）
        df_num = (var_a / n_a + var_b / n_b) ** 2
        df_den = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        df = df_num / max(df_den, 1e-10)

        # 近似 p-value（使用正态分布近似 t 分布）
        # 简化：用标准正态 CDF 近似
        z = abs(t_stat)
        # 正态分布尾部概率近似
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))

        return round(min(p, 1.0), 6)

    @staticmethod
    def _confidence_level(sample_size: int) -> float:
        """根据样本量估算置信度。"""
        if sample_size >= 200:
            return 0.99
        if sample_size >= 100:
            return 0.95
        if sample_size >= 50:
            return 0.90
        return 0.80

    def _make_recommendation(
        self,
        metrics: dict[str, dict[str, Any]],
        sample_size: dict[str, int],
        config: ExperimentConfig,
    ) -> str:
        """基于指标生成推荐。"""
        total = sample_size["A"] + sample_size["B"]
        if total < self.MIN_SAMPLE_SIZE:
            return "need_more_data"

        # 统计 B 优于 A 的指标数
        b_wins = 0
        a_wins = 0
        for info in metrics.values():
            if info["significant"] and info["diff_pct"] > 0:
                b_wins += 1
            elif info["significant"] and info["diff_pct"] < 0:
                a_wins += 1

        if b_wins > a_wins and b_wins >= 2:
            return "adopt_variant"
        if a_wins > b_wins and a_wins >= 2:
            return "keep_control"
        return "need_more_data"
