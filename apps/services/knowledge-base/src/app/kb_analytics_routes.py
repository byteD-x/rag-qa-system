from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shared.auth import CurrentUser

from .kb_api_support import audit_event, can_manage_everything, check_readiness, list_audit_events, require_kb_permission
from .kb_runtime import KB_MANAGE_PERMISSION, KB_READ_PERMISSION, db
from .kb_schemas import KBAnalyticsDashboardResponse, KBAnalyticsGovernanceResponse, KBAnalyticsOperationsResponse


router = APIRouter()
STALLED_THRESHOLD_HOURS = 24
LOW_VISUAL_REGION_CONFIDENCE = 0.8
OPERATIONS_RETRYABLE_LIMIT = 8
OPERATIONS_STALLED_LIMIT = 8
OPERATIONS_CONNECTOR_LIMIT = 8
OPERATIONS_INCIDENT_LIMIT = 12


def _scope_clause(user: CurrentUser, view: str, *, field_name: str = "created_by") -> tuple[str, tuple[Any, ...]]:
    if view == "personal":
        return f"{field_name} = %s", (user.user_id,)
    if not can_manage_everything(user):
        raise HTTPException(status_code=403, detail={"detail": "admin dashboard requires kb.manage or platform_admin", "code": "permission_denied"})
    return "TRUE", ()


def _distribution_rows(rows: list[dict[str, Any]], *, key_field: str = "key") -> list[dict[str, Any]]:
    return [
        {
            "key": str(row.get(key_field) or ""),
            "count": int(row.get("total_count") or 0),
        }
        for row in rows
    ]


def _serialize_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return None


def _document_effective_now(row: dict[str, Any], *, reference_time: datetime | None = None) -> bool:
    now = reference_time or datetime.now(timezone.utc)
    effective_from = row.get("effective_from")
    effective_to = row.get("effective_to")
    if isinstance(effective_from, datetime) and effective_from > now:
        return False
    if isinstance(effective_to, datetime) and effective_to < now:
        return False
    return True


def _serialize_governance_document(row: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "document_id": str(row.get("document_id") or ""),
        "base_id": str(row.get("base_id") or ""),
        "base_name": str(row.get("base_name") or ""),
        "file_name": str(row.get("file_name") or ""),
        "status": str(row.get("status") or ""),
        "enhancement_status": str(row.get("enhancement_status") or ""),
        "version_family_key": str(row.get("version_family_key") or ""),
        "version_label": str(row.get("version_label") or ""),
        "version_number": int(row.get("version_number")) if row.get("version_number") is not None else None,
        "version_status": str(row.get("version_status") or ""),
        "is_current_version": bool(row.get("is_current_version")),
        "effective_from": _serialize_timestamp(row.get("effective_from")),
        "effective_to": _serialize_timestamp(row.get("effective_to")),
        "effective_now": _document_effective_now(row),
        "visual_asset_count": int(row.get("visual_asset_count") or 0),
        "low_confidence_region_count": int(row.get("low_confidence_region_count") or 0),
        "low_confidence_asset_id": str(row.get("low_confidence_asset_id") or ""),
        "low_confidence_region_id": str(row.get("low_confidence_region_id") or ""),
        "low_confidence_region_label": str(row.get("low_confidence_region_label") or ""),
        "low_confidence_region_confidence": float(row.get("low_confidence_region_confidence")) if row.get("low_confidence_region_confidence") is not None else None,
        "low_confidence_region_bbox": [float(item) for item in list(row.get("low_confidence_region_bbox") or []) if isinstance(item, (int, float))][:4],
        "created_at": _serialize_timestamp(row.get("created_at")),
        "updated_at": _serialize_timestamp(row.get("updated_at")),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "review_status": str(row.get("review_status") or ""),
        "reviewer_note": str(row.get("reviewer_note") or ""),
        "reviewed_at": _serialize_timestamp(row.get("reviewed_at")),
        "reviewed_by_user_id": str(row.get("reviewed_by_user_id") or ""),
        "reviewed_by_email": str(row.get("reviewed_by_email") or ""),
        "reason": reason,
    }


