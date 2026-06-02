from __future__ import annotations

import asyncio
from typing import Any

import httpx

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .gateway_config import QUERYABLE_STATUSES
from .gateway_runtime import runtime_settings
from .gateway_schemas import ChatScopePayload
from .gateway_transport import downstream_headers, parse_corpus_id, request_service_json


# ---------------------------------------------------------------------------
# 多租户隔离
# ---------------------------------------------------------------------------

# 租户级知识库映射: tenant_id → {corpus_ids, 配额}
_tenant_kb_registry: dict[str, dict[str, Any]] = {}


def register_tenant(
    tenant_id: str,
    *,
    allowed_corpus_ids: list[str] | None = None,
    quota_tokens_per_day: int = 0,
) -> None:
    """注册租户及其可访问的知识库范围。

    参数:
        tenant_id: 租户标识
        allowed_corpus_ids: 允许访问的知识库 ID 列表（空=全部）
        quota_tokens_per_day: 日配额（0=不限制）
    """
    _tenant_kb_registry[tenant_id] = {
        "allowed_corpus_ids": allowed_corpus_ids or [],
        "quota_tokens_per_day": quota_tokens_per_day,
        "registered_at": __import__("time").time(),
    }


def tenant_scope_filter(
    tenant_id: str,
    corpus_ids: list[str],
) -> list[str]:
    """根据租户权限过滤知识库范围。

    返回过滤后的知识库 ID 列表。
    """
    if not tenant_id or tenant_id not in _tenant_kb_registry:
        return corpus_ids  # 未注册的租户不受限制

    tenant_config = _tenant_kb_registry[tenant_id]
    allowed = tenant_config.get("allowed_corpus_ids") or []
    if not allowed:
        return corpus_ids  # 空列表 = 允许全部

    return [cid for cid in corpus_ids if cid in allowed]


def tenant_has_access(tenant_id: str, corpus_id: str) -> bool:
    """检查租户是否有权访问指定知识库。"""
    if not tenant_id or tenant_id not in _tenant_kb_registry:
        return True
    allowed = _tenant_kb_registry[tenant_id].get("allowed_corpus_ids") or []
    return not allowed or corpus_id in allowed


# ---------------------------------------------------------------------------
# Scope 解析
# ---------------------------------------------------------------------------


def default_scope() -> dict[str, Any]:
    return {
        "mode": "all",
        "corpus_ids": [],
        "document_ids": [],
        "documents_by_corpus": {},
        "allow_common_knowledge": False,
        "agent_profile_id": "",
        "prompt_template_id": "",
        "execution_mode": "grounded",
    }


def normalize_execution_mode(value: str | None, *, default: str = "grounded") -> str:
    normalized = str(value or "").strip().lower() or default
    if normalized not in {"grounded", "agent"}:
        raise_api_error(400, "unsupported_execution_mode", f"unsupported execution mode: {normalized}")
    return normalized


def normalize_scope_payload(payload: ChatScopePayload | None) -> dict[str, Any]:
    if payload is None:
        return default_scope()
    mode = payload.mode.strip().lower() or "all"
    if mode not in {"single", "multi", "all"}:
        raise_api_error(400, "unsupported_scope_mode", f"unsupported scope mode: {payload.mode}")
    corpus_ids = [item.strip() for item in payload.corpus_ids if item.strip()]
    document_ids = [item.strip() for item in payload.document_ids if item.strip()]
    if mode == "single" and len(corpus_ids) != 1:
        raise_api_error(400, "invalid_scope", "single mode requires exactly one corpus id")
    if mode == "multi" and not corpus_ids:
        raise_api_error(400, "invalid_scope", "multi mode requires at least one corpus id")
    return {
        "mode": mode,
        "corpus_ids": list(dict.fromkeys(corpus_ids)),
        "document_ids": list(dict.fromkeys(document_ids)),
        "allow_common_knowledge": bool(payload.allow_common_knowledge),
        "agent_profile_id": payload.agent_profile_id.strip(),
        "prompt_template_id": payload.prompt_template_id.strip(),
        "execution_mode": "grounded",
    }


