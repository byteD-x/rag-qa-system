from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from shared import auth as auth_module


REPO_ROOT = Path(__file__).resolve().parents[1]
KB_SRC = REPO_ROOT / "apps/services/knowledge-base/src"
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


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
        "app.kb_sql_sync",
        "app.kb_url_sync",
        "app.runtime",
        "app.db",
        "app",
    ):
        sys.modules.pop(name, None)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _load_gateway_module(module_name: str):
    _prioritize_sys_path(GATEWAY_SRC)
    for name in (
        module_name,
        "app.main",
        "app.gateway_chat_service",
        "app.gateway_platform_store",
        "app.gateway_scope",
        "app.gateway_schemas",
        "app",
    ):
        sys.modules.pop(name, None)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_scope_payload_preserves_agent_profile_and_prompt_template_ids() -> None:
    gateway_scope = _load_gateway_module("app.gateway_scope")
    gateway_schemas = _load_gateway_module("app.gateway_schemas")

    payload = gateway_schemas.ChatScopePayload(
        mode="multi",
        corpus_ids=["kb:base-1"],
        agent_profile_id="profile-1",
        prompt_template_id="template-1",
    )

    normalized = gateway_scope.normalize_scope_payload(payload)

    assert normalized["agent_profile_id"] == "profile-1"
    assert normalized["prompt_template_id"] == "template-1"


def test_platform_instruction_text_combines_template_persona_and_tools() -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")

    result = gateway_chat_service._platform_instruction_text(
        {
            "prompt_template": {"content": "Always answer in bullet points."},
            "agent_profile": {
                "persona_prompt": "You are the finance policy analyst.",
                "enabled_tools": ["search_scope", "calculator"],
            },
        }
    )

    assert "Always answer in bullet points." in result
    assert "finance policy analyst" in result
    assert "search_scope" in result
    assert "calculator" in result


def test_execute_url_sync_dry_run_builds_text_candidates(monkeypatch) -> None:
    kb_url_sync = _load_kb_module("app.kb_url_sync")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    class _Response:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8") -> None:
            self.text = text
            self.status_code = 200
            self.headers = {"content-type": content_type}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, headers: dict[str, str]):
            assert headers == {}
            return _Response("<html><head><title>Expense Policy</title></head><body><h1>审批规则</h1><p>财务审批必填。</p></body></html>")

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            self._rows = []

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

    result = kb_url_sync.execute_url_sync(
        base_id="base-1",
        connector_type="web_crawler",
        urls=["https://docs.example.test/policy"],
        category="policies",
        delete_missing=True,
        dry_run=True,
        max_urls=8,
        user=user,
        db=fake_db,
        storage=fake_storage,
        client_factory=lambda: _Client(),
    )

    assert result["dry_run"] is True
    assert result["counts"]["create"] == 1
    assert result["urls"] == ["https://docs.example.test/policy"]
    assert result["items"][0]["file_name"] == "Expense-Policy.txt"


def test_execute_sql_sync_dry_run_converts_rows_to_documents(monkeypatch) -> None:
    kb_sql_sync = _load_kb_module("app.kb_sql_sync")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    monkeypatch.setenv("KB_REPORTING_DSN", "postgresql://example")

    rows = [
        {
            "id": "row-1",
            "title": "Expense Rule",
            "content": "超过 500 元需要财务复核",
            "updated_at": "2026-03-10T10:00:00+00:00",
        }
    ]

    class _Cursor:
        def execute(self, query):
            assert query.lower().startswith("select")

        def fetchmany(self, size: int):
            assert size >= 2
            return list(rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_sql_sync.psycopg, "connect", lambda *args, **kwargs: _Connection())

    class _ConnectorCursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            self._rows = []

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _ConnectorConnection:
        def cursor(self):
            return _ConnectorCursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_db = SimpleNamespace(connect=lambda: _ConnectorConnection())
    fake_storage = SimpleNamespace()

    result = kb_sql_sync.execute_sql_sync(
        base_id="base-1",
        dsn_env="KB_REPORTING_DSN",
        query="SELECT id, title, content, updated_at FROM expense_rules",
        id_column="id",
        text_column="content",
        title_column="title",
        updated_at_column="updated_at",
        category="rules",
        delete_missing=True,
        dry_run=True,
        max_rows=8,
        user=user,
        db=fake_db,
        storage=fake_storage,
    )

    assert result["dry_run"] is True
    assert result["counts"]["create"] == 1
    assert result["row_count"] == 1
    assert result["items"][0]["file_name"] == "Expense-Rule.txt"
