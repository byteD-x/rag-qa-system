#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 评估模块

集成 RAGAS 评估框架，提供离线评估和 A/B 测试能力。
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


@dataclass
class EvaluationSample:
    """评估样本"""
    question: str
    answer: str
    contexts: List[str]
    ground_truth: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class EvaluationMetrics:
    """评估指标"""
    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevancy: float
    overall_score: float


@dataclass
class EvaluationResult:
    """单次评估结果"""
    sample_id: str
    question: str
    answer: str
    contexts: List[str]
    ground_truth: str
    metrics: EvaluationMetrics
    metadata: Dict = field(default_factory=dict)


@dataclass
class BatchEvaluationResult:
    """批量评估结果"""
    run_id: str
    total_samples: int
    successful_samples: int
    failed_samples: int
    avg_metrics: Dict[str, float]
    individual_results: List[EvaluationResult]
    timestamp: str


@dataclass
class ABTestResult:
    """A/B 测试结果"""
    test_id: str
    config_a_name: str
    config_b_name: str
    metrics_comparison: Dict[str, Dict[str, float]]
    winner: str
    statistical_significance: Dict[str, bool]
    timestamp: str


class RAGEvaluator:
    """RAG 评估器"""

    def __init__(self, ragas_api_key: Optional[str] = None):
        """
        初始化 RAG 评估器

        Args:
            ragas_api_key: RAGAS API 密钥（可选，用于云端评估）
        """
        self._ragas_api_key = ragas_api_key
        self._metrics = {}
        self._initialized = False

    def _init_ragas_metrics(self):
        """初始化 RAGAS 指标"""
        if self._initialized:
            return

        try:
            from ragas import evaluate
            from ragas.metrics import (
                context_precision,
                context_recall,
                faithfulness,
                answer_relevancy,
            )

            self._metrics = {
                "context_precision": context_precision,
                "context_recall": context_recall,
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
            }
            self._initialized = True
        except ImportError as e:
            raise ImportError(
                "RAGAS is not installed. Please install it with: pip install ragas"
            ) from e

    def evaluate_sample(
        self,
        sample: EvaluationSample,
    ) -> EvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本

        Returns:
            评估结果
        """
        self._init_ragas_metrics()

        try:
            from datasets import Dataset

            dataset = Dataset.from_dict({
                "question": [sample.question],
                "answer": [sample.answer],
                "contexts": [[sample.contexts]],
                "ground_truth": [[sample.ground_truth]],
            })

            result = evaluate(
                dataset,
                metrics=list(self._metrics.values()),
            )

            scores = result.to_pandas().iloc[0]

            metrics = EvaluationMetrics(
                context_precision=float(scores["context_precision"]),
                context_recall=float(scores["context_recall"]),
                faithfulness=float(scores["faithfulness"]),
                answer_relevancy=float(scores["answer_relevancy"]),
                overall_score=float(scores.mean()),
            )

            return EvaluationResult(
                sample_id=str(uuid4()),
                question=sample.question,
                answer=sample.answer,
                contexts=sample.contexts,
                ground_truth=sample.ground_truth,
                metrics=metrics,
                metadata=sample.metadata,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to evaluate sample: {e}") from e

    def evaluate_batch(
        self,
        samples: List[EvaluationSample],
    ) -> BatchEvaluationResult:
        """
        批量评估

        Args:
            samples: 评估样本列表

        Returns:
            批量评估结果
        """
        self._init_ragas_metrics()

        try:
            from datasets import Dataset

            questions = []
            answers = []
            contexts_list = []
            ground_truths = []

            for sample in samples:
                questions.append(sample.question)
                answers.append(sample.answer)
                contexts_list.append([sample.contexts])
                ground_truths.append([sample.ground_truth])

            dataset = Dataset.from_dict({
                "question": questions,
                "answer": answers,
                "contexts": contexts_list,
                "ground_truth": ground_truths,
            })

            result = evaluate(
                dataset,
                metrics=list(self._metrics.values()),
            )

            df = result.to_pandas()

            individual_results = []
            for idx in range(len(df)):
                row = df.iloc[idx]
                metrics = EvaluationMetrics(
                    context_precision=float(row["context_precision"]),
                    context_recall=float(row["context_recall"]),
                    faithfulness=float(row["faithfulness"]),
                    answer_relevancy=float(row["answer_relevancy"]),
                    overall_score=float(row[["context_precision", "context_recall", "faithfulness", "answer_relevancy"]].mean()),
                )

                individual_results.append(
                    EvaluationResult(
                        sample_id=str(uuid4()),
                        question=samples[idx].question,
                        answer=samples[idx].answer,
                        contexts=samples[idx].contexts,
                        ground_truth=samples[idx].ground_truth,
                        metrics=metrics,
                        metadata=samples[idx].metadata,
                    )
                )

            avg_metrics = {
                "context_precision": float(df["context_precision"].mean()),
                "context_recall": float(df["context_recall"].mean()),
                "faithfulness": float(df["faithfulness"].mean()),
                "answer_relevancy": float(df["answer_relevancy"].mean()),
                "overall_score": float(df[["context_precision", "context_recall", "faithfulness", "answer_relevancy"]].mean().mean()),
            }

            return BatchEvaluationResult(
                run_id=str(uuid4()),
                total_samples=len(samples),
                successful_samples=len(individual_results),
                failed_samples=0,
                avg_metrics=avg_metrics,
                individual_results=individual_results,
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            raise RuntimeError(f"Failed to evaluate batch: {e}") from e

    def ab_test(
        self,
        samples_a: List[EvaluationSample],
        samples_b: List[EvaluationSample],
        config_a_name: str = "Config A",
        config_b_name: str = "Config B",
    ) -> ABTestResult:
        """
        A/B 测试

        Args:
            samples_a: 配置 A 的评估样本
            samples_b: 配置 B 的评估样本
            config_a_name: 配置 A 名称
            config_b_name: 配置 B 名称

        Returns:
            A/B 测试结果
        """
        result_a = self.evaluate_batch(samples_a)
        result_b = self.evaluate_batch(samples_b)

        metrics_comparison = {}
        winner_metrics = {}
        statistical_significance = {}

        for metric_name in ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]:
            mean_a = result_a.avg_metrics[metric_name]
            mean_b = result_b.avg_metrics[metric_name]

            std_a = statistics.stdev(
                [r.metrics.__dict__[metric_name] for r in result_a.individual_results]
            ) if len(result_a.individual_results) > 1 else 0.0

            std_b = statistics.stdev(
                [r.metrics.__dict__[metric_name] for r in result_b.individual_results]
            ) if len(result_b.individual_results) > 1 else 0.0

            metrics_comparison[metric_name] = {
                "config_a": mean_a,
                "config_b": mean_b,
                "diff": mean_b - mean_a,
                "diff_percent": ((mean_b - mean_a) / mean_a * 100) if mean_a > 0 else 0.0,
            }

            winner_metrics[metric_name] = config_b_name if mean_b > mean_a else config_a_name

            if std_a > 0 and std_b > 0:
                z_score = abs(mean_b - mean_a) / ((std_a**2 / len(samples_a) + std_b**2 / len(samples_b)) ** 0.5)
                statistical_significance[metric_name] = z_score > 1.96
            else:
                statistical_significance[metric_name] = False

        winner_count = sum(1 for v in winner_metrics.values() if v == config_b_name)
        winner = config_b_name if winner_count > 2 else config_a_name

        return ABTestResult(
            test_id=str(uuid4()),
            config_a_name=config_a_name,
            config_b_name=config_b_name,
            metrics_comparison=metrics_comparison,
            winner=winner,
            statistical_significance=statistical_significance,
            timestamp=datetime.now().isoformat(),
        )

    def create_evaluation_dataset(
        self,
        samples: List[EvaluationSample],
        output_path: str,
    ) -> str:
        """
        创建评估数据集

        Args:
            samples: 评估样本列表
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        dataset = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "samples": [
                {
                    "question": sample.question,
                    "answer": sample.answer,
                    "contexts": sample.contexts,
                    "ground_truth": sample.ground_truth,
                    "metadata": sample.metadata,
                }
                for sample in samples
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)

        return output_path

    def load_evaluation_dataset(
        self,
        dataset_path: str,
    ) -> List[EvaluationSample]:
        """
        加载评估数据集

        Args:
            dataset_path: 数据集文件路径

        Returns:
            评估样本列表
        """
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        samples = []
        for item in dataset.get("samples", []):
            samples.append(
                EvaluationSample(
                    question=item["question"],
                    answer=item["answer"],
                    contexts=item["contexts"],
                    ground_truth=item["ground_truth"],
                    metadata=item.get("metadata", {}),
                )
            )

        return samples

    def generate_report(
        self,
        result: BatchEvaluationResult,
        output_path: str = "evaluation_report.json",
    ) -> str:
        """
        生成评估报告

        Args:
            result: 批量评估结果
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        report = {
            "report_id": str(uuid4()),
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_samples": result.total_samples,
                "successful_samples": result.successful_samples,
                "failed_samples": result.failed_samples,
                "success_rate": result.successful_samples / result.total_samples if result.total_samples > 0 else 0.0,
            },
            "metrics": {
                "averages": result.avg_metrics,
                "details": {
                    metric_name: self._calculate_metric_stats(result, metric_name)
                    for metric_name in ["context_precision", "context_recall", "faithfulness", "answer_relevancy", "overall_score"]
                },
            },
            "individual_results": [
                {
                    "sample_id": r.sample_id,
                    "question": r.question,
                    "metrics": {
                        "context_precision": r.metrics.context_precision,
                        "context_recall": r.metrics.context_recall,
                        "faithfulness": r.metrics.faithfulness,
                        "answer_relevancy": r.metrics.answer_relevancy,
                        "overall_score": r.metrics.overall_score,
                    },
                }
                for r in result.individual_results
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return output_path

    def _calculate_metric_stats(
        self,
        result: BatchEvaluationResult,
        metric_name: str,
    ) -> Dict[str, float]:
        """计算指标统计信息"""
        values = []
        for r in result.individual_results:
            if metric_name == "overall_score":
                values.append(r.metrics.overall_score)
            else:
                values.append(getattr(r.metrics, metric_name))

        if not values:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "median": 0.0}

        return {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            "median": statistics.median(values),
        }


_evaluator: Optional[RAGEvaluator] = None


def get_evaluator(ragas_api_key: Optional[str] = None) -> RAGEvaluator:
    """获取全局评估器实例"""
    global _evaluator
    if _evaluator is None:
        _evaluator = RAGEvaluator(ragas_api_key)
    return _evaluator


def evaluate_sample(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: str,
) -> EvaluationResult:
    """评估单个样本"""
    sample = EvaluationSample(
        question=question,
        answer=answer,
        contexts=contexts,
        ground_truth=ground_truth,
    )
    return get_evaluator().evaluate_sample(sample)


def evaluate_batch(
    samples: List[Dict[str, Any]],
) -> BatchEvaluationResult:
    """批量评估"""
    evaluation_samples = [
        EvaluationSample(
            question=sample["question"],
            answer=sample["answer"],
            contexts=sample["contexts"],
            ground_truth=sample["ground_truth"],
            metadata=sample.get("metadata", {}),
        )
        for sample in samples
    ]
    return get_evaluator().evaluate_batch(evaluation_samples)


def generate_evaluation_report(
    result: BatchEvaluationResult,
    output_path: str = "evaluation_report.json",
) -> str:
    """生成评估报告"""
    return get_evaluator().generate_report(result, output_path)


if __name__ == "__main__":
    print("=" * 70)
    print("RAG 评估器测试")
    print("=" * 70)

    evaluator = RAGEvaluator()

    test_samples = [
        EvaluationSample(
            question="如何使用 Python 读取文件？",
            answer="使用 open() 函数可以读取文件。例如：with open('file.txt', 'r') as f: content = f.read()",
            contexts=[
                "Python 提供了多种文件操作方法，最常用的是 open() 函数。",
                "open() 函数支持多种模式，包括读取 ('r')、写入 ('w') 和追加 ('a')。",
                "使用 with 语句可以自动管理文件资源，无需手动关闭。",
            ],
            ground_truth="使用 open() 函数读取文件，推荐使用 with 语句自动管理资源。",
        ),
        EvaluationSample(
            question="Docker 是什么？",
            answer="Docker 是一个容器化平台，可以将应用及其依赖打包到容器中运行。",
            contexts=[
                "Docker 是一个开源的容器化平台。",
                "容器技术可以实现应用的隔离和便携性。",
                "Docker 容器可以在任何支持 Docker 的环境中运行。",
            ],
            ground_truth="Docker 是一个开源的容器化平台，用于打包和部署应用。",
        ),
    ]

    print("\n创建评估数据集...")
    dataset_path = evaluator.create_evaluation_dataset(
        test_samples,
        "test_evaluation_dataset.json"
    )
    print(f"数据集已保存至：{dataset_path}")

    print("\n加载评估数据集...")
    loaded_samples = evaluator.load_evaluation_dataset(dataset_path)
    print(f"加载了 {len(loaded_samples)} 个样本")

    print("\n批量评估（需要 RAGAS 安装）...")
    try:
        result = evaluator.evaluate_batch(loaded_samples)
        print(f"总样本数：{result.total_samples}")
        print(f"成功样本数：{result.successful_samples}")
        print(f"平均指标:")
        for metric_name, value in result.avg_metrics.items():
            print(f"  {metric_name}: {value:.4f}")

        print("\n生成评估报告...")
        report_path = evaluator.generate_report(result, "test_evaluation_report.json")
        print(f"报告已保存至：{report_path}")

    except ImportError as e:
        print(f"跳过评估测试（RAGAS 未安装）: {e}")
        print("\n提示：安装 RAGAS 后运行完整测试：pip install ragas")
