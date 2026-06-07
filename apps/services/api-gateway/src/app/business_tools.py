from __future__ import annotations

from typing import Any

from .tool_registry import tool_registry


BUSINESS_TOOL_NAMES = frozenset(
    {
        "backup_cleanup_dry_run",
        "data_controls_dry_run",
        "kb_scope_summary",
        "workflow_trace_summary",
        "tool_registry_stats",
    }
)
_REGISTERED = False


def ensure_business_tools_registered() -> None:
    """Register read-only business tools once for platform demos and Agent traces."""
    global _REGISTERED
    if _REGISTERED and BUSINESS_TOOL_NAMES.issubset(set(tool_registry.tool_names)):
        return

    _register_kb_scope_summary()
    _register_workflow_trace_summary()
    _register_tool_registry_stats()
    _register_backup_cleanup_dry_run()
    _register_data_controls_dry_run()
    _REGISTERED = True


def extend_with_enabled_business_tools(tools: list[Any], enabled_tools: set[str]) -> None:
    if not enabled_tools.intersection(BUSINESS_TOOL_NAMES):
        return
    ensure_business_tools_registered()
    existing_names = {str(getattr(tool, "name", "")) for tool in tools}
    for tool in tool_registry.get_langchain_tools(enabled_tools=enabled_tools, categories=["system"]):
        if tool.name not in existing_names:
            tools.append(tool)
            existing_names.add(tool.name)


def _register_kb_scope_summary() -> None:
    @tool_registry.register(
        name="kb_scope_summary",
        description="Summarize the selected knowledge-base scope without reading document content.",
        category="system",
        parameters={
            "type": "object",
            "properties": {
                "scope_snapshot": {"type": "object"},
                "corpus_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        timeout_seconds=3.0,
    )
    async def kb_scope_summary(
        scope_snapshot: dict[str, Any] | None = None,
        corpus_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        scope = dict(scope_snapshot or {})
        ids = _string_list(corpus_ids or scope.get("corpus_ids") or scope.get("selected_corpus_ids") or [])
        documents = scope.get("documents")
        if documents is None:
            documents = scope.get("document_ids")
        if isinstance(documents, dict):
            document_count = len(documents)
        elif isinstance(documents, list):
            document_count = len(documents)
        else:
            document_count = int(scope.get("document_count") or 0)
        return {
            "corpus_count": len(ids),
            "corpus_ids": ids,
            "document_count": document_count,
            "has_scope": bool(ids or document_count or scope),
        }


def _register_workflow_trace_summary() -> None:
    @tool_registry.register(
        name="workflow_trace_summary",
        description="Summarize model route, cache, tool-call and hallucination-gate metadata from one workflow trace.",
        category="system",
        parameters={
            "type": "object",
            "properties": {
                "workflow_run": {"type": "object"},
                "workflow_state": {"type": "object"},
                "tool_calls": {"type": "array", "items": {"type": "object"}},
            },
        },
        timeout_seconds=3.0,
    )
    async def workflow_trace_summary(
        workflow_run: dict[str, Any] | None = None,
        workflow_state: dict[str, Any] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        run = dict(workflow_run or {})
        state = dict(workflow_state or run.get("workflow_state") or {})
        response = dict(state.get("response") or {})
        trace = dict(response.get("llm_trace") or state.get("llm_trace") or {})
        cache = dict(response.get("semantic_cache") or state.get("semantic_cache") or {})
        hallucination = dict(response.get("hallucination") or state.get("hallucination") or {})
        calls = list(tool_calls if tool_calls is not None else run.get("tool_calls") or state.get("tool_calls") or [])
        successful_calls = [
            call for call in calls
            if bool(call.get("success", call.get("error") in (None, "")))
        ]
        return {
            "trace_completeness": _trace_completeness(trace=trace, cache=cache, hallucination=hallucination, tool_calls=calls),
            "tool_call_count": len(calls),
            "tool_success_rate": round(len(successful_calls) / max(len(calls), 1), 4),
            "model_route": trace.get("model_resolved") or trace.get("route") or trace.get("model") or "",
            "fallback_used": bool(trace.get("fallback_used") or trace.get("fallback_model")),
            "cache_hit": bool(cache.get("hit") or cache.get("cache_hit")),
            "hallucination_passed": hallucination.get("passed"),
        }


def _register_tool_registry_stats() -> None:
    @tool_registry.register(
        name="tool_registry_stats",
        description="Return read-only tool registry counts, enabled states and success-rate statistics.",
        category="system",
        parameters={"type": "object", "properties": {}},
        timeout_seconds=3.0,
    )
    async def tool_registry_stats() -> dict[str, Any]:
        return tool_registry.stats()


def _register_backup_cleanup_dry_run() -> None:
    @tool_registry.register(
        name="backup_cleanup_dry_run",
        description="Preview backup cleanup impact without deleting files or exposing full paths.",
        category="system",
        parameters={
            "type": "object",
            "properties": {
                "retention_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                "max_candidates": {"type": "integer", "minimum": 0, "maximum": 100},
                "target_scope": {"type": "string", "enum": ["workspace", "tenant", "knowledge_base", "logs"]},
                "reason": {"type": "string", "maxLength": 240},
                "candidate_paths": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "name": {"type": "string"},
                            "size_bytes": {"type": "integer", "minimum": 0},
                        },
                    },
                },
                "total_bytes": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        timeout_seconds=3.0,
    )
    async def backup_cleanup_dry_run(
        retention_days: int = 30,
        max_candidates: int = 20,
        target_scope: str = "workspace",
        reason: str = "",
        candidate_paths: list[Any] | None = None,
        total_bytes: int | None = None,
    ) -> dict[str, Any]:
        candidates = list(candidate_paths or [])
        safe_max = _clamp_int(max_candidates, minimum=0, maximum=100, default=20)
        safe_retention_days = _clamp_int(retention_days, minimum=1, maximum=3650, default=30)
        safe_scope = str(target_scope or "workspace").strip() or "workspace"
        if safe_scope not in {"workspace", "tenant", "knowledge_base", "logs"}:
            safe_scope = "workspace"
        bytes_from_candidates = sum(_candidate_size_bytes(item) for item in candidates)
        reclaimable_bytes = max(int(total_bytes or 0), bytes_from_candidates)
        return {
            "dry_run": True,
            "apply": False,
            "operation": "backup_cleanup_preview",
            "candidate_count": len(candidates),
            "preview_count": min(len(candidates), safe_max),
            "retention_days": safe_retention_days,
            "max_candidates": safe_max,
            "target_scope": safe_scope,
            "reclaimable_bytes": reclaimable_bytes,
            "preview_items": [_redact_path_ref(item) for item in candidates[:safe_max]],
            "reason_present": bool(str(reason or "").strip()),
            "reason_length": min(len(str(reason or "")), 240),
            "safety": _dry_run_safety("admin_read"),
        }


def _register_data_controls_dry_run() -> None:
    @tool_registry.register(
        name="data_controls_dry_run",
        description="Preview data-control maintenance actions without mutating memory, usage or RAG export data.",
        category="system",
        parameters={
            "type": "object",
            "properties": {
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["memory", "usage", "export_rag"]},
                },
                "action": {
                    "type": "string",
                    "enum": ["audit", "retention_review", "export_readiness"],
                },
                "max_targets": {"type": "integer", "minimum": 0, "maximum": 100},
                "reason": {"type": "string", "maxLength": 240},
                "target_refs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "path": {"type": "string"},
                            "type": {"type": "string"},
                        },
                    },
                },
            },
            "additionalProperties": False,
        },
        timeout_seconds=3.0,
    )
    async def data_controls_dry_run(
        scopes: list[str] | None = None,
        action: str = "audit",
        max_targets: int = 20,
        reason: str = "",
        target_refs: list[Any] | None = None,
    ) -> dict[str, Any]:
        allowed_scopes = {"memory", "usage", "export_rag"}
        requested_scopes = _string_list(scopes or [])
        selected_scopes = [scope for scope in requested_scopes if scope in allowed_scopes]
        rejected_scopes = [scope for scope in requested_scopes if scope not in allowed_scopes]
        if not selected_scopes:
            selected_scopes = sorted(allowed_scopes)
        safe_action = str(action or "audit").strip() or "audit"
        if safe_action not in {"audit", "retention_review", "export_readiness"}:
            safe_action = "audit"
        safe_max = _clamp_int(max_targets, minimum=0, maximum=100, default=20)
        refs = list(target_refs or [])
        return {
            "dry_run": True,
            "apply": False,
            "operation": "data_controls_preview",
            "action": safe_action,
            "scopes": selected_scopes,
            "rejected_scopes": rejected_scopes,
            "target_count": len(refs),
            "preview_count": min(len(refs), safe_max),
            "max_targets": safe_max,
            "reason_present": bool(str(reason or "").strip()),
            "reason_length": min(len(str(reason or "")), 240),
            "control_summary": {
                "memory": "review retention and export eligibility only",
                "usage": "review aggregate usage records only",
                "export_rag": "review export readiness only",
            },
            "safety": _dry_run_safety("admin_read"),
        }


