from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from shared import auth as auth_module


REPO_ROOT = Path(__file__).resolve().parents[1]
KB_SRC = REPO_ROOT / "apps/services/knowledge-base/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)


def _load_kb_module(module_name: str):
    _prioritize_sys_path(KB_SRC)
    for name in (module_name, "app.main", "app.kb_local_sync", "app.runtime", "app.db", "app"):
        sys.modules.pop(name, None)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_resolve_local_connector_directory_blocks_paths_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    kb_local_sync = _load_kb_module("app.kb_local_sync")
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    monkeypatch.setenv("KB_LOCAL_CONNECTOR_ROOTS", str(allowed_root))

    with pytest.raises(HTTPException) as exc_info:
        kb_local_sync.resolve_local_connector_directory(str(blocked_root))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "local_connector_path_forbidden"


def test_collect_local_sync_candidates_scans_supported_files_only(monkeypatch, tmp_path: Path) -> None:
    kb_local_sync = _load_kb_module("app.kb_local_sync")
    root = tmp_path / "source"
    root.mkdir()
    (root / "policy.txt").write_text("expense approval", encoding="utf-8")
    (root / "notes.md").write_text("ignore", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "guide.pdf").write_bytes(b"%PDF-1.7")

    candidates, ignored = kb_local_sync.collect_local_sync_candidates(root, recursive=True, max_files=10)

    assert [item.relative_path for item in candidates] == ["nested/guide.pdf", "policy.txt"]
    assert all(item.file_type in {"txt", "pdf"} for item in candidates)
    assert ignored == ["notes.md"]


def test_plan_local_directory_sync_marks_create_update_skip_and_soft_delete(tmp_path: Path) -> None:
    kb_local_sync = _load_kb_module("app.kb_local_sync")
    candidate_create = kb_local_sync.LocalSyncCandidate(
        absolute_path=tmp_path / "new.txt",
        relative_path="new.txt",
        file_name="new.txt",
        file_type="txt",
        size_bytes=10,
        content_hash="hash-new",
        source_uri="file:///new.txt",
        source_updated_at=kb_local_sync.datetime(2026, 3, 10, tzinfo=kb_local_sync.timezone.utc),
    )
    candidate_update = kb_local_sync.LocalSyncCandidate(
        absolute_path=tmp_path / "changed.txt",
        relative_path="changed.txt",
        file_name="changed.txt",
        file_type="txt",
        size_bytes=12,
        content_hash="hash-updated",
        source_uri="file:///changed.txt",
        source_updated_at=kb_local_sync.datetime(2026, 3, 10, tzinfo=kb_local_sync.timezone.utc),
    )
    candidate_skip = kb_local_sync.LocalSyncCandidate(
        absolute_path=tmp_path / "same.txt",
        relative_path="same.txt",
        file_name="same.txt",
        file_type="txt",
        size_bytes=8,
        content_hash="hash-same",
        source_uri="file:///same.txt",
        source_updated_at=kb_local_sync.datetime(2026, 3, 10, tzinfo=kb_local_sync.timezone.utc),
    )
    existing_documents = {
        "file:///changed.txt": {
            "id": "doc-update",
            "file_name": "changed.txt",
            "content_hash": "hash-old",
            "source_deleted_at": None,
            "source_metadata_json": {"relative_path": "changed.txt"},
        },
        "file:///same.txt": {
            "id": "doc-skip",
            "file_name": "same.txt",
            "content_hash": "hash-same",
            "source_deleted_at": None,
            "source_metadata_json": {"relative_path": "same.txt"},
        },
        "file:///missing.txt": {
            "id": "doc-delete",
            "file_name": "missing.txt",
            "content_hash": "hash-missing",
            "source_deleted_at": None,
            "source_metadata_json": {"relative_path": "missing.txt"},
        },
    }

    plan = kb_local_sync.plan_local_directory_sync(
        candidates=[candidate_create, candidate_update, candidate_skip],
        existing_documents=existing_documents,
        delete_missing=True,
    )

    assert [(item.action, item.reason) for item in plan] == [
        ("create", "new_source"),
        ("update", "content_changed"),
        ("skip", "unchanged"),
        ("soft_delete", "missing_from_source"),
    ]


def test_execute_local_directory_sync_dry_run_reports_actions(monkeypatch, tmp_path: Path) -> None:
    kb_local_sync = _load_kb_module("app.kb_local_sync")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    source_root = tmp_path / "allowed"
    source_root.mkdir()
    source_dir = source_root / "team-docs"
    source_dir.mkdir()
    (source_dir / "policy.txt").write_text("expense approval", encoding="utf-8")
    monkeypatch.setenv("KB_LOCAL_CONNECTOR_ROOTS", str(source_root))

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            self._rows = []
            return None

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_db = SimpleNamespace(connect=lambda: _Connection())
    fake_storage = SimpleNamespace()

    result = kb_local_sync.execute_local_directory_sync(
        base_id="base-1",
        source_path=str(source_dir),
        category="policies",
        recursive=True,
        delete_missing=True,
        dry_run=True,
        max_files=10,
        user=user,
        db=fake_db,
        storage=fake_storage,
    )

    assert result["dry_run"] is True
    assert result["counts"]["create"] == 1
    assert result["counts"]["update"] == 0
    assert result["counts"]["soft_delete"] == 0
    assert result["items"][0]["action"] == "create"
    assert result["items"][0]["relative_path"] == "policy.txt"