def _document_governance_queue(
    user: CurrentUser,
    *,
    view: str,
    limit: int,
    predicate_sql: str,
    order_sql: str,
    reason_resolver,
) -> tuple[int, list[dict[str, Any]]]:
    clause, params = _scope_clause(user, view, field_name="d.created_by")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH matched_docs AS (
                    SELECT
                        d.id::text AS document_id,
                        d.base_id::text AS base_id,
                        b.name AS base_name,
                        d.file_name,
                        d.status,
                        d.enhancement_status,
                        d.version_family_key,
                        d.version_label,
                        d.version_number,
                        d.version_status,
                        d.is_current_version,
                        d.effective_from,
                        d.effective_to,
                        d.created_at,
                        d.updated_at,
                        COALESCE((d.stats_json->>'visual_asset_count')::int, 0) AS visual_asset_count,
                        (
                            SELECT COUNT(*)
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                        )::int AS low_confidence_region_count,
                        COALESCE((
                            SELECT region.asset_id::text
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                            ORDER BY region.confidence ASC, region.region_index ASC
                            LIMIT 1
                        ), '') AS low_confidence_asset_id,
                        COALESCE((
                            SELECT region.id::text
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                            ORDER BY region.confidence ASC, region.region_index ASC
                            LIMIT 1
                        ), '') AS low_confidence_region_id,
                        COALESCE((
                            SELECT region.region_label
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                            ORDER BY region.confidence ASC, region.region_index ASC
                            LIMIT 1
                        ), '') AS low_confidence_region_label,
                        (
                            SELECT region.confidence
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                            ORDER BY region.confidence ASC, region.region_index ASC
                            LIMIT 1
                        ) AS low_confidence_region_confidence,
                        COALESCE((
                            SELECT region.bbox_json
                            FROM kb_visual_asset_regions region
                            WHERE region.document_id = d.id
                              AND region.confidence IS NOT NULL
                              AND region.confidence < %s
                            ORDER BY region.confidence ASC, region.region_index ASC
                            LIMIT 1
                        ), '[]'::jsonb) AS low_confidence_region_bbox,
                        COALESCE(NULLIF(d.stats_json->>'owner_user_id', ''), d.created_by::text, '') AS owner_user_id,
                        COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') AS review_status,
                        COALESCE(NULLIF(d.stats_json->>'reviewer_note', ''), '') AS reviewer_note,
                        NULLIF(d.stats_json->>'reviewed_at', '')::timestamptz AS reviewed_at,
                        COALESCE(NULLIF(d.stats_json->>'reviewed_by_user_id', ''), '') AS reviewed_by_user_id,
                        COALESCE(NULLIF(d.stats_json->>'reviewed_by_email', ''), '') AS reviewed_by_email
                    FROM kb_documents d
                    JOIN kb_bases b ON b.id = d.base_id
                    WHERE {clause}
                      AND {predicate_sql}
                )
                SELECT *, COUNT(*) OVER() AS total_count
                FROM matched_docs
                ORDER BY {order_sql}
                LIMIT %s
                """,
                params + (
                    LOW_VISUAL_REGION_CONFIDENCE,
                    LOW_VISUAL_REGION_CONFIDENCE,
                    LOW_VISUAL_REGION_CONFIDENCE,
                    LOW_VISUAL_REGION_CONFIDENCE,
                    LOW_VISUAL_REGION_CONFIDENCE,
                    LOW_VISUAL_REGION_CONFIDENCE,
                    limit,
                ),
            )
            rows = cur.fetchall()
    total_count = int(rows[0].get("total_count") or 0) if rows else 0
    return total_count, [_serialize_governance_document(row, reason=reason_resolver(row)) for row in rows]


def _pending_review_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="""
            (
                COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = 'review_pending'
                OR (
                    COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = ''
                    AND COALESCE(d.version_status, '') = 'draft'
                )
                OR (
                    COALESCE(d.version_status, '') = 'active'
                    AND d.effective_from IS NOT NULL
                    AND d.effective_from > NOW()
                    AND COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') <> 'approved'
                )
            )
        """,
        order_sql="""
            CASE
                WHEN COALESCE(review_status, '') = 'review_pending' THEN 0
                WHEN COALESCE(version_status, '') = 'draft' THEN 1
                ELSE 2
            END ASC,
            effective_from ASC NULLS LAST,
            created_at DESC
        """,
        reason_resolver=lambda row: (
            "review_pending"
            if str(row.get("review_status") or "") == "review_pending"
            else ("draft_version" if str(row.get("version_status") or "") == "draft" else "scheduled_publish")
        ),
    )


def _approved_ready_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="""
            COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = 'approved'
            AND (
                COALESCE(d.version_status, '') = 'draft'
                OR (
                    COALESCE(d.version_status, '') = 'active'
                    AND (
                        d.effective_from IS NOT NULL
                        AND d.effective_from > NOW()
                    )
                )
            )
        """,
        order_sql="reviewed_at DESC NULLS LAST, effective_from ASC NULLS LAST, updated_at DESC",
        reason_resolver=lambda _row: "approved_ready",
    )


def _rejected_documents_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = 'rejected'",
        order_sql="reviewed_at DESC NULLS LAST, updated_at DESC",
        reason_resolver=lambda _row: "rejected_review",
    )


def _expired_documents_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="d.effective_to IS NOT NULL AND d.effective_to < NOW()",
        order_sql="effective_to DESC, updated_at DESC",
        reason_resolver=lambda _row: "expired_effective_window",
    )


def _visual_attention_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="""
            COALESCE((d.stats_json->>'visual_asset_count')::int, 0) > 0
            AND COALESCE(NULLIF(d.enhancement_status, ''), 'none') NOT IN ('visual_ready', 'summary_vectors_ready', 'chunk_vectors_ready')
        """,
        order_sql="visual_asset_count DESC, updated_at DESC",
        reason_resolver=lambda row: f"visual_pipeline_{str(row.get('enhancement_status') or 'none')}",
    )


def _missing_version_family_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql="""
            COALESCE(NULLIF(d.version_family_key, ''), '') = ''
            AND (
                COALESCE(NULLIF(d.version_label, ''), '') <> ''
                OR d.version_number IS NOT NULL
                OR d.supersedes_document_id IS NOT NULL
            )
        """,
        order_sql="updated_at DESC, created_at DESC",
        reason_resolver=lambda _row: "version_metadata_without_family",
    )


def _visual_low_confidence_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    return _document_governance_queue(
        user,
        view=view,
        limit=limit,
        predicate_sql=f"""
            EXISTS (
                SELECT 1
                FROM kb_visual_asset_regions region
                WHERE region.document_id = d.id
                  AND region.confidence IS NOT NULL
                  AND region.confidence < {LOW_VISUAL_REGION_CONFIDENCE}
            )
        """,
        order_sql="low_confidence_region_count DESC, updated_at DESC",
        reason_resolver=lambda _row: "visual_pipeline_low_confidence",
    )


def _version_conflict_queue(user: CurrentUser, *, view: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    clause, params = _scope_clause(user, view, field_name="d.created_by")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped_docs AS (
                    SELECT d.*, b.name AS base_name
                    FROM kb_documents d
                    JOIN kb_bases b ON b.id = d.base_id
                    WHERE {clause}
                      AND COALESCE(NULLIF(d.version_family_key, ''), '') <> ''
                ),
                conflict_families AS (
                    SELECT
                        d.base_id::text AS base_id,
                        MAX(d.base_name) AS base_name,
                        d.version_family_key,
                        COUNT(*) FILTER (WHERE d.is_current_version = TRUE) AS current_version_count,
                        COUNT(*) FILTER (WHERE COALESCE(d.version_status, '') = 'active') AS active_version_count,
                        COUNT(*) AS total_versions,
                        MAX(d.version_number) AS latest_version_number,
                        ARRAY_REMOVE(ARRAY_AGG(CASE WHEN d.is_current_version = TRUE THEN d.id::text ELSE NULL END), NULL) AS current_document_ids,
                        ARRAY_REMOVE(ARRAY_AGG(CASE WHEN d.is_current_version = TRUE THEN COALESCE(NULLIF(d.version_label, ''), d.file_name) ELSE NULL END), NULL) AS current_labels
                    FROM scoped_docs d
                    GROUP BY d.base_id, d.version_family_key
                    HAVING COUNT(*) FILTER (WHERE d.is_current_version = TRUE) > 1
                )
                SELECT *, COUNT(*) OVER() AS total_count
                FROM conflict_families
                ORDER BY current_version_count DESC, total_versions DESC, version_family_key ASC
                LIMIT %s
                """,
                params + (limit,),
            )
            rows = cur.fetchall()
    total_count = int(rows[0].get("total_count") or 0) if rows else 0
    items = [
        {
            "base_id": str(row.get("base_id") or ""),
            "base_name": str(row.get("base_name") or ""),
            "version_family_key": str(row.get("version_family_key") or ""),
            "current_version_count": int(row.get("current_version_count") or 0),
            "active_version_count": int(row.get("active_version_count") or 0),
            "total_versions": int(row.get("total_versions") or 0),
            "latest_version_number": int(row.get("latest_version_number")) if row.get("latest_version_number") is not None else None,
            "current_document_ids": [str(item) for item in (row.get("current_document_ids") or []) if item],
            "current_labels": [str(item) for item in (row.get("current_labels") or []) if item],
        }
        for row in rows
    ]
    return total_count, items


