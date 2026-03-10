from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_connector_sync import (
    ConnectorSyncCandidate,
    ConnectorSyncPlanItem,
    execute_connector_sync,
    load_existing_connector_documents,
    plan_connector_sync,
)
from .kb_schemas import ALLOWED_KB_FILE_TYPES


LOCAL_CONNECTOR_SOURCE_TYPE = "local_directory"
DEFAULT_LOCAL_CONNECTOR_MAX_FILES = 256


@dataclass(frozen=True)
class LocalSyncCandidate:
    absolute_path: Path
    relative_path: str
    file_name: str
    file_type: str
    size_bytes: int
    content_hash: str
    source_uri: str
    source_updated_at: datetime


@dataclass(frozen=True)
class LocalSyncPlanItem:
    action: str
    source_uri: str
    file_name: str
    relative_path: str
    document_id: str = ""
    reason: str = ""


def _normalize_relative_path(path: Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _allowed_connector_roots() -> tuple[Path, ...]:
    raw = os.getenv("KB_LOCAL_CONNECTOR_ROOTS", "").strip()
    if not raw:
        return ()
    roots: list[Path] = []
    for item in raw.split(os.pathsep):
        cleaned = item.strip()
        if not cleaned:
            continue
        roots.append(Path(cleaned).expanduser().resolve())
    return tuple(roots)


def _max_connector_files() -> int:
    raw = os.getenv("KB_LOCAL_CONNECTOR_MAX_FILES", str(DEFAULT_LOCAL_CONNECTOR_MAX_FILES)).strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return DEFAULT_LOCAL_CONNECTOR_MAX_FILES


def _is_under_root(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def resolve_local_connector_directory(source_path: str) -> tuple[Path, Path]:
    allowed_roots = _allowed_connector_roots()
    if not allowed_roots:
        raise_api_error(
            503,
            "local_connector_disabled",
            "local directory connector is disabled because KB_LOCAL_CONNECTOR_ROOTS is empty",
        )
    try:
        candidate = Path(source_path).expanduser().resolve(strict=True)
    except FileNotFoundError:
        raise_api_error(404, "local_connector_path_not_found", "local connector source path was not found")
    if not candidate.is_dir():
        raise_api_error(400, "local_connector_path_invalid", "local connector source path must be a directory")
    for root in allowed_roots:
        if _is_under_root(candidate, root):
            return root, candidate
    raise_api_error(
        403,
        "local_connector_path_forbidden",
        "local connector source path is outside the configured KB_LOCAL_CONNECTOR_ROOTS",
    )


def collect_local_sync_candidates(
    source_dir: Path,
    *,
    recursive: bool,
    max_files: int | None = None,
) -> tuple[list[LocalSyncCandidate], list[str]]:
    iterator = source_dir.rglob("*") if recursive else source_dir.glob("*")
    candidates: list[LocalSyncCandidate] = []
    ignored: list[str] = []
    limit = max_files if max_files is not None else _max_connector_files()
    for path in sorted((item for item in iterator if item.is_file()), key=lambda item: str(item).lower()):
        relative_path = _normalize_relative_path(path.relative_to(source_dir))
        file_type = path.suffix.lower().lstrip(".")
        if file_type not in ALLOWED_KB_FILE_TYPES:
            ignored.append(relative_path)
            continue
        if len(candidates) >= limit:
            raise_api_error(
                400,
                "local_connector_too_many_files",
                f"local connector matched more than {limit} supported files",
            )
        stat = path.stat()
        candidates.append(
            LocalSyncCandidate(
                absolute_path=path,
                relative_path=relative_path,
                file_name=relative_path or path.name,
                file_type=file_type,
                size_bytes=int(stat.st_size),
                content_hash=_file_sha256(path),
                source_uri=path.resolve().as_uri(),
                source_updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            )
        )
    return candidates, ignored


def load_existing_local_documents(*, base_id: str, cur: Any) -> dict[str, dict[str, Any]]:
    return load_existing_connector_documents(base_id=base_id, source_type=LOCAL_CONNECTOR_SOURCE_TYPE, cur=cur)


def plan_local_directory_sync(
    *,
    candidates: list[LocalSyncCandidate],
    existing_documents: dict[str, dict[str, Any]],
    delete_missing: bool,
) -> list[LocalSyncPlanItem]:
    generic_plan = plan_connector_sync(
        candidates=[
            ConnectorSyncCandidate(
                file_name=item.file_name,
                file_type=item.file_type,
                size_bytes=item.size_bytes,
                content_hash=item.content_hash,
                source_uri=item.source_uri,
                source_updated_at=item.source_updated_at,
                relative_path=item.relative_path,
                content_bytes=b"",
                source_metadata={},
            )
            for item in candidates
        ],
        existing_documents=existing_documents,
        delete_missing=delete_missing,
    )
    return [
        LocalSyncPlanItem(
            action=item.action,
            source_uri=item.source_uri,
            file_name=item.file_name,
            relative_path=item.relative_path,
            document_id=item.document_id,
            reason=item.reason,
        )
        for item in generic_plan
    ]


def _build_source_metadata(*, relative_path: str, connector_root: Path, source_dir: Path) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "connector_root": str(connector_root),
        "source_dir": str(source_dir),
        "sync_mode": LOCAL_CONNECTOR_SOURCE_TYPE,
    }


def execute_local_directory_sync(
    *,
    base_id: str,
    source_path: str,
    category: str,
    recursive: bool,
    delete_missing: bool,
    dry_run: bool,
    max_files: int | None,
    user: CurrentUser,
    db: Any,
    storage: Any,
) -> dict[str, Any]:
    connector_root, source_dir = resolve_local_connector_directory(source_path)
    candidates, ignored = collect_local_sync_candidates(source_dir, recursive=recursive, max_files=max_files)
    generic_candidates = [
        ConnectorSyncCandidate(
            file_name=item.file_name,
            file_type=item.file_type,
            size_bytes=item.size_bytes,
            content_hash=item.content_hash,
            source_uri=item.source_uri,
            source_updated_at=item.source_updated_at,
            relative_path=item.relative_path,
            content_bytes=item.absolute_path.read_bytes(),
            source_metadata=_build_source_metadata(
                relative_path=item.relative_path,
                connector_root=connector_root,
                source_dir=source_dir,
            ),
        )
        for item in candidates
    ]
    result = execute_connector_sync(
        base_id=base_id,
        source_type=LOCAL_CONNECTOR_SOURCE_TYPE,
        source_label="local directory",
        source_path=str(source_dir),
        candidates=generic_candidates,
        delete_missing=delete_missing,
        dry_run=dry_run,
        category=category,
        user=user,
        db=db,
        storage=storage,
        storage_service="kb-connector-local",
        ignored_files=ignored,
        extra_result={"recursive": recursive},
    )
    result["recursive"] = recursive
    return result


__all__ = [
    "DEFAULT_LOCAL_CONNECTOR_MAX_FILES",
    "LOCAL_CONNECTOR_SOURCE_TYPE",
    "LocalSyncCandidate",
    "LocalSyncPlanItem",
    "collect_local_sync_candidates",
    "execute_local_directory_sync",
    "plan_local_directory_sync",
    "resolve_local_connector_directory",
]
