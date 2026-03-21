from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_api_support import audit_event, can_manage_everything
from .kb_runtime import VISUAL_ASSET_URL_EXPIRES_SECONDS, db, storage


VISUAL_REGION_TITLE_RE = re.compile(r"^Page\s+\d+\s+(.+)$", re.IGNORECASE)


def fetch_base_documents(base_id: str, *, user: CurrentUser, cur=None) -> list[dict[str, Any]]:
    if cur is not None:
        return fetch_base_documents_with_cursor(cur, base_id, user=user)
    with db.connect() as conn:
        with conn.cursor() as next_cur:
            return fetch_base_documents_with_cursor(next_cur, base_id, user=user)


def fetch_base_documents_with_cursor(cur, base_id: str, *, user: CurrentUser) -> list[dict[str, Any]]:
    if can_manage_everything(user):
        cur.execute(
            """
            SELECT *
            FROM kb_documents
            WHERE base_id = %s
            ORDER BY created_at DESC
            """,
            (base_id,),
        )
    else:
        cur.execute(
            """
            SELECT *
            FROM kb_documents
            WHERE base_id = %s
              AND created_by = %s
            ORDER BY created_at DESC
            """,
            (base_id, user.user_id),
        )
    return [serialize_document(row) for row in cur.fetchall()]


def load_base(base_id: str, *, user: CurrentUser, request: Request | None = None, action: str = "kb.base.get") -> dict[str, Any]:
    row = load_base_unscoped(base_id)
    owner_id = str(row.get("created_by") or "")
    if owner_id != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="knowledge_base",
                resource_id=base_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "knowledge base is outside your scope")
    return row


def load_base_unscoped(base_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_bases WHERE id = %s", (base_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "knowledge_base_not_found", "knowledge base not found")
    return row


def load_document(
    document_id: str,
    *,
    user: CurrentUser,
    request: Request | None = None,
    action: str = "kb.document.get",
) -> dict[str, Any]:
    row = load_document_unscoped(document_id)
    owner_id = str(row.get("created_by") or "")
    if owner_id != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="document",
                resource_id=document_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "document is outside your scope")
    return row


def load_document_unscoped(document_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "document_not_found", "document not found")
    return serialize_document(row)


def load_visual_asset(
    asset_id: str,
    *,
    user: CurrentUser,
    request: Request | None = None,
    action: str = "kb.visual_asset.get",
) -> dict[str, Any]:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT assets.*, documents.created_by AS document_created_by
                FROM kb_visual_assets assets
                JOIN kb_documents documents ON documents.id = assets.document_id
                WHERE assets.id = %s
                """,
                (asset_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "visual_asset_not_found", "visual asset not found")
    owner_id = str(row.get("document_created_by") or "")
    if owner_id != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="visual_asset",
                resource_id=asset_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "visual asset is outside your scope")
    return row


def ensure_base_exists(base_id: str, *, user: CurrentUser, request: Request | None = None, action: str = "kb.base.get") -> None:
    load_base(base_id, user=user, request=request, action=action)


def load_ingest_job(
    job_id: str,
    *,
    user: CurrentUser,
    request: Request | None = None,
    action: str = "kb.ingest.get",
) -> dict[str, Any] | None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT jobs.*, documents.status AS document_status, documents.query_ready,
                       documents.enhancement_status AS document_enhancement_status,
                       documents.query_ready_at, documents.hybrid_ready_at, documents.ready_at,
                       documents.created_by AS document_created_by
                FROM kb_ingest_jobs jobs
                JOIN kb_documents documents ON documents.id = jobs.document_id
                WHERE jobs.id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    if str(row.get("document_created_by") or "") != user.user_id and not can_manage_everything(user):
        if request is not None:
            audit_event(
                action=action,
                outcome="denied",
                request=request,
                user=user,
                resource_type="ingest_job",
                resource_id=job_id,
                scope="owner",
            )
        raise_api_error(403, "permission_denied", "ingest job is outside your scope")
    return row


def load_latest_ingest_job_for_document(document_id: str, *, user: CurrentUser) -> dict[str, Any] | None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT jobs.*, documents.status AS document_status, documents.query_ready,
                       documents.enhancement_status AS document_enhancement_status,
                       documents.query_ready_at, documents.hybrid_ready_at, documents.ready_at,
                       documents.created_by AS document_created_by
                FROM kb_ingest_jobs jobs
                JOIN kb_documents documents ON documents.id = jobs.document_id
                WHERE jobs.document_id = %s
                ORDER BY jobs.created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    if str(row.get("document_created_by") or "") != user.user_id and not can_manage_everything(user):
        raise_api_error(403, "permission_denied", "ingest job is outside your scope")
    return row


def list_document_versions(document_id: str, *, user: CurrentUser) -> list[dict[str, Any]]:
    document = load_document(document_id, user=user, action="kb.document.versions")
    family_key = str(document.get("version_family_key") or "")
    with db.connect() as conn:
        with conn.cursor() as cur:
            if can_manage_everything(user):
                cur.execute(
                    """
                    SELECT *
                    FROM kb_documents
                    WHERE base_id = %s
                      AND version_family_key = %s
                    ORDER BY is_current_version DESC, version_number DESC, created_at DESC
                    """,
                    (document["base_id"], family_key),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM kb_documents
                    WHERE base_id = %s
                      AND version_family_key = %s
                      AND created_by = %s
                    ORDER BY is_current_version DESC, version_number DESC, created_at DESC
                    """,
                    (document["base_id"], family_key, user.user_id),
                )
            rows = cur.fetchall()
    return [serialize_document(row) for row in rows]


