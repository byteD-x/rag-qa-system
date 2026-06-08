from __future__ import annotations

import time

from fastapi import APIRouter, Request

from shared.auth import CurrentUser

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_llm_models import discover_openai_compatible_models, llm_config_summary
from .gateway_runtime import CHAT_PERMISSION
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
    PromptTemplateRequest,
    ToolWorkflowRequest,
    UpdateAgentProfileRequest,
    UpdatePromptTemplateRequest,
)
from .tool_workflow import run_tool_workflow


router = APIRouter()


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