def _governance_payload(user: CurrentUser, *, view: str, limit: int) -> dict[str, Any]:
    pending_count, pending_items = _pending_review_queue(user, view=view, limit=limit)
    approved_count, approved_items = _approved_ready_queue(user, view=view, limit=limit)
    rejected_count, rejected_items = _rejected_documents_queue(user, view=view, limit=limit)
    expired_count, expired_items = _expired_documents_queue(user, view=view, limit=limit)
    visual_count, visual_items = _visual_attention_queue(user, view=view, limit=limit)
    visual_low_confidence_count, visual_low_confidence_items = _visual_low_confidence_queue(user, view=view, limit=limit)
    missing_count, missing_items = _missing_version_family_queue(user, view=view, limit=limit)
    conflict_count, conflict_items = _version_conflict_queue(user, view=view, limit=limit)
    return {
        "view": view,
        "limit": limit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "pending_review": pending_count,
            "approved_ready": approved_count,
            "rejected_documents": rejected_count,
            "expired_documents": expired_count,
            "visual_attention": visual_count,
            "visual_low_confidence": visual_low_confidence_count,
            "missing_version_family": missing_count,
            "version_conflicts": conflict_count,
        },
        "queues": {
            "pending_review": pending_items,
            "approved_ready": approved_items,
            "rejected_documents": rejected_items,
            "expired_documents": expired_items,
            "visual_attention": visual_items,
            "visual_low_confidence": visual_low_confidence_items,
            "missing_version_family": missing_items,
            "version_conflicts": conflict_items,
        },
        "data_quality": {
            "unsupported_fields": [],
            "degraded_sections": [],
        },
    }


