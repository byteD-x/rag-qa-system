from __future__ import annotations

from typing import Any
from uuid import uuid4

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .db import to_json
from .gateway_runtime import gateway_db


def _is_platform_admin(user: CurrentUser) -> bool:
    return str(user.role or "") == "platform_admin"


def serialize_prompt_template(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "template_id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "content": str(row.get("content") or ""),
        "visibility": str(row.get("visibility") or "personal"),
        "tags": list(row.get("tags_json") or []),
        "favorite": bool(row.get("favorite")),
        "user_id": str(row.get("user_id") or ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def serialize_agent_profile(row: dict[str, Any], *, prompt_template: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "profile_id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "description": str(row.get("description") or ""),
        "persona_prompt": str(row.get("persona_prompt") or ""),
        "enabled_tools": list(row.get("enabled_tools_json") or []),
        "default_corpus_ids": list(row.get("default_corpus_ids_json") or []),
        "prompt_template_id": str(row.get("prompt_template_id") or ""),
        "prompt_template": prompt_template,
        "user_id": str(row.get("user_id") or ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def list_prompt_templates(user: CurrentUser) -> list[dict[str, Any]]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM chat_prompt_templates
                WHERE user_id = %s OR visibility = 'public'
                ORDER BY favorite DESC, updated_at DESC
                """,
                (user.user_id,),
            )
            rows = cur.fetchall()
    return [serialize_prompt_template(row) for row in rows]


def load_prompt_template(template_id: str, user: CurrentUser, *, writable: bool = False) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_prompt_templates WHERE id = %s", (template_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "prompt_template_not_found", "prompt template not found")
    owner_id = str(row.get("user_id") or "")
    visibility = str(row.get("visibility") or "personal")
    if writable:
        if owner_id != user.user_id and not _is_platform_admin(user):
            raise_api_error(403, "permission_denied", "prompt template is outside your scope")
    else:
        if owner_id != user.user_id and visibility != "public" and not _is_platform_admin(user):
            raise_api_error(403, "permission_denied", "prompt template is outside your scope")
    return row


def create_prompt_template(*, user: CurrentUser, name: str, content: str, visibility: str, tags: list[str], favorite: bool) -> dict[str, Any]:
    template_id = str(uuid4())
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_prompt_templates (id, user_id, name, content, visibility, tags_json, favorite)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING *
                """,
                (template_id, user.user_id, name, content, visibility, to_json(tags), favorite),
            )
            row = cur.fetchone()
        conn.commit()
    return serialize_prompt_template(row or {})


def update_prompt_template(
    template_id: str,
    *,
    user: CurrentUser,
    name: str | None = None,
    content: str | None = None,
    visibility: str | None = None,
    tags: list[str] | None = None,
    favorite: bool | None = None,
) -> dict[str, Any]:
    current = load_prompt_template(template_id, user, writable=True)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_prompt_templates
                SET name = %s,
                    content = %s,
                    visibility = %s,
                    tags_json = %s::jsonb,
                    favorite = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    name if name is not None else str(current.get("name") or ""),
                    content if content is not None else str(current.get("content") or ""),
                    visibility if visibility is not None else str(current.get("visibility") or "personal"),
                    to_json(tags if tags is not None else list(current.get("tags_json") or [])),
                    favorite if favorite is not None else bool(current.get("favorite")),
                    template_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return serialize_prompt_template(row or {})


def delete_prompt_template(template_id: str, *, user: CurrentUser) -> None:
    load_prompt_template(template_id, user, writable=True)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_prompt_templates WHERE id = %s", (template_id,))
        conn.commit()


def list_agent_profiles(user: CurrentUser) -> list[dict[str, Any]]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            if _is_platform_admin(user):
                cur.execute("SELECT * FROM chat_agent_profiles ORDER BY updated_at DESC")
            else:
                cur.execute("SELECT * FROM chat_agent_profiles WHERE user_id = %s ORDER BY updated_at DESC", (user.user_id,))
            rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        template = None
        if row.get("prompt_template_id"):
            template = serialize_prompt_template(load_prompt_template(str(row.get("prompt_template_id") or ""), user))
        items.append(serialize_agent_profile(row, prompt_template=template))
    return items


def load_agent_profile(profile_id: str, user: CurrentUser, *, writable: bool = False) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chat_agent_profiles WHERE id = %s", (profile_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "agent_profile_not_found", "agent profile not found")
    if str(row.get("user_id") or "") != user.user_id and not _is_platform_admin(user):
        raise_api_error(403, "permission_denied", "agent profile is outside your scope")
    if writable and str(row.get("user_id") or "") != user.user_id and not _is_platform_admin(user):
        raise_api_error(403, "permission_denied", "agent profile is outside your scope")
    return row


def create_agent_profile(
    *,
    user: CurrentUser,
    name: str,
    description: str,
    persona_prompt: str,
    enabled_tools: list[str],
    default_corpus_ids: list[str],
    prompt_template_id: str,
) -> dict[str, Any]:
    profile_id = str(uuid4())
    if prompt_template_id:
        load_prompt_template(prompt_template_id, user)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_agent_profiles (
                    id, user_id, name, description, persona_prompt,
                    enabled_tools_json, default_corpus_ids_json, prompt_template_id
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::uuid)
                RETURNING *
                """,
                (
                    profile_id,
                    user.user_id,
                    name,
                    description,
                    persona_prompt,
                    to_json(enabled_tools),
                    to_json(default_corpus_ids),
                    prompt_template_id or None,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    template = serialize_prompt_template(load_prompt_template(prompt_template_id, user)) if prompt_template_id else None
    return serialize_agent_profile(row or {}, prompt_template=template)


def update_agent_profile(
    profile_id: str,
    *,
    user: CurrentUser,
    name: str | None = None,
    description: str | None = None,
    persona_prompt: str | None = None,
    enabled_tools: list[str] | None = None,
    default_corpus_ids: list[str] | None = None,
    prompt_template_id: str | None = None,
) -> dict[str, Any]:
    current = load_agent_profile(profile_id, user, writable=True)
    if prompt_template_id:
        load_prompt_template(prompt_template_id, user)
    next_template_id = (
        prompt_template_id
        if prompt_template_id is not None
        else str(current.get("prompt_template_id") or "")
    )
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_agent_profiles
                SET name = %s,
                    description = %s,
                    persona_prompt = %s,
                    enabled_tools_json = %s::jsonb,
                    default_corpus_ids_json = %s::jsonb,
                    prompt_template_id = %s::uuid,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    name if name is not None else str(current.get("name") or ""),
                    description if description is not None else str(current.get("description") or ""),
                    persona_prompt if persona_prompt is not None else str(current.get("persona_prompt") or ""),
                    to_json(enabled_tools if enabled_tools is not None else list(current.get("enabled_tools_json") or [])),
                    to_json(default_corpus_ids if default_corpus_ids is not None else list(current.get("default_corpus_ids_json") or [])),
                    next_template_id or None,
                    profile_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    template = serialize_prompt_template(load_prompt_template(next_template_id, user)) if next_template_id else None
    return serialize_agent_profile(row or {}, prompt_template=template)


def delete_agent_profile(profile_id: str, *, user: CurrentUser) -> None:
    load_agent_profile(profile_id, user, writable=True)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_agent_profiles WHERE id = %s", (profile_id,))
        conn.commit()


def resolve_platform_context(scope_snapshot: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    agent_profile_id = str(scope_snapshot.get("agent_profile_id") or "").strip()
    prompt_template_id = str(scope_snapshot.get("prompt_template_id") or "").strip()
    agent_profile = None
    prompt_template = None
    if prompt_template_id:
        prompt_template = serialize_prompt_template(load_prompt_template(prompt_template_id, user))
    if agent_profile_id:
        profile_row = load_agent_profile(agent_profile_id, user)
        inherited_template = prompt_template
        if not inherited_template and profile_row.get("prompt_template_id"):
            inherited_template = serialize_prompt_template(load_prompt_template(str(profile_row.get("prompt_template_id") or ""), user))
        agent_profile = serialize_agent_profile(profile_row, prompt_template=inherited_template)
        if prompt_template is None:
            prompt_template = inherited_template
    return {"agent_profile": agent_profile, "prompt_template": prompt_template}
