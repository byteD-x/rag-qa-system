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
    for name in (
        module_name,
        "app.main",
        "app.kb_connector_sync",
        "app.kb_local_sync",
        "app.kb_notion_sync",
        "app.runtime",
        "app.db",
        "app",
    ):
        sys.modules.pop(name, None)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_notion_connector_requires_enable_flag_and_token(monkeypatch) -> None:
    kb_notion_sync = _load_kb_module("app.kb_notion_sync")
    monkeypatch.delenv("KB_NOTION_CONNECTOR_ENABLED", raising=False)
    monkeypatch.delenv("KB_NOTION_API_TOKEN", raising=False)

    class _Client:
        def request(self, method: str, url: str, headers: dict[str, str]):
            raise AssertionError("request should not be attempted when connector is disabled")

    with pytest.raises(HTTPException) as exc_info:
        kb_notion_sync.fetch_notion_page_candidate(_Client(), "0123456789abcdef0123456789abcdef")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "notion_connector_disabled"


def test_collect_notion_sync_candidates_builds_text_document(monkeypatch) -> None:
    kb_notion_sync = _load_kb_module("app.kb_notion_sync")
    monkeypatch.setenv("KB_NOTION_CONNECTOR_ENABLED", "true")
    monkeypatch.setenv("KB_NOTION_API_TOKEN", "secret-token")

    class _Response:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def request(self, method: str, url: str, headers: dict[str, str]):
            assert headers["Authorization"] == "Bearer secret-token"
            if "/pages/" in url:
                return _Response(
                    {
                        "id": "01234567-89ab-cdef-0123-456789abcdef",
                        "url": "https://www.notion.so/expense-policy",
                        "last_edited_time": "2026-03-10T10:00:00.000Z",
                        "parent": {"type": "workspace"},
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "Expense Policy"}],
                            }
                        },
                    }
                )
            if "/blocks/" in url and "/children" in url:
                return _Response(
                    {
                        "results": [
                            {
                                "id": "block-1",
                                "type": "heading_1",
                                "has_children": False,
                                "heading_1": {"rich_text": [{"plain_text": "Approval Flow"}]},
                            },
                            {
                                "id": "block-2",
                                "type": "to_do",
                                "has_children": False,
                                "to_do": {"checked": True, "rich_text": [{"plain_text": "Finance review required"}]},
                            },
                        ]
                    }
                )
            raise AssertionError(f"unexpected url: {url}")

    candidates = kb_notion_sync.collect_notion_sync_candidates(
        ["01234567-89ab-cdef-0123-456789abcdef"],
        max_pages=4,
        client=_Client(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.file_name == "notion-page-0123456789abcdef0123456789abcdef.txt"
    assert candidate.source_metadata["page_title"] == "Expense Policy"
    assert candidate.source_metadata["parent_type"] == "workspace"
    assert candidate.content_type == "text/plain; charset=utf-8"
    assert b"# Expense Policy" in candidate.content_bytes
    assert b"Approval Flow" in candidate.content_bytes
    assert b"[x] Finance review required" in candidate.content_bytes


def test_execute_notion_sync_dry_run_reports_actions(monkeypatch) -> None:
    kb_notion_sync = _load_kb_module("app.kb_notion_sync")
    monkeypatch.setenv("KB_NOTION_CONNECTOR_ENABLED", "true")
    monkeypatch.setenv("KB_NOTION_API_TOKEN", "secret-token")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    class _Response:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method: str, url: str, headers: dict[str, str]):
            if "/pages/" in url:
                return _Response(
                    {
                        "id": "01234567-89ab-cdef-0123-456789abcdef",
                        "url": "https://www.notion.so/expense-policy",
                        "last_edited_time": "2026-03-10T10:00:00.000Z",
                        "parent": {"type": "workspace"},
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "Expense Policy"}],
                            }
                        },
                    }
                )
            return _Response({"results": [{"id": "block-1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": [{"plain_text": "approval from finance"}]}}]})

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

    result = kb_notion_sync.execute_notion_sync(
        base_id="base-1",
        page_ids=["01234567-89ab-cdef-0123-456789abcdef"],
        category="policies",
        delete_missing=True,
        dry_run=True,
        max_pages=10,
        user=user,
        db=fake_db,
        storage=fake_storage,
        client_factory=lambda: _Client(),
    )

    assert result["dry_run"] is True
    assert result["counts"]["create"] == 1
    assert result["counts"]["update"] == 0
    assert result["counts"]["soft_delete"] == 0
    assert result["page_ids"] == ["0123456789abcdef0123456789abcdef"]
    assert result["items"][0]["file_name"] == "notion-page-0123456789abcdef0123456789abcdef.txt"