def _governance_batch_events_payload(user: CurrentUser, *, view: str, limit: int) -> dict[str, Any]:
    normalized_view = view.strip().lower() or "personal"
    if normalized_view == "admin" and not can_manage_everything(user):
        raise HTTPException(status_code=403, detail={"detail": "admin governance events require kb.manage or platform_admin", "code": "permission_denied"})
    actor_user_id = user.user_id if normalized_view == "personal" else ""
    items = list_audit_events(
        actor_user_id=actor_user_id,
        resource_type="document_batch",
        action="kb.document.batch_update",
        limit=limit,
    )
    return {
        "view": normalized_view,
        "limit": limit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def _batch_event_sort_key(item: dict[str, Any]) -> str:
    return str(item.get("created_at") or "")


def _governance_batch_event_detail_payload(
    user: CurrentUser,
    *,
    view: str,
    task_id: str,
    timeline_limit: int,
    timeline_offset: int,
    timeline_filter: str,
) -> dict[str, Any]:
    normalized_view = view.strip().lower() or "personal"
    if normalized_view == "admin" and not can_manage_everything(user):
        raise HTTPException(status_code=403, detail={"detail": "admin governance events require kb.manage or platform_admin", "code": "permission_denied"})
    actor_user_id = user.user_id if normalized_view == "personal" else ""
    items = list_audit_events(
        actor_user_id=actor_user_id,
        resource_type="document_batch",
        resource_id=task_id,
        action="kb.document.batch_update",
        limit=1,
    )
    if not items:
        raise HTTPException(status_code=404, detail={"detail": "governance batch task not found", "code": "governance_batch_task_not_found"})
    event = items[0]
    parent_task_id = str((event.get("details") or {}).get("retry_of_task_id") or "")
    related_candidates = list_audit_events(
        actor_user_id=actor_user_id,
        resource_type="document_batch",
        action="kb.document.batch_update",
        limit=max(100, timeline_limit + timeline_offset + 20),
    )
    direct_retries = [
        item
        for item in related_candidates
        if str((item.get("details") or {}).get("retry_of_task_id") or "") == task_id
    ]
    direct_retries.sort(key=_batch_event_sort_key, reverse=True)
    upstream_items = [item for item in related_candidates if parent_task_id and str(item.get("resource_id") or "") == parent_task_id]
    upstream_items.sort(key=_batch_event_sort_key, reverse=True)
    if timeline_filter == "retries":
        related_items = [event, *direct_retries]
    elif timeline_filter == "upstream":
        related_items = [*upstream_items[:1], event]
        related_items.sort(key=_batch_event_sort_key, reverse=True)
    else:
        related_items = [event, *direct_retries, *upstream_items[:1]]
        related_items.sort(key=_batch_event_sort_key, reverse=True)
    timeline_total = len(related_items)
    paged_timeline_items = related_items[timeline_offset: timeline_offset + timeline_limit]
    latest_retry = direct_retries[0] if direct_retries else None
    return {
        "view": normalized_view,
        "task_id": task_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "item": event,
        "retry_summary": {
            "parent_task_id": parent_task_id or None,
            "retry_count": len(direct_retries),
            "failed_retry_count": sum(1 for item in direct_retries if int((item.get("details") or {}).get("failed") or 0) > 0),
            "latest_retry_task_id": (str(latest_retry.get("resource_id") or "") or None) if latest_retry else None,
            "latest_retry_outcome": (str(latest_retry.get("outcome") or "") or None) if latest_retry else None,
            "latest_retry_at": latest_retry.get("created_at") if latest_retry else None,
            "latest_retry_failed": int((latest_retry.get("details") or {}).get("failed") or 0) if latest_retry else 0,
            "latest_retry_succeeded": int((latest_retry.get("details") or {}).get("succeeded") or 0) if latest_retry else 0,
        },
        "timeline": {
            "items": paged_timeline_items,
            "total": timeline_total,
            "limit": timeline_limit,
            "offset": timeline_offset,
            "filter": timeline_filter,
            "has_more": timeline_offset + len(paged_timeline_items) < timeline_total,
        },
    }


def _funnel_stats(user: CurrentUser, *, view: str, days: int) -> dict[str, int]:
    base_clause, base_params = _scope_clause(user, view, field_name="created_by")
    document_clause, document_params = _scope_clause(user, view, field_name="created_by")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total_count
                FROM kb_bases
                WHERE {base_clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                base_params + (days,),
            )
            base_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT COUNT(*) AS uploaded_count
                FROM kb_documents
                WHERE {document_clause}
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                document_params + (days,),
            )
            uploaded_row = cur.fetchone() or {}
            cur.execute(
                f"""
                SELECT COUNT(*) AS ready_count
                FROM kb_documents
                WHERE {document_clause}
                  AND ready_at IS NOT NULL
                  AND ready_at >= NOW() - (%s || ' days')::interval
                """,
                document_params + (days,),
            )
            ready_row = cur.fetchone() or {}
    return {
        "knowledge_bases_created": int(base_row.get("total_count") or 0),
        "documents_uploaded": int(uploaded_row.get("uploaded_count") or 0),
        "documents_ready": int(ready_row.get("ready_count") or 0),
    }


def _document_status_distribution(user: CurrentUser, *, view: str) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(status, ''), 'unknown') AS key,
                    COUNT(*) AS total_count
                FROM kb_documents
                WHERE {clause}
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params,
            )
            rows = cur.fetchall()
    return _distribution_rows(rows)


def _enhancement_status_distribution(user: CurrentUser, *, view: str) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(enhancement_status, ''), 'none') AS key,
                    COUNT(*) AS total_count
                FROM kb_documents
                WHERE {clause}
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params,
            )
            rows = cur.fetchall()
    return _distribution_rows(rows)


def _latest_job_status_distribution(user: CurrentUser, *, view: str) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped_docs AS (
                    SELECT id
                    FROM kb_documents
                    WHERE {clause}
                ),
                latest_jobs AS (
                    SELECT DISTINCT ON (jobs.document_id)
                        jobs.document_id,
                        jobs.status
                    FROM kb_ingest_jobs jobs
                    JOIN scoped_docs docs ON docs.id = jobs.document_id
                    ORDER BY jobs.document_id ASC, jobs.created_at DESC
                )
                SELECT
                    COALESCE(NULLIF(status, ''), 'missing') AS key,
                    COUNT(*) AS total_count
                FROM latest_jobs
                GROUP BY key
                ORDER BY total_count DESC, key ASC
                """,
                params,
            )
            rows = cur.fetchall()
    return _distribution_rows(rows)


def _upload_to_ready_latency(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS sample_count,
                    AVG(EXTRACT(EPOCH FROM (ready_at - created_at)) * 1000.0) AS avg_ms,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (ready_at - created_at)) * 1000.0) AS p50_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (ready_at - created_at)) * 1000.0) AS p95_ms,
                    MAX(EXTRACT(EPOCH FROM (ready_at - created_at)) * 1000.0) AS max_ms
                FROM kb_documents
                WHERE {clause}
                  AND ready_at IS NOT NULL
                  AND ready_at >= NOW() - (%s || ' days')::interval
                  AND ready_at >= created_at
                """,
                params + (days,),
            )
            row = cur.fetchone() or {}
    return {
        "count": int(row.get("sample_count") or 0),
        "avg_ms": round(float(row.get("avg_ms") or 0.0), 3) if row.get("avg_ms") is not None else None,
        "p50_ms": round(float(row.get("p50_ms") or 0.0), 3) if row.get("p50_ms") is not None else None,
        "p95_ms": round(float(row.get("p95_ms") or 0.0), 3) if row.get("p95_ms") is not None else None,
        "max_ms": round(float(row.get("max_ms") or 0.0), 3) if row.get("max_ms") is not None else None,
        "unsupported": False,
    }


