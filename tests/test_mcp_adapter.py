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
async def test_mcp_initialize_returns_readonly_capabilities(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)

    response = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "init-1"
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "rag-qa-gateway-readonly"
    assert result["capabilities"] == {"tools": {"listChanged": False}}


@pytest.mark.asyncio
async def test_mcp_tools_list_exposes_safe_whitelist_only(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()

    response = await adapter.handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"}
    assert "backup_cleanup_dry_run" not in names
    assert "data_controls_dry_run" not in names
    assert "prompt_preview" not in str(tools)
    assert "config_audit" not in str(tools)
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)


@pytest.mark.asyncio
async def test_mcp_tools_call_returns_summary_and_structured_content(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    from app.business_tools import ensure_business_tools_registered
    from app.tool_registry import tool_registry

    tool_registry._tools.clear()
    tool_registry._category_index.clear()
    tool_registry._cache.clear()
    ensure_business_tools_registered()

    response = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "kb_scope_summary",
                "arguments": {
                    "scope_snapshot": {"corpus_ids": ["kb-1"], "document_count": 2},
                },
            },
        }
    )

    result = response["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    assert "kb_scope_summary completed" in result["content"][0]["text"]
    assert result["structuredContent"]["corpus_ids"] == ["kb-1"]
    assert result["structuredContent"]["document_count"] == 2
    assert "prompt_preview" not in str(result)


@pytest.mark.asyncio
async def test_mcp_tools_call_rejects_blocked_tools_and_non_object_arguments(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)

    blocked = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": "blocked",
            "method": "tools/call",
            "params": {"name": "data_controls_dry_run", "arguments": {}},
        }
    )
    assert blocked["error"]["code"] == -32602
    assert blocked["error"]["data"]["reason"] == "tool is not allowed"

    invalid_args = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": "invalid-args",
            "method": "tools/call",
            "params": {"name": "tool_registry_stats", "arguments": []},
        }
    )
    assert invalid_args["error"]["code"] == -32602
    assert invalid_args["error"]["data"]["reason"] == "arguments must be an object"


@pytest.mark.asyncio
async def test_mcp_audit_details_redacts_non_whitelisted_tool_name(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    leaked_tool_name = "prompt_preview C:/private/source.txt"
    message = {
        "jsonrpc": "2.0",
        "id": "blocked",
        "method": "tools/call",
        "params": {"name": leaked_tool_name, "arguments": {}},
    }

    response = await adapter.handle_mcp_request(message)
    details = adapter.mcp_audit_details(message, response)

    assert response["error"]["code"] == -32602
    assert details["has_error"] is True
    assert details["tool_name"] == "not_allowed"
    details_text = str(details)
    assert "prompt_preview" not in details_text
    assert "C:/private/source.txt" not in details_text


@pytest.mark.asyncio
async def test_mcp_unknown_method_returns_jsonrpc_error(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    leaked_method = "prompt_preview C:/private/source.txt"
    message = {"jsonrpc": "2.0", "id": 9, "method": leaked_method}

    response = await adapter.handle_mcp_request(message)
    details = adapter.mcp_audit_details(message, response)

    assert response["id"] == 9
    assert response["error"]["code"] == -32601
    assert response["error"]["message"] == "Method not found"
    assert details["method"] == "not_allowed"
    response_text = str(response)
    details_text = str(details)
    assert "prompt_preview" not in response_text
    assert "prompt_preview" not in details_text
    assert "C:/private/source.txt" not in response_text
    assert "C:/private/source.txt" not in details_text
