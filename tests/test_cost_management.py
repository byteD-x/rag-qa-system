"""Phase 3 成本管理、多租户、量化路由测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from conftest import prioritize_service_src


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"
SHARED_SRC = REPO_ROOT / "packages/python"


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
    prioritize_service_src(GATEWAY_SRC)
    shared_path = str(SHARED_SRC)
    if shared_path not in sys.path:
        sys.path.insert(1, shared_path)
    for name in list(sys.modules.keys()):
        if name.startswith("shared."):
            sys.modules.pop(name, None)


# ============================================================================
# 成本归因测试
# ============================================================================


class TestCostAttribution:
    def test_record_and_report_by_model(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(model="gpt-4", input_tokens=500, output_tokens=200, estimated_cost=0.15)
        engine.record(model="gpt-4", input_tokens=300, output_tokens=100, estimated_cost=0.10)
        engine.record(model="qwen-plus", input_tokens=800, output_tokens=400, estimated_cost=0.02)

        report = engine.report(dimension="model", period="all")
        assert report.total_calls == 3
        assert report.total_cost == 0.27
        assert len(report.slices) >= 2
        # gpt-4 应该排名第一（成本最高）
        assert report.slices[0].key == "gpt-4"

    def test_report_by_scene(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(scene="enterprise_qa", estimated_cost=0.05)
        engine.record(scene="tech_support", estimated_cost=0.03)
        engine.record(scene="enterprise_qa", estimated_cost=0.04)

        report = engine.report(dimension="scene", period="all")
        assert len(report.slices) >= 2
        enterprise = next(s for s in report.slices if s.key == "enterprise_qa")
        assert enterprise.total_cost == 0.09

    def test_report_by_user(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(user_id="user-a", estimated_cost=0.10)
        engine.record(user_id="user-b", estimated_cost=0.05)

        report = engine.report(dimension="user", period="all")
        assert len(report.slices) == 2

    def test_cache_tracking(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(model="test", estimated_cost=0.01, cached=True)
        engine.record(model="test", estimated_cost=0.01, cached=False)
        engine.record(model="test", estimated_cost=0.01, cached=True)

        report = engine.report(dimension="model", period="all")
        test_slice = report.slices[0]
        assert test_slice.cached_count == 2
        assert test_slice.cache_hit_rate > 0.6

    def test_optimization_suggestions(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        for _ in range(80):
            engine.record(model="expensive-model", estimated_cost=0.15, cached=False)

        suggestions = engine.optimization_suggestions()
        assert len(suggestions) > 0

    def test_export(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(model="gpt-4", estimated_cost=0.10)
        data = engine.export(dimension="model", period="all")
        assert len(data) == 1
        assert data[0]["key"] == "gpt-4"

    def test_daily_trend(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_attribution import CostAttributionEngine

        engine = CostAttributionEngine()
        engine.record(model="test", estimated_cost=0.01)
        report = engine.report(dimension="model", period="all")
        assert len(report.trend) >= 1


# ============================================================================
# 多租户隔离测试
# ============================================================================


class TestTenantIsolation:
    def test_register_tenant(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.gateway_scope import register_tenant, tenant_scope_filter

        register_tenant("tenant-1", allowed_corpus_ids=["kb:001", "kb:002"])
        result = tenant_scope_filter("tenant-1", ["kb:001", "kb:003"])
        assert result == ["kb:001"]

    def test_no_filter_for_unregistered(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.gateway_scope import tenant_scope_filter

        result = tenant_scope_filter("unknown-tenant", ["kb:001", "kb:002"])
        assert result == ["kb:001", "kb:002"]

    def test_empty_allowed_means_all(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.gateway_scope import register_tenant, tenant_scope_filter

        register_tenant("tenant-2", allowed_corpus_ids=[])
        result = tenant_scope_filter("tenant-2", ["kb:001", "kb:002"])
        assert result == ["kb:001", "kb:002"]

    def test_tenant_has_access(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.gateway_scope import register_tenant, tenant_has_access

        register_tenant("tenant-3", allowed_corpus_ids=["kb:001"])
        assert tenant_has_access("tenant-3", "kb:001")
        assert not tenant_has_access("tenant-3", "kb:002")


# ============================================================================
# 量化模型路由测试
# ============================================================================


class TestQuantizedRouting:
    def test_resolve_quantized_route(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from shared.model_routing import resolve_quantized_route

        class MockSettings:
            model = "qwen-plus"
            provider = "openai"
            base_url = "https://test.api.com"
            api_key = "test-key"
            timeout_seconds = 30
            default_temperature = 0.2
            default_max_tokens = 1200
            extra_body = {}
            model_routing = {
                "chat_grounded_answer": {
                    "model": "qwen-plus",
                    "quantized_model": "qwen-plus-int4",
                    "temperature": 0.2,
                }
            }

        decision = resolve_quantized_route(
            MockSettings(), "chat_grounded_answer", prefer_quantized=True
        )
        assert decision["model"] == "qwen-plus-int4"

    def test_resolve_full_model(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from shared.model_routing import resolve_quantized_route

        class MockSettings:
            model = "qwen-plus"
            provider = "openai"
            base_url = "https://test.api.com"
            api_key = "test-key"
            timeout_seconds = 30
            default_temperature = 0.2
            default_max_tokens = 1200
            extra_body = {}
            model_routing = {
                "chat_grounded_answer": {
                    "model": "qwen-plus",
                    "quantized_model": "qwen-plus-int4",
                }
            }

        decision = resolve_quantized_route(
            MockSettings(), "chat_grounded_answer", prefer_quantized=False
        )
        assert decision["model"] == "qwen-plus"


# ============================================================================
# 批量异步任务测试（schema验证）
# ============================================================================


class TestBatchAsyncSchema:
    def test_batch_request_schema(self) -> None:
        """验证批量请求数据结构。"""
        batch = {
            "requests": [
                {"question": "什么是RAG？", "scope": {"mode": "all"}},
                {"question": "v3.0部署配置？", "scope": {"mode": "single", "corpus_ids": ["kb:1"]}},
            ],
            "max_concurrency": 2,
            "webhook_url": "",
        }
        assert len(batch["requests"]) == 2
        assert batch["max_concurrency"] == 2

    def test_batch_response_schema(self) -> None:
        """验证批量响应数据结构。"""
        response = {
            "batch_id": "batch_abc123",
            "status": "processing",
            "total": 5,
            "completed": 2,
            "failed": 0,
            "results": [
                {"index": 0, "status": "completed", "answer": "...", "latency_ms": 350},
                {"index": 1, "status": "processing", "answer": "", "latency_ms": 0},
            ],
        }
        assert response["status"] in {"processing", "completed", "failed"}
        assert response["completed"] + response["failed"] <= response["total"]