def _ingest_summary(user: CurrentUser, *, view: str) -> dict[str, Any]:
    clause, params = _scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped_docs AS (
                    SELECT id, status, query_ready, updated_at
                    FROM kb_documents
                    WHERE {clause}
                ),
                latest_jobs AS (
                    SELECT DISTINCT ON (jobs.document_id)
                        jobs.document_id,
                        jobs.status AS job_status,
                        jobs.updated_at AS job_updated_at
                    FROM kb_ingest_jobs jobs
                    JOIN scoped_docs docs ON docs.id = jobs.document_id
                    ORDER BY jobs.document_id ASC, jobs.created_at DESC
                )
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(*) FILTER (WHERE docs.status = 'ready') AS ready_documents,
                    COUNT(*) FILTER (WHERE docs.query_ready = TRUE) AS queryable_documents,
                    COUNT(*) FILTER (WHERE docs.status = 'failed') AS failed_documents,
                    COUNT(*) FILTER (WHERE docs.status <> 'ready') AS unfinished_documents,
                    COUNT(*) FILTER (
                        WHERE docs.status NOT IN ('ready', 'failed')
                          AND COALESCE(latest_jobs.job_updated_at, docs.updated_at) <= NOW() - (%s || ' hours')::interval
                    ) AS stalled_documents,
                    COUNT(*) FILTER (WHERE latest_jobs.job_status = 'dead_letter') AS dead_letter_documents,
                    COUNT(*) FILTER (WHERE latest_jobs.job_status IN ('queued', 'retry', 'processing')) AS in_progress_documents
                FROM scoped_docs docs
                LEFT JOIN latest_jobs ON latest_jobs.document_id = docs.id
                """,
                params + (STALLED_THRESHOLD_HOURS,),
            )
            row = cur.fetchone() or {}
    return {
        "total_documents": int(row.get("total_documents") or 0),
        "ready_documents": int(row.get("ready_documents") or 0),
        "queryable_documents": int(row.get("queryable_documents") or 0),
        "failed_documents": int(row.get("failed_documents") or 0),
        "unfinished_documents": int(row.get("unfinished_documents") or 0),
        "stalled_documents": int(row.get("stalled_documents") or 0),
        "dead_letter_documents": int(row.get("dead_letter_documents") or 0),
        "in_progress_documents": int(row.get("in_progress_documents") or 0),
        "stalled_threshold_hours": STALLED_THRESHOLD_HOURS,
    }


def _dashboard_payload(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    return {
        "view": view,
        "days": days,
        "funnel": _funnel_stats(user, view=view, days=days),
        "ingest_health": {
            "summary": _ingest_summary(user, view=view),
            "document_status_distribution": _document_status_distribution(user, view=view),
            "latest_job_status_distribution": _latest_job_status_distribution(user, view=view),
            "enhancement_status_distribution": _enhancement_status_distribution(user, view=view),
            "upload_to_ready_latency_ms": _upload_to_ready_latency(user, view=view, days=days),
        },
        "data_quality": {
            "unsupported_fields": [],
            "degraded_sections": [],
        },
    }


def _service_health_status_from_checks(checks: dict[str, Any], *, degraded_sections: list[dict[str, Any]] | None = None) -> str:
    statuses = [str((item or {}).get("status") or "") for item in checks.values()]
    if any(status == "failed" for status in statuses):
        return "failed"
    if degraded_sections or any(status not in {"", "ok"} for status in statuses):
        return "degraded"
    return "ok"


def _operations_degraded_section(section_key: str, exc: Exception) -> dict[str, Any]:
    return {
        "key": section_key,
        "detail": "operations section degraded during payload build",
        "error_type": exc.__class__.__name__,
    }


def _operations_section(section_key: str, builder, fallback: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        return builder(), []
    except Exception as exc:
        return fallback, [_operations_degraded_section(section_key, exc)]


def _empty_ingest_ops() -> dict[str, Any]:
    return {
        "summary": {
            "total_documents": 0,
            "ready_documents": 0,
            "queryable_documents": 0,
            "failed_documents": 0,
            "unfinished_documents": 0,
            "stalled_documents": 0,
            "dead_letter_documents": 0,
            "in_progress_documents": 0,
            "stalled_threshold_hours": STALLED_THRESHOLD_HOURS,
        },
        "retryable_jobs": [],
        "stalled_documents": [],
    }


def _empty_connector_ops() -> dict[str, Any]:
    return {
        "summary": {
            "total_connectors": 0,
            "scheduled_connectors": 0,
            "due_connectors": 0,
            "recent_failed_runs": 0,
        },
        "items": [],
    }


def _retryable_ingest_jobs(user: CurrentUser, *, view: str, limit: int) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view, field_name="docs.created_by")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH latest_retryable_jobs AS (
                    SELECT DISTINCT ON (jobs.document_id)
                        jobs.id::text AS job_id,
                        jobs.document_id::text AS document_id,
                        docs.base_id::text AS base_id,
                        bases.name AS base_name,
                        docs.file_name,
                        docs.status AS document_status,
                        docs.enhancement_status,
                        jobs.status AS job_status,
                        jobs.phase,
                        jobs.error_message,
                        jobs.last_error_code,
                        jobs.attempt_count,
                        jobs.max_attempts,
                        jobs.updated_at,
                        jobs.next_retry_at
                    FROM kb_ingest_jobs jobs
                    JOIN kb_documents docs ON docs.id = jobs.document_id
                    JOIN kb_bases bases ON bases.id = docs.base_id
                    WHERE {clause}
                      AND jobs.status IN ('failed', 'dead_letter')
                    ORDER BY jobs.document_id ASC, jobs.created_at DESC
                )
                SELECT *
                FROM latest_retryable_jobs
                ORDER BY updated_at DESC, file_name ASC
                LIMIT %s
                """,
                params + (limit,),
            )
            rows = cur.fetchall()
    return [
        {
            "job_id": str(row.get("job_id") or ""),
            "document_id": str(row.get("document_id") or ""),
            "base_id": str(row.get("base_id") or ""),
            "base_name": str(row.get("base_name") or ""),
            "file_name": str(row.get("file_name") or ""),
            "document_status": str(row.get("document_status") or ""),
            "enhancement_status": str(row.get("enhancement_status") or ""),
            "job_status": str(row.get("job_status") or ""),
            "phase": str(row.get("phase") or ""),
            "error_message": str(row.get("error_message") or ""),
            "last_error_code": str(row.get("last_error_code") or ""),
            "attempt_count": int(row.get("attempt_count") or 0),
            "max_attempts": int(row.get("max_attempts") or 0),
            "updated_at": _serialize_timestamp(row.get("updated_at")),
            "next_retry_at": _serialize_timestamp(row.get("next_retry_at")),
            "retryable": True,
        }
        for row in rows
    ]


