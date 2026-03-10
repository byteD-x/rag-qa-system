from __future__ import annotations

from fastapi import APIRouter, Request

from shared.auth import CurrentUser

from .gateway_audit_support import require_permission, write_gateway_audit_event
from .gateway_runtime import CHAT_PERMISSION
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
from .gateway_schemas import AgentProfileRequest, PromptTemplateRequest, UpdateAgentProfileRequest, UpdatePromptTemplateRequest


router = APIRouter()


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
