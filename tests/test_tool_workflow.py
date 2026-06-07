from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _load_gateway_module(module_name: str, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://test.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("KB_SERVICE_URL", "http://localhost:8200")
    monkeypatch.setenv("GATEWAY_GRAPH_CHECKPOINTER", "memory")

    target = str(GATEWAY_SRC)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()
    module = importlib.import_module(module_name)
    return importlib.reload(module)


@pytest.mark.asyncio
async def test_direct_workflow_keeps_plain_tool_result(monkeypatch) -> None:
    tool_workflow = _load_gateway_module("app.tool_workflow", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()

    result = await tool_workflow.run_tool_workflow(
        tool_name="data_controls_dry_run",
        payload={"scopes": []},
    )

    assert result["success"] is True
    assert result["workflow_mode"] == "direct"
    assert result["metadata"]["repair_count"] == 0
    assert "planning" not in result
    assert "reflection" not in result
    assert "repair" not in result


@pytest.mark.asyncio
async def test_plan_reflect_repair_repairs_empty_data_control_scopes_once(monkeypatch) -> None:
    tool_workflow = _load_gateway_module("app.tool_workflow", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()

    result = await tool_workflow.run_tool_workflow(
        tool_name="data_controls_dry_run",
        payload={"scopes": [], "action": "audit"},
        workflow_mode="plan_reflect_repair",
    )

    assert result["success"] is True
    assert result["workflow_mode"] == "plan_reflect_repair"
    assert result["metadata"]["repair_count"] == 1
    assert result["planning"]["tool_name"] == "data_controls_dry_run"
    assert result["reflection"]["repairable"] is True
    assert result["repair"]["applied"] is True
    assert result["data"]["scopes"] == ["memory", "usage", "export_rag"]


@pytest.mark.asyncio
async def test_plan_reflect_repair_does_not_repair_unknown_or_dangerous_payload(monkeypatch) -> None:
    tool_workflow = _load_gateway_module("app.tool_workflow", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()

    unknown = await tool_workflow.run_tool_workflow(
        tool_name="unknown_tool",
        payload={},
        workflow_mode="plan_reflect_repair",
    )
    assert unknown["success"] is False
    assert unknown["metadata"]["repair_count"] == 0
    assert "repair" not in unknown
    assert unknown["reflection"]["repairable"] is False

    dangerous = await tool_workflow.run_tool_workflow(
        tool_name="data_controls_dry_run",
        payload={"scopes": [], "apply": True},
        workflow_mode="plan_reflect_repair",
    )
    assert dangerous["success"] is False
    assert dangerous["metadata"]["repair_count"] == 0
    assert "repair" not in dangerous
    assert dangerous["reflection"]["repairable"] is False


@pytest.mark.asyncio
async def test_tool_workflow_rejects_non_business_tool(monkeypatch) -> None:
    tool_workflow = _load_gateway_module("app.tool_workflow", monkeypatch)
    from app.tool_registry import ToolDefinition, tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    tool_registry.register_direct(
        ToolDefinition(
            name="custom_registered_tool",
            description="custom read tool",
            handler=lambda: {"ok": True},
            is_async=False,
        )
    )

    result = await tool_workflow.run_tool_workflow(
        tool_name="custom_registered_tool",
        payload={},
        workflow_mode="plan_reflect_repair",
    )

    assert result["success"] is False
    assert result["metadata"]["repair_count"] == 0
    assert "repair" not in result
    assert result["reflection"]["repairable"] is False
    assert "not allowed" in result["error"]


@pytest.mark.asyncio
async def test_plan_reflect_repair_does_not_repair_confirmation_denied(monkeypatch) -> None:
    tool_workflow = _load_gateway_module("app.tool_workflow", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()
    stats_tool = tool_registry.get("tool_registry_stats")
    assert stats_tool is not None
    stats_tool.requires_confirmation = True
    try:
        result = await tool_workflow.run_tool_workflow(
            tool_name="tool_registry_stats",
            payload={},
            workflow_mode="plan_reflect_repair",
        )
    finally:
        stats_tool.requires_confirmation = False

    assert result["success"] is False
    assert result["metadata"]["repair_count"] == 0
    assert "repair" not in result
    assert result["reflection"]["repairable"] is False
    assert "confirmation" in result["error"]
