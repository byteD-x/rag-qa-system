from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_connector_sync import ConnectorSyncCandidate, execute_connector_sync


SQL_CONNECTOR_SOURCE_TYPE = "sql_query"
DEFAULT_SQL_CONNECTOR_MAX_ROWS = 256
SELECT_QUERY_RE = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
ENV_NAME_RE = re.compile(r"^[A-Z0-9_]{1,64}$")


def _resolve_sql_dsn(env_name: str) -> str:
    normalized = str(env_name or "").strip().upper()
    if not ENV_NAME_RE.fullmatch(normalized):
        raise_api_error(400, "sql_connector_env_invalid", "dsn_env must be an uppercase env var name")
    dsn = os.getenv(normalized, "").strip()
    if not dsn:
        raise_api_error(503, "sql_connector_env_missing", f"sql connector env is missing: {normalized}")
    return dsn


def _validate_query(query: str) -> str:
    cleaned = str(query or "").strip()
    if not cleaned:
        raise_api_error(400, "sql_connector_query_missing", "sql connector query must not be empty")
    if not SELECT_QUERY_RE.match(cleaned):
        raise_api_error(400, "sql_connector_query_invalid", "sql connector only supports SELECT statements")
    if ";" in cleaned.rstrip(";"):
        raise_api_error(400, "sql_connector_query_invalid", "sql connector only supports a single statement")
    return cleaned.rstrip(";")


def _max_rows(value: int | None) -> int:
    raw = int(value) if value is not None else DEFAULT_SQL_CONNECTOR_MAX_ROWS
    return max(1, min(raw, 1000))


def _render_row_text(row: dict[str, Any], *, text_column: str, title_column: str) -> str:
    text_value = row.get(text_column)
    title_value = str(row.get(title_column) or row.get(text_column) or "SQL Record").strip()
    if isinstance(text_value, (dict, list)):
        body = json.dumps(text_value, ensure_ascii=False, indent=2)
    else:
        body = str(text_value or "").strip()
    if not body:
        body = json.dumps(row, ensure_ascii=False, default=str, indent=2)
    return f"# {title_value}\n\n{body}\n"


def _slugify_title(title: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(title or "").strip())[:80].strip("-")
    return cleaned or fallback


def execute_sql_sync(
    *,
    base_id: str,
    dsn_env: str,
    query: str,
    id_column: str,
    text_column: str,
    title_column: str,
    updated_at_column: str,
    category: str,
    delete_missing: bool,
    dry_run: bool,
    max_rows: int | None,
    user: CurrentUser,
    db: Any,
    storage: Any,
) -> dict[str, Any]:
    cleaned_query = _validate_query(query)
    dsn = _resolve_sql_dsn(dsn_env)
    connector_candidates: list[ConnectorSyncCandidate] = []
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(cleaned_query)
            rows = cur.fetchmany(_max_rows(max_rows) + 1)
    if len(rows) > _max_rows(max_rows):
        raise_api_error(400, "sql_connector_too_many_rows", f"sql connector matched more than {_max_rows(max_rows)} rows")
    for row in rows:
        record_id = str(row.get(id_column) or "").strip()
        if not record_id:
            raise_api_error(400, "sql_connector_id_missing", f"sql connector row is missing {id_column}")
        title = str(row.get(title_column) or record_id).strip() if title_column else record_id
        updated_at_value = row.get(updated_at_column) if updated_at_column else None
        if isinstance(updated_at_value, datetime):
            source_updated_at = updated_at_value.astimezone(timezone.utc)
        elif updated_at_value:
            try:
                source_updated_at = datetime.fromisoformat(str(updated_at_value).replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                source_updated_at = datetime.now(timezone.utc)
        else:
            source_updated_at = datetime.now(timezone.utc)
        rendered = _render_row_text(row, text_column=text_column, title_column=title_column)
        encoded = rendered.encode("utf-8")
        connector_candidates.append(
            ConnectorSyncCandidate(
                file_name=f"{_slugify_title(title, record_id)}.txt",
                file_type="txt",
                size_bytes=len(encoded),
                content_hash=hashlib.sha256(encoded).hexdigest(),
                source_uri=f"sql://{dsn_env.upper()}/{record_id}",
                source_updated_at=source_updated_at,
                relative_path=title,
                content_bytes=encoded,
                source_metadata={
                    "connector_type": SQL_CONNECTOR_SOURCE_TYPE,
                    "dsn_env": dsn_env.upper(),
                    "record_id": record_id,
                    "title": title,
                },
                content_type="text/plain; charset=utf-8",
            )
        )
    return execute_connector_sync(
        base_id=base_id,
        source_type=SQL_CONNECTOR_SOURCE_TYPE,
        source_label="sql query",
        source_path=f"sql://{dsn_env.upper()}",
        candidates=connector_candidates,
        delete_missing=delete_missing,
        dry_run=dry_run,
        category=category,
        user=user,
        db=db,
        storage=storage,
        storage_service="kb-connector-sql",
        ignored_files=[],
        extra_result={"row_count": len(connector_candidates)},
    )
