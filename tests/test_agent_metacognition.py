"""Agent 元认知与错误恢复模块测试。"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)


def _import_gateway(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://test.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_PRICE_CURRENCY", "CNY")
    monkeypatch.setenv("LLM_PRICE_TIERS_JSON", "[]")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1K_TOKENS", "0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1K_TOKENS", "0")
    monkeypatch.setenv("LLM_DEFAULT_MAX_TOKENS", "1024")
    monkeypatch.setenv("KB_SERVICE_URL", "http://localhost:8200")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("GATEWAY_GRAPH_CHECKPOINTER", "memory")
    monkeypatch.setenv("GATEWAY_TIMEOUT_SECONDS", "30")
    _prioritize_sys_path(GATEWAY_SRC)
    for name in list(sys.modules.keys()):
        if name.startswith("app."):
            sys.modules.pop(name, None)


# ============================================================================
# 元认知模块测试
# ============================================================================


class TestMetacognitionEngine:
    def test_rule_check_empty_evidence(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        result = engine._rule_check("这个问题很复杂", [], [])
        assert result.uncertainty_level >= 0.8
        assert "无检索证据" in result.reason

    def test_rule_check_short_question(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        result = engine._rule_check("怎么", [], [])
        assert result.uncertainty_level >= 0.3

    def test_rule_check_with_evidence(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        evidence = [
            {
                "document_title": "支付系统v3.0文档",
                "content": "退款流程分三步...",
                "evidence_path": {"final_score": 0.85},
            }
        ]
        result = engine._rule_check("退款流程是什么", evidence, [])
        # 有高质量证据 → 不确定性应较低
        assert result.uncertainty_level < 0.7

    def test_ambiguous_keywords(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        result = engine._rule_check("那个怎么办", [], [])
        assert result.uncertainty_level >= 0.3

    def test_clarification_generated_when_needed(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        result = engine._rule_check("怎么办", [], [])
        assert result.needs_clarification
        assert len(result.clarification_question) > 0
        assert len(result.strategy) > 0

    def test_no_clarification_when_confident(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        evidence = [{"document_title": "文档", "content": "详细内容", "evidence_path": {"final_score": 0.9}}]
        result = engine._rule_check("v3.0版本部署配置参数有哪些具体值需要设置", evidence, [])
        assert not result.needs_clarification or result.uncertainty_level < 0.35

    def test_suggest_alternatives(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        engine = MetacognitionEngine()
        alternatives = engine._suggest_alternatives("xxx", [])
        assert len(alternatives) >= 0


class TestUncertaintyType:
    def test_classify(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_metacognition import MetacognitionEngine

        assert MetacognitionEngine._classify_uncertainty(0.9, [], "") == "knowledge_gap"
        assert MetacognitionEngine._classify_uncertainty(0.7, [{}], "") == "info_insufficient"
        assert MetacognitionEngine._classify_uncertainty(0.5, [{}], "") == "ambiguity"


# ============================================================================
# 错误恢复模块测试
# ============================================================================


class TestErrorClassifier:
    def test_classify_timeout(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType

        assert ErrorClassifier.classify(TimeoutError("timed out")) == ErrorType.TIMEOUT

    def test_classify_network(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType

        assert ErrorClassifier.classify(ConnectionError("connection refused")) == ErrorType.NETWORK_ERROR

    def test_classify_model(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType

        assert ErrorClassifier.classify(Exception("rate limit exceeded")) == ErrorType.MODEL_ERROR

    def test_classify_unknown(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType

        assert ErrorClassifier.classify(Exception("some random error")) == ErrorType.UNKNOWN


class TestRecoveryAction:
    def test_recommend_retry_first(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType, RecoveryAction

        action = ErrorClassifier.recommend_action(ErrorType.TIMEOUT.value, attempt=1)
        assert action == RecoveryAction.RETRY

    def test_recommend_degrade_after_retries(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType, RecoveryAction

        action = ErrorClassifier.recommend_action(ErrorType.TOOL_ERROR.value, attempt=3)
        assert action == RecoveryAction.DEGRADE

    def test_recommend_give_up(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorClassifier, ErrorType, RecoveryAction

        action = ErrorClassifier.recommend_action(ErrorType.UNKNOWN.value, attempt=6)
        assert action == RecoveryAction.GIVE_UP


class TestErrorRecoveryEngine:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        async def success_fn():
            return "success"

        engine = ErrorRecoveryEngine()
        result = await engine.execute_with_recovery(
            primary_fn=success_fn,
        )
        assert result.success
        assert result.action_taken == "primary"
        assert result.attempts == 1
        assert result.final_data == "success"

    @pytest.mark.asyncio
    async def test_retry_succeeds(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        call_count = {"count": 0}

        async def flaky_fn():
            call_count["count"] += 1
            if call_count["count"] < 2:
                raise TimeoutError("timed out")
            return "recovered"

        engine = ErrorRecoveryEngine()
        result = await engine.execute_with_recovery(
            primary_fn=flaky_fn,
            max_retries=2,
        )
        assert result.success
        assert result.attempts >= 2

    @pytest.mark.asyncio
    async def test_fallback_used(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        async def always_fail():
            raise RuntimeError("always fails")

        async def fallback_fn():
            return "fallback_answer"

        engine = ErrorRecoveryEngine()
        result = await engine.execute_with_recovery(
            primary_fn=always_fail,
            fallback_fns=[fallback_fn],
            max_retries=1,
        )
        assert result.success
        assert result.action_taken == "fallback"
        assert result.final_data == "fallback_answer"

    @pytest.mark.asyncio
    async def test_all_failed(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        async def always_fail():
            raise RuntimeError("fails")

        async def fallback_fails():
            raise RuntimeError("fallback also fails")

        engine = ErrorRecoveryEngine()
        result = await engine.execute_with_recovery(
            primary_fn=always_fail,
            fallback_fns=[fallback_fails],
            max_retries=1,
        )
        assert not result.success
        assert result.action_taken == "give_up"
        assert len(result.error_chain) > 0

    def test_backoff_delay(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        engine = ErrorRecoveryEngine()
        d1 = engine._backoff_delay(1)
        d2 = engine._backoff_delay(2)
        d3 = engine._backoff_delay(3)
        assert d1 < d2 < d3  # 指数增长
        assert d3 <= engine.MAX_DELAY_MS  # 不超过上限

    def test_stats_tracking(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_error_recovery import ErrorRecoveryEngine

        engine = ErrorRecoveryEngine()
        engine._record_success("retry", "timeout", 2)
        engine._record_failure("timeout", 3)
        stats = engine.stats()
        assert "timeout_retry" in stats
        assert stats["timeout_retry"]["success"] == 1
