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


def _assert_no_private_markers(value: object) -> None:
    text = str(value)
    assert "prompt_preview" not in text
    assert "C:/private/source.txt" not in text


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
async def test_mcp_missing_id_request_returns_null_id_response(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)

    response = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {},
        }
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert response["result"]["protocolVersion"] == adapter.MCP_PROTOCOL_FALLBACK_VERSION
    details = adapter.mcp_audit_details({"jsonrpc": "2.0", "method": "initialize"}, response)
    assert details == {"method": "initialize", "has_error": False}


@pytest.mark.asyncio
async def test_mcp_rejects_non_object_request_without_echoing_payload(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)

    response = await adapter.handle_mcp_request(["prompt_preview", "C:/private/source.txt"])

    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "Invalid Request"
    _assert_no_private_markers(response)


@pytest.mark.asyncio
async def test_mcp_rejects_non_object_params_without_echoing_payload(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    message = {
        "jsonrpc": "2.0",
        "id": "bad-params",
        "method": "tools/call",
        "params": ["prompt_preview", "C:/private/source.txt"],
    }

    response = await adapter.handle_mcp_request(message)
    details = adapter.mcp_audit_details(message, response)

    assert response["id"] == "bad-params"
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["reason"] == "params must be an object"
    assert details == {"method": "tools/call", "has_error": True, "error_code": -32602}
    _assert_no_private_markers(response)
    _assert_no_private_markers(details)


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
async def test_mcp_tool_registry_stats_projects_whitelisted_tools_only(monkeypatch) -> None:
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
            "id": "stats-1",
            "method": "tools/call",
            "params": {"name": "tool_registry_stats", "arguments": {}},
        }
    )

    result = response["result"]
    assert result["isError"] is False
    content = result["structuredContent"]
    assert set(content["tools"]) == {"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"}
    assert content["registered_tools"] == 3
    assert content["enabled_tools"] == 3
    result_text = str(result)
    assert "backup_cleanup_dry_run" not in result_text
    assert "data_controls_dry_run" not in result_text
    assert "prompt_preview" not in result_text


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
async def test_mcp_blocked_tool_error_response_does_not_echo_tool_name(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)
    message = {
        "jsonrpc": "2.0",
        "id": "blocked-private",
        "method": "tools/call",
        "params": {"name": "prompt_preview C:/private/source.txt", "arguments": {}},
    }

    response = await adapter.handle_mcp_request(message)
    details = adapter.mcp_audit_details(message, response)

    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["reason"] == "tool is not allowed"
    assert details["tool_name"] == "not_allowed"
    _assert_no_private_markers(response)
    _assert_no_private_markers(details)


@pytest.mark.asyncio
async def test_mcp_failed_tool_returns_is_error_with_sanitized_text(monkeypatch) -> None:
    adapter = _load_gateway_module("app.gateway_mcp_adapter", monkeypatch)

    async def fake_failed_workflow(**_kwargs: object) -> dict[str, object]:
        return {"success": False, "error": "workflow failed\r\n" + ("x" * 300)}

    monkeypatch.setattr(adapter, "run_tool_workflow", fake_failed_workflow)

    response = await adapter.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": "failed-tool",
            "method": "tools/call",
            "params": {"name": "kb_scope_summary", "arguments": {}},
        }
    )

    result = response["result"]
    text = result["content"][0]["text"]
    assert response["id"] == "failed-tool"
    assert "error" not in response
    assert result["isError"] is True
    assert "structuredContent" not in result
    assert text.startswith("workflow failed")
    assert "\r" not in text
    assert "\n" not in text
    assert len(text) == 240


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
