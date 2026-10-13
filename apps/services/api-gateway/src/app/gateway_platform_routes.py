from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request

from shared.auth import CurrentUser

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_llm_models import discover_openai_compatible_models, llm_config_summary
from .gateway_model_config import (
    create_model_config,
    disable_model_config,
    list_model_configs,
    load_model_config,
    update_model_config,
)
from .gateway_runtime import CHAT_PERMISSION
from .gateway_runtime import gateway_db, runtime_settings
from .governance_metrics import get_governance_metrics
from .gateway_platform_store import (
    create_agent_profile,
    create_prompt_template,
    delete_agent_profile,
    delete_prompt_template,
    list_agent_profiles,
    list_prompt_templates,
    load_agent_profile,
    load_prompt_template,
    serialize_agent_profile,
    serialize_prompt_template,
    update_agent_profile,
    update_prompt_template,
)
from .gateway_schemas import (
    AgentProfileRequest,
    LLMModelDiscoveryRequest,
    ModelProviderConfigRequest,
    PromptTemplateRequest,
    ToolWorkflowRequest,
    UpdateAgentProfileRequest,
    UpdatePromptTemplateRequest,
    UpdateModelProviderConfigRequest,
    CacheConfigRequest,
    CacheInvalidateRequest,
)
from .business_tools import ensure_business_tools_registered
from .model_health import model_health_monitor
from .semantic_cache import semantic_cache
from .tool_registry import tool_registry
from .gateway_workflows import serialize_workflow_run
from shared.api_errors import raise_api_error
from .tool_workflow import run_tool_workflow


router = APIRouter()


def _require_model_admin(request: Request, user: CurrentUser, *, action: str, resource_id: str = "") -> None:
    require_permission(request, user, "kb.manage", action=action, resource_type="model_provider_config", resource_id=resource_id)


@router.get("/api/v1/platform/model-configs")
async def get_model_configs(request: Request, user: CurrentUser) -> dict[str, object]:
    _require_model_admin(request, user, action="platform.model_config.list")
    return {"items": list_model_configs()}


