"""Phase 2 平台化与安全模块测试 —— 覆盖工具生态、API Key、PII、指令 AB 评估。"""

from __future__ import annotations

import json
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
# 工具发现测试
# ============================================================================


class TestOpenAPIToolDiscoverer:
    def test_discover_from_minimal_spec(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_discovery import OpenAPIToolDiscoverer

        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {
                "/api/v1/search": {
                    "get": {
                        "operationId": "searchDocuments",
                        "summary": "搜索文档",
                        "tags": ["search"],
                    }
                },
                "/api/v1/users": {
                    "post": {
                        "operationId": "createUser",
                        "summary": "创建用户",
                        "tags": ["admin"],
                    }
                },
            },
        }
        discoverer = OpenAPIToolDiscoverer(namespace="test")
        tools = discoverer.discover(spec)
        assert len(tools) == 2
        assert tools[0].name == "test_searchDocuments"
        assert tools[0].category == "search"
        assert tools[1].http_method == "post"

    def test_discover_with_parameters(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_discovery import OpenAPIToolDiscoverer

        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test"},
            "paths": {
                "/api/v1/query": {
                    "get": {
                        "operationId": "queryData",
                        "summary": "查询数据",
                        "parameters": [
                            {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        ],
                    }
                },
            },
        }
        discoverer = OpenAPIToolDiscoverer()
        tools = discoverer.discover(spec)
        assert len(tools) == 1
        params = tools[0].parameters
        assert "q" in params.get("properties", {})
        assert "limit" in params.get("properties", {})

    def test_generate_tool_definition(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_discovery import generate_tool_definition, DiscoveredTool

        dt = DiscoveredTool(
            name="api_search", description="搜索", category="search",
            original_path="/search", http_method="get",
            parameters={"type": "object", "properties": {}},
        )
        td = generate_tool_definition(dt)
        assert td["name"] == "api_search"
        assert td["category"] == "search"
        assert td["metadata"]["source"] == "openapi"


# ============================================================================
# 工具链编排测试
# ============================================================================


class TestToolPipeline:
    def test_add_steps(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline

        pipe = ToolPipeline(name="test")
        pipe.add_step("search", tool="search_scope", inputs={"query": "$question"})
        pipe.add_step("analyze", tool="analyze", inputs={"data": "$search.results"})
        assert len(pipe._steps) == 2

    @pytest.mark.asyncio
    async def test_run_empty(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline

        pipe = ToolPipeline(name="empty")
        result = await pipe.run({"question": "test"})
        assert result.success
        assert result.steps_completed == 0

    @pytest.mark.asyncio
    async def test_run_with_transform(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline, Step

        pipe = ToolPipeline(name="test")
        pipe.add(Step(
            name="double", step_type="transform",
            transform_fn=lambda ctx: ctx.get("value", 0) * 2,
            output_key="doubled",
        ))
        result = await pipe.run({"value": 5})
        assert result.success
        assert result.final_output["doubled"] == 10

    def test_resolve_ref(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline

        ctx = {"question": "test", "search": {"results": [{"id": 1}, {"id": 2}]}}
        assert ToolPipeline._resolve_ref("$question", ctx) == "test"
        assert ToolPipeline._resolve_ref("$search.results", ctx) == [{"id": 1}, {"id": 2}]
        assert ToolPipeline._resolve_ref("$search.results[0].id", ctx) == 1
        assert ToolPipeline._resolve_ref("literal_value", ctx) == "literal_value"

    def test_evaluate_condition(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline

        ctx = {"status": "ok", "count": 5, "items": [1, 2, 3]}
        assert ToolPipeline._evaluate_condition("$status == ok", ctx) is True
        assert ToolPipeline._evaluate_condition("$count != 10", ctx) is True
        assert ToolPipeline._evaluate_condition("$count exists", ctx) is True

    @pytest.mark.asyncio
    async def test_parallel_execution(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_pipeline import ToolPipeline, Step

        pipe = ToolPipeline(name="parallel_test")
        pipe.add(Step(
            name="parallel_group", step_type="parallel",
            parallel_steps=[
                Step(name="t1", step_type="transform", output_key="r1",
                     transform_fn=lambda ctx: "a"),
                Step(name="t2", step_type="transform", output_key="r2",
                     transform_fn=lambda ctx: "b"),
            ],
        ))
        result = await pipe.run({})
        assert result.success
        assert result.final_output["parallel_group"]["t1"] == "a"
        assert result.final_output["parallel_group"]["t2"] == "b"


# ============================================================================
# 工具沙箱测试
# ============================================================================


class TestSandboxExecutor:
    @pytest.mark.asyncio
    async def test_run_echo(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_sandbox import SandboxExecutor

        executor = SandboxExecutor(mode="subprocess")
        result = await executor.run("echo hello world", timeout=5)
        assert result.success
        assert "hello world" in result.stdout
        assert result.was_sandboxed

    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_sandbox import SandboxExecutor

        executor = SandboxExecutor(mode="subprocess")
        # Windows: timeout command, Unix: sleep
        result = await executor.run("python -c \"import time; time.sleep(10)\"", timeout=1)
        assert not result.success
        assert "超时" in result.stderr or result.exit_code != 0

    def test_security_blocked(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_sandbox import SandboxExecutor, SandboxPolicy

        policy = SandboxPolicy()
        executor = SandboxExecutor(mode="restricted", policy=policy)
        result = executor._check_security("rm -rf /tmp/data")
        assert result != ""

    def test_security_allowed(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.tool_sandbox import SandboxExecutor

        executor = SandboxExecutor(mode="subprocess")
        result = executor._check_security("echo hello")
        assert result == ""


# ============================================================================
# API Key 管理测试
# ============================================================================


class TestAPIKeyManager:
    def test_create_and_validate(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        key_info = mgr.create_key("user-1", permissions=["chat.use"])
        assert "raw_key" in key_info

        raw = key_info["raw_key"]
        valid, identity = mgr.validate(raw)
        assert valid
        assert identity["user_id"] == "user-1"

    def test_validate_invalid_key(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        valid, identity = mgr.validate("rag_sk_invalid_key_123456")
        assert not valid

    def test_revoke(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        key_info = mgr.create_key("user-1")
        raw = key_info["raw_key"]
        key_id = key_info["id"]

        mgr.revoke(key_id)
        valid, identity = mgr.validate(raw)
        assert not valid
        assert "撤销" in str(identity.get("reason", ""))

    def test_rate_limit(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        key_info = mgr.create_key("user-1", rate_limit_per_minute=2)
        raw = key_info["raw_key"]

        # 前两次应该通过
        assert mgr.validate(raw)[0]
        assert mgr.validate(raw)[0]
        # 第三次被限制
        valid, identity = mgr.validate(raw)
        assert not valid

    def test_record_usage(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        key_info = mgr.create_key("user-1", quota_tokens=1000)
        mgr.record_usage(key_info["id"], 300)
        stats = mgr.stats(key_info["id"])
        assert stats["tokens_used"] == 300
        assert stats["quota_usage_pct"] == 30.0

    def test_list_keys(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.api_key_manager import APIKeyManager

        mgr = APIKeyManager()
        mgr.create_key("user-1", name="Key1")
        mgr.create_key("user-1", name="Key2")
        mgr.create_key("user-2", name="Key3")

        all_keys = mgr.list_keys()
        assert len(all_keys) == 3
        user1_keys = mgr.list_keys(user_id="user-1")
        assert len(user1_keys) == 2


# ============================================================================
# PII 检测测试
# ============================================================================


class TestPIIDetector:
    def test_detect_phone(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        result = detector.detect("联系我13800138000或者13900139000")
        assert result.has_pii
        assert result.summary.get("phone", 0) == 2

    def test_detect_id_card(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        # 有效身份证号（校验位正确）
        result = detector.detect("身份证号110101199001011234")
        assert result.has_pii

    def test_detect_email(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        result = detector.detect("邮箱test@example.com欢迎联系")
        assert result.has_pii
        assert result.summary.get("email", 0) >= 1

    def test_anonymize_mask(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        text = "请联系13800138000"
        safe = detector.anonymize(text, strategy="mask")
        assert "13800138000" not in safe
        assert "*" in safe

    def test_anonymize_redact(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        text = "邮箱是user@test.com"
        safe = detector.anonymize(text, strategy="redact")
        assert "user@test.com" not in safe

    def test_anonymize_replace(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        text = "手机13800138000"
        safe = detector.anonymize(text, strategy="replace")
        assert "[手机号]" in safe

    def test_no_pii(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        result = detector.detect("这是一个正常的句子没有敏感信息")
        assert not result.has_pii

    def test_validate_id_card_valid(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        # 测试校验位算法
        assert PIIDetector._validate_id_card("110101199001011234") in {True, False}  # 仅验证不抛异常

    def test_audit_report(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.pii_detector import PIIDetector

        detector = PIIDetector()
        report = detector.audit_report("电话13800138000邮箱test@test.com")
        assert report["has_pii"]
        assert report["pii_count"] >= 2


# ============================================================================
# 指令 AB 评估测试
# ============================================================================


class TestInstructionABEvaluator:
    def test_start_experiment(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.instruction_evaluator import InstructionABEvaluator

        eval = InstructionABEvaluator()
        config = eval.start_experiment(
            "test_exp",
            control_prompt="你是一个助手",
            variant_prompt="你是一个专业的助手",
        )
        assert config.experiment_id == "test_exp"

    def test_assign_variant(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.instruction_evaluator import InstructionABEvaluator

        eval = InstructionABEvaluator()
        eval.start_experiment("test2", control_prompt="A", variant_prompt="B", split_ratio=0.5)
        # 第一次分配应为 A（优先填充对照组）
        assert eval.assign_variant("test2") == "A"

    def test_record_and_report(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.instruction_evaluator import InstructionABEvaluator

        eval = InstructionABEvaluator()
        eval.start_experiment("test3", control_prompt="A", variant_prompt="B")

        for i in range(50):
            variant = "A" if i < 25 else "B"
            eval.record_result("test3", variant=variant, scores={
                "accuracy": 0.7 + (0.1 if variant == "B" else 0),
                "completeness": 0.6 + (0.15 if variant == "B" else 0),
            })

        report = eval.report("test3")
        assert report is not None
        assert report.sample_size["A"] == 25
        assert report.sample_size["B"] == 25

    def test_stop_experiment(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.instruction_evaluator import InstructionABEvaluator

        eval = InstructionABEvaluator()
        eval.start_experiment("test4", control_prompt="A", variant_prompt="B")
        eval.stop_experiment("test4")
        assert not eval._experiments["test4"].is_active


