"""上下文优化模块测试 —— 覆盖 context_window、context_prioritizer。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()


def _import_gateway(module_name: str, monkeypatch) -> None:
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
    monkeypatch.setenv("GATEWAY_RETRIEVAL_FANOUT_LIMIT", "4")
    monkeypatch.setenv("GATEWAY_CHAT_MAX_IN_FLIGHT_GLOBAL", "10")
    monkeypatch.setenv("GATEWAY_CHAT_MAX_IN_FLIGHT_PER_USER", "2")
    monkeypatch.setenv("GATEWAY_CHAT_SESSION_COST_BUDGET", "0")
    _prioritize_sys_path(GATEWAY_SRC)
    for name in list(sys.modules.keys()):
        if name.startswith("app."):
            sys.modules.pop(name, None)


# ============================================================================
# Token 估算测试
# ============================================================================


class TestEstimateTokens:
    def test_empty_text(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import estimate_tokens
        assert estimate_tokens("") == 0

    def test_chinese_text(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import estimate_tokens
        tokens = estimate_tokens("这是一个测试问题")
        assert tokens > 5
        assert tokens < 25

    def test_english_text(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import estimate_tokens
        tokens = estimate_tokens("This is a test question for token estimation")
        assert tokens > 5
        assert tokens < 30

    def test_mixed_text(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import estimate_tokens
        tokens = estimate_tokens("中文Chinese混合Mixed123测试")
        assert tokens > 5

    def test_monotonic(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import estimate_tokens
        short = estimate_tokens("短")
        medium = estimate_tokens("中等长度的文本用于测试")
        long_text = estimate_tokens("一段很长的文本" * 100)
        assert short < medium < long_text


# ============================================================================
# 滑动窗口管理器测试
# ============================================================================


class TestContextWindowManager:
    def test_empty_history(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=1000)
        kept, stats = mgr.manage([])
        assert kept == []
        assert stats.total_tokens == 0

    def test_basic_sliding(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=200)
        history = [{"role": "user", "content": f"问题{i}" * 10} for i in range(20)]
        kept, stats = mgr.manage(history)
        assert len(kept) < 20
        assert stats.messages_dropped > 0

    def test_keep_last_messages(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=800, min_history_turns=2)
        history = [
            {"role": "user", "content": "旧问题1"},
            {"role": "assistant", "content": "旧回答1"},
            {"role": "user", "content": "旧问题2"},
            {"role": "assistant", "content": "旧回答2"},
            {"role": "user", "content": "当前问题需要详细回答"},
        ]
        kept, stats = mgr.manage(history)
        assert len(kept) >= 4
        assert kept[-1]["content"] == "当前问题需要详细回答"

    def test_reserved_messages(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=200)
        history = [
            {"role": "user", "content": "重要问题", "id": "msg-1"},
            {"role": "assistant", "content": "回答1", "id": "msg-2"},
            {"role": "user", "content": "普通问题" * 10, "id": "msg-3"},
            {"role": "assistant", "content": "回答2", "id": "msg-4"},
        ]
        kept, stats = mgr.manage(history, reserved_message_ids={"msg-1"})
        kept_ids = {msg.get("id") for msg in kept}
        assert "msg-1" in kept_ids

    def test_system_prompt_budget(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=1000, system_reserve_ratio=0.3)
        system_prompt = "系统提示词" * 200
        kept, stats = mgr.manage([], system_prompt=system_prompt)
        # 允许 ±5% 的估算误差
        assert stats.system_tokens <= 380

    def test_evidence_budget(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=1000, evidence_ratio=0.3)
        evidence = "证据内容" * 200
        kept, stats = mgr.manage([], evidence_block=evidence)
        assert stats.evidence_tokens <= 380

    def test_overflow_detection(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import ContextWindowManager
        mgr = ContextWindowManager(max_tokens=50)
        history = [{"role": "user", "content": "很长的问题" * 20}]
        kept, stats = mgr.manage(history)
        assert stats.overflow

    def test_convenience_function(self, monkeypatch) -> None:
        _import_gateway("app.context_window", monkeypatch)
        from app.context_window import manage_context_window
        history = [
            {"role": "user", "content": "测试问题"},
            {"role": "assistant", "content": "测试回答"},
        ]
        kept, stats = manage_context_window(history, max_tokens=500)
        assert len(kept) == 2
        assert stats.budget_limit == 500


# ============================================================================

# ============================================================================
# 上下文优先级排序测试
# ============================================================================


class TestContextPrioritizer:
    def test_empty_history(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        ranked = p.rank([], "测试问题")
        assert ranked == []

    def test_rank_relevance(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        history = [
            {"role": "user", "content": "有什么好看的电影推荐吗"},
            {"role": "assistant", "content": "推荐星际穿越和盗梦空间"},
            {"role": "user", "content": "v3.0版本部署配置参数是什么"},
        ]
        ranked = p.rank(history, "v3.0部署配置")
        top = ranked[0]
        assert "v3.0" in top.message["content"] or "部署" in top.message["content"]

    def test_rank_recency(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        now = time.time()
        history = [
            {"role": "user", "content": "旧问题", "created_at": now - 7200},
            {"role": "user", "content": "新问题", "created_at": now - 60},
        ]
        ranked = p.rank(history, "测试", current_time=now)
        assert ranked[0].score.recency > ranked[-1].score.recency

    def test_rank_importance(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        history = [
            {"role": "user", "content": "你好"},
            {"role": "user", "content": "生产数据库连接池配置错误导致超时，需要紧急修复"},
        ]
        ranked = p.rank(history, "测试")
        high_importance = [rm for rm in ranked if "超时" in rm.message["content"]]
        assert len(high_importance) > 0
        assert high_importance[0].score.importance > 0.2

    def test_rank_low_importance(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        history = [
            {"role": "user", "content": "好的"},
            {"role": "user", "content": "v3.0版本发布时间是什么"},
        ]
        ranked = p.rank(history, "v3.0版本发布")
        low = [rm for rm in ranked if rm.message["content"] == "好的"]
        relevant = [rm for rm in ranked if "v3.0" in rm.message["content"]]
        if low and relevant:
            assert low[0].score.importance < relevant[0].score.importance

    def test_rank_and_select(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        history = [{"role": "user", "content": f"消息{i}" * 5} for i in range(20)]
        selected = p.rank_and_select(history, "测试消息10", token_budget=200, min_turns=1)
        assert len(selected) > 0
        assert len(selected) < 20

    def test_composite_score_range(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        history = [
            {"role": "user", "content": "部署配置参数查询"},
            {"role": "assistant", "content": "v3.0需要配置数据库连接池和缓存参数"},
            {"role": "user", "content": "好的谢谢"},
        ]
        ranked = p.rank(history, "部署参数")
        for rm in ranked:
            assert 0.0 <= rm.score.relevance <= 1.0
            assert 0.0 <= rm.score.recency <= 1.0
            assert 0.0 <= rm.score.importance <= 1.0
            assert 0.0 <= rm.score.composite <= 1.0


class TestQuestionFeatures:
    def test_extract_features(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        qf = p._extract_question_features("v3.0版本的部署参数配置是什么？")
        assert len(qf.tokens) > 0
        assert qf.question_length > 0

    def test_temporal_detection(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        qf = p._extract_question_features("最近版本有什么变化")
        assert qf.has_temporal

    def test_no_temporal(self, monkeypatch) -> None:
        _import_gateway("app.context_prioritizer", monkeypatch)
        from app.context_prioritizer import ContextPrioritizer
        p = ContextPrioritizer()
        qf = p._extract_question_features("什么是RAG")
        assert not qf.has_temporal