def _trace_completeness(
    *,
    trace: dict[str, Any],
    cache: dict[str, Any],
    hallucination: dict[str, Any],
    tool_calls: list[dict[str, Any]],
) -> float:
    checks = [
        bool(trace),
        bool(trace.get("model_resolved") or trace.get("route") or trace.get("model")),
        "fallback_used" in trace or "fallback_model" in trace,
        bool(cache),
        bool(hallucination),
        len(tool_calls) > 0,
    ]
    return round(sum(1 for item in checks if item) / len(checks), 4)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clamp_int(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _candidate_size_bytes(item: Any) -> int:
    if not isinstance(item, dict):
        return 0
    try:
        return max(int(item.get("size_bytes") or item.get("bytes") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _redact_path_ref(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        raw_ref = item.get("name") or item.get("file_name") or item.get("path") or item.get("uri") or item.get("id")
        size_bytes = _candidate_size_bytes(item)
    else:
        raw_ref = item
        size_bytes = 0
    label = _basename_only(raw_ref)
    payload: dict[str, Any] = {"label": label or "redacted"}
    if size_bytes:
        payload["size_bytes"] = size_bytes
    return payload


def _basename_only(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    text = text.rstrip("/")
    if not text:
        return ""
    return text.rsplit("/", 1)[-1][:120]


def _dry_run_safety(required_permission: str) -> dict[str, Any]:
    return {
        "required_permission": required_permission,
        "destructive_actions_allowed": False,
        "mutates_state": False,
        "redacts_sensitive_refs": True,
    }
