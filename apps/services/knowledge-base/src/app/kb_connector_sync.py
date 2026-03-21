from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from shared.auth import CurrentUser

from .db import to_json
from .kb_version_assist import build_version_assist
from .vector_store import delete_document_vectors


@dataclass(frozen=True)
class ConnectorSyncCandidate:
    file_name: str
    file_type: str
    size_bytes: int
    content_hash: str
    source_uri: str
    source_updated_at: datetime
    relative_path: str
    content_bytes: bytes
    source_metadata: dict[str, Any]
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class ConnectorSyncPlanItem:
    action: str
    source_uri: str
    file_name: str
    relative_path: str
    document_id: str = ""
    reason: str = ""


def load_existing_connector_documents(*, base_id: str, source_type: str, cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM kb_documents
        WHERE base_id = %s
          AND source_type = %s
          AND is_current_version = TRUE
        """,
        (base_id, source_type),
    )
    rows = cur.fetchall()
    return {
        str(row.get("source_uri") or ""): row
        for row in rows
        if str(row.get("source_uri") or "").strip()
    }


def plan_connector_sync(
    *,
    candidates: list[ConnectorSyncCandidate],
    existing_documents: dict[str, dict[str, Any]],
    delete_missing: bool,
) -> list[ConnectorSyncPlanItem]:
    plan: list[ConnectorSyncPlanItem] = []
    seen_source_uris = {candidate.source_uri for candidate in candidates}
    for candidate in candidates:
        existing = existing_documents.get(candidate.source_uri)
        if existing is None:
            plan.append(
                ConnectorSyncPlanItem(
                    action="create",
                    source_uri=candidate.source_uri,
                    file_name=candidate.file_name,
                    relative_path=candidate.relative_path,
                    reason="new_source",
                )
            )
            continue
        existing_hash = str(existing.get("content_hash") or "")
        existing_name = str(existing.get("file_name") or "")
        existing_deleted_at = existing.get("source_deleted_at")
        if existing_deleted_at:
            reason = "restore_deleted_source"
        elif existing_hash != candidate.content_hash:
            reason = "content_changed"
        elif existing_name != candidate.file_name:
            reason = "file_name_changed"
        else:
            plan.append(
                ConnectorSyncPlanItem(
                    action="skip",
                    source_uri=candidate.source_uri,
                    file_name=candidate.file_name,
                    relative_path=candidate.relative_path,
                    document_id=str(existing.get("id") or ""),
                    reason="unchanged",
                )
            )
            continue
        plan.append(
            ConnectorSyncPlanItem(
                action="update",
                source_uri=candidate.source_uri,
                file_name=candidate.file_name,
                relative_path=candidate.relative_path,
                document_id=str(existing.get("id") or ""),
                reason=reason,
            )
        )
    if delete_missing:
        for source_uri, existing in existing_documents.items():
            if source_uri in seen_source_uris or existing.get("source_deleted_at"):
                continue
            source_metadata = existing.get("source_metadata_json") or {}
            relative_path = source_metadata.get("relative_path") if isinstance(source_metadata, dict) else ""
            plan.append(
                ConnectorSyncPlanItem(
                    action="soft_delete",
                    source_uri=source_uri,
                    file_name=str(existing.get("file_name") or ""),
                    relative_path=str(relative_path or ""),
                    document_id=str(existing.get("id") or ""),
                    reason="missing_from_source",
                )
            )
    return plan


def _load_version_assist_documents(*, base_id: str, cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM kb_documents
        WHERE base_id = %s
          AND source_deleted_at IS NULL
        ORDER BY is_current_version DESC, version_number DESC, created_at DESC
        """,
        (base_id,),
    )
    return cur.fetchall()