def serialize_ingest_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "job_id": str(row.get("id") or ""),
        "retryable": str(row.get("status") or "") in {"retry", "failed", "dead_letter"},
    }


def serialize_document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "effective_now": document_effective_now(row),
    }


def document_effective_now(row: dict[str, Any], *, reference_time: datetime | None = None) -> bool:
    now = reference_time or datetime.now(timezone.utc)
    effective_from = row.get("effective_from")
    effective_to = row.get("effective_to")
    if isinstance(effective_from, datetime) and effective_from > now:
        return False
    if isinstance(effective_to, datetime) and effective_to < now:
        return False
    return True


def list_document_visual_assets(document_id: str, *, user: CurrentUser) -> list[dict[str, Any]]:
    load_document(document_id, user=user, action="kb.document.visual_assets")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM kb_visual_assets
                WHERE document_id = %s
                ORDER BY page_number ASC NULLS LAST, asset_index ASC
                """,
                (document_id,),
            )
            rows = cur.fetchall()
    return [serialize_visual_asset(row) for row in rows]


def list_visual_asset_regions(asset_id: str, *, user: CurrentUser) -> list[dict[str, Any]]:
    asset = load_visual_asset(asset_id, user=user, action="kb.visual_asset.regions")
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id::text AS region_id,
                    asset_id::text AS asset_id,
                    document_id::text AS document_id,
                    region_index,
                    page_number,
                    region_label,
                    layout_hints_json,
                    bbox_json,
                    confidence,
                    summary,
                    ocr_text
                FROM kb_visual_asset_regions
                WHERE asset_id = %s::uuid
                ORDER BY region_index ASC
                """,
                (asset_id,),
            )
            rows = cur.fetchall()
            if rows:
                return [_serialize_stored_visual_region(row, asset=asset) for row in rows]
            cur.execute(
                """
                SELECT
                    sections.id::text AS region_id,
                    sections.title,
                    sections.summary,
                    sections.text,
                    sections.page_number,
                    COALESCE(sections.asset_id::text, '') AS asset_id,
                    sections.section_index
                FROM kb_sections sections
                WHERE sections.asset_id = %s::uuid
                  AND sections.source_kind = 'visual_region'
                ORDER BY sections.section_index ASC
                """,
                (asset_id,),
            )
            rows = cur.fetchall()
    return [_serialize_visual_region(row, asset=asset) for row in rows]


