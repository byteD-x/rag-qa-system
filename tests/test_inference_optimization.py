"""测试推理优化能力：语义缓存、模型健康监控、复杂度分类、请求合并。"""

from __future__ import annotations

import importlib
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


def _import_gateway(module_name: str, monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://test.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("KB_SERVICE_URL", "http://localhost:8200")
    monkeypatch.setenv("GATEWAY_GRAPH_CHECKPOINTER", "memory")
    _prioritize_sys_path(GATEWAY_SRC)
    for name in list(sys.modules.keys()):
        if name.startswith("app.") and "tool_registry" not in name:
            sys.modules.pop(name, None)


# ============================================================================
# 语义缓存测试
# ============================================================================


class TestSemanticCache:
    """测试三层缓存体系。"""

    def test_cache_hit_exact(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache, CacheHit

        cache = SemanticCache()

        # 存储
        cache._memory_cache.clear()
        cache._lru_order.clear()

    @pytest.mark.asyncio
    async def test_store_and_lookup_exact(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()
        cache._lru_order.clear()

        await cache.store(
            question="退款流程是什么？",
            answer="退款流程共三步...",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(question="退款流程是什么？", corpus_ids=["kb:abc"], model_name="qwen-plus")
        assert hit is not None
        assert hit.cache_level == "exact"
        assert "三步" in hit.cached_answer

    @pytest.mark.asyncio
    async def test_lookup_miss_different_question(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()

        await cache.store(
            question="退款流程是什么？",
            answer="退款流程共三步...",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(question="退货的步骤是什么？", corpus_ids=["kb:abc"], model_name="qwen-plus")
        # 无 embedding_fn 时不会有语义命中
        assert hit is None or hit.cache_level != "exact"

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()

        await cache.store(
            question="测试问题",
            answer="测试答案",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
            ttl_seconds=0.001,  # 1ms
        )

        await asyncio.sleep(0.01)

        hit = await cache.lookup(question="测试问题", corpus_ids=["kb:abc"], model_name="qwen-plus")
        assert hit is None

    @pytest.mark.asyncio
    async def test_invalidate_by_corpus(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()

        await cache.store(
            question="问题A",
            answer="答案A",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )
        await cache.store(
            question="问题B",
            answer="答案B",
            answer_mode="grounded",
            corpus_ids=["kb:xyz"],
            model_name="qwen-plus",
        )

        removed = await cache.invalidate(corpus_id="kb:abc")
        assert removed >= 1  # 至少一条被移除

        hit_a = await cache.lookup(question="问题A", corpus_ids=["kb:abc"], model_name="qwen-plus")
        assert hit_a is None  # 已失效

        hit_b = await cache.lookup(question="问题B", corpus_ids=["kb:xyz"], model_name="qwen-plus")
        assert hit_b is not None  # 未受影响

    def test_cosine_similarity(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import _cosine_similarity

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(1.0)

        c = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, c) == pytest.approx(0.0)

        d = [1.0, 1.0, 0.0]
        assert _cosine_similarity(a, d) == pytest.approx(0.707, abs=1e-3)

    def test_cosine_similarity_empty(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import _cosine_similarity

        assert _cosine_similarity([], []) == 0.0
        assert _cosine_similarity([1.0], [2.0]) == 0.0  # length mismatch

    def test_lru_eviction(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache(max_entries=3)
        cache._memory_cache.clear()

        # 同步模拟存储（绕过 async）
        from app.semantic_cache import CacheEntry
        for i in range(5):
            entry = CacheEntry(
                cache_key=f"key-{i}",
                question_embedding=[],
                question=f"q{i}",
                answer=f"a{i}",
                answer_mode="grounded",
                citations=[],
                usage={},
                corpus_ids=["kb:x"],
                model_name="test",
                created_at=time.time(),
                ttl_seconds=999,
            )
            cache._memory_cache[entry.cache_key] = entry
            cache._lru_order.append(entry.cache_key)
            cache._evict_lru()

        assert len(cache._memory_cache) <= 3
        # 最旧的 key-0, key-1 应被驱逐
        assert "key-0" not in cache._memory_cache
        assert "key-1" not in cache._memory_cache

    def test_cache_stats(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()

        from app.semantic_cache import CacheEntry
        entry = CacheEntry(
            cache_key="k1", question_embedding=[], question="q", answer="a",
            answer_mode="g", citations=[], usage={}, corpus_ids=["kb:x"],
            model_name="t", created_at=time.time(), ttl_seconds=999,
        )
        cache._memory_cache["k1"] = entry

        stats = cache.stats()
        assert stats["total_entries"] >= 1
        assert "hit_rate_estimate" in stats


# ============================================================================
# 模型健康监控测试
# ============================================================================


class TestModelHealth:
    """测试模型健康监控、熔断和路由选择。"""

    def test_record_success_and_get_stats(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor()
        monitor._models.clear()

        monitor.record_success("qwen-plus", latency_ms=350, input_tokens=500, output_tokens=100)
        monitor.record_success("qwen-plus", latency_ms=400, input_tokens=600, output_tokens=120)

        stats = monitor.get_stats("qwen-plus")
        assert stats is not None
        assert stats.total_calls == 2
        assert stats.total_success == 2
        assert stats.success_rate == 1.0
        assert stats.health_score > 0.8

    def test_record_failure_triggers_circuit_breaker(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor(circuit_breaker_threshold=3)
        monitor._models.clear()

        for _ in range(3):
            monitor.record_failure("gpt-4o", error_type="timeout")

        stats = monitor.get_stats("gpt-4o")
        assert stats is not None
        assert stats.consecutive_failures == 3
        assert stats.circuit_open

    def test_pick_best_prefer_speed(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor()
        monitor._models.clear()

        monitor.record_success("fast-model", latency_ms=100)
        monitor.record_success("slow-model", latency_ms=1000)

        best = monitor.pick_best(["fast-model", "slow-model"], prefer="speed")
        assert best == "fast-model"

    def test_pick_best_excludes_circuit_open(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor(circuit_breaker_threshold=1)
        monitor._models.clear()

        monitor.record_success("healthy-model", latency_ms=200)
        monitor.record_failure("broken-model", error_type="timeout")

        best = monitor.pick_best(["healthy-model", "broken-model"])
        assert best == "healthy-model"

    def test_pick_best_all_unavailable(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor(circuit_breaker_threshold=1)
        monitor._models.clear()

        monitor.record_failure("broken-a", error_type="timeout")
        monitor.record_failure("broken-b", error_type="timeout")

        best = monitor.pick_best(["broken-a", "broken-b"])
        assert best is None  # 全部熔断，无可选

    def test_summary(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor(circuit_breaker_threshold=2)
        monitor._models.clear()

        monitor.record_success("healthy", latency_ms=200)
        monitor.record_failure("unhealthy", error_type="timeout")
        monitor.record_failure("unhealthy", error_type="timeout")

        summary = monitor.summary()
        assert summary["total_models"] >= 2
        assert summary["healthy_models"] >= 1
        assert summary["circuit_open_models"] >= 1

    def test_latency_percentiles(self, monkeypatch) -> None:
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor(window_size=100)
        monitor._models.clear()

        for lat in [100, 200, 300, 400, 500]:
            monitor.record_success("test-model", latency_ms=lat)

        stats = monitor.get_stats("test-model")
        assert stats is not None
        assert 280 <= stats.latency_p50 <= 320
        assert 450 <= stats.latency_p95 <= 510


# ============================================================================
# 复杂度分类器测试
# ============================================================================


class TestComplexityClassifier:
    """测试问题复杂度快速评估。"""

    def test_trivial_greeting(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        result = classify_complexity("你好")
        assert result.score == 1
        assert result.label == "trivial"
        assert result.can_use_small_model
        assert result.should_cache

    def test_simple_query(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        result = classify_complexity("退款流程是什么？")
        assert result.score <= 2
        assert result.recommended_route == "grounded"

    def test_complex_comparison(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        result = classify_complexity("请比较v2.0和v3.0版本中退款流程的差异")
        assert result.score >= 3
        assert "complex_compare" in result.features

    def test_very_complex_multi_step(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        result = classify_complexity(
            "先列出所有退款类型，然后分析每种类型的审批条件，最后总结最常见的拒绝原因并计算拒绝率"
        )
        assert result.score >= 4
        assert result.recommended_model_tier == "premium"

    def test_multi_corpus_context(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        result = classify_complexity(
            "退款流程是什么？",
            context={"corpus_ids": ["a", "b", "c", "d"]},
        )
        assert result.score >= 2
        assert "multi_corpus" in result.features

    def test_resolve_model_for_complexity(self, monkeypatch) -> None:
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import (
            classify_complexity,
            resolve_model_for_complexity,
        )

        result = classify_complexity("你好")
        model = resolve_model_for_complexity(result, available_models=["qwen-turbo", "qwen-plus"])
        assert model == "qwen-turbo"


# ============================================================================
# 请求合并测试
# ============================================================================


class TestRequestCoalescer:
    """测试请求合并与去重。"""

    @pytest.mark.asyncio
    async def test_leader_follower(self, monkeypatch) -> None:
        _import_gateway("app.request_coalescer", monkeypatch)

        from app.request_coalescer import RequestCoalescer, coalesce_key

        coalescer = RequestCoalescer(window_ms=200)
        key = coalesce_key("测试问题", ["kb:abc"])

        results = []

        async def leader_task():
            async with coalescer.coalesce(key) as cr:
                if cr.is_leader:
                    await asyncio.sleep(0.05)  # 模拟工作
                    cr.set_response({"answer": "测试答案"})
                else:
                    await cr._event.wait()
                    results.append(("follower", cr.response))

        async def follower_task():
            await asyncio.sleep(0.01)  # 稍微延迟
            async with coalescer.coalesce(key) as cr:
                if cr.is_leader:
                    pass
                else:
                    await cr._event.wait()
                    results.append(("follower", cr.response))

        await asyncio.gather(leader_task(), follower_task())

        # leader 先完成，follower 获取相同结果
        assert len(results) >= 1
        assert results[0][1]["answer"] == "测试答案"

    def test_coalesce_key_deterministic(self, monkeypatch) -> None:
        _import_gateway("app.request_coalescer", monkeypatch)
        from app.request_coalescer import coalesce_key

        k1 = coalesce_key("测试问题", ["kb:a", "kb:b"], "qwen-plus")
        k2 = coalesce_key("测试问题", ["kb:b", "kb:a"], "qwen-plus")  # 顺序不同
        assert k1 == k2  # corpus_ids 排序后应相同

        k3 = coalesce_key("另一个问题", ["kb:a"], "qwen-plus")
        assert k1 != k3

    def test_coalescer_stats(self, monkeypatch) -> None:
        _import_gateway("app.request_coalescer", monkeypatch)
        from app.request_coalescer import RequestCoalescer

        coalescer = RequestCoalescer(window_ms=100)
        stats = coalescer.stats()
        assert "total_requests" in stats
        assert "coalesce_rate" in stats
        assert stats["window_ms"] == 100


# ============================================================================
# 集成测试
# ============================================================================


class TestInferenceIntegration:
    """测试模块间联动。"""

    def test_complexity_drives_cache_decision(self, monkeypatch) -> None:
        """简单问题应建议缓存，复杂问题不应。"""
        _import_gateway("app.complexity_classifier", monkeypatch)
        from app.complexity_classifier import classify_complexity

        trivial = classify_complexity("你好")
        assert trivial.should_cache

        complex_q = classify_complexity("请比较v2和v3退款流程差异，分析影响范围并计算涉及部门数量")
        assert not complex_q.should_cache
        assert not complex_q.can_use_small_model

    def test_model_health_informs_routing(self, monkeypatch) -> None:
        """模型健康状态应影响路由选择。"""
        _import_gateway("app.model_health", monkeypatch)
        from app.model_health import ModelHealthMonitor

        monitor = ModelHealthMonitor()
        monitor._models.clear()

        # 所有模型都健康
        for m in ["qwen-turbo", "qwen-plus", "qwen-max"]:
            monitor.record_success(m, latency_ms=300)

        best = monitor.pick_best(["qwen-turbo", "qwen-plus", "qwen-max"], prefer="speed")
        assert best is not None

    @pytest.mark.asyncio
    async def test_cache_invalidate_on_document_update(self, monkeypatch) -> None:
        """文档更新时应能失效相关缓存。"""
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()

        await cache.store(
            question="问题X",
            answer="答案X",
            answer_mode="grounded",
            corpus_ids=["kb:project-a"],
            model_name="qwen-plus",
        )

        removed = await cache.invalidate(corpus_id="kb:project-a")
        assert removed >= 1


import asyncio