@router.post("/api/v1/platform/model-configs")
async def post_model_config(payload: ModelProviderConfigRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    _require_model_admin(request, user, action="platform.model_config.create")
    item = create_model_config(payload=payload.model_dump(), user_id=user.user_id)
    write_gateway_audit_event(action="platform.model_config.create", outcome="success", request=request, user=user, resource_type="model_provider_config", resource_id=str(item.get("id") or ""), scope="managed")
    return item


@router.patch("/api/v1/platform/model-configs/{config_id}")
async def patch_model_config(config_id: str, payload: UpdateModelProviderConfigRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    _require_model_admin(request, user, action="platform.model_config.update", resource_id=config_id)
    item = update_model_config(config_id, payload=payload.model_dump(exclude_unset=True))
    write_gateway_audit_event(action="platform.model_config.update", outcome="success", request=request, user=user, resource_type="model_provider_config", resource_id=config_id, scope="managed")
    return item


@router.delete("/api/v1/platform/model-configs/{config_id}")
async def remove_model_config(config_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _require_model_admin(request, user, action="platform.model_config.disable", resource_id=config_id)
    disable_model_config(config_id)
    write_gateway_audit_event(action="platform.model_config.disable", outcome="success", request=request, user=user, resource_type="model_provider_config", resource_id=config_id, scope="managed")
    return {"disabled": True, "config_id": config_id}


@router.post("/api/v1/platform/model-configs/{config_id}/test")
async def test_model_config(config_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _require_model_admin(request, user, action="platform.model_config.test", resource_id=config_id)
    row = load_model_config(config_id, include_secret=True)
    result = await discover_openai_compatible_models(
        provider=str(row.get("provider_type") or "openai-compatible"),
        base_url=str(row.get("base_url") or ""),
        credential=str(row.get("api_key") or ""),
        max_models=1,
    )
    write_gateway_audit_event(action="platform.model_config.test", outcome="success", request=request, user=user, resource_type="model_provider_config", resource_id=config_id, scope="connectivity", details={"provider": result.get("provider", "")})
    return {"ok": True, "provider": result.get("provider", ""), "model_count": result.get("count", 0)}


@router.post("/api/v1/agents/tool-workflow")
async def post_tool_workflow(payload: ToolWorkflowRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    started_at = time.perf_counter()
    require_permission(request, user, CHAT_PERMISSION, action="agent.tool_workflow.run", resource_type="tool_workflow")
    result = await run_tool_workflow(
        tool_name=payload.tool_name,
        payload=payload.payload,
        workflow_mode=payload.workflow_mode,
    )
    success = bool(result.get("success"))
    failure_reason = "" if success else _tool_workflow_failure_reason(result)
    get_governance_metrics().record_tool_workflow(
        success=success,
        duration_ms=(time.perf_counter() - started_at) * 1000,
        failure_reason=failure_reason,
    )
    write_gateway_audit_event(
        action="agent.tool_workflow.run",
        outcome="success" if success else "failed",
        request=request,
        user=user,
        resource_type="tool_workflow",
        resource_id=payload.tool_name,
        scope=str(result.get("workflow_mode") or payload.workflow_mode),
        details={"repair_count": (result.get("metadata") or {}).get("repair_count", 0)},
    )
    return result


def _tool_workflow_failure_reason(result: dict[str, object]) -> str:
    if str(result.get("workflow_mode") or "").strip() not in {"direct", "plan_reflect_repair"}:
        return "bad_workflow"
    error = str(result.get("error") or "").lower()
    if "not allowed" in error:
        return "tool_not_allowed"
    if "confirmation" in error:
        return "confirmation_required"
    if "not found" in error:
        return "tool_not_found"
    return "tool_workflow_failed"


def _platform_manage(request: Request, user: CurrentUser, *, action: str, resource_type: str) -> None:
    require_permission(request, user, "kb.manage", action=action, resource_type=resource_type)


def _platform_read(request: Request, user: CurrentUser, *, action: str, resource_type: str) -> None:
    require_permission(request, user, CHAT_PERMISSION, action=action, resource_type=resource_type)


def _run_summary(row: dict[str, object]) -> dict[str, object]:
    state = dict(row.get("workflow_state_json") or {})
    response = dict(state.get("response") or {})
    retrieval = dict(state.get("retrieval_meta") or {})
    decomposition = dict(retrieval.get("decomposition") or {})
    agent = dict(retrieval.get("agent") or {})
    latency = dict(response.get("latency") or state.get("timing") or {})
    reflection = state.get("reflection") or {}
    tool_calls = list(row.get("tool_calls_json") or [])
    return {
        "id": str(row.get("id") or ""),
        "session_id": str(row.get("session_id") or ""),
        "status": str(row.get("status") or "running"),
        "execution_mode": str(row.get("execution_mode") or "grounded"),
        "question": str(row.get("question") or ""),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
        "tool_calls_used": len(tool_calls) or int(agent.get("tool_calls_used") or 0),
        "total_latency_ms": float(latency.get("total_ms") or 0.0),
        "answer_mode": str(response.get("answer_mode") or state.get("answer_mode") or ""),
        "complexity_score": decomposition.get("complexity_score", 1),
        "requires_decomposition": bool(decomposition.get("requires_decomposition")),
        "reflection_passed": reflection.get("reflection_passed"),
    }


@router.get("/api/v1/platform/agent/runs")
async def list_platform_agent_runs(
    request: Request,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    status: str = Query(default="", max_length=32),
) -> dict[str, object]:
    _platform_read(request, user, action="platform.agent_run.list", resource_type="agent_run")
    clauses = ["user_id = %s"]
    params: list[object] = [user.user_id]
    if status.strip():
        clauses.append("status = %s")
        params.append(status.strip().lower())
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM chat_workflow_runs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT %s",
                (*params, limit),
            )
            rows = cur.fetchall()
    return {"items": [_run_summary(row) for row in rows], "total": len(rows)}


@router.get("/api/v1/platform/agent/runs/{run_id}")
async def get_platform_agent_run(run_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.agent_run.get", resource_type="agent_run")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_workflow_runs WHERE id = %s AND user_id = %s", (run_id, user.user_id))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "agent_run_not_found", "agent run not found")
    serialized = serialize_workflow_run(row)
    state = dict(serialized.get("workflow_state") or {})
    response = dict(state.get("response") or {})
    retrieval = dict(state.get("retrieval_meta") or {})
    decomposition = dict(retrieval.get("decomposition") or {})
    agent = dict(retrieval.get("agent") or {})
    timing = dict(response.get("latency") or state.get("timing") or {})
    reflection = {
        "passed": bool(state.get("reflection_passed")),
        "confidence": float(state.get("reflection_confidence") or 0.0),
        "completeness_score": float(state.get("reflection_completeness") or 0.0),
        "accuracy_score": float(state.get("reflection_accuracy") or 0.0),
        "citation_score": float(state.get("reflection_citation") or 0.0),
        "issues": list(state.get("reflection_issues") or []),
        "suggestions": list(state.get("reflection_suggestions") or []),
        "needs_retry": bool(state.get("reflection_needs_retry")),
    }
    return {
        **_run_summary(row),
        "contextualized_question": str(state.get("contextualized_question") or ""),
        "complexity_score": decomposition.get("complexity_score", 1),
        "requires_decomposition": bool(decomposition.get("requires_decomposition")),
        "sub_tasks": list(decomposition.get("sub_tasks") or []),
        "execution_order": list(decomposition.get("execution_order") or []),
        "agent_events": list(state.get("agent_events") or agent.get("events") or []),
        "tool_calls": list(serialized.get("tool_calls") or []),
        "reflection": reflection if any(reflection.values()) else None,
        "evidence_count": int(state.get("evidence_count") or 0),
        "answer_mode": str(response.get("answer_mode") or state.get("answer_mode") or ""),
        "total_latency_ms": float(timing.get("total_ms") or 0.0),
        "retrieval_ms": float(timing.get("retrieval_ms") or 0.0),
        "generation_ms": float(timing.get("generation_ms") or 0.0),
    }


@router.get("/api/v1/platform/agent/registry/summary")
async def get_platform_tool_summary(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.tool_registry.summary", resource_type="tool_registry")
    ensure_business_tools_registered()
    return tool_registry.stats()


@router.get("/api/v1/platform/agent/tools")
async def list_platform_tools(request: Request, user: CurrentUser, category: str = Query(default="", max_length=64)) -> dict[str, object]:
    _platform_read(request, user, action="platform.tool_registry.list", resource_type="tool_registry")
    ensure_business_tools_registered()
    tools = tool_registry.list_by_category(category.strip()) if category.strip() else tool_registry.list_all()
    return {"items": [tool_registry.stats()["tools"][item.name] | {"name": item.name} for item in tools]}


@router.post("/api/v1/platform/agent/tools/{tool_name}/toggle")
async def toggle_platform_tool(tool_name: str, payload: dict[str, bool], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.tool_registry.toggle", resource_type="tool",)
    ensure_business_tools_registered()
    if not tool_registry.set_enabled(tool_name, bool(payload.get("enabled"))):
        raise_api_error(404, "tool_not_found", "tool not found")
    return {"name": tool_name, "enabled": bool(payload.get("enabled"))}


@router.get("/api/v1/platform/memory/entries")
async def list_memory_entries(request: Request, user: CurrentUser, memory_type: str = Query(default="", max_length=32), limit: int = Query(default=20, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    _platform_read(request, user, action="platform.memory.list", resource_type="memory")
    clauses = ["user_id = %s"]
    params: list[object] = [user.user_id]
    if memory_type.strip():
        clauses.append("memory_type = %s")
        params.append(memory_type.strip().lower())
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            where = " AND ".join(clauses)
            cur.execute(f"SELECT COUNT(*) AS total FROM agent_memory_entries WHERE {where}", params)
            total = int((cur.fetchone() or {}).get("total") or 0)
            cur.execute(f"SELECT * FROM agent_memory_entries WHERE {where} ORDER BY updated_at DESC LIMIT %s OFFSET %s", (*params, limit, offset))
            rows = cur.fetchall()
    return {"items": [_serialize_memory(row) for row in rows], "total": total}


def _serialize_memory(row: dict[str, object]) -> dict[str, object]:
    return {"id": str(row.get("id") or ""), "user_id": str(row.get("user_id") or ""), "memory_type": str(row.get("memory_type") or "fact"), "subject": str(row.get("subject") or ""), "predicate": str(row.get("predicate") or ""), "object": str(row.get("object") or ""), "confidence": float(row.get("confidence") or 0.0), "source_session_id": str(row.get("source_session_id") or ""), "version": int(row.get("version") or 1), "is_active": bool(row.get("is_active")), "created_at": row.get("created_at"), "updated_at": row.get("updated_at")}


@router.get("/api/v1/platform/memory/search")
async def search_memory_entries(request: Request, user: CurrentUser, query: str = Query(min_length=1, max_length=512), memory_type: str = Query(default="", max_length=32), limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    _platform_read(request, user, action="platform.memory.search", resource_type="memory")
    pattern = f"%{query.strip()}%"
    clauses = ["user_id = %s", "(subject ILIKE %s OR predicate ILIKE %s OR object ILIKE %s)"]
    params: list[object] = [user.user_id, pattern, pattern, pattern]
    if memory_type.strip():
        clauses.append("memory_type = %s")
        params.append(memory_type.strip().lower())
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM agent_memory_entries WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT %s", (*params, limit))
            rows = cur.fetchall()
    return {"items": [_serialize_memory(row) for row in rows], "total": len(rows)}


@router.delete("/api/v1/platform/memory/entries/{memory_id}")
async def deactivate_memory_entry(memory_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.memory.deactivate", resource_type="memory")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE agent_memory_entries SET is_active = FALSE, updated_at = NOW() WHERE id = %s AND user_id = %s RETURNING id", (memory_id, user.user_id))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise_api_error(404, "memory_not_found", "memory entry not found")
    return {"id": memory_id, "is_active": False}


@router.get("/api/v1/platform/memory/stats")
async def get_memory_stats(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.memory.stats", resource_type="memory")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total_entries, COUNT(*) FILTER (WHERE is_active) AS active_entries FROM agent_memory_entries WHERE user_id = %s", (user.user_id,))
            summary = cur.fetchone() or {}
            cur.execute("SELECT memory_type, COUNT(*) AS count FROM agent_memory_entries WHERE user_id = %s GROUP BY memory_type ORDER BY count DESC", (user.user_id,))
            by_type = cur.fetchall()
            cur.execute("SELECT subject, COUNT(*) AS count FROM agent_memory_entries WHERE user_id = %s AND is_active GROUP BY subject ORDER BY count DESC, subject LIMIT 20", (user.user_id,))
            subjects = cur.fetchall()
    return {"total_entries": int(summary.get("total_entries") or 0), "active_entries": int(summary.get("active_entries") or 0), "by_type": {str(row.get("memory_type")): int(row.get("count") or 0) for row in by_type}, "top_subjects": [{"subject": str(row.get("subject") or ""), "count": int(row.get("count") or 0)} for row in subjects]}


@router.get("/api/v1/platform/cost/breakdown")
async def get_platform_cost_breakdown(request: Request, user: CurrentUser, period_days: int = Query(default=7, ge=1, le=90)) -> dict[str, object]:
    _platform_read(request, user, action="platform.cost.breakdown", resource_type="cost")
    where = "role = 'assistant' AND user_id = %s AND created_at >= NOW() - (%s || ' days')::interval"
    params = (user.user_id, period_days)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'prompt_tokens',''),'0')::double precision),0) AS input_tokens, COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'completion_tokens',''),'0')::double precision),0) AS output_tokens, COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}',''),'0')::double precision),0) AS total_cost, COUNT(*) AS total_calls FROM chat_messages WHERE {where}", params)
            totals = cur.fetchone() or {}
            cur.execute(f"SELECT COALESCE(NULLIF(model,''),'unknown') AS model, COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'prompt_tokens',''),'0')::double precision),0) AS input_tokens, COALESCE(SUM(COALESCE(NULLIF(usage_json ->> 'completion_tokens',''),'0')::double precision),0) AS output_tokens, COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}',''),'0')::double precision),0) AS estimated_cost, COUNT(*) AS calls FROM chat_messages WHERE {where} GROUP BY model ORDER BY estimated_cost DESC", params)
            models = cur.fetchall()
            cur.execute(f"SELECT DATE(created_at) AS day, COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}',''),'0')::double precision),0) AS cost, COUNT(*) AS calls FROM chat_messages WHERE {where} GROUP BY DATE(created_at) ORDER BY day", params)
            days = cur.fetchall()
            cur.execute(f"SELECT COALESCE(NULLIF(scope_snapshot_json ->> 'execution_mode',''),'grounded') AS scene, COALESCE(SUM(COALESCE(NULLIF(usage_json #>> '{{_meta,cost,estimated_cost}}',''),'0')::double precision),0) AS cost FROM chat_messages WHERE {where} GROUP BY scene ORDER BY cost DESC", params)
            scenes = cur.fetchall()
    total_cost = float(totals.get("total_cost") or 0.0)
    return {"by_model": [{"model": str(row.get("model")), "input_tokens": float(row.get("input_tokens") or 0), "output_tokens": float(row.get("output_tokens") or 0), "estimated_cost": float(row.get("estimated_cost") or 0), "calls": int(row.get("calls") or 0)} for row in models], "by_day": [{"date": str(row.get("day") or ""), "cost": float(row.get("cost") or 0), "calls": int(row.get("calls") or 0)} for row in days], "by_scene": [{"scene": str(row.get("scene") or ""), "cost": float(row.get("cost") or 0), "percentage": round(float(row.get("cost") or 0) / max(total_cost, 0.000001) * 100, 2)} for row in scenes], "total_cost": total_cost, "total_tokens": int(float(totals.get("input_tokens") or 0) + float(totals.get("output_tokens") or 0)), "total_calls": int(totals.get("total_calls") or 0), "currency": runtime_settings.llm_price_currency, "period_days": period_days}