def _stalled_documents(user: CurrentUser, *, view: str, limit: int) -> list[dict[str, Any]]:
    clause, params = _scope_clause(user, view, field_name="docs.created_by")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped_docs AS (
                    SELECT
                        docs.id,
                        docs.base_id,
                        docs.file_name,
                        docs.status,
                        docs.enhancement_status,
                        docs.updated_at,
                        bases.name AS base_name
                    FROM kb_documents docs
                    JOIN kb_bases bases ON bases.id = docs.base_id
                    WHERE {clause}
                ),
                latest_jobs AS (
                    SELECT DISTINCT ON (jobs.document_id)
                        jobs.document_id,
                        jobs.id::text AS job_id,
                        jobs.status AS job_status,
                        jobs.phase,
                        jobs.error_message,
                        jobs.last_error_code,
                        jobs.updated_at AS job_updated_at
                    FROM kb_ingest_jobs jobs
                    JOIN scoped_docs docs ON docs.id = jobs.document_id
                    ORDER BY jobs.document_id ASC, jobs.created_at DESC
                )
                SELECT
                    docs.id::text AS document_id,
                    docs.base_id::text AS base_id,
                    docs.base_name,
                    docs.file_name,
                    docs.status AS document_status,
                    docs.enhancement_status,
                    COALESCE(latest_jobs.job_id, '') AS job_id,
                    COALESCE(latest_jobs.job_status, '') AS job_status,
                    COALESCE(latest_jobs.phase, '') AS phase,
                    COALESCE(latest_jobs.error_message, '') AS error_message,
                    COALESCE(latest_jobs.last_error_code, '') AS last_error_code,
                    COALESCE(latest_jobs.job_updated_at, docs.updated_at) AS last_activity_at
                FROM scoped_docs docs
                LEFT JOIN latest_jobs ON latest_jobs.document_id = docs.id
                WHERE docs.status NOT IN ('ready', 'failed')
                  AND COALESCE(latest_jobs.job_updated_at, docs.updated_at) <= NOW() - (%s || ' hours')::interval
                ORDER BY last_activity_at ASC, docs.updated_at ASC
                LIMIT %s
                """,
                params + (STALLED_THRESHOLD_HOURS, limit),
            )
            rows = cur.fetchall()
    return [
        {
            "document_id": str(row.get("document_id") or ""),
            "base_id": str(row.get("base_id") or ""),
            "base_name": str(row.get("base_name") or ""),
            "file_name": str(row.get("file_name") or ""),
            "document_status": str(row.get("document_status") or ""),
            "enhancement_status": str(row.get("enhancement_status") or ""),
            "job_id": str(row.get("job_id") or ""),
            "job_status": str(row.get("job_status") or ""),
            "phase": str(row.get("phase") or ""),
            "error_message": str(row.get("error_message") or ""),
            "last_error_code": str(row.get("last_error_code") or ""),
            "last_activity_at": _serialize_timestamp(row.get("last_activity_at")),
        }
        for row in rows
    ]


def _ingest_operations_payload(user: CurrentUser, *, view: str) -> dict[str, Any]:
    return {
        "summary": _ingest_summary(user, view=view),
        "retryable_jobs": _retryable_ingest_jobs(user, view=view, limit=OPERATIONS_RETRYABLE_LIMIT),
        "stalled_documents": _stalled_documents(user, view=view, limit=OPERATIONS_STALLED_LIMIT),
    }


def _connector_scope_clause(user: CurrentUser, view: str) -> tuple[str, tuple[Any, ...]]:
    if view == "personal":
        return "(connectors.created_by = %s OR bases.created_by = %s)", (user.user_id, user.user_id)
    if not can_manage_everything(user):
        raise HTTPException(status_code=403, detail={"detail": "admin dashboard requires kb.manage or platform_admin", "code": "permission_denied"})
    return "TRUE", ()


def _connector_operations_summary(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    clause, params = _connector_scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped_connectors AS (
                    SELECT connectors.id
                    FROM kb_connectors connectors
                    JOIN kb_bases bases ON bases.id = connectors.base_id
                    WHERE {clause}
                )
                SELECT
                    COUNT(*) AS total_connectors,
                    COUNT(*) FILTER (WHERE connectors.status = 'active' AND connectors.schedule_enabled = TRUE) AS scheduled_connectors,
                    COUNT(*) FILTER (
                        WHERE connectors.status = 'active'
                          AND connectors.schedule_enabled = TRUE
                          AND connectors.next_run_at IS NOT NULL
                          AND connectors.next_run_at <= NOW()
                    ) AS due_connectors
                FROM kb_connectors connectors
                JOIN scoped_connectors scoped ON scoped.id = connectors.id
                """,
                params,
            )
            summary_row = cur.fetchone() or {}
            cur.execute(
                f"""
                WITH scoped_connectors AS (
                    SELECT connectors.id
                    FROM kb_connectors connectors
                    JOIN kb_bases bases ON bases.id = connectors.base_id
                    WHERE {clause}
                )
                SELECT COUNT(*) AS total_count
                FROM kb_connector_runs runs
                JOIN scoped_connectors scoped ON scoped.id = runs.connector_id
                WHERE runs.status = 'failed'
                  AND runs.started_at >= NOW() - (%s || ' days')::interval
                """,
                params + (days,),
            )
            failed_row = cur.fetchone() or {}
    return {
        "total_connectors": int(summary_row.get("total_connectors") or 0),
        "scheduled_connectors": int(summary_row.get("scheduled_connectors") or 0),
        "due_connectors": int(summary_row.get("due_connectors") or 0),
        "recent_failed_runs": int(failed_row.get("total_count") or 0),
    }


