"""多 Agent 协作与成本预算模块测试。"""

from __future__ import annotations

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
# Agent 编排器测试
# ============================================================================


class TestAgentOrchestrator:
    def test_plan_basic(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        plan = orchestrator._decompose_question(
            "v3.0版本部署配置参数是什么",
            {"corpus_ids": ["kb:1"]},
            ["search_scope", "search_corpus"],
        )
        assert len(plan) >= 2  # 至少 RETRIEVER + SYNTHESIZER
        # SYNTHESIZER 应该依赖其他任务
        synthesizer = [t for t in plan if t.worker_type == "synthesizer"]
        assert len(synthesizer) == 1
        assert len(synthesizer[0].depends_on) > 0

    def test_plan_with_compare(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        plan = orchestrator._decompose_question(
            "v3.0和v2.0的区别是什么",
            {"corpus_ids": ["kb:1"]},
            ["search_scope"],
        )
        # 应有 COMPARATOR
        comparators = [t for t in plan if t.worker_type == "comparator"]
        assert len(comparators) > 0

    def test_plan_with_multi_corpus(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        plan = orchestrator._decompose_question(
            "支付系统退款流程",
            {"corpus_ids": ["kb:1", "kb:2", "kb:3"]},
            ["search_scope"],
        )
        # 多知识库 → ANALYZER
        analyzers = [t for t in plan if t.worker_type == "analyzer"]
        assert len(analyzers) > 0

    def test_execution_order(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator, SubTask, WorkerType

        orchestrator = AgentOrchestrator()
        tasks = [
            SubTask(id="t0", description="检索", worker_type=WorkerType.RETRIEVER.value, priority=8),
            SubTask(id="t1", description="分析", worker_type=WorkerType.ANALYZER.value, depends_on=["t0"], priority=6),
            SubTask(id="t2", description="综合", worker_type=WorkerType.SYNTHESIZER.value, depends_on=["t0", "t1"], priority=1),
        ]
        order = orchestrator._build_execution_order(tasks)
        assert len(order) == 3
        assert order[0] == ["t0"]     # 无依赖
        assert order[1] == ["t1"]     # 依赖 t0
        assert order[2] == ["t2"]     # 依赖 t0, t1

    def test_aggregate_evidence_dedup(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator, WorkerResult

        results = [
            WorkerResult(task_id="t0", success=True, evidence=[
                {"chunk_id": "c1", "content": "证据1"},
                {"chunk_id": "c2", "content": "证据2"},
            ]),
            WorkerResult(task_id="t1", success=True, evidence=[
                {"chunk_id": "c1", "content": "证据1"},  # 重复
                {"chunk_id": "c3", "content": "证据3"},
            ]),
        ]
        aggregated = AgentOrchestrator._aggregate_evidence(results)
        assert len(aggregated) == 3  # 去重后 3 条
        chunks = {e["chunk_id"] for e in aggregated}
        assert chunks == {"c1", "c2", "c3"}

    @pytest.mark.asyncio
    async def test_execute_with_mock_worker(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator, ExecutionPlan, WorkerType, SubTask, WorkerResult

        async def mock_retriever(task):
            return WorkerResult(
                task_id=task.id,
                success=True,
                evidence=[{"chunk_id": f"ev-{task.id}", "content": "证据"}],
                worker_type=task.worker_type,
            )

        orchestrator = AgentOrchestrator()
        plan = ExecutionPlan(
            plan_id="test-plan",
            question="测试问题",
            sub_tasks=[
                SubTask(id="t0", description="检索", worker_type=WorkerType.RETRIEVER.value, priority=8),
                SubTask(id="t1", description="综合", worker_type=WorkerType.SYNTHESIZER.value,
                        depends_on=["t0"], priority=1),
            ],
            execution_order=[["t0"], ["t1"]],
        )
        result = await orchestrator.execute(
            plan,
            worker_fn_map={
                "retriever": mock_retriever,
                "synthesizer": mock_retriever,
            },
        )
        assert result.success_count == 2
        assert result.failure_count == 0
        assert len(result.aggregated_evidence) > 0

    @pytest.mark.asyncio
    async def test_execute_worker_timeout(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.agent_orchestrator import AgentOrchestrator, ExecutionPlan, WorkerType, SubTask

        async def slow_worker(task):
            import asyncio
            await asyncio.sleep(5)
            return []

        orchestrator = AgentOrchestrator(worker_timeout=0.1)  # 极短超时
        plan = ExecutionPlan(
            plan_id="test-timeout",
            sub_tasks=[SubTask(id="t0", description="慢任务", worker_type=WorkerType.RETRIEVER.value)],
            execution_order=[["t0"]],
        )
        result = await orchestrator.execute(
            plan,
            worker_fn_map={"retriever": slow_worker},
        )
        assert result.failure_count == 1


# ============================================================================
# 成本预算测试
# ============================================================================


class TestCostEstimation:
    def test_estimate_cost_basic(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import estimate_cost

        result = estimate_cost(1000, 500)
        assert result["total_cost"] > 0
        assert result["input_cost"] > 0
        assert result["output_cost"] > 0

    def test_estimate_cost_with_model(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import estimate_cost

        result = estimate_cost(1000, 500, model_name="gpt-4")
        assert result["total_cost"] > 0

    def test_estimate_tokens_to_cost(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import estimate_tokens_to_cost

        cost = estimate_tokens_to_cost(1000, model_name="deepseek-v3")
        assert cost > 0
        # deepseek 应该比 gpt-4 便宜
        cost_gpt4 = estimate_tokens_to_cost(1000, model_name="gpt-4")
        assert cost < cost_gpt4


class TestCostBudgetController:
    def test_configure_and_check_healthy(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController, BudgetStatus

        ctrl = CostBudgetController()
        ctrl.configure("user-1", "session-1", max_tokens=10000)
        allowed, state = ctrl.check("user-1", "session-1", 100)
        assert allowed
        assert state.status == BudgetStatus.HEALTHY.value

    def test_check_warning(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController, BudgetStatus

        ctrl = CostBudgetController()
        ctrl.configure("user-1", "session-1", max_tokens=1000)
        allowed, state = ctrl.check("user-1", "session-1", 850)  # 85%
        assert allowed
        assert state.status == BudgetStatus.WARNING.value

    def test_check_exceeded_hard(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController, BudgetStatus

        ctrl = CostBudgetController()
        ctrl.configure("user-1", "session-1", max_tokens=1000, hard_limit=True)
        # 先消耗 800
        ctrl.record("user-1", "session-1", 800)
        # 再请求 300 → 超支
        allowed, state = ctrl.check("user-1", "session-1", 300)
        assert not allowed
        assert state.status == BudgetStatus.EXCEEDED.value

    def test_record_and_status(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController

        ctrl = CostBudgetController()
        ctrl.configure("user-1", "session-1", max_tokens=5000)
        ctrl.record("user-1", "session-1", 1000, cost=0.05)
        statuses = ctrl.status("user-1", "session-1")
        assert "session" in statuses
        assert statuses["session"].tokens_used == 1000

    def test_reset(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController

        ctrl = CostBudgetController()
        ctrl.configure("user-1", "session-1", max_tokens=5000)
        ctrl.record("user-1", "session-1", 1000)
        ctrl.reset("user-1", "session-1", level="session")
        statuses = ctrl.status("user-1", "session-1")
        assert statuses["session"].tokens_used == 0

    def test_no_config_no_block(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.cost_budget import CostBudgetController

        ctrl = CostBudgetController()
        # 未配置预算 → 不拦截
        allowed, state = ctrl.check("new-user", "new-session", 99999)
        assert allowed
