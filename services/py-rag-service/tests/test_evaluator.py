#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 评估器测试
"""

import pytest
import json
from pathlib import Path
from app.evaluator import (
    RAGEvaluator,
    EvaluationSample,
    EvaluationMetrics,
    EvaluationResult,
    BatchEvaluationResult,
    ABTestResult,
)


class TestEvaluationSample:
    """测试评估样本"""

    def test_create_sample(self):
        """测试创建评估样本"""
        sample = EvaluationSample(
            question="如何使用 Python？",
            answer="使用 Python 很简单",
            contexts=["上下文 1", "上下文 2"],
            ground_truth="Python 是一种编程语言",
        )

        assert sample.question == "如何使用 Python？"
        assert sample.answer == "使用 Python 很简单"
        assert len(sample.contexts) == 2
        assert sample.ground_truth == "Python 是一种编程语言"

    def test_sample_with_metadata(self):
        """测试带元数据的样本"""
        sample = EvaluationSample(
            question="测试问题",
            answer="测试答案",
            contexts=["上下文"],
            ground_truth="标准答案",
            metadata={"source": "test", "difficulty": "easy"},
        )

        assert sample.metadata["source"] == "test"
        assert sample.metadata["difficulty"] == "easy"


class TestEvaluationMetrics:
    """测试评估指标"""

    def test_create_metrics(self):
        """测试创建评估指标"""
        metrics = EvaluationMetrics(
            context_precision=0.85,
            context_recall=0.90,
            faithfulness=0.88,
            answer_relevancy=0.92,
            overall_score=0.89,
        )

        assert metrics.context_precision == 0.85
        assert metrics.context_recall == 0.90
        assert metrics.faithfulness == 0.88
        assert metrics.answer_relevancy == 0.92
        assert metrics.overall_score == 0.89

    def test_metrics_range(self):
        """测试指标范围"""
        metrics = EvaluationMetrics(
            context_precision=1.0,
            context_recall=0.0,
            faithfulness=0.5,
            answer_relevancy=0.75,
            overall_score=0.5625,
        )

        assert 0.0 <= metrics.context_precision <= 1.0
        assert 0.0 <= metrics.context_recall <= 1.0
        assert 0.0 <= metrics.faithfulness <= 1.0
        assert 0.0 <= metrics.answer_relevancy <= 1.0


class TestRAGEvaluator:
    """测试 RAG 评估器"""

    @pytest.fixture
    def evaluator(self):
        """创建评估器实例"""
        return RAGEvaluator()

    @pytest.fixture
    def sample(self):
        """创建测试样本"""
        return EvaluationSample(
            question="如何使用 Python 读取文件？",
            answer="使用 open() 函数可以读取文件",
            contexts=[
                "Python 提供了 open() 函数用于文件操作",
                "open() 函数支持读取和写入模式",
            ],
            ground_truth="使用 open() 函数读取文件",
        )

    def test_create_evaluator(self, evaluator):
        """测试创建评估器"""
        assert evaluator is not None

    def test_create_evaluation_dataset(self, evaluator, sample, tmp_path):
        """测试创建评估数据集"""
        output_path = tmp_path / "test_dataset.json"
        
        result_path = evaluator.create_evaluation_dataset(
            [sample],
            str(output_path),
        )

        assert Path(result_path).exists()
        
        with open(result_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        assert dataset["version"] == "1.0"
        assert "samples" in dataset
        assert len(dataset["samples"]) == 1
        assert dataset["samples"][0]["question"] == sample.question

    def test_load_evaluation_dataset(self, evaluator, sample, tmp_path):
        """测试加载评估数据集"""
        output_path = tmp_path / "test_dataset.json"
        evaluator.create_evaluation_dataset([sample], str(output_path))

        loaded_samples = evaluator.load_evaluation_dataset(str(output_path))

        assert len(loaded_samples) == 1
        assert loaded_samples[0].question == sample.question
        assert loaded_samples[0].answer == sample.answer

    def test_evaluate_sample_mock(self, evaluator, sample, monkeypatch):
        """测试评估单个样本（模拟）"""
        try:
            from ragas import evaluate as ragas_evaluate
        except ImportError:
            pytest.skip("RAGAS not installed")

        def mock_evaluate(dataset, metrics):
            class MockResult:
                def to_pandas(self):
                    import pandas as pd
                    return pd.DataFrame({
                        "context_precision": [0.85],
                        "context_recall": [0.90],
                        "faithfulness": [0.88],
                        "answer_relevancy": [0.92],
                    })
            return MockResult()

        monkeypatch.setattr("ragas.evaluate", mock_evaluate)

        result = evaluator.evaluate_sample(sample)
        
        assert result.question == sample.question
        assert result.answer == sample.answer
        assert isinstance(result.metrics, EvaluationMetrics)
        assert 0.0 <= result.metrics.context_precision <= 1.0
        assert 0.0 <= result.metrics.context_recall <= 1.0
        assert 0.0 <= result.metrics.faithfulness <= 1.0
        assert 0.0 <= result.metrics.answer_relevancy <= 1.0

    def test_evaluate_batch_mock(self, evaluator, sample, monkeypatch):
        """测试批量评估（模拟）"""
        try:
            from ragas import evaluate as ragas_evaluate
        except ImportError:
            pytest.skip("RAGAS not installed")

        def mock_evaluate(dataset, metrics):
            class MockResult:
                def to_pandas(self):
                    import pandas as pd
                    return pd.DataFrame({
                        "context_precision": [0.85, 0.80],
                        "context_recall": [0.90, 0.88],
                        "faithfulness": [0.88, 0.85],
                        "answer_relevancy": [0.92, 0.90],
                    })
            return MockResult()

        monkeypatch.setattr("ragas.evaluate", mock_evaluate)

        samples = [sample, sample]
        result = evaluator.evaluate_batch(samples)

        assert result.total_samples == 2
        assert result.successful_samples == 2
        assert result.failed_samples == 0
        assert isinstance(result.avg_metrics, dict)
        assert "context_precision" in result.avg_metrics
        assert "context_recall" in result.avg_metrics
        assert "faithfulness" in result.avg_metrics
        assert "answer_relevancy" in result.avg_metrics

    def test_ab_test_mock(self, evaluator, sample, monkeypatch):
        """测试 A/B 测试（模拟）"""
        try:
            from ragas import evaluate as ragas_evaluate
        except ImportError:
            pytest.skip("RAGAS not installed")

        def mock_evaluate(dataset, metrics):
            class MockResult:
                def to_pandas(self):
                    import pandas as pd
                    return pd.DataFrame({
                        "context_precision": [0.85, 0.80],
                        "context_recall": [0.90, 0.88],
                        "faithfulness": [0.88, 0.85],
                        "answer_relevancy": [0.92, 0.90],
                    })
            return MockResult()

        monkeypatch.setattr("ragas.evaluate", mock_evaluate)

        samples_a = [sample, sample]
        samples_b = [sample, sample]
        
        result = evaluator.ab_test(
            samples_a,
            samples_b,
            config_a_name="Config A",
            config_b_name="Config B",
        )

        assert isinstance(result, ABTestResult)
        assert result.config_a_name == "Config A"
        assert result.config_b_name == "Config B"
        assert result.winner in ["Config A", "Config B"]
        assert "context_precision" in result.metrics_comparison
        assert "context_recall" in result.metrics_comparison
        assert "faithfulness" in result.metrics_comparison
        assert "answer_relevancy" in result.metrics_comparison

    def test_generate_report(self, evaluator, sample, tmp_path, monkeypatch):
        """测试生成评估报告"""
        try:
            from ragas import evaluate as ragas_evaluate
        except ImportError:
            pytest.skip("RAGAS not installed")

        def mock_evaluate(dataset, metrics):
            class MockResult:
                def to_pandas(self):
                    import pandas as pd
                    return pd.DataFrame({
                        "context_precision": [0.85],
                        "context_recall": [0.90],
                        "faithfulness": [0.88],
                        "answer_relevancy": [0.92],
                    })
            return MockResult()

        monkeypatch.setattr("ragas.evaluate", mock_evaluate)

        result = evaluator.evaluate_batch([sample])
        output_path = tmp_path / "test_report.json"
        
        report_path = evaluator.generate_report(result, str(output_path))

        assert Path(report_path).exists()

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        assert "summary" in report
        assert "metrics" in report
        assert "individual_results" in report
        assert report["summary"]["total_samples"] == 1
        assert report["summary"]["successful_samples"] == 1


class TestEvaluationResult:
    """测试评估结果"""

    def test_create_result(self):
        """测试创建评估结果"""
        metrics = EvaluationMetrics(
            context_precision=0.85,
            context_recall=0.90,
            faithfulness=0.88,
            answer_relevancy=0.92,
            overall_score=0.89,
        )

        result = EvaluationResult(
            sample_id="test-123",
            question="测试问题",
            answer="测试答案",
            contexts=["上下文 1"],
            ground_truth="标准答案",
            metrics=metrics,
        )

        assert result.sample_id == "test-123"
        assert result.question == "测试问题"
        assert result.metrics.overall_score == 0.89


class TestBatchEvaluationResult:
    """测试批量评估结果"""

    def test_create_batch_result(self):
        """测试创建批量评估结果"""
        result = BatchEvaluationResult(
            run_id="run-123",
            total_samples=10,
            successful_samples=9,
            failed_samples=1,
            avg_metrics={
                "context_precision": 0.85,
                "context_recall": 0.90,
                "faithfulness": 0.88,
                "answer_relevancy": 0.92,
                "overall_score": 0.89,
            },
            individual_results=[],
            timestamp="2026-03-05T10:00:00",
        )

        assert result.run_id == "run-123"
        assert result.total_samples == 10
        assert result.successful_samples == 9
        assert result.failed_samples == 1
        assert result.avg_metrics["overall_score"] == 0.89


class TestABTestResult:
    """测试 A/B 测试结果"""

    def test_create_ab_result(self):
        """测试创建 A/B 测试结果"""
        result = ABTestResult(
            test_id="ab-123",
            config_a_name="Config A",
            config_b_name="Config B",
            metrics_comparison={
                "context_precision": {
                    "config_a": 0.85,
                    "config_b": 0.88,
                    "diff": 0.03,
                    "diff_percent": 3.53,
                },
                "context_recall": {
                    "config_a": 0.90,
                    "config_b": 0.92,
                    "diff": 0.02,
                    "diff_percent": 2.22,
                },
            },
            winner="Config B",
            statistical_significance={
                "context_precision": True,
                "context_recall": False,
            },
            timestamp="2026-03-05T10:00:00",
        )

        assert result.test_id == "ab-123"
        assert result.winner == "Config B"
        assert result.metrics_comparison["context_precision"]["diff"] == 0.03
        assert result.statistical_significance["context_precision"] is True


class TestIntegration:
    """集成测试"""

    def test_full_evaluation_pipeline(self, tmp_path):
        """测试完整评估流程"""
        evaluator = RAGEvaluator()

        samples = [
            EvaluationSample(
                question="问题 1",
                answer="答案 1",
                contexts=["上下文 1"],
                ground_truth="标准答案 1",
            ),
            EvaluationSample(
                question="问题 2",
                answer="答案 2",
                contexts=["上下文 2"],
                ground_truth="标准答案 2",
            ),
        ]

        dataset_path = tmp_path / "dataset.json"
        evaluator.create_evaluation_dataset(samples, str(dataset_path))

        loaded_samples = evaluator.load_evaluation_dataset(str(dataset_path))
        assert len(loaded_samples) == 2

        report_path = tmp_path / "report.json"
        
        try:
            result = evaluator.evaluate_batch(loaded_samples)
            evaluator.generate_report(result, str(report_path))

            assert Path(report_path).exists()
        except ImportError:
            pytest.skip("RAGAS not installed")