@router.get("/api/v1/platform/cost/model-health")
async def get_platform_model_health(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.cost.model_health", resource_type="model_health")
    return model_health_monitor.summary()


@router.get("/api/v1/platform/cache/stats")
async def get_platform_cache_stats(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.cache.stats", resource_type="cache")
    return semantic_cache.stats()


@router.get("/api/v1/platform/cache/config")
async def get_platform_cache_config(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.cache.config.get", resource_type="cache")
    return semantic_cache.config()


@router.patch("/api/v1/platform/cache/config")
async def patch_platform_cache_config(payload: CacheConfigRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.cache.config.update", resource_type="cache")
    return semantic_cache.update_config(**payload.model_dump(exclude_none=True))


@router.post("/api/v1/platform/cache/invalidate")
async def invalidate_platform_cache(payload: CacheInvalidateRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.cache.invalidate", resource_type="cache")
    count = await semantic_cache.invalidate(**payload.model_dump())
    return {"invalidated_count": count}


@router.get("/api/v1/platform/llm/config")
async def get_llm_config(request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.llm.config.get", resource_type="llm_provider")
    return llm_config_summary()


@router.post("/api/v1/platform/llm/models/discover")
async def post_discover_llm_models(payload: LLMModelDiscoveryRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.llm.models.discover", resource_type="llm_provider")
    result = await discover_openai_compatible_models(
        provider=payload.provider,
        base_url=payload.base_url,
        credential=payload.credential,
        max_models=payload.max_models,
    )
    write_gateway_audit_event(
        action="platform.llm.models.discover",
        outcome="success",
        request=request,
        user=user,
        resource_type="llm_provider",
        scope="manual_discovery",
        details={
            "provider": result.get("provider", ""),
            "base_url": result.get("base_url", ""),
            "model_count": result.get("count", 0),
            "api_key_supplied": bool(payload.credential),
        },
    )
    return result


@router.get("/api/v1/platform/prompt-templates")
async def get_prompt_templates(request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.prompt_template.list", resource_type="prompt_template")
    return {"items": list_prompt_templates(user)}


@router.post("/api/v1/platform/prompt-templates")
async def post_prompt_template(payload: PromptTemplateRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.prompt_template.create", resource_type="prompt_template")
    item = create_prompt_template(
        user=user,
        name=payload.name,
        content=payload.content,
        visibility=payload.visibility,
        tags=payload.tags,
        favorite=payload.favorite,
    )
    write_gateway_audit_event(action="platform.prompt_template.create", outcome="success", request=request, user=user, resource_type="prompt_template", resource_id=str(item.get("id") or ""), scope="owner")
    return item


@router.get("/api/v1/platform/prompt-templates/{template_id}")
async def get_prompt_template(template_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.prompt_template.get", resource_type="prompt_template", resource_id=template_id)
    return serialize_prompt_template(load_prompt_template(template_id, user))


@router.patch("/api/v1/platform/prompt-templates/{template_id}")
async def patch_prompt_template(template_id: str, payload: UpdatePromptTemplateRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.prompt_template.update", resource_type="prompt_template", resource_id=template_id)
    item = update_prompt_template(
        template_id,
        user=user,
        name=payload.name,
        content=payload.content,
        visibility=payload.visibility,
        tags=payload.tags,
        favorite=payload.favorite,
    )
    write_gateway_audit_event(action="platform.prompt_template.update", outcome="success", request=request, user=user, resource_type="prompt_template", resource_id=template_id, scope="owner")
    return item


@router.delete("/api/v1/platform/prompt-templates/{template_id}")
async def remove_prompt_template(template_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.prompt_template.delete", resource_type="prompt_template", resource_id=template_id)
    delete_prompt_template(template_id, user=user)
    write_gateway_audit_event(action="platform.prompt_template.delete", outcome="success", request=request, user=user, resource_type="prompt_template", resource_id=template_id, scope="owner")
    return {"deleted": True, "template_id": template_id}


@router.get("/api/v1/platform/agent-profiles")
async def get_agent_profiles(request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.agent_profile.list", resource_type="agent_profile")
    return {"items": list_agent_profiles(user)}


@router.post("/api/v1/platform/agent-profiles")
async def post_agent_profile(payload: AgentProfileRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.agent_profile.create", resource_type="agent_profile")
    item = create_agent_profile(
        user=user,
        name=payload.name,
        description=payload.description,
        persona_prompt=payload.persona_prompt,
        enabled_tools=payload.enabled_tools,
        default_corpus_ids=payload.default_corpus_ids,
        prompt_template_id=payload.prompt_template_id,
    )
    write_gateway_audit_event(action="platform.agent_profile.create", outcome="success", request=request, user=user, resource_type="agent_profile", resource_id=str(item.get("id") or ""), scope="owner")
    return item


@router.get("/api/v1/platform/agent-profiles/{profile_id}")
async def get_agent_profile(profile_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.agent_profile.get", resource_type="agent_profile", resource_id=profile_id)
    row = load_agent_profile(profile_id, user)
    return serialize_agent_profile(row)


@router.patch("/api/v1/platform/agent-profiles/{profile_id}")
async def patch_agent_profile(profile_id: str, payload: UpdateAgentProfileRequest, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.agent_profile.update", resource_type="agent_profile", resource_id=profile_id)
    item = update_agent_profile(
        profile_id,
        user=user,
        name=payload.name,
        description=payload.description,
        persona_prompt=payload.persona_prompt,
        enabled_tools=payload.enabled_tools,
        default_corpus_ids=payload.default_corpus_ids,
        prompt_template_id=payload.prompt_template_id,
    )
    write_gateway_audit_event(action="platform.agent_profile.update", outcome="success", request=request, user=user, resource_type="agent_profile", resource_id=profile_id, scope="owner")
    return item


@router.delete("/api/v1/platform/agent-profiles/{profile_id}")
async def remove_agent_profile(profile_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    require_permission(request, user, CHAT_PERMISSION, action="platform.agent_profile.delete", resource_type="agent_profile", resource_id=profile_id)
    delete_agent_profile(profile_id, user=user)
    write_gateway_audit_event(action="platform.agent_profile.delete", outcome="success", request=request, user=user, resource_type="agent_profile", resource_id=profile_id, scope="owner")
    return {"deleted": True, "profile_id": profile_id}
