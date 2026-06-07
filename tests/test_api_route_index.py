from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/generate_api_route_index.py"
ROUTE_INDEX_PATH = REPO_ROOT / "docs/API_ROUTE_INDEX.md"


def _load_route_index_module():
    spec = importlib.util.spec_from_file_location("generate_api_route_index_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def test_parse_routes_from_file_extracts_fastapi_decorators(tmp_path: Path) -> None:
    module = _load_route_index_module()
    source = tmp_path / "sample_routes.py"
    source.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter, FastAPI",
                "",
                "router = APIRouter()",
                "app = FastAPI()",
                "",
                '@router.get("/healthz")',
                "def healthz():",
                "    return {'status': 'ok'}",
                "",
                '@router.api_route("/items/{item_id}", methods=["PATCH", "POST"])',
                "async def upsert_item():",
                "    return {}",
                "",
                '@app.route("/legacy")',
                "def legacy():",
                "    return {}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    routes = module.parse_routes_from_file(source, repo_root=tmp_path)

    assert [(route.path, route.methods, route.handler) for route in routes] == [
        ("/healthz", ("GET",), "healthz"),
        ("/items/{item_id}", ("PATCH", "POST"), "upsert_item"),
        ("/legacy", ("GET",), "legacy"),
    ]
    assert {route.source for route in routes} == {"sample_routes.py"}
    assert {route.service for route in routes} == {"custom"}


def test_api_route_index_document_matches_current_sources() -> None:
    module = _load_route_index_module()

    generated = module.generate_for_repo(repo_root=REPO_ROOT)

    assert ROUTE_INDEX_PATH.read_text(encoding="utf-8") == generated


def test_route_index_cli_writes_output_and_stdout(tmp_path: Path, capsys) -> None:
    module = _load_route_index_module()
    source_dir = tmp_path / "app"
    source_dir.mkdir()
    source = source_dir / "sample_routes.py"
    source.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                "",
                '@router.post("/api/v1/items")',
                "def create_item():",
                "    return {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "docs" / "routes.md"

    assert module.main(["--repo-root", str(tmp_path), str(source_dir), "--output", str(output)]) == 0
    written = output.read_text(encoding="utf-8")
    assert "`/api/v1/items`" in written
    assert "`create_item`" in written
    assert "`app/sample_routes.py:4`" in written

    assert module.main(["--repo-root", str(tmp_path), str(source)]) == 0
    stdout = capsys.readouterr().out
    assert "# API 路由清单" in stdout
    assert "`/api/v1/items`" in stdout


def test_route_index_cli_rejects_missing_explicit_source(tmp_path: Path) -> None:
    module = _load_route_index_module()
    output = tmp_path / "routes.md"

    with pytest.raises(SystemExit) as exc:
        module.main(["--repo-root", str(tmp_path), "missing_routes.py", "--output", str(output)])

    assert exc.value.code == 2
    assert not output.exists()
