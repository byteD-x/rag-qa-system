from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from shared import auth as auth_module
from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
KB_SRC = REPO_ROOT / "apps/services/knowledge-base/src"


def _load_kb_module(module_name: str):
    target = str(KB_SRC)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()
    module = importlib.import_module(module_name)
    return importlib.reload(module)


class _AclCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._source_rows = rows
        self._rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.calls.append((query, params))
        base_id = str(params[0])
        if len(params) == 5:
            requested_ids = {str(item) for item in params[1]}
            is_admin = bool(params[2])
            department = str(params[3] or "")
        else:
            requested_ids = None
            is_admin = bool(params[1])
            department = str(params[2] or "")

        def is_visible(row: dict[str, Any]) -> bool:
            allowed = {str(item).strip().lower() for item in row.get("allowed_departments", []) if str(item).strip()}
            return is_admin or not allowed or (bool(department) and department in allowed)

        self._rows = [
            row
            for row in self._source_rows
            if str(row.get("base_id")) == base_id
            and (requested_ids is None or str(row["id"]) in requested_ids)
            and is_visible(row)
        ]

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _AclConnection:
    def __init__(self, cursor: _AclCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self) -> _AclCursor:
        return self.cursor_instance

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def acl_documents() -> list[dict[str, Any]]:
    return [
        {"id": "doc-public", "base_id": "base-1", "allowed_departments": []},
        {"id": "doc-finance", "base_id": "base-1", "allowed_departments": ["finance"]},
        {"id": "doc-hr", "base_id": "base-1", "allowed_departments": ["hr"]},
    ]


@pytest.mark.parametrize(
    ("department", "is_admin", "expected_ids"),
    [
        ("finance", False, ["doc-public", "doc-finance"]),
        ("hr", False, ["doc-public", "doc-hr"]),
        ("", False, ["doc-public"]),
        ("finance", True, ["doc-public", "doc-finance", "doc-hr"]),
    ],
    ids=["same_department", "cross_department", "no_department_public_only", "administrator_all"],
)
def test_resolve_document_ids_applies_document_acl(
    monkeypatch,
    acl_documents: list[dict[str, Any]],
    department: str,
    is_admin: bool,
    expected_ids: list[str],
) -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    cursor = _AclCursor(acl_documents)
    monkeypatch.setattr(kb_retrieve.db, "connect", lambda: _AclConnection(cursor))

    resolved = kb_retrieve._resolve_document_ids(
        base_id="base-1",
        document_ids=[],
        user_department=department,
        is_admin=is_admin,
    )

    assert resolved == expected_ids
    query, params = cursor.calls[0]
    assert "allowed_departments" in query
    assert params[0] == "base-1"
    assert params[1:] == (is_admin, department.lower(), department.lower())


def test_explicit_document_ids_are_intersected_with_department_acl(
    monkeypatch,
    acl_documents: list[dict[str, Any]],
) -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    cursor = _AclCursor(acl_documents)
    monkeypatch.setattr(kb_retrieve.db, "connect", lambda: _AclConnection(cursor))

    resolved = kb_retrieve._resolve_document_ids(
        base_id="base-1",
        document_ids=["doc-hr", "doc-finance", "doc-public"],
        user_department="finance",
    )

    assert resolved == ["doc-public", "doc-finance"]
    query, params = cursor.calls[0]
    assert "id = ANY" in query
    assert params[1] == ["doc-hr", "doc-finance", "doc-public"]
    assert params[2:] == (False, "finance", "finance")


def test_retrieval_access_context_is_department_scoped_and_admin_is_global() -> None:
    kb_query_routes = _load_kb_module("app.kb_query_routes")
    member = auth_module.AuthUser(
        user_id="reader-1",
        email="reader@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
        department="finance",
    )
    no_department = auth_module.AuthUser(
        user_id="reader-2",
        email="reader2@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    admin = auth_module.AuthUser(
        user_id="admin-1",
        email="admin@local",
        role="platform_admin",
        permissions=auth_module.permissions_for_role("platform_admin"),
        department="hr",
    )

    assert kb_query_routes._retrieval_access_kwargs(member) == {"user_department": "finance"}
    assert kb_query_routes._retrieval_access_kwargs(no_department) == {}
    assert kb_query_routes._retrieval_access_kwargs(admin) == {"is_admin": True}


def test_shared_read_base_check_does_not_require_creator(monkeypatch) -> None:
    kb_store = _load_kb_module("app.kb_resource_store")
    calls: list[str] = []
    monkeypatch.setattr(
        kb_store,
        "load_base_unscoped",
        lambda base_id: calls.append(base_id) or {"id": base_id, "created_by": "owner-1"},
    )

    def fail_owner_scoped_lookup(*args, **kwargs):
        raise AssertionError("shared reads must not require knowledge-base ownership")

    monkeypatch.setattr(kb_store, "load_base", fail_owner_scoped_lookup)
    reader = auth_module.AuthUser(
        user_id="reader-1",
        email="reader@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
        department="finance",
    )

    kb_store.ensure_base_exists("base-1", user=reader, allow_shared_read=True)

    assert calls == ["base-1"]
