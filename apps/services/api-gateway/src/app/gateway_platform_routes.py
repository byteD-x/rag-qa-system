from __future__ import annotations

import time
from dataclasses import asdict
from urllib.parse import urlparse

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
from .api_key_manager import APIKeyManager
from .webhook_manager import WebhookManager
from .pii_detector import PIIDetector, PIType
from .instruction_evaluator import InstructionABEvaluator


router = APIRouter()

api_key_manager = APIKeyManager(db=gateway_db)
webhook_manager = WebhookManager(db=gateway_db)
ab_evaluator = InstructionABEvaluator(db=gateway_db)
_experiment_owners: dict[str, str] = {}
_pii_configs: dict[str, dict[str, object]] = {}
_default_pii_types = [item.value for item in PIType]


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


# ---------------------------------------------------------------------------
# Platform management capabilities
# ---------------------------------------------------------------------------


def _owned_api_key(key_id: str, user: CurrentUser) -> dict[str, object]:
    item = next((key for key in api_key_manager.list_keys(user.user_id) if key["id"] == key_id), None)
    if item is None:
        raise_api_error(404, "api_key_not_found", "api key not found")
    return item


@router.get("/api/v1/platform/api-keys")
async def list_platform_api_keys(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.api_key.list", resource_type="api_key")
    return {"items": api_key_manager.list_keys(user.user_id)}


@router.post("/api/v1/platform/api-keys")
async def create_platform_api_key(payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.api_key.create", resource_type="api_key")
    name = str(payload.get("name") or "").strip()
    permissions_raw = payload.get("permissions")
    permissions = [str(item).strip().lower() for item in permissions_raw] if isinstance(permissions_raw, list) else []
    allowed_permissions = {"chat.use", "kb.read", "kb.write", "kb.manage", "audit.read"}
    if not name:
        raise_api_error(400, "invalid_api_key_name", "name is required")
    if not permissions or any(item not in allowed_permissions for item in permissions):
        raise_api_error(400, "invalid_api_key_permissions", "permissions contains unsupported values")
    try:
        quota_tokens = int(payload.get("quota_tokens") or 0)
        rate_limit = int(payload.get("rate_limit") or 60)
    except (TypeError, ValueError):
        raise_api_error(400, "invalid_api_key_limits", "quota_tokens and rate_limit must be integers")
    if quota_tokens < 0 or rate_limit < 1 or rate_limit > 600:
        raise_api_error(400, "invalid_api_key_limits", "quota or rate limit is out of range")
    item = api_key_manager.create_key(
        user.user_id,
        name=name,
        permissions=list(dict.fromkeys(permissions)),
        quota_tokens=quota_tokens,
        rate_limit_per_minute=rate_limit,
    )
    write_gateway_audit_event(action="platform.api_key.create", outcome="success", request=request, user=user, resource_type="api_key", resource_id=str(item["id"]), scope="owner")
    return item


@router.post("/api/v1/platform/api-keys/{key_id}/rotate")
async def rotate_platform_api_key(key_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.api_key.rotate", resource_type="api_key",)
    _owned_api_key(key_id, user)
    item = api_key_manager.rotate_key(key_id)
    if item is None:
        raise_api_error(404, "api_key_not_found", "api key not found")
    write_gateway_audit_event(action="platform.api_key.rotate", outcome="success", request=request, user=user, resource_type="api_key", resource_id=key_id, scope="owner", details={"new_key_id": item["id"]})
    return item


@router.post("/api/v1/platform/api-keys/{key_id}/revoke")
async def revoke_platform_api_key(key_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.api_key.revoke", resource_type="api_key",)
    _owned_api_key(key_id, user)
    if not api_key_manager.revoke(key_id):
        raise_api_error(404, "api_key_not_found", "api key not found")
    write_gateway_audit_event(action="platform.api_key.revoke", outcome="success", request=request, user=user, resource_type="api_key", resource_id=key_id, scope="owner")
    return {"revoked": True, "id": key_id}


def _serialize_webhook(registration: object) -> dict[str, object]:
    item = asdict(registration)
    item.pop("secret", None)
    item.pop("owner_user_id", None)
    return item


def _serialize_delivery(delivery: object) -> dict[str, object]:
    item = asdict(delivery)
    item.pop("payload", None)
    return item


def _validate_webhook_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise_api_error(400, "invalid_webhook_url", "webhook url must use http or https")
    return url


def _owned_webhook(webhook_id: str, user: CurrentUser):
    item = next((hook for hook in webhook_manager.list_hooks(user.user_id) if hook.id == webhook_id), None)
    if item is None:
        raise_api_error(404, "webhook_not_found", "webhook not found")
    return item


@router.get("/api/v1/platform/webhooks")
async def list_platform_webhooks(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.webhook.list", resource_type="webhook")
    return {"items": [_serialize_webhook(item) for item in webhook_manager.list_hooks(user.user_id)]}


@router.get("/api/v1/platform/webhooks/deliveries")
async def list_platform_webhook_deliveries(request: Request, user: CurrentUser, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    _platform_read(request, user, action="platform.webhook.delivery.list", resource_type="webhook_delivery")
    deliveries = []
    for hook in webhook_manager.list_hooks(user.user_id):
        deliveries.extend(webhook_manager.history(hook.id, limit=limit))
    deliveries.sort(key=lambda item: item.created_at, reverse=True)
    return {"items": [_serialize_delivery(item) for item in deliveries[:limit]]}


@router.post("/api/v1/platform/webhooks")
async def register_platform_webhook(payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.webhook.create", resource_type="webhook")
    url = _validate_webhook_url(payload.get("url"))
    events_raw = payload.get("events")
    events = [str(item).strip() for item in events_raw if str(item).strip()] if isinstance(events_raw, list) else ["*"]
    registration = webhook_manager.register(url, events=events, secret=str(payload.get("secret") or ""), description=str(payload.get("description") or "").strip(), owner_user_id=user.user_id)
    write_gateway_audit_event(action="platform.webhook.create", outcome="success", request=request, user=user, resource_type="webhook", resource_id=registration.id, scope="owner")
    return _serialize_webhook(registration)


@router.post("/api/v1/platform/webhooks/{webhook_id}/test")
async def test_platform_webhook(webhook_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.webhook.test", resource_type="webhook")
    _owned_webhook(webhook_id, user)
    deliveries = await webhook_manager.trigger("platform.webhook.test", {"requested_by": user.user_id}, webhook_id=webhook_id)
    if not deliveries:
        raise_api_error(409, "webhook_inactive", "webhook is inactive")
    return {"delivery": _serialize_delivery(deliveries[0])}


@router.patch("/api/v1/platform/webhooks/{webhook_id}")
async def update_platform_webhook(webhook_id: str, payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.webhook.update", resource_type="webhook")
    _owned_webhook(webhook_id, user)
    is_active = payload.get("is_active")
    if is_active is not None and not isinstance(is_active, bool):
        raise_api_error(400, "invalid_webhook_status", "is_active must be boolean")
    events_raw = payload.get("events")
    events = None
    if events_raw is not None:
        if not isinstance(events_raw, list):
            raise_api_error(400, "invalid_webhook_events", "events must be an array")
        events = [str(item).strip() for item in events_raw if str(item).strip()]
    registration = webhook_manager.update(webhook_id, owner_user_id=user.user_id, is_active=is_active, description=str(payload["description"]) if "description" in payload else None, events=events)
    if registration is None:
        raise_api_error(404, "webhook_not_found", "webhook not found")
    return _serialize_webhook(registration)


@router.delete("/api/v1/platform/webhooks/{webhook_id}")
async def delete_platform_webhook(webhook_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.webhook.delete", resource_type="webhook")
    _owned_webhook(webhook_id, user)
    if not webhook_manager.unregister(webhook_id):
        raise_api_error(404, "webhook_not_found", "webhook not found")
    return {"deleted": True, "id": webhook_id}


def _pii_config(user: CurrentUser) -> dict[str, object]:
    if user.user_id in _pii_configs:
        return dict(_pii_configs[user.user_id])
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT strategy, mask_char, enabled_types_json FROM platform_pii_configs WHERE user_id = %s", (user.user_id,))
            row = cur.fetchone()
    if row:
        config = {"strategy": str(row.get("strategy") or "mask"), "mask_char": str(row.get("mask_char") or "*"), "enabled_types": list(row.get("enabled_types_json") or _default_pii_types)}
        _pii_configs[user.user_id] = config
        return config
    return {"strategy": "mask", "mask_char": "*", "enabled_types": list(_default_pii_types)}


@router.get("/api/v1/platform/pii/config")
async def get_platform_pii_config(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.pii.config.get", resource_type="pii_config")
    return _pii_config(user)


@router.patch("/api/v1/platform/pii/config")
async def save_platform_pii_config(payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.pii.config.update", resource_type="pii_config")
    strategy = str(payload.get("strategy") or "mask").strip().lower()
    if strategy not in {"mask", "hash", "redact", "replace"}:
        raise_api_error(400, "invalid_pii_strategy", "unsupported pii strategy")
    enabled_raw = payload.get("enabled_types")
    enabled_types = [str(item).strip().lower() for item in enabled_raw] if isinstance(enabled_raw, list) else list(_default_pii_types)
    if any(item not in _default_pii_types for item in enabled_types):
        raise_api_error(400, "invalid_pii_types", "unsupported pii type")
    mask_char = str(payload.get("mask_char") or "*")
    if len(mask_char) != 1:
        raise_api_error(400, "invalid_mask_char", "mask_char must be one character")
    config = {"strategy": strategy, "mask_char": mask_char, "enabled_types": list(dict.fromkeys(enabled_types))}
    _pii_configs[user.user_id] = config
    from .db import to_json
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO platform_pii_configs (user_id, strategy, mask_char, enabled_types_json)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id) DO UPDATE SET strategy = EXCLUDED.strategy, mask_char = EXCLUDED.mask_char, enabled_types_json = EXCLUDED.enabled_types_json, updated_at = NOW()
                """,
                (user.user_id, strategy, mask_char, to_json(config["enabled_types"])),
            )
        conn.commit()
    return config


@router.post("/api/v1/platform/pii/test")
async def test_platform_pii(payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.pii.test", resource_type="pii_config")
    text = str(payload.get("text") or "")
    if not text or len(text) > 20000:
        raise_api_error(400, "invalid_pii_text", "text must contain 1 to 20000 characters")
    config = _pii_config(user)
    strategy = str(payload.get("strategy") or config["strategy"])
    if strategy not in {"mask", "hash", "redact", "replace"}:
        raise_api_error(400, "invalid_pii_strategy", "unsupported pii strategy")
    detector = PIIDetector(enabled_types=list(config["enabled_types"]))
    report = detector.audit_report(text)
    return {**report, "sanitized": detector.anonymize(text, strategy=strategy, mask_char=str(config["mask_char"]))}


@router.get("/api/v1/platform/experiments")
async def list_platform_experiments(request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.experiment.list", resource_type="experiment")
    return {"items": [item for item in ab_evaluator.list_experiments() if item.get("owner_user_id") == user.user_id or _experiment_owners.get(item["experiment_id"]) == user.user_id]}


@router.post("/api/v1/platform/experiments")
async def start_platform_experiment(payload: dict[str, object], request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.experiment.create", resource_type="experiment")
    experiment_id = str(payload.get("experiment_id") or f"exp_{int(time.time() * 1000)}").strip()
    control_prompt = str(payload.get("control_prompt") or "")
    variant_prompt = str(payload.get("variant_prompt") or "")
    if not control_prompt or not variant_prompt:
        raise_api_error(400, "invalid_experiment_prompts", "control_prompt and variant_prompt are required")
    if experiment_id in _experiment_owners or ab_evaluator.owner(experiment_id):
        raise_api_error(409, "experiment_exists", "experiment already exists")
    try:
        target = int(payload.get("sample_size_target") or 100)
        split_ratio = float(payload.get("split_ratio") or 0.5)
    except (TypeError, ValueError):
        raise_api_error(400, "invalid_experiment_config", "sample_size_target and split_ratio are invalid")
    if target < 30 or target > 1000 or not 0.1 <= split_ratio <= 0.9:
        raise_api_error(400, "invalid_experiment_config", "experiment configuration is out of range")
    ab_evaluator.set_owner(user.user_id)
    config = ab_evaluator.start_experiment(experiment_id, name=str(payload.get("name") or experiment_id), control_prompt=control_prompt, variant_prompt=variant_prompt, sample_size_target=target, split_ratio=split_ratio)
    _experiment_owners[experiment_id] = user.user_id
    return {"experiment_id": config.experiment_id, "name": config.name, "is_active": config.is_active, "sample_size": 0, "target": config.sample_size_target, "created_at": config.created_at}


@router.post("/api/v1/platform/experiments/{experiment_id}/stop")
async def stop_platform_experiment(experiment_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_manage(request, user, action="platform.experiment.stop", resource_type="experiment")
    if (_experiment_owners.get(experiment_id) or ab_evaluator.owner(experiment_id)) != user.user_id:
        raise_api_error(404, "experiment_not_found", "experiment not found")
    ab_evaluator.stop_experiment(experiment_id)
    return {"experiment_id": experiment_id, "is_active": False}


@router.get("/api/v1/platform/experiments/{experiment_id}/report")
async def get_platform_experiment_report(experiment_id: str, request: Request, user: CurrentUser) -> dict[str, object]:
    _platform_read(request, user, action="platform.experiment.report", resource_type="experiment",)
    if (_experiment_owners.get(experiment_id) or ab_evaluator.owner(experiment_id)) != user.user_id:
        raise_api_error(404, "experiment_not_found", "experiment not found")
    report = ab_evaluator.report(experiment_id)
    if report is None:
        raise_api_error(404, "experiment_not_found", "experiment not found")
    return asdict(report)


@router.get("/api/v1/platform/orchestration/runs")
async def list_platform_orchestration_runs(request: Request, user: CurrentUser, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    _platform_read(request, user, action="platform.orchestration.list", resource_type="orchestration_run")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_workflow_runs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user.user_id, limit))
            rows = cur.fetchall()
    items = []
    for row in rows:
        state = dict(row.get("workflow_state_json") or {})
        retrieval = dict(state.get("retrieval_meta") or {})
        decomposition = dict(retrieval.get("decomposition") or {})
        sub_tasks = list(decomposition.get("sub_tasks") or [])
        worker_results = [{"task_id": task.get("id"), "worker_type": task.get("category", "retrieval"), "success": task.get("status") not in {"failed", "error"}, "execution_time_ms": 0, "evidence": []} for task in sub_tasks]
        failures = sum(1 for item in worker_results if not item["success"])
        items.append({"plan_id": str(row.get("id") or ""), "question": str(row.get("question") or ""), "sub_tasks": sub_tasks, "execution_order": list(decomposition.get("execution_order") or []), "success_count": len(worker_results) - failures, "failure_count": failures, "total_time_ms": float((state.get("timing") or {}).get("total_ms") or 0), "worker_types": list(dict.fromkeys(item["worker_type"] for item in worker_results)), "worker_results": worker_results})
    return {"items": items, "total": len(items)}
