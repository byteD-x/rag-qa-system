"""测试推理优化能力：语义缓存、模型健康监控。"""

from __future__ import annotations

import importlib
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
    async def test_semantic_lookup_default_disabled(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        calls: list[str] = []

        async def fake_embed(text: str) -> list[float]:
            calls.append(text)
            return [1.0, 0.0]

        cache = SemanticCache(embedding_fn=fake_embed)

        await cache.store(
            question="退款流程是什么？",
            answer="退款流程需要审批。",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(question="退货流程怎么走？", corpus_ids=["kb:abc"], model_name="qwen-plus")
        stats = cache.stats()

        assert hit is None
        assert calls == []
        assert stats["semantic_enabled"] is False
        assert stats["semantic_skipped"] == 1

    @pytest.mark.asyncio
    async def test_semantic_lookup_hits_same_scope_when_enabled(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        async def fake_embed(_: str) -> list[float]:
            return [1.0, 0.0]

        cache = SemanticCache(embedding_fn=fake_embed, semantic_enabled=True, semantic_threshold=0.9)

        await cache.store(
            question="退款流程是什么？",
            answer="退款流程需要审批。",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(question="退货流程怎么走？", corpus_ids=["kb:abc"], model_name="qwen-plus")
        stats = cache.stats()

        assert hit is not None
        assert hit.cache_level == "semantic"
        assert hit.cached_answer == "退款流程需要审批。"
        assert stats["semantic_enabled"] is True
        assert stats["semantic_hits"] == 1

    @pytest.mark.asyncio
    async def test_semantic_lookup_does_not_cross_scope(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        async def fake_embed(_: str) -> list[float]:
            return [1.0, 0.0]

        cache = SemanticCache(embedding_fn=fake_embed, semantic_enabled=True, semantic_threshold=0.9)

        await cache.store(
            question="退款流程是什么？",
            answer="退款流程需要审批。",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(question="退货流程怎么走？", corpus_ids=["kb:xyz"], model_name="qwen-plus")
        stats = cache.stats()

        assert hit is None
        assert stats["semantic_misses"] == 1

    @pytest.mark.asyncio
    async def test_semantic_lookup_does_not_cross_model(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        async def fake_embed(_: str) -> list[float]:
            return [1.0, 0.0]

        cache = SemanticCache(embedding_fn=fake_embed, semantic_enabled=True, semantic_threshold=0.9)

        await cache.store(
            question="refund policy workflow",
            answer="Refunds require approval.",
            answer_mode="grounded",
            corpus_ids=["kb:abc"],
            model_name="qwen-plus",
        )

        hit = await cache.lookup(
            question="how do refunds work?",
            corpus_ids=["kb:abc"],
            model_name="gpt-4.1-mini",
        )
        stats = cache.stats()

        assert hit is None
        assert stats["semantic_misses"] == 1

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
        stats = cache.stats()
        assert hit is None
        assert stats["expired"] >= 1
        assert stats["misses"] >= 1

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
        assert _cosine_similarity([1.0], [2.0, 3.0]) == 0.0  # length mismatch

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
                corpus_key="kb:x",
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
            cache_key="k1", corpus_key="kb:x", question_embedding=[], question="q", answer="a",
            answer_mode="g", citations=[], usage={}, corpus_ids=["kb:x"],
            model_name="t", created_at=time.time(), ttl_seconds=999,
        )
        cache._memory_cache["k1"] = entry

        stats = cache.stats()
        assert stats["enabled"] is True
        assert stats["size"] >= 1
        assert stats["ttl_seconds"] == 3600.0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["writes"] == 0
        assert stats["expired"] == 0
        assert stats["clears"] == 0
        assert stats["semantic_enabled"] is False
        assert stats["semantic_hits"] == 0
        assert stats["total_entries"] >= 1
        assert "hit_rate_estimate" in stats

    def test_cache_stats_prunes_expired_entries_consistently(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import CacheEntry, SemanticCache

        cache = SemanticCache()
        cache._memory_cache.clear()
        cache._lru_order.clear()
        now = time.time()
        entries = [
            CacheEntry(
                cache_key="expired-1", corpus_key="kb:x", question_embedding=[], question="old-1", answer="a",
                answer_mode="g", citations=[], usage={}, corpus_ids=["kb:x"],
                model_name="t", created_at=now - 10, ttl_seconds=1,
            ),
            CacheEntry(
                cache_key="expired-2", corpus_key="kb:x", question_embedding=[], question="old-2", answer="a",
                answer_mode="g", citations=[], usage={}, corpus_ids=["kb:x"],
                model_name="t", created_at=now - 20, ttl_seconds=1,
            ),
            CacheEntry(
                cache_key="live", corpus_key="kb:x", question_embedding=[], question="live", answer="a",
                answer_mode="g", citations=[], usage={}, corpus_ids=["kb:x"],
                model_name="t", created_at=now, ttl_seconds=999,
            ),
        ]
        for entry in entries:
            cache._memory_cache[entry.cache_key] = entry
            cache._lru_order.append(entry.cache_key)

        stats = cache.stats()
        stats_after_prune = cache.stats()

        assert stats["expired_entries"] == 2
        assert stats["expired"] == 2
        assert stats["size"] == 1
        assert stats["total_entries"] == 1
        assert stats_after_prune["expired_entries"] == 0
        assert stats_after_prune["expired"] == 2
        assert stats_after_prune["size"] == 1
        assert stats_after_prune["total_entries"] == 1

    @pytest.mark.asyncio
    async def test_cache_stats_tracks_runtime_events(self, monkeypatch) -> None:
        _import_gateway("app.semantic_cache", monkeypatch)
        from app.semantic_cache import SemanticCache

        cache = SemanticCache(default_ttl=123.0)
        cache._memory_cache.clear()
        cache._lru_order.clear()

        await cache.store(
            question="q",
            answer="a",
            answer_mode="grounded",
            corpus_ids=["kb:x"],
            model_name="m",
        )
        hit = await cache.lookup(question="q", corpus_ids=["kb:x"], model_name="m")
        miss = await cache.lookup(question="missing", corpus_ids=["kb:x"], model_name="m")
        removed = await cache.invalidate(corpus_id="kb:x")

        stats = cache.stats()

        assert hit is not None
        assert miss is None
        assert removed == 1
        assert stats["enabled"] is True
        assert stats["ttl_seconds"] == 123.0
        assert stats["size"] == 0
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["writes"] == 1
        assert stats["clears"] == 1
        assert stats["hit_rate"] == 0.5


def test_gateway_metrics_summary_includes_response_cache(monkeypatch) -> None:
    _import_gateway("app.gateway_system_routes", monkeypatch)
    from app import gateway_system_routes
    from app.governance_metrics import get_governance_metrics

    monkeypatch.setattr(
        gateway_system_routes.semantic_cache,
        "stats",
        lambda: {
            "enabled": True,
            "ttl_seconds": 3600.0,
            "size": 2,
            "hits": 3,
            "misses": 1,
            "writes": 2,
            "expired": 0,
            "clears": 0,
        },
    )
    get_governance_metrics().reset()
    get_governance_metrics().record_tool_workflow(success=False, duration_ms=2.0, failure_reason="tool_not_found")

    payload = gateway_system_routes.get_metrics_summary()

    assert payload["response_cache_summary"]["enabled"] is True
    assert payload["response_cache_summary"]["size"] == 2
    assert payload["response_cache_summary"]["hits"] == 3
    assert payload["response_cache_summary"]["misses"] == 1
    assert payload["governance_metrics"]["events"]["tool_workflow"]["failure"] == 1
    assert payload["governance_metrics"]["events"]["tool_workflow"]["failure_reasons"] == {"tool_not_found": 1}


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
# 集成测试
# ============================================================================


class TestInferenceIntegration:
    """测试模块间联动。"""

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
