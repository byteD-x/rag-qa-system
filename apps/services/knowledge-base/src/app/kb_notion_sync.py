from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from typing import Any

import httpx

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_connector_sync import ConnectorSyncCandidate, execute_connector_sync


NOTION_CONNECTOR_SOURCE_TYPE = "notion_page"
DEFAULT_NOTION_CONNECTOR_MAX_PAGES = 32
NOTION_API_VERSION = os.getenv("KB_NOTION_API_VERSION", "2022-06-28").strip() or "2022-06-28"
_RICH_TEXT_TYPES = (
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "quote",
    "callout",
    "code",
)


def _notion_api_token() -> str:
    return os.getenv("KB_NOTION_API_TOKEN", "").strip()


def _notion_api_base_url() -> str:
    return os.getenv("KB_NOTION_API_BASE_URL", "https://api.notion.com/v1").strip().rstrip("/")


def _notion_enabled() -> bool:
    return os.getenv("KB_NOTION_CONNECTOR_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _max_connector_pages() -> int:
    raw = os.getenv("KB_NOTION_CONNECTOR_MAX_PAGES", str(DEFAULT_NOTION_CONNECTOR_MAX_PAGES)).strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return DEFAULT_NOTION_CONNECTOR_MAX_PAGES


def _notion_headers() -> dict[str, str]:
    token = _notion_api_token()
    if not _notion_enabled() or not token:
        raise_api_error(
            503,
            "notion_connector_disabled",
            "notion connector is disabled because KB_NOTION_CONNECTOR_ENABLED or KB_NOTION_API_TOKEN is missing",
        )
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
    }


def _normalize_page_id(value: str) -> str:
    normalized = re.sub(r"[^0-9a-fA-F]", "", str(value or ""))
    if len(normalized) != 32:
        raise_api_error(400, "notion_connector_page_id_invalid", "notion page id must contain 32 hex characters")
    return normalized.lower()


def _page_filename(page_id: str) -> str:
    return f"notion-page-{page_id}.txt"


def _page_url(page_payload: dict[str, Any], page_id: str) -> str:
    url = str(page_payload.get("url") or "").strip()
    return url or f"https://www.notion.so/{page_id}"


def _extract_page_title(page_payload: dict[str, Any]) -> str:
    properties = page_payload.get("properties") or {}
    if isinstance(properties, dict):
        for value in properties.values():
            if isinstance(value, dict) and value.get("type") == "title":
                parts = value.get("title") or []
                title = "".join(str(item.get("plain_text") or "") for item in parts if isinstance(item, dict)).strip()
                if title:
                    return title
    return str(page_payload.get("id") or "Untitled Page")