async def fetch_corpus_documents(client: httpx.AsyncClient, *, user: CurrentUser, corpus_id: str, kb_service_url: str) -> list[dict[str, Any]]:
    corpus_type, raw_id = parse_corpus_id(corpus_id)
    payload = await request_service_json(
        client,
        "GET",
        f"{kb_service_url}/api/v1/kb/bases/{raw_id}/documents",
        headers=downstream_headers(user),
    )
    items = payload.get("items", []) if isinstance(payload, dict) else []
    normalized: list[dict[str, Any]] = []
    for item in items:
        status_value = str(item.get("status") or "")
        queryable = bool(item.get("query_ready")) or status_value in QUERYABLE_STATUSES
        title = str(item.get("title") or item.get("file_name") or "")
        version_label = str(item.get("version_label") or "").strip()
        version_suffix = f" [{version_label}]" if version_label else ""
        if bool(item.get("is_current_version")):
            version_suffix = f"{version_suffix} [current]" if version_suffix else " [current]"
        normalized.append(
            {
                "id": str(item.get("id") or ""),
                "document_id": str(item.get("id") or ""),
                "corpus_id": corpus_id,
                "corpus_type": corpus_type,
                "display_name": f"{title}{version_suffix}",
                "title": title,
                "file_name": str(item.get("file_name") or item.get("title") or ""),
                "status": status_value,
                "query_ready": queryable,
                "created_at": item.get("created_at"),
                "raw": item,
            }
        )
    return normalized


async def fetch_corpora(user: CurrentUser, *, include_counts: bool, kb_service_url: str) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        kb_payload = await request_service_json(client, "GET", f"{kb_service_url}/api/v1/kb/bases", headers=downstream_headers(user))
        corpora = [
            {
                "corpus_id": f"kb:{item['id']}",
                "id": str(item["id"]),
                "corpus_type": "kb",
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "document_count": 0,
                "queryable_document_count": 0,
            }
            for item in kb_payload.get("items", []) if isinstance(kb_payload, dict)
        ]
        if include_counts and corpora:
            doc_lists = await asyncio.gather(
                *[fetch_corpus_documents(client, user=user, corpus_id=item["corpus_id"], kb_service_url=kb_service_url) for item in corpora]
            )
            for corpus, documents in zip(corpora, doc_lists, strict=False):
                corpus["document_count"] = len(documents)
                corpus["queryable_document_count"] = sum(1 for item in documents if item["query_ready"])
        return corpora


async def resolve_scope_snapshot(
    user: CurrentUser,
    scope_payload: ChatScopePayload | None,
    *,
    fetch_corpora_fn: Any,
    fetch_corpus_documents_fn: Any,
) -> dict[str, Any]:
    scope = normalize_scope_payload(scope_payload)
    corpora = await fetch_corpora_fn(user, include_counts=False)
    corpus_map = {item["corpus_id"]: item for item in corpora}
    selected_corpus_ids = [item["corpus_id"] for item in corpora] if scope["mode"] == "all" else scope["corpus_ids"]
    if scope["mode"] != "all":
        missing = [item for item in selected_corpus_ids if item not in corpus_map]
        if missing:
            raise_api_error(400, "unknown_corpus_ids", f"unknown corpus ids: {', '.join(missing)}")
    if scope["mode"] == "single" and len(selected_corpus_ids) != 1:
        raise_api_error(400, "invalid_scope", "single mode requires exactly one queryable corpus")
    selected_documents: list[str] = []
    documents_by_corpus: dict[str, list[str]] = {}
    if scope["document_ids"]:
        timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            doc_lists = await asyncio.gather(
                *[fetch_corpus_documents_fn(client, user=user, corpus_id=corpus_id) for corpus_id in selected_corpus_ids]
            )
        valid_documents = {item["document_id"]: item["corpus_id"] for documents in doc_lists for item in documents}
        for document_id in scope["document_ids"]:
            if document_id not in valid_documents:
                raise_api_error(400, "document_scope_mismatch", f"document id is outside the selected corpora: {document_id}")
            selected_documents.append(document_id)
            documents_by_corpus.setdefault(valid_documents[document_id], []).append(document_id)
    return {
        "mode": scope["mode"],
        "corpus_ids": selected_corpus_ids,
        "document_ids": list(dict.fromkeys(selected_documents)),
        "documents_by_corpus": {corpus_id: list(dict.fromkeys(ids)) for corpus_id, ids in documents_by_corpus.items() if ids},
        "allow_common_knowledge": bool(scope["allow_common_knowledge"]),
        "agent_profile_id": str(scope.get("agent_profile_id") or ""),
        "prompt_template_id": str(scope.get("prompt_template_id") or ""),
        "execution_mode": "grounded",
    }
