from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from shared.auth import CurrentUser

from .kb_api_support import audit_event, require_kb_permission
from .kb_local_sync import execute_local_directory_sync
from .kb_notion_sync import execute_notion_sync
from .kb_resource_store import ensure_base_exists
from .kb_runtime import KB_WRITE_PERMISSION, db, storage
from .kb_schemas import LocalDirectorySyncRequest, NotionSyncRequest


router = APIRouter()


@router.post("/api/v1/kb/connectors/local-directory/sync")
def sync_local_directory(payload: LocalDirectorySyncRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(
        request,
        user,
        KB_WRITE_PERMISSION,
        action="kb.connector.local_directory.sync",
        resource_type="knowledge_base",
        resource_id=payload.base_id,
    )
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.connector.local_directory.sync")
    result = execute_local_directory_sync(
        base_id=payload.base_id,
        source_path=payload.source_path,
        category=payload.category,
        recursive=payload.recursive,
        delete_missing=payload.delete_missing,
        dry_run=payload.dry_run,
        max_files=payload.max_files,
        user=user,
        db=db,
        storage=storage,
    )
    audit_event(
        action="kb.connector.local_directory.sync",
        outcome="success",
        request=request,
        user=user,
        resource_type="knowledge_base",
        resource_id=payload.base_id,
        scope="owner",
        details={
            "source_path": result.get("source_path", ""),
            "dry_run": bool(result.get("dry_run")),
            "counts": dict(result.get("counts") or {}),
            "ignored_file_count": len(list(result.get("ignored_files") or [])),
        },
    )
    return result


@router.post("/api/v1/kb/connectors/notion/sync")
def sync_notion_pages(payload: NotionSyncRequest, request: Request, user: CurrentUser) -> dict[str, Any]:
    require_kb_permission(
        request,
        user,
        KB_WRITE_PERMISSION,
        action="kb.connector.notion.sync",
        resource_type="knowledge_base",
        resource_id=payload.base_id,
    )
    ensure_base_exists(payload.base_id, user=user, request=request, action="kb.connector.notion.sync")
    result = execute_notion_sync(
        base_id=payload.base_id,
        page_ids=payload.page_ids,
        category=payload.category,
        delete_missing=payload.delete_missing,
        dry_run=payload.dry_run,
        max_pages=payload.max_pages,
        user=user,
        db=db,
        storage=storage,
    )
    audit_event(
        action="kb.connector.notion.sync",
        outcome="success",
        request=request,
        user=user,
        resource_type="knowledge_base",
        resource_id=payload.base_id,
        scope="owner",
        details={
            "page_count": len(list(result.get("page_ids") or [])),
            "dry_run": bool(result.get("dry_run")),
            "counts": dict(result.get("counts") or {}),
        },
    )
    return result
