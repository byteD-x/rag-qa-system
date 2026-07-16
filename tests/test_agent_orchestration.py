"""多 Agent 协作与成本预算模块测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

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