def list_visual_storage_keys_for_documents(document_ids: list[str], *, cur=None) -> list[str]:
    if not document_ids:
        return []
    if cur is not None:
        cur.execute(
            """
            SELECT storage_key, thumbnail_key
            FROM kb_visual_assets
            WHERE document_id = ANY(%s::uuid[])
            """,
            (document_ids,),
        )
        keys: list[str] = []
        for row in cur.fetchall():
            for key in (str(row.get("storage_key") or ""), str(row.get("thumbnail_key") or "")):
                if key and key not in keys:
                    keys.append(key)
        return keys
    with db.connect() as conn:
        with conn.cursor() as next_cur:
            return list_visual_storage_keys_for_documents(document_ids, cur=next_cur)


def serialize_visual_asset(row: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(row.get("id") or "")
    storage_key = str(row.get("storage_key") or "")
    return {
        **row,
        "asset_id": asset_id,
        "thumbnail_url": f"/api/v1/kb/visual-assets/{asset_id}/thumbnail" if asset_id else "",
        "image_url": storage.presign_get_object(storage_key, expires_in=VISUAL_ASSET_URL_EXPIRES_SECONDS)
        if storage_key
        else "",
    }


def _serialize_visual_region(row: dict[str, Any], *, asset: dict[str, Any]) -> dict[str, Any]:
    title = str(row.get("title") or "").strip()
    layout_hints, ocr_text = _split_visual_region_text(str(row.get("text") or ""))
    match = VISUAL_REGION_TITLE_RE.match(title)
    region_label = str(match.group(1) if match else title).strip() or "region"
    summary = str(row.get("summary") or "").strip() or ocr_text[:180].strip()
    return {
        "region_id": str(row.get("region_id") or ""),
        "asset_id": str(row.get("asset_id") or asset.get("id") or ""),
        "document_id": str(asset.get("document_id") or ""),
        "page_number": int(row.get("page_number") or asset.get("page_number") or 0) or None,
        "region_label": region_label,
        "layout_hints": layout_hints,
        "bbox": [],
        "confidence": None,
        "summary": summary,
        "ocr_text": ocr_text,
        "thumbnail_url": f"/api/v1/kb/visual-assets/{str(asset.get('id') or '')}/thumbnail" if str(asset.get("id") or "") else "",
    }


def _split_visual_region_text(text: str) -> tuple[list[str], str]:
    lines = [str(line).strip() for line in str(text or "").splitlines() if str(line).strip()]
    layout_hints: list[str] = []
    if lines and lines[0].lower().startswith("layout:"):
        layout_hints = [part.strip() for part in lines.pop(0).split(":", 1)[-1].split(",") if part.strip()]
    if lines and lines[0].lower().startswith("region:"):
        lines.pop(0)
    return layout_hints, "\n".join(lines).strip()


def _serialize_stored_visual_region(row: dict[str, Any], *, asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "region_id": str(row.get("region_id") or ""),
        "asset_id": str(row.get("asset_id") or asset.get("id") or ""),
        "document_id": str(row.get("document_id") or asset.get("document_id") or ""),
        "page_number": int(row.get("page_number") or asset.get("page_number") or 0) or None,
        "region_label": str(row.get("region_label") or "").strip() or "region",
        "layout_hints": _json_list(row.get("layout_hints_json")),
        "bbox": _json_number_list(row.get("bbox_json")),
        "confidence": float(row.get("confidence")) if row.get("confidence") is not None else None,
        "summary": str(row.get("summary") or "").strip(),
        "ocr_text": str(row.get("ocr_text") or "").strip(),
        "thumbnail_url": f"/api/v1/kb/visual-assets/{str(asset.get('id') or '')}/thumbnail" if str(asset.get("id") or "") else "",
    }


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _json_number_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value[:4]:
        if isinstance(item, (int, float)):
            result.append(float(item))
    return result
