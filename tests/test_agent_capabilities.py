"""测试 Agent 增强能力：工具注册中心、任务拆解、反思闭环、记忆提取。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    if sys.path[:1] == [target]:
        return
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)


def _import_module(module_name: str, monkeypatch) -> None:
    """导入 gateway app 模块，配置最小环境。"""
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

    _prioritize_sys_path(GATEWAY_SRC)

    for name in list(sys.modules.keys()):
        if name.startswith("app."):
            sys.modules.pop(name, None)


# ============================================================================
# 工具注册中心测试
# ============================================================================


class TestToolRegistry:
    """测试工具注册中心的注册、发现、执行、缓存等功能。"""

    def test_register_and_get_tool(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import ToolDefinition, tool_registry as tr

        # 清理
        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

        # 注册工具
        @tr.register(name="test_search", description="测试搜索工具", category="search")
        async def test_search(query: str, limit: int = 5) -> dict:
            return {"results": [query], "count": limit}

        assert "test_search" in tr._tools
        tool = tr.get("test_search")
        assert tool is not None
        assert tool.name == "test_search"
        assert tool.category == "search"
        assert tool.is_async
        assert tool.enabled

        # 清理
        tr._tools.clear()

    def test_register_sync_tool(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()

        @tr.register(name="calculator", description="计算工具", category="compute")
        def calculator(expression: str) -> dict:
            return {"result": eval(expression)}

        tool = tr.get("calculator")
        assert tool is not None
        assert not tool.is_async  # sync function

        tr._tools.clear()

    def test_list_by_category(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()

        @tr.register(name="tool_a", description="A", category="search")
        async def tool_a() -> dict:
            return {}

        @tr.register(name="tool_b", description="B", category="compute")
        async def tool_b() -> dict:
            return {}

        search_tools = tr.list_by_category("search")
        assert len(search_tools) == 1
        assert search_tools[0].name == "tool_a"

        compute_tools = tr.list_by_category("compute")
        assert len(compute_tools) == 1
        assert compute_tools[0].name == "tool_b"

        tr._tools.clear()

    def test_unregister(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()

        @tr.register(name="temp_tool", description="临时工具", category="general")
        async def temp_tool() -> dict:
            return {}

        assert "temp_tool" in tr._tools
        assert tr.unregister("temp_tool")
        assert "temp_tool" not in tr._tools

    def test_get_llm_tools_format(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()

        @tr.register(name="my_tool", description="我的工具", category="general")
        async def my_tool(param: str) -> dict:
            return {"value": param}

        tools = tr.get_llm_tools()
        assert len(tools) == 1
        func = tools[0]["function"]
        assert func["name"] == "my_tool"
        assert "param" in func["parameters"]["properties"]

        tr._tools.clear()

    def test_get_llm_tools_filter_enabled(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()

        @tr.register(name="tool_x", description="X", category="search")
        async def tool_x() -> dict:
            return {}

        @tr.register(name="tool_y", description="Y", category="compute")
        async def tool_y() -> dict:
            return {}

        tools = tr.get_llm_tools(enabled_tools={"tool_x"})
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "tool_x"

        tr._tools.clear()

    @pytest.mark.asyncio
    async def test_disabled_tool_is_hidden_and_not_executable(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

        @tr.register(name="toggle_me", description="可启停工具", category="general")
        async def toggle_me() -> dict:
            return {"ok": True}

        assert tr.set_enabled("toggle_me", False)
        assert not tr.get("toggle_me").enabled
        assert tr.get_llm_tools() == []

        result = await tr.execute("toggle_me", {})
        assert not result.success
        assert "disabled" in result.error

        stats = tr.stats()
        assert stats["enabled_tools"] == 0
        assert stats["tools"]["toggle_me"]["enabled"] is False
        assert stats["tools"]["toggle_me"]["description"] == "可启停工具"

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

    @pytest.mark.asyncio
    async def test_execute_async_tool(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._cache.clear()

        @tr.register(name="echo", description="回显", category="general")
        async def echo(message: str) -> dict:
            return {"echo": message}

        result = await tr.execute("echo", {"message": "hello"})
        assert result.success
        assert result.data["echo"] == "hello"
        assert result.duration_ms > 0
        assert not result.from_cache

        tr._tools.clear()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        result = await tr.execute("nonexistent", {})
        assert not result.success
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_execute_cache_hit(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._cache.clear()

        call_count = 0

        @tr.register(name="cached_tool", description="缓存工具", category="general", cache_ttl_seconds=60.0)
        async def cached_tool(value: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"value": value, "call": call_count}

        # 第一次调用
        r1 = await tr.execute("cached_tool", {"value": "x"})
        assert r1.success
        assert call_count == 1

        # 第二次调用应命中缓存
        r2 = await tr.execute("cached_tool", {"value": "x"})
        assert r2.success
        assert r2.from_cache
        assert call_count == 1  # 未增加

        # 不同参数不命中缓存
        r3 = await tr.execute("cached_tool", {"value": "y"})
        assert r3.success
        assert not r3.from_cache
        assert call_count == 2

        tr._tools.clear()
        tr._cache.clear()

    def test_stats(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()

        @tr.register(name="stat_tool", description="统计工具", category="general")
        async def stat_tool() -> dict:
            return {}

        s = tr.stats()
        assert s["registered_tools"] >= 1
        assert s["enabled_tools"] >= 1
        assert "stat_tool" in s["tools"]
        assert s["tools"]["stat_tool"]["enabled"] is True

        tr._tools.clear()

    def test_tool_definition_success_rate(self, monkeypatch) -> None:
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import ToolDefinition

        td = ToolDefinition(
            name="test",
            description="测试",
            handler=lambda: None,
            category="general",
        )
        assert td.success_rate == 1.0  # 默认 1.0
        td.total_calls = 10
        td.total_success = 8
        assert td.success_rate == 0.8
        assert td.avg_duration_ms == 0.0
        td.total_duration_ms = 500.0
        assert td.avg_duration_ms == 50.0

    @pytest.mark.asyncio
    async def test_business_tools_register_idempotently(self, monkeypatch) -> None:
        _import_module("app.business_tools", monkeypatch)
        from app.business_tools import ensure_business_tools_registered
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

        ensure_business_tools_registered()
        ensure_business_tools_registered()

        expected = {
            "backup_cleanup_dry_run",
            "data_controls_dry_run",
            "kb_scope_summary",
            "workflow_trace_summary",
            "tool_registry_stats",
        }
        assert expected.issubset(set(tr.tool_names))
        system_names = [tool.name for tool in tr.list_by_category("system")]
        for name in expected:
            assert system_names.count(name) == 1
        backup_schema = tr.get("backup_cleanup_dry_run").parameters
        assert backup_schema["additionalProperties"] is False
        assert "apply" not in backup_schema["properties"]
        assert "delete_candidates" not in backup_schema["properties"]
        data_controls_schema = tr.get("data_controls_dry_run").parameters
        assert data_controls_schema["additionalProperties"] is False
        assert data_controls_schema["properties"]["scopes"]["items"]["enum"] == [
            "memory",
            "usage",
            "export_rag",
        ]

        scope_result = await tr.execute(
            "kb_scope_summary",
            {"scope_snapshot": {"corpus_ids": ["kb:a", "kb:b"], "document_count": 3}},
        )
        assert scope_result.success
        assert scope_result.data["corpus_count"] == 2
        assert scope_result.data["document_count"] == 3

        trace_result = await tr.execute(
            "workflow_trace_summary",
            {
                "workflow_run": {
                    "workflow_state": {
                        "response": {
                            "llm_trace": {"model_resolved": "test-model", "fallback_used": False},
                            "semantic_cache": {"hit": True},
                            "hallucination": {"passed": True},
                        }
                    },
                    "workflow_events": [
                        {"stage": "retrieval_completed", "status": "running", "evidence_count": 2, "retrieval_ms": 18.5},
                        {"stage": "persisted", "status": "completed", "evidence_count": 2, "retrieval_ms": 18.5},
                    ],
                    "tool_calls": [{"tool": "search", "success": True}],
                }
            },
        )
        assert trace_result.success
        assert trace_result.data["trace_completeness"] >= 0.8
        assert trace_result.data["tool_success_rate"] == 1.0
        assert trace_result.data["timeline"][0]["stage"] == "retrieval_completed"
        assert trace_result.data["failure_summary"]["failed"] is False

        backup_result = await tr.execute(
            "backup_cleanup_dry_run",
            {
                "retention_days": 7,
                "max_candidates": 2,
                "reason": "review E:/secret/project/backups before cleanup",
                "candidate_paths": [
                    "E:/secret/project/backups/a.zip",
                    {"path": "/srv/private/backups/b.zip", "size_bytes": 2048},
                    {"path": "/srv/private/backups/c.zip", "size_bytes": 1024},
                ],
            },
        )
        assert backup_result.success
        assert backup_result.data["dry_run"] is True
        assert backup_result.data["apply"] is False
        assert backup_result.data["candidate_count"] == 3
        assert backup_result.data["preview_items"] == [
            {"label": "a.zip"},
            {"label": "b.zip", "size_bytes": 2048},
        ]
        assert backup_result.data["reason_present"] is True
        assert "reason" not in backup_result.data
        assert "E:/secret" not in str(backup_result.data)
        assert "/srv/private" not in str(backup_result.data)

        data_controls_result = await tr.execute(
            "data_controls_dry_run",
            {
                "scopes": ["memory", "usage", "dangerous"],
                "reason": "inspect /srv/private/export.csv only",
                "target_refs": [
                    "tenant-a/private/session-1",
                    {"path": "/srv/private/export.csv", "id": "export-1"},
                ],
            },
        )
        assert data_controls_result.success
        assert data_controls_result.data["dry_run"] is True
        assert data_controls_result.data["apply"] is False
        assert data_controls_result.data["scopes"] == ["memory", "usage"]
        assert data_controls_result.data["rejected_scopes"] == ["dangerous"]
        assert data_controls_result.data["target_count"] == 2
        assert data_controls_result.data["reason_present"] is True
        assert "reason" not in data_controls_result.data
        assert "target_refs" not in data_controls_result.data
        assert "/srv/private" not in str(data_controls_result.data)

        forbidden_payload = await tr.execute(
            "backup_cleanup_dry_run",
            {
                "apply": True,
                "delete_candidates": ["E:/secret/project/backups/a.zip"],
            },
        )
        assert not forbidden_payload.success
        assert "TypeError" in forbidden_payload.error

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

    @pytest.mark.asyncio
    async def test_workflow_trace_summary_handles_sparse_and_failed_tool_calls(self, monkeypatch) -> None:
        _import_module("app.business_tools", monkeypatch)
        from app.business_tools import ensure_business_tools_registered
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

        ensure_business_tools_registered()

        empty_result = await tr.execute("workflow_trace_summary", {})
        assert empty_result.success
        assert empty_result.data["trace_completeness"] == 0.0
        assert empty_result.data["tool_call_count"] == 0
        assert empty_result.data["tool_success_rate"] == 0.0
        assert empty_result.data["model_route"] == ""
        assert empty_result.data["fallback_used"] is False
        assert empty_result.data["cache_hit"] is False
        assert empty_result.data["hallucination_passed"] is None
        assert empty_result.data["timeline"] == []
        assert empty_result.data["failure_summary"]["failed"] is False
        assert empty_result.data["resume_summary"]["can_resume"] is False

        partial_state_result = await tr.execute(
            "workflow_trace_summary",
            {
                "workflow_state": {
                    "llm_trace": {
                        "model": "test-model-lite",
                        "fallback_used": True,
                    },
                    "stage": "generation_completed",
                    "resume_target": "persist_message",
                    "resume": {"resumed": True, "source_stage": "generation_completed", "source_run_id": "run-1"},
                },
                "tool_calls": [],
            },
        )
        assert partial_state_result.success
        assert partial_state_result.data["trace_completeness"] == 0.5
        assert partial_state_result.data["tool_call_count"] == 0
        assert partial_state_result.data["tool_success_rate"] == 0.0
        assert partial_state_result.data["model_route"] == "test-model-lite"
        assert partial_state_result.data["fallback_used"] is True
        assert partial_state_result.data["cache_hit"] is False
        assert partial_state_result.data["hallucination_passed"] is None
        assert partial_state_result.data["timeline"][0]["stage"] == "generation_completed"
        assert partial_state_result.data["resume_summary"]["can_resume"] is True
        assert partial_state_result.data["resume_summary"]["resume_target"] == "persist_message"

        failed_call_result = await tr.execute(
            "workflow_trace_summary",
            {
                "workflow_state": {
                    "stage": "failed",
                    "error": {"type": "RuntimeError", "detail": "answer generation failed"},
                    "response": {
                        "llm_trace": {
                            "route": "quality",
                            "fallback_model": "test-fallback",
                        },
                        "semantic_cache": {"cache_hit": False},
                        "hallucination": {"passed": False},
                    }
                },
                "workflow_events": [
                    {"stage": "retrieval_completed", "status": "running", "evidence_count": 3, "retrieval_ms": 10.0},
                    {
                        "stage": "failed",
                        "status": "failed",
                        "evidence_count": 3,
                        "retrieval_ms": 10.0,
                        "error": {"type": "RuntimeError", "class": "runtime", "detail": "answer generation failed"},
                    },
                ],
                "tool_calls": [
                    {"tool": "search", "error": "upstream unavailable"},
                    {"tool": "summarize", "success": True},
                    {"tool": "rerank", "success": False},
                ],
            },
        )
        assert failed_call_result.success
        assert failed_call_result.data["trace_completeness"] == 1.0
        assert failed_call_result.data["tool_call_count"] == 3
        assert failed_call_result.data["tool_success_rate"] == 0.3333
        assert failed_call_result.data["model_route"] == "quality"
        assert failed_call_result.data["fallback_used"] is True
        assert failed_call_result.data["cache_hit"] is False
        assert failed_call_result.data["hallucination_passed"] is False
        assert failed_call_result.data["timeline"][1]["stage"] == "failed"
        assert failed_call_result.data["timeline"][-1]["stage"] == "tool_calls"
        assert failed_call_result.data["failure_summary"]["failed"] is True
        assert failed_call_result.data["failure_summary"]["failed_tool_call_count"] == 2
        assert "RuntimeError" in failed_call_result.data["failure_summary"]["reasons"]

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()


# ============================================================================
# 任务拆解引擎测试
# ============================================================================


class TestTaskDecomposer:
    """测试问题复杂度评估和任务拆解逻辑。"""

    def test_assess_complexity_simple_question(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import assess_complexity

        score = assess_complexity("你好")
        assert 1 <= score <= 2, f"简单问候复杂度应低，实际: {score}"

    def test_assess_complexity_comparison_question(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import assess_complexity

        score = assess_complexity("请比较v2.0和v3.0版本中退款流程的差异，并计算两个版本各涉及多少章节")
        assert score >= 3, f"复杂比较问题应触发拆解，实际: {score}"

    def test_assess_complexity_multi_step(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import assess_complexity

        score = assess_complexity("先列出所有申请类型，然后分析每种类型的审批条件，最后总结最常见的拒绝原因")
        assert score >= 3, f"多步推理应高复杂度，实际: {score}"

    def test_assess_complexity_with_context(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import assess_complexity

        score = assess_complexity(
            "退款流程是什么？",
            context={"corpus_ids": ["a", "b", "c", "d"], "has_version_conflict": True},
        )
        assert score >= 3, f"多知识库+版本冲突应提升复杂度，实际: {score}"

    def test_build_execution_order_simple(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import _build_execution_order, SubTask

        # 无依赖：全部可并行
        tasks = [
            SubTask(id="t1", description="任务1", question="?1", category="retrieval"),
            SubTask(id="t2", description="任务2", question="?2", category="retrieval"),
        ]
        order = _build_execution_order(tasks)
        assert len(order) == 1  # 只有一组
        assert len(order[0]) == 2  # 两个任务都在同一组

    def test_build_execution_order_with_deps(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import _build_execution_order, SubTask

        # t3 依赖 t1 和 t2
        tasks = [
            SubTask(id="t1", description="任务1", question="?1", category="retrieval"),
            SubTask(id="t2", description="任务2", question="?2", category="retrieval"),
            SubTask(id="t3", description="任务3", question="?3", depends_on=["t1", "t2"], category="reasoning"),
        ]
        order = _build_execution_order(tasks)
        assert len(order) == 2  # 两组
        assert "t3" in order[1]  # t3 在第二组
        assert "t1" in order[0] and "t2" in order[0]  # t1,t2 在第一组

    def test_build_execution_order_empty(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import _build_execution_order

        assert _build_execution_order([]) == []

    def test_decomposition_result_defaults(self, monkeypatch) -> None:
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import DecompositionResult

        result = DecompositionResult(original_question="测试", complexity_score=1)
        assert not result.requires_decomposition
        assert result.sub_tasks == []
        assert result.execution_order == []


# ============================================================================
# Agent 反思闭环测试
# ============================================================================


class TestAgentReflection:
    """测试输出自检、失败分析和策略记忆。"""

    def test_selfcheck_result_defaults(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import SelfCheckResult

        check = SelfCheckResult(
            passed=True,
            completeness_score=0.9,
            accuracy_score=0.95,
            citation_score=0.88,
            confidence=0.91,
        )
        assert check.passed
        assert check.completeness_score == 0.9
        assert not check.needs_retry

    def test_selfcheck_result_needs_retry(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import SelfCheckResult

        check = SelfCheckResult(
            passed=False,
            completeness_score=0.3,
            accuracy_score=0.2,
            citation_score=0.1,
            issues=["编造了不存在的引用"],
            needs_retry=True,
            retry_hint="仅使用证据中明确包含的信息",
            confidence=0.2,
        )
        assert check.needs_retry
        assert len(check.issues) == 1

    def test_failure_analysis_timeout(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import _quick_failure_analysis

        analysis = _quick_failure_analysis(
            "search_scope",
            "Request timed out after 30 seconds",
            {"query": "test"},
        )
        assert analysis is not None
        assert analysis.root_cause == "timeout"
        assert analysis.recoverable
        assert analysis.suggested_action == "retry"

    def test_failure_analysis_empty_result(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import _quick_failure_analysis

        analysis = _quick_failure_analysis(
            "search_corpus",
            "no result found for query",
            {"query": "nonexistent"},
        )
        assert analysis is not None
        assert analysis.root_cause == "retrieval_empty"
        assert "expand_scope" in analysis.suggested_action

    def test_failure_analysis_permission_denied(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import _quick_failure_analysis

        analysis = _quick_failure_analysis(
            "delete_document",
            "Permission denied: forbidden",
            {},
        )
        assert analysis is not None
        assert not analysis.recoverable
        assert analysis.suggested_action == "give_up"

    def test_failure_analysis_unknown_returns_none(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import _quick_failure_analysis

        # 未知错误类型返回 None，交给 LLM 分析
        analysis = _quick_failure_analysis(
            "custom_tool",
            "unexpected internal error code 0xFF",
            {},
        )
        assert analysis is None

    def test_strategy_record_and_retrieve(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import AgentReflector, StrategyRecord

        reflector = AgentReflector(
            build_chat_model_fn=lambda **kw: None,
            settings=type("Settings", (), {"model": "test", "default_max_tokens": 100})(),
        )

        reflector.record_strategy(
            scenario_key="multi_version_comparison",
            approach="分别检索各版本 → 比较差异 → 汇总",
            tool_sequence=["search_scope", "search_corpus"],
            success=True,
        )

        strategy = reflector.get_strategy("multi_version_comparison")
        assert strategy is not None
        assert strategy.success_rate > 0.5
        assert len(strategy.tool_sequence) == 2

        strategies = reflector.list_strategies(min_success_rate=0.5)
        assert len(strategies) >= 1

    def test_strategy_success_rate_update(self, monkeypatch) -> None:
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import AgentReflector

        reflector = AgentReflector(
            build_chat_model_fn=lambda **kw: None,
            settings=type("Settings", (), {"model": "test", "default_max_tokens": 100})(),
        )

        # 3 次成功，1 次失败
        for i in range(3):
            reflector.record_strategy("test_strategy", "approach A", ["tool1"], success=True)
        reflector.record_strategy("test_strategy", "approach A", ["tool1"], success=False)

        strategy = reflector.get_strategy("test_strategy")
        assert strategy is not None
        # 指数移动平均后成功率应 > 0.5
        assert strategy.success_rate > 0.5


# ============================================================================
# 记忆提取测试
# ============================================================================


class TestMemoryExtractor:
    """测试记忆三元组模型和冲突解决。"""

    def test_memory_triple_creation(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import MemoryTriple

        triple = MemoryTriple(
            subject="用户角色",
            predicate="是",
            object="后端开发工程师",
            memory_type="preference",
            confidence=0.95,
        )
        assert triple.subject == "用户角色"
        assert triple.memory_type == "preference"
        assert triple.confidence == 0.95

    def test_memory_entry_creation(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import MemoryEntry

        entry = MemoryEntry(
            id="mem-001",
            user_id="user-001",
            memory_type="fact",
            subject="当前版本",
            predicate="是",
            object="v3.0",
            embedding_id="emb-001",
            confidence=0.9,
            source_session_id="session-001",
        )
        assert entry.memory_type == "fact"
        assert entry.is_active  # 默认活跃

    def test_format_messages(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import _format_messages

        messages = [
            {"role": "user", "content": "我是后端工程师，负责支付系统"},
            {"role": "assistant", "content": "明白了，您是负责支付系统的后端工程师。"},
        ]
        result = _format_messages(messages)
        assert "[user]" in result
        assert "后端工程师" in result

    def test_format_messages_truncation(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import _format_messages

        # 超过 12 条时只取最近 12 条
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
        result = _format_messages(messages)
        lines = result.strip().split("\n")
        assert len(lines) <= 12

    def test_parse_json_response_markdown_block(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import _parse_json_response

        response = """```json
{"memories": [{"subject": "test", "predicate": "is", "object": "value", "memory_type": "fact", "confidence": 0.9}]}
```"""
        parsed = _parse_json_response(response)
        assert len(parsed.get("memories", [])) == 1

    def test_parse_json_response_plain(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import _parse_json_response

        response = '{"memories": []}'
        parsed = _parse_json_response(response)
        assert parsed.get("memories") == []

    def test_parse_json_response_invalid(self, monkeypatch) -> None:
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import _parse_json_response

        response = "这不是有效的JSON"
        parsed = _parse_json_response(response)
        assert parsed == {}


# ============================================================================
# 集成联动测试
# ============================================================================


class TestIntegration:
    """测试各模块间的接口兼容性。"""

    def test_tool_registry_compatible_with_agent(self, monkeypatch) -> None:
        """工具注册中心产出的工具定义应与 Agent 兼容。"""
        _import_module("app.tool_registry", monkeypatch)
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()

        @tr.register(name="search_scope", description="跨语料库搜索", category="search")
        async def search_scope(search_question: str, limit: int = 8) -> dict:
            return {"result_count": 0, "summary": "no results"}

        llm_tools = tr.get_llm_tools()
        assert len(llm_tools) == 1
        assert llm_tools[0]["type"] == "function"
        func = llm_tools[0]["function"]
        # 兼容 OpenAI function-calling 格式
        assert "name" in func
        assert "description" in func
        assert "parameters" in func

        tr._tools.clear()

    def test_business_tools_can_extend_agent_runtime_contract(self, monkeypatch) -> None:
        _import_module("app.business_tools", monkeypatch)
        from app.business_tools import extend_with_enabled_business_tools
        from app.tool_registry import tool_registry as tr

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

        tools = []
        extend_with_enabled_business_tools(tools, {"search_scope"})
        assert tools == []
        assert "kb_scope_summary" not in tr.tool_names

        extend_with_enabled_business_tools(
            tools,
            {"backup_cleanup_dry_run", "data_controls_dry_run", "kb_scope_summary", "tool_registry_stats"},
        )

        assert [tool.name for tool in tools] == [
            "kb_scope_summary",
            "tool_registry_stats",
            "backup_cleanup_dry_run",
            "data_controls_dry_run",
        ]
        assert "workflow_trace_summary" in tr.tool_names

        tr.set_enabled("kb_scope_summary", False)
        tools = []
        extend_with_enabled_business_tools(
            tools,
            {"kb_scope_summary", "tool_registry_stats", "backup_cleanup_dry_run"},
        )

        assert [tool.name for tool in tools] == ["tool_registry_stats", "backup_cleanup_dry_run"]

        tr._tools.clear()
        tr._category_index.clear()
        tr._cache.clear()

    def test_decomposition_result_feeds_agent(self, monkeypatch) -> None:
        """任务拆解结果应能正确驱动 Agent 并行执行。"""
        _import_module("app.task_decomposer", monkeypatch)
        from app.task_decomposer import DecompositionResult, SubTask, _build_execution_order

        sub_tasks = [
            SubTask(id="t1", description="检索v2", question="v2退货流程", category="retrieval"),
            SubTask(id="t2", description="检索v3", question="v3退货流程", category="retrieval"),
            SubTask(id="t3", description="比较差异", question="对比v2和v3", depends_on=["t1", "t2"], category="reasoning"),
        ]
        order = _build_execution_order(sub_tasks)

        result = DecompositionResult(
            original_question="比较v2和v3退货流程差异",
            complexity_score=4,
            requires_decomposition=True,
            sub_tasks=sub_tasks,
            execution_order=order,
            reasoning="需要分别检索两个版本再比较",
        )

        # 验证：可以驱动两阶段并行执行
        assert len(result.execution_order) == 2  # 两个并行组
        assert len(result.execution_order[0]) == 2  # t1, t2 并行
        assert result.execution_order[1] == ["t3"]  # t3 依赖前两者

    def test_reflection_result_can_trigger_retry(self, monkeypatch) -> None:
        """反思自检失败时应能触发回答修正。"""
        _import_module("app.agent_reflection", monkeypatch)
        from app.agent_reflection import SelfCheckResult

        # 模拟低质量回答的自检结果
        check = SelfCheckResult(
            passed=False,
            completeness_score=0.4,
            accuracy_score=0.3,
            citation_score=0.2,
            issues=["引用[3]不存在", "声称了证据没有的事实"],
            needs_retry=True,
            retry_hint="移除编造内容，仅保留证据支持的结论",
            confidence=0.25,
        )
        assert check.needs_retry
        assert len(check.issues) >= 2
        assert check.confidence < 0.5
        assert check.retry_hint  # 有重试指导

    @pytest.mark.asyncio
    async def test_memory_store_upsert_and_search(self, monkeypatch) -> None:
        """MemoryStore 的基础接口应可调用。"""
        _import_module("app.memory_extractor", monkeypatch)
        from app.memory_extractor import MemoryStore, MemoryEntry

        store = MemoryStore(db_session_factory=lambda: None, qdrant_client=None)

        entry = MemoryEntry(
            id="test-1",
            user_id="user-1",
            memory_type="preference",
            subject="回答风格",
            predicate="偏好",
            object="简洁技术风格",
            embedding_id="emb-1",
            confidence=0.9,
            source_session_id="s1",
        )
        result = await store.upsert(entry)
        assert result is True
