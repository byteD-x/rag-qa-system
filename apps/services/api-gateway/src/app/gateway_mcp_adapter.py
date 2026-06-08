from __future__ import annotations

import json
from typing import Any

from .business_tools import ensure_business_tools_registered
from .tool_registry import tool_registry
from .tool_workflow import WORKFLOW_MODE_DIRECT, run_tool_workflow


MCP_ADAPTER_TOOL_NAMES = frozenset({"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"})
MCP_SERVER_NAME = "rag-qa-gateway-readonly"
MCP_PROTOCOL_FALLBACK_VERSION = "2024-11-05"


async def handle_mcp_request(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")

    request_id = message.get("id")
    if message.get("jsonrpc") != "2.0":
        return _jsonrpc_error(request_id, -32600, "Invalid JSON-RPC request")

    method = str(message.get("method") or "").strip()
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _jsonrpc_error(request_id, -32602, "Invalid params", {"reason": "params must be an object"})

    if method == "initialize":
        return _jsonrpc_result(request_id, _initialize_result(params))
    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": _list_tools()})
    if method == "tools/call":
        return await _call_tool(request_id, params)
    return _jsonrpc_error(request_id, -32601, f"Method not found: {method or 'unknown'}")


def mcp_audit_details(message: Any, response: dict[str, Any]) -> dict[str, Any]:
    request = message if isinstance(message, dict) else {}
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    details: dict[str, Any] = {
        "method": str(request.get("method") or ""),
        "has_error": bool(error),
    }
    if error:
        details["error_code"] = error.get("code")
    params = request.get("params")
    if isinstance(params, dict) and str(request.get("method") or "") == "tools/call":
        details["tool_name"] = _audit_tool_name(params.get("name"))
    return details


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = str(params.get("protocolVersion") or "").strip()
    return {
        "protocolVersion": requested_version or MCP_PROTOCOL_FALLBACK_VERSION,
        "serverInfo": {
            "name": MCP_SERVER_NAME,
            "version": "0.1.0",
        },
        "capabilities": {
            "tools": {"listChanged": False},
        },
    }


def _list_tools() -> list[dict[str, Any]]:
    ensure_business_tools_registered()
    tools = tool_registry.get_llm_tools(enabled_tools=set(MCP_ADAPTER_TOOL_NAMES), categories=["system"])
    items: list[dict[str, Any]] = []
    for tool in tools:
        fn = dict(tool.get("function") or {})
        name = str(fn.get("name") or "").strip()
        if name not in MCP_ADAPTER_TOOL_NAMES:
            continue
        items.append(
            {
                "name": name,
                "description": str(fn.get("description") or ""),
                "inputSchema": dict(fn.get("parameters") or {"type": "object", "properties": {}}),
            }
        )
    return sorted(items, key=lambda item: str(item["name"]))


async def _call_tool(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(params.get("name") or "").strip()
    if not tool_name:
        return _jsonrpc_error(request_id, -32602, "Invalid params", {"reason": "tool name is required"})
    if tool_name not in MCP_ADAPTER_TOOL_NAMES:
        return _jsonrpc_error(request_id, -32602, "Invalid params", {"reason": "tool is not allowed"})

    raw_arguments = params.get("arguments", {})
    if not isinstance(raw_arguments, dict):
        return _jsonrpc_error(request_id, -32602, "Invalid params", {"reason": "arguments must be an object"})

    workflow = await run_tool_workflow(
        tool_name=tool_name,
        payload=raw_arguments,
        workflow_mode=WORKFLOW_MODE_DIRECT,
        allowed_tools=set(MCP_ADAPTER_TOOL_NAMES),
    )
    if bool(workflow.get("success")):
        return _jsonrpc_result(request_id, _tool_call_result(tool_name=tool_name, data=dict(workflow.get("data") or {})))
    return _jsonrpc_result(
        request_id,
        {
            "content": [{"type": "text", "text": _safe_text(workflow.get("error") or "tool execution failed")}],
            "isError": True,
        },
    )


def _tool_call_result(*, tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(str(key) for key in data.keys())
    summary = f"{tool_name} completed"
    if keys:
        summary = f"{summary}; fields: {', '.join(keys[:8])}"
    return {
        "content": [{"type": "text", "text": summary}],
        "structuredContent": data,
        "isError": False,
    }


def _audit_tool_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    if name in MCP_ADAPTER_TOOL_NAMES:
        return name
    return "not_allowed"


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def _safe_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return "tool execution failed"
    try:
        json.dumps(text)
    except TypeError:
        return "tool execution failed"
    return text[:240]