def execute_connector_sync(
    *,
    base_id: str,
    source_type: str,
    source_label: str,
    source_path: str,
    candidates: list[ConnectorSyncCandidate],
    delete_missing: bool,
    dry_run: bool,
    category: str,
    user: CurrentUser,
    db: Any,
    storage: Any,
    storage_service: str,
    ignored_files: list[str] | None = None,
    extra_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ignored = list(ignored_files or [])
    with db.connect() as conn:
        with conn.cursor() as cur:
            existing_documents = load_existing_connector_documents(base_id=base_id, source_type=source_type, cur=cur)
    plan = plan_connector_sync(candidates=candidates, existing_documents=existing_documents, delete_missing=delete_missing)
    if dry_run:
        with db.connect() as conn:
            with conn.cursor() as cur:
                version_assist_documents = _load_version_assist_documents(base_id=base_id, cur=cur)
        candidate_map = {candidate.source_uri: candidate for candidate in candidates}
        plan_items: list[dict[str, Any]] = []
        for item in plan:
            payload = dict(item.__dict__)
            if item.action == "create":
                candidate = candidate_map.get(item.source_uri)
                if candidate is not None:
                    payload["version_assist"] = build_version_assist(
                        candidate={
                            "file_name": candidate.file_name,
                            "relative_path": candidate.relative_path,
                            "source_uri": candidate.source_uri,
                            "source_updated_at": candidate.source_updated_at,
                            "source_metadata": candidate.source_metadata,
                        },
                        existing_documents=version_assist_documents,
                    )
            plan_items.append(payload)
        return {
            "base_id": base_id,
            "source_path": source_path,
            "delete_missing": delete_missing,
            "dry_run": True,
            "ignored_files": ignored,
            "counts": {
                "create": sum(1 for item in plan if item.action == "create"),
                "update": sum(1 for item in plan if item.action == "update"),
                "skip": sum(1 for item in plan if item.action == "skip"),
                "soft_delete": sum(1 for item in plan if item.action == "soft_delete"),
            },
            "items": plan_items,
            **dict(extra_result or {}),
        }

    existing_by_source_uri = {candidate.source_uri: candidate for candidate in candidates}
    result_items: list[dict[str, Any]] = []
    soft_deleted_ids: list[str] = []
    with db.connect() as conn:
        with conn.cursor() as cur:
            existing_documents = load_existing_connector_documents(base_id=base_id, source_type=source_type, cur=cur)
            version_assist_documents = _load_version_assist_documents(base_id=base_id, cur=cur)
            for item in plan:
                if item.action == "skip":
                    existing = existing_documents.get(item.source_uri) or {}
                    candidate = existing_by_source_uri[item.source_uri]
                    cur.execute(
                        """
                        UPDATE kb_documents
                        SET last_synced_at = NOW(),
                            source_updated_at = %s,
                            source_deleted_at = NULL,
                            source_metadata_json = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            candidate.source_updated_at,
                            to_json(candidate.source_metadata),
                            existing.get("id"),
                        ),
                    )
                    result_items.append(
                        {
                            "action": item.action,
                            "document_id": str(existing.get("id") or ""),
                            "job_id": "",
                            "file_name": candidate.file_name,
                            "relative_path": candidate.relative_path,
                            "reason": item.reason,
                        }
                    )
                    continue
                if item.action == "soft_delete":
                    cur.execute(
                        """
                        UPDATE kb_documents
                        SET source_deleted_at = NOW(),
                            last_synced_at = NOW(),
                            status = 'source_deleted',
                            query_ready = FALSE,
                            enhancement_status = 'source_deleted',
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (item.document_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO kb_document_events (document_id, stage, message, details_json)
                        VALUES (%s, 'source_deleted', %s, %s::jsonb)
                        """,
                        (
                            item.document_id,
                            f"{source_label} connector marked source as deleted",
                            to_json({"source_type": source_type, "source_uri": item.source_uri}),
                        ),
                    )
                    soft_deleted_ids.append(item.document_id)
                    result_items.append(
                        {
                            "action": item.action,
                            "document_id": item.document_id,
                            "job_id": "",
                            "file_name": item.file_name,
                            "relative_path": item.relative_path,
                            "reason": item.reason,
                        }
                    )
                    continue

                candidate = existing_by_source_uri[item.source_uri]
                existing = existing_documents.get(item.source_uri) or {}
                create_new_version = item.action == "create" or item.reason == "content_changed"
                document_id = str(uuid4()) if create_new_version else str(existing.get("id") or uuid4())
                job_id = str(uuid4())
                version_assist = (
                    build_version_assist(
                        candidate={
                            "file_name": candidate.file_name,
                            "relative_path": candidate.relative_path,
                            "source_uri": candidate.source_uri,
                            "source_updated_at": candidate.source_updated_at,
                            "source_metadata": candidate.source_metadata,
                        },
                        existing_documents=[row for row in version_assist_documents if str(row.get("id") or "") != str(existing.get("id") or "")],
                    )
                    if item.action == "create"
                    else {}
                )
                storage_key = storage.build_storage_key(
                    service=storage_service,
                    document_id=document_id,
                    file_name=candidate.file_name,
                )
                storage.put_bytes(
                    storage_key,
                    candidate.content_bytes,
                    metadata={
                        "document_id": document_id,
                        "source_type": source_type,
                        "source_uri": candidate.source_uri,
                    },
                    content_type=candidate.content_type or mimetypes.guess_type(candidate.file_name)[0] or "application/octet-stream",
                )
                next_stats = dict(existing.get("stats_json") or {})
                if category.strip():
                    next_stats["category"] = category.strip()
                next_stats["connector_sync"] = source_type
                if version_assist:
                    next_stats["version_assist"] = version_assist
                elif item.action == "create":
                    next_stats.pop("version_assist", None)
                create_version_family_key = document_id
                create_version_label = "v1"
                create_version_number = 1
                create_supersedes_document_id = None
                if item.action == "create" and version_assist and bool(version_assist.get("auto_apply")):
                    matched_document_id = str(version_assist.get("matched_document_id") or version_assist.get("suggested_supersedes_document_id") or "").strip()
                    matched_document = next(
                        (row for row in version_assist_documents if str(row.get("id") or "").strip() == matched_document_id),
                        None,
                    )
                    if matched_document is not None:
                        create_version_family_key = str(
                            version_assist.get("suggested_version_family_key")
                            or matched_document.get("version_family_key")
                            or matched_document_id
                        )
                        create_version_number = int(matched_document.get("version_number") or 1) + 1
                        create_version_label = str(version_assist.get("suggested_version_label") or "") or f"v{create_version_number}"
                        create_supersedes_document_id = str(
                            version_assist.get("suggested_supersedes_document_id") or matched_document_id
                        ) or None
                        cur.execute(
                            """
                            UPDATE kb_documents
                            SET is_current_version = FALSE,
                                version_status = CASE
                                    WHEN version_status = 'active' THEN 'superseded'
                                    ELSE version_status
                                END,
                                updated_at = NOW()
                            WHERE base_id = %s
                              AND version_family_key = %s
                              AND is_current_version = TRUE
                            """,
                            (base_id, create_version_family_key),
                        )
                if item.action == "create":
                    cur.execute(
                        """
                        INSERT INTO kb_documents (
                            id, base_id, file_name, file_type, content_hash, storage_path,
                            storage_key, size_bytes, status, query_ready, enhancement_status,
                            created_by, stats_json, source_type, source_uri, source_updated_at,
                            source_deleted_at, last_synced_at, source_metadata_json,
                            version_family_key, version_label, version_number, version_status,
                            is_current_version, effective_from, supersedes_document_id
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, '',
                            %s, %s, 'uploaded', FALSE, '', %s, %s::jsonb, %s, %s, %s,
                            NULL, NOW(), %s::jsonb, %s, %s, %s, 'active', TRUE, %s, NULL
                        )
                        """,
                        (
                            document_id,
                            base_id,
                            candidate.file_name,
                            candidate.file_type,
                            candidate.content_hash,
                            storage_key,
                            candidate.size_bytes,
                            user.user_id,
                            to_json(next_stats),
                            source_type,
                            candidate.source_uri,
                            candidate.source_updated_at,
                            to_json(candidate.source_metadata),
                            create_version_family_key,
                            create_version_label,
                            create_version_number,
                            candidate.source_updated_at,
                            create_supersedes_document_id,
                        ),
                    )
                elif item.reason == "content_changed":
                    previous_version_number = int(existing.get("version_number") or 1)
                    next_version_number = previous_version_number + 1
                    version_family_key = str(existing.get("version_family_key") or existing.get("id") or "")
                    cur.execute(
                        """
                        UPDATE kb_documents
                        SET is_current_version = FALSE,
                            version_status = CASE
                                WHEN version_status = 'active' THEN 'superseded'
                                ELSE version_status
                            END,
                            updated_at = NOW()
                        WHERE base_id = %s
                          AND version_family_key = %s
                          AND is_current_version = TRUE
                        """,
                        (base_id, version_family_key),
                    )
                    cur.execute(
                        """
                        INSERT INTO kb_documents (
                            id, base_id, file_name, file_type, content_hash, storage_path,
                            storage_key, size_bytes, status, query_ready, enhancement_status,
                            created_by, stats_json, source_type, source_uri, source_updated_at,
                            source_deleted_at, last_synced_at, source_metadata_json,
                            version_family_key, version_label, version_number, version_status,
                            is_current_version, effective_from, supersedes_document_id
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, '',
                            %s, %s, 'uploaded', FALSE, '', %s, %s::jsonb, %s, %s, %s,
                            NULL, NOW(), %s::jsonb, %s, %s, %s, 'active', TRUE, %s, %s
                        )
                        """,
                        (
                            document_id,
                            base_id,
                            candidate.file_name,
                            candidate.file_type,
                            candidate.content_hash,
                            storage_key,
                            candidate.size_bytes,
                            user.user_id,
                            to_json(next_stats),
                            source_type,
                            candidate.source_uri,
                            candidate.source_updated_at,
                            to_json(candidate.source_metadata),
                            version_family_key,
                            f"v{next_version_number}",
                            next_version_number,
                            candidate.source_updated_at,
                            existing.get("id"),
                        ),
                    )
                else:
                    previous_storage_key = str(existing.get("storage_key") or "")
                    cur.execute(
                        """
                        UPDATE kb_documents
                        SET file_name = %s,
                            file_type = %s,
                            content_hash = %s,
                            storage_key = %s,
                            size_bytes = %s,
                            status = 'uploaded',
                            query_ready = FALSE,
                            enhancement_status = '',
                            source_updated_at = %s,
                            source_deleted_at = NULL,
                            last_synced_at = NOW(),
                            source_metadata_json = %s::jsonb,
                            stats_json = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            candidate.file_name,
                            candidate.file_type,
                            candidate.content_hash,
                            storage_key,
                            candidate.size_bytes,
                            candidate.source_updated_at,
                            to_json(candidate.source_metadata),
                            to_json(next_stats),
                            document_id,
                        ),
                    )
                    if previous_storage_key and previous_storage_key != storage_key:
                        storage.delete_object(previous_storage_key)
                cur.execute(
                    """
                    INSERT INTO kb_ingest_jobs (id, document_id, status, phase, query_ready, enhancement_status, checkpoint_json)
                    VALUES (%s, %s, 'queued', 'uploaded', FALSE, '', %s::jsonb)
                    """,
                    (job_id, document_id, to_json({"source_type": source_type, "source_uri": candidate.source_uri})),
                )
                cur.execute(
                    """
                    INSERT INTO kb_document_events (document_id, stage, message, details_json)
                    VALUES (%s, 'uploaded', %s, %s::jsonb)
                    """,
                    (
                        document_id,
                        f"{source_label} connector synced file",
                        to_json(
                            {
                                "job_id": job_id,
                                "source_type": source_type,
                                "source_uri": candidate.source_uri,
                                "relative_path": candidate.relative_path,
                                "sync_action": item.action,
                            }
                        ),
                    ),
                )
                result_items.append(
                    {
                        "action": item.action,
                        "document_id": document_id,
                        "job_id": job_id,
                        "file_name": candidate.file_name,
                        "relative_path": candidate.relative_path,
                        "reason": item.reason,
                        "version_assist": version_assist,
                    }
                )
                if item.action == "create":
                    version_assist_documents.insert(
                        0,
                        {
                            "id": document_id,
                            "file_name": candidate.file_name,
                            "source_uri": candidate.source_uri,
                            "source_updated_at": candidate.source_updated_at,
                            "source_metadata_json": candidate.source_metadata,
                            "version_family_key": create_version_family_key,
                            "version_number": create_version_number,
                            "updated_at": candidate.source_updated_at,
                            "is_current_version": True,
                        },
                    )
        conn.commit()
    for document_id in soft_deleted_ids:
        delete_document_vectors(document_id)
    return {
        "base_id": base_id,
        "source_path": source_path,
        "delete_missing": delete_missing,
        "dry_run": False,
        "ignored_files": ignored,
        "counts": {
            "create": sum(1 for item in result_items if item["action"] == "create"),
            "update": sum(1 for item in result_items if item["action"] == "update"),
            "skip": sum(1 for item in result_items if item["action"] == "skip"),
            "soft_delete": sum(1 for item in result_items if item["action"] == "soft_delete"),
        },
        "items": result_items,
        **dict(extra_result or {}),
    }


__all__ = [
    "ConnectorSyncCandidate",
    "ConnectorSyncPlanItem",
    "execute_connector_sync",
    "load_existing_connector_documents",
    "plan_connector_sync",
]