def _rich_text_to_string(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(str(item.get("plain_text") or "") for item in items if isinstance(item, dict)).strip()


def _block_to_lines(block: dict[str, Any]) -> list[str]:
    block_type = str(block.get("type") or "")
    if block_type in _RICH_TEXT_TYPES:
        payload = block.get(block_type) or {}
        text = _rich_text_to_string(payload.get("rich_text"))
        checked = payload.get("checked")
        if block_type == "to_do" and text:
            prefix = "[x] " if checked else "[ ] "
            return [prefix + text]
        if text:
            return [text]
    if block_type == "table_row":
        cells = block.get("table_row", {}).get("cells") or []
        values = [" ".join(str(part.get("plain_text") or "") for part in cell if isinstance(part, dict)).strip() for cell in cells]
        rendered = " | ".join(item for item in values if item)
        return [rendered] if rendered else []
    if block_type == "child_page":
        title = str((block.get("child_page") or {}).get("title") or "").strip()
        return [f"Child page: {title}"] if title else []
    return []


def _fetch_json(client: httpx.Client, method: str, url: str) -> dict[str, Any]:
    response = client.request(method, url, headers=_notion_headers())
    if response.status_code == 404:
        raise_api_error(404, "notion_connector_page_not_found", "notion page or block was not found")
    if response.status_code == 401:
        raise_api_error(502, "notion_connector_auth_failed", "notion connector authentication failed")
    if response.status_code >= 400:
        raise_api_error(502, "notion_connector_upstream_error", "notion connector upstream request failed")
    payload = response.json()
    if not isinstance(payload, dict):
        raise_api_error(502, "notion_connector_upstream_invalid", "notion connector returned invalid JSON")
    return payload


def _fetch_block_children(client: httpx.Client, block_id: str, *, depth: int = 0, max_depth: int = 8) -> list[str]:
    if depth > max_depth:
        return []
    url = f"{_notion_api_base_url()}/blocks/{block_id}/children?page_size=100"
    payload = _fetch_json(client, "GET", url)
    results = payload.get("results") or []
    lines: list[str] = []
    if not isinstance(results, list):
        return lines
    for item in results:
        if not isinstance(item, dict):
            continue
        lines.extend(_block_to_lines(item))
        if bool(item.get("has_children")) and item.get("id"):
            lines.extend(_fetch_block_children(client, str(item["id"]), depth=depth + 1, max_depth=max_depth))
    return lines


def fetch_notion_page_candidate(client: httpx.Client, page_id: str) -> ConnectorSyncCandidate:
    normalized_id = _normalize_page_id(page_id)
    page_payload = _fetch_json(client, "GET", f"{_notion_api_base_url()}/pages/{normalized_id}")
    page_title = _extract_page_title(page_payload)
    body_lines = _fetch_block_children(client, normalized_id)
    page_url = _page_url(page_payload, normalized_id)
    last_edited_time = str(page_payload.get("last_edited_time") or "").strip()
    if not last_edited_time:
        raise_api_error(502, "notion_connector_missing_timestamp", "notion page did not include last_edited_time")
    source_updated_at = datetime.fromisoformat(last_edited_time.replace("Z", "+00:00"))
    text_lines = [f"# {page_title}", "", *[line for line in body_lines if line.strip()]]
    encoded = "\n".join(text_lines).strip().encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    return ConnectorSyncCandidate(
        file_name=_page_filename(normalized_id),
        file_type="txt",
        size_bytes=len(encoded),
        content_hash=content_hash,
        source_uri=page_url,
        source_updated_at=source_updated_at,
        relative_path=page_title,
        content_bytes=encoded,
        source_metadata={
            "relative_path": page_title,
            "page_id": normalized_id,
            "page_title": page_title,
            "page_url": page_url,
            "last_edited_time": last_edited_time,
            "sync_mode": NOTION_CONNECTOR_SOURCE_TYPE,
            "parent_type": str((page_payload.get("parent") or {}).get("type") or ""),
        },
        content_type="text/plain; charset=utf-8",
    )


def collect_notion_sync_candidates(
    page_ids: list[str],
    *,
    max_pages: int | None = None,
    client: httpx.Client,
) -> list[ConnectorSyncCandidate]:
    normalized_ids = list(dict.fromkeys(_normalize_page_id(item) for item in page_ids))
    limit = max_pages if max_pages is not None else _max_connector_pages()
    if len(normalized_ids) > limit:
        raise_api_error(400, "notion_connector_too_many_pages", f"notion connector matched more than {limit} pages")
    return [fetch_notion_page_candidate(client, page_id) for page_id in normalized_ids]


def execute_notion_sync(
    *,
    base_id: str,
    page_ids: list[str],
    category: str,
    delete_missing: bool,
    dry_run: bool,
    max_pages: int | None,
    user: CurrentUser,
    db: Any,
    storage: Any,
    client_factory: Any = None,
) -> dict[str, Any]:
    factory = client_factory or (lambda: httpx.Client(timeout=httpx.Timeout(30.0)))
    with factory() as client:
        candidates = collect_notion_sync_candidates(page_ids, max_pages=max_pages, client=client)
    normalized_ids = [str(candidate.source_metadata.get("page_id") or "") for candidate in candidates]
    return execute_connector_sync(
        base_id=base_id,
        source_type=NOTION_CONNECTOR_SOURCE_TYPE,
        source_label="notion",
        source_path="notion://" + ",".join(normalized_ids),
        candidates=candidates,
        delete_missing=delete_missing,
        dry_run=dry_run,
        category=category,
        user=user,
        db=db,
        storage=storage,
        storage_service="kb-connector-notion",
        ignored_files=[],
        extra_result={"page_ids": normalized_ids},
    )


__all__ = [
    "DEFAULT_NOTION_CONNECTOR_MAX_PAGES",
    "NOTION_CONNECTOR_SOURCE_TYPE",
    "collect_notion_sync_candidates",
    "execute_notion_sync",
    "fetch_notion_page_candidate",
]
