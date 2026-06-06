from __future__ import annotations

from typing import Any

from .tool_registry import tool_registry


BUSINESS_TOOL_NAMES = frozenset(
    {
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
