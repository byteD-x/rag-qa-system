from __future__ import annotations

from typing import Any

from .business_tools import BUSINESS_TOOL_NAMES, ensure_business_tools_registered
from .tool_registry import ToolRegistry, ToolResult, tool_registry


WORKFLOW_MODE_DIRECT = "direct"
WORKFLOW_MODE_PLAN_REFLECT_REPAIR = "plan_reflect_repair"
ALLOWED_WORKFLOW_MODES = {WORKFLOW_MODE_DIRECT, WORKFLOW_MODE_PLAN_REFLECT_REPAIR}


async def run_tool_workflow(
    *,
    tool_name: str,
    payload: dict[str, Any] | None = None,
    workflow_mode: str = WORKFLOW_MODE_DIRECT,
    registry: ToolRegistry | None = None,
    allowed_tools: set[str] | None = None,
) -> dict[str, Any]:
    selected_registry = registry or tool_registry
    ensure_business_tools_registered()
    mode = _normalize_workflow_mode(workflow_mode)
    params = dict(payload or {})
    allowed = set(BUSINESS_TOOL_NAMES) if allowed_tools is None else set(allowed_tools)
    if tool_name not in allowed:
        result = ToolResult(tool_name=tool_name, success=False, error="tool is not allowed for controlled workflow")
        response = _workflow_response(mode=mode, tool_name=tool_name, result=result, repair_count=0)
        if mode == WORKFLOW_MODE_PLAN_REFLECT_REPAIR:
            response["planning"] = _planning_metadata(tool_name=tool_name, payload=params)
            response["reflection"] = _reflection_metadata(result, repairable=False)
        return response
    if mode == WORKFLOW_MODE_DIRECT:
        result = await selected_registry.execute(tool_name, params)
        response = _workflow_response(mode=mode, tool_name=tool_name, result=result, repair_count=0)
        return response

    planning = _planning_metadata(tool_name=tool_name, payload=params)
    validation_error = _planning_validation_error(tool_name=tool_name, payload=params)
    if validation_error:
        failed = ToolResult(tool_name=tool_name, success=False, error=validation_error)
        repairable = _is_repairable(tool_name=tool_name, payload=params, result=failed)
        response = _workflow_response(mode=mode, tool_name=tool_name, result=failed, repair_count=0)
        response["planning"] = planning
        response["reflection"] = _reflection_metadata(failed, repairable=repairable)
        if not repairable:
            return response
        repaired_payload = _repair_payload(params)
        repaired_result = await selected_registry.execute(tool_name, repaired_payload)
        response = _workflow_response(
            mode=mode,
            tool_name=tool_name,
            result=repaired_result,
            repair_count=1,
        )
        response["planning"] = planning
        response["reflection"] = _reflection_metadata(failed, repairable=True)
        response["repair"] = _repair_metadata(repaired_payload)
        return response

    result = await selected_registry.execute(tool_name, params)
    response = _workflow_response(mode=mode, tool_name=tool_name, result=result, repair_count=0)
    response["planning"] = _planning_metadata(tool_name=tool_name, payload=params)
    if result.success:
        return response

    response["reflection"] = _reflection_metadata(result, repairable=False)
    return response


def _normalize_workflow_mode(value: str) -> str:
    mode = str(value or WORKFLOW_MODE_DIRECT).strip().lower()
    if mode not in ALLOWED_WORKFLOW_MODES:
        raise ValueError(f"unsupported workflow_mode: {mode}")
    return mode


def _workflow_response(
    *,
    mode: str,
    tool_name: str,
    result: ToolResult,
    repair_count: int,
) -> dict[str, Any]:
    return {
        "workflow_mode": mode,
        "tool_name": tool_name,
        "success": result.success,
        "data": dict(result.data or {}),
        "error": result.error,
        "metadata": {
            "workflow_mode": mode,
            "repair_count": repair_count,
            "tool_success": result.success,
            "from_cache": result.from_cache,
            "duration_ms": result.duration_ms,
        },
    }


def _planning_metadata(*, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": "single_controlled_tool",
        "tool_name": tool_name,
        "payload_keys": sorted(payload.keys()),
    }


def _reflection_metadata(result: ToolResult, *, repairable: bool) -> dict[str, Any]:
    return {
        "status": "failed",
        "error": result.error,
        "repairable": repairable,
    }


def _is_repairable(*, tool_name: str, payload: dict[str, Any], result: ToolResult) -> bool:
    if result.success or tool_name != "data_controls_dry_run":
        return False
    if set(payload.keys()) - {"scopes", "action", "max_targets", "reason", "target_refs"}:
        return False
    scopes = payload.get("scopes")
    return scopes == [] and "scopes" in result.error


def _repair_payload(payload: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(payload)
    repaired["scopes"] = ["memory", "usage", "export_rag"]
    return repaired


def _repair_metadata(repaired_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "applied": True,
        "reason": "data_controls_empty_scopes",
        "attempts": 1,
        "payload_keys": sorted(repaired_payload.keys()),
    }


def _planning_validation_error(*, tool_name: str, payload: dict[str, Any]) -> str:
    if tool_name == "data_controls_dry_run" and payload.get("scopes") == []:
        return "data_controls_dry_run scopes must not be empty"
    return ""