def _connector_operation_items(user: CurrentUser, *, view: str, limit: int) -> list[dict[str, Any]]:
    clause, params = _connector_scope_clause(user, view)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    connectors.id::text AS connector_id,
                    connectors.base_id::text AS base_id,
                    bases.name AS base_name,
                    connectors.name,
                    connectors.connector_type,
                    connectors.status,
                    connectors.schedule_enabled,
                    connectors.last_run_at,
                    connectors.next_run_at,
                    connectors.last_result_json,
                    latest_run.status AS latest_run_status,
                    latest_run.error_message AS latest_error_message,
                    latest_run.started_at AS latest_run_started_at,
                    latest_run.finished_at AS latest_run_finished_at
                FROM kb_connectors connectors
                JOIN kb_bases bases ON bases.id = connectors.base_id
                LEFT JOIN LATERAL (
                    SELECT runs.status, runs.error_message, runs.started_at, runs.finished_at
                    FROM kb_connector_runs runs
                    WHERE runs.connector_id = connectors.id
                    ORDER BY runs.started_at DESC
                    LIMIT 1
                ) latest_run ON TRUE
                WHERE {clause}
                ORDER BY
                    CASE
                        WHEN connectors.status = 'active'
                          AND connectors.schedule_enabled = TRUE
                          AND connectors.next_run_at IS NOT NULL
                          AND connectors.next_run_at <= NOW() THEN 0
                        WHEN COALESCE(latest_run.status, '') = 'failed' THEN 1
                        ELSE 2
                    END ASC,
                    connectors.next_run_at ASC NULLS LAST,
                    connectors.updated_at DESC
                LIMIT %s
                """,
                params + (limit,),
            )
            rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        last_result = dict(row.get("last_result_json") or {})
        items.append(
            {
                "connector_id": str(row.get("connector_id") or ""),
                "base_id": str(row.get("base_id") or ""),
                "base_name": str(row.get("base_name") or ""),
                "name": str(row.get("name") or ""),
                "connector_type": str(row.get("connector_type") or ""),
                "status": str(row.get("status") or ""),
                "schedule_enabled": bool(row.get("schedule_enabled")),
                "next_run_at": _serialize_timestamp(row.get("next_run_at")),
                "last_run_at": _serialize_timestamp(row.get("last_run_at") or row.get("latest_run_finished_at") or row.get("latest_run_started_at")),
                "last_run_outcome": str(row.get("latest_run_status") or ""),
                "last_error": str(row.get("latest_error_message") or last_result.get("error_message") or ""),
            }
        )
    return items


def _connector_operations_payload(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    return {
        "summary": _connector_operations_summary(user, view=view, days=days),
        "items": _connector_operation_items(user, view=view, limit=OPERATIONS_CONNECTOR_LIMIT),
    }


def _is_operations_incident(item: dict[str, Any]) -> bool:
    action = str(item.get("action") or "")
    outcome = str(item.get("outcome") or "")
    if not (action.startswith("kb.ingest.") or action.startswith("kb.connector.")):
        return False
    if "retry" in action:
        return True
    return outcome in {"failed", "retry", "partial_success", "denied"}


def _incident_feed_payload(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    normalized_view = view.strip().lower() or "personal"
    if normalized_view == "admin" and not can_manage_everything(user):
        raise HTTPException(status_code=403, detail={"detail": "admin dashboard requires kb.manage or platform_admin", "code": "permission_denied"})
    actor_user_id = user.user_id if normalized_view == "personal" else ""
    created_from = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    candidates = list_audit_events(
        actor_user_id=actor_user_id,
        created_from=created_from,
        limit=max(80, OPERATIONS_INCIDENT_LIMIT * 4),
    )
    items = [
        {
            "id": str(item.get("id") or ""),
            "trace_id": str(item.get("trace_id") or ""),
            "resource_type": str(item.get("resource_type") or ""),
            "resource_id": str(item.get("resource_id") or ""),
            "action": str(item.get("action") or ""),
            "outcome": str(item.get("outcome") or ""),
            "created_at": item.get("created_at"),
            "details": dict(item.get("details") or {}),
        }
        for item in candidates
        if _is_operations_incident(item)
    ][:OPERATIONS_INCIDENT_LIMIT]
    return {"items": items}


def _operations_payload(user: CurrentUser, *, view: str, days: int) -> dict[str, Any]:
    degraded_sections: list[dict[str, Any]] = []
    service_health_checks = check_readiness()
    ingest_ops, ingest_degraded = _operations_section("ingest_ops", lambda: _ingest_operations_payload(user, view=view), _empty_ingest_ops())
    connector_ops, connector_degraded = _operations_section("connector_ops", lambda: _connector_operations_payload(user, view=view, days=days), _empty_connector_ops())
    incident_feed, incident_degraded = _operations_section("incident_feed", lambda: _incident_feed_payload(user, view=view, days=days), {"items": []})
    degraded_sections.extend(ingest_degraded)
    degraded_sections.extend(connector_degraded)
    degraded_sections.extend(incident_degraded)
    return {
        "view": view,
        "days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service_health": {
            "status": _service_health_status_from_checks(service_health_checks, degraded_sections=degraded_sections),
            "checks": service_health_checks,
        },
        "ingest_ops": ingest_ops,
        "connector_ops": connector_ops,
        "incident_feed": incident_feed,
        "data_quality": {
            "unsupported_fields": [],
            "degraded_sections": degraded_sections,
        },
    }


@router.get(
    "/api/v1/kb/analytics/dashboard",
    response_model=KBAnalyticsDashboardResponse,
    summary="知识库主链路分析看板",
    description="返回知识库创建、文档上传、文档 ready 漏斗与 ingest 健康度聚合结果，供 gateway dashboard 复用或前端直接消费。",
)
def get_kb_dashboard(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅统计当前用户资源；admin 统计管理范围内全部资源。"),
    days: int = Query(default=14, ge=1, le=90, description="漏斗与 ready 耗时统计的滚动时间窗口，单位为天。"),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_READ_PERMISSION, action="kb.analytics.dashboard.get", resource_type="kb_analytics_dashboard")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported analytics view", "code": "analytics_view_invalid"})
    payload = _dashboard_payload(user, view=normalized_view, days=days)
    audit_event(
        action="kb.analytics.dashboard.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="kb_analytics_dashboard",
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "days": days},
    )
    return payload


@router.get(
    "/api/v1/kb/analytics/operations",
    response_model=KBAnalyticsOperationsResponse,
    summary="知识库运维总览工作台",
    description="返回 KB 依赖健康、ingest 风险队列、connector 运行情况与近期运维事故流，供知识库管理员值班排障使用。",
)
def get_kb_operations(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅统计当前用户资源；admin 统计管理范围内全部资源。"),
    days: int = Query(default=14, ge=1, le=90, description="近期 connector 失败和 incident feed 的滚动时间窗口，单位为天。"),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_MANAGE_PERMISSION, action="kb.analytics.operations.get", resource_type="kb_analytics_operations")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported operations view", "code": "analytics_view_invalid"})
    payload = _operations_payload(user, view=normalized_view, days=days)
    audit_event(
        action="kb.analytics.operations.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="kb_analytics_operations",
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "days": days},
    )
    return payload


@router.get(
    "/api/v1/kb/analytics/governance",
    response_model=KBAnalyticsGovernanceResponse,
    summary="知识库治理工作台",
    description="返回企业知识库治理队列，包括待审核版本、过期文档、视觉待处理文档、版本元数据缺口与多 current 版本冲突。",
)
def get_kb_governance(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅统计当前用户资源；admin 统计管理范围内全部资源。"),
    limit: int = Query(default=8, ge=1, le=50, description="每个治理队列返回的样本数量上限。"),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_MANAGE_PERMISSION, action="kb.analytics.governance.get", resource_type="kb_analytics_governance")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported governance view", "code": "analytics_view_invalid"})
    payload = _governance_payload(user, view=normalized_view, limit=limit)
    audit_event(
        action="kb.analytics.governance.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="kb_analytics_governance",
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "limit": limit},
    )
    return payload


@router.get(
    "/api/v1/kb/analytics/governance/batch-events",
    summary="知识库批量治理审计记录",
    description="返回治理工作台最近的批量治理审计事件，供治理页直接展示失败项、补丁内容与批量重试上下文。",
)
def get_kb_governance_batch_events(
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅返回当前用户触发的批量治理事件；admin 返回管理范围内全部批量治理事件。"),
    limit: int = Query(default=12, ge=1, le=50, description="返回的批量治理事件数量上限。"),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_MANAGE_PERMISSION, action="kb.analytics.governance.batch_events.get", resource_type="kb_analytics_governance")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported governance view", "code": "analytics_view_invalid"})
    payload = _governance_batch_events_payload(user, view=normalized_view, limit=limit)
    audit_event(
        action="kb.analytics.governance.batch_events.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="kb_analytics_governance",
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "limit": limit},
    )
    return payload


@router.get(
    "/api/v1/kb/analytics/governance/batch-events/{task_id}",
    summary="知识库批量治理任务详情",
    description="返回单个批量治理任务的详情与重试时间线，供治理页按 task_id 查看失败项与重试历史。",
)
def get_kb_governance_batch_event_detail(
    task_id: str,
    request: Request,
    user: CurrentUser,
    view: str = Query(default="personal", max_length=16, description="personal 仅返回当前用户触发的批量治理任务；admin 返回管理范围内全部批量治理任务。"),
    timeline_limit: int = Query(default=10, ge=1, le=50, description="批量治理重试时间线每次返回的记录上限。"),
    timeline_offset: int = Query(default=0, ge=0, le=500, description="批量治理重试时间线偏移量。"),
    timeline_filter: str = Query(default="all", max_length=16, description="批量治理时间线过滤器：all / retries / upstream。"),
) -> dict[str, Any]:
    require_kb_permission(request, user, KB_MANAGE_PERMISSION, action="kb.analytics.governance.batch_event_detail.get", resource_type="kb_analytics_governance")
    normalized_view = view.strip().lower() or "personal"
    if normalized_view not in {"personal", "admin"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported governance view", "code": "analytics_view_invalid"})
    normalized_timeline_filter = timeline_filter.strip().lower() or "all"
    if normalized_timeline_filter not in {"all", "retries", "upstream"}:
        raise HTTPException(status_code=400, detail={"detail": "unsupported batch timeline filter", "code": "governance_batch_timeline_filter_invalid"})
    payload = _governance_batch_event_detail_payload(
        user,
        view=normalized_view,
        task_id=task_id.strip(),
        timeline_limit=timeline_limit,
        timeline_offset=timeline_offset,
        timeline_filter=normalized_timeline_filter,
    )
    audit_event(
        action="kb.analytics.governance.batch_event_detail.get",
        outcome="success",
        request=request,
        user=user,
        resource_type="kb_analytics_governance",
        resource_id=task_id.strip(),
        scope="admin" if normalized_view == "admin" else "owner",
        details={"view": normalized_view, "timeline_limit": timeline_limit, "timeline_offset": timeline_offset, "timeline_filter": normalized_timeline_filter},
    )
    return payload
