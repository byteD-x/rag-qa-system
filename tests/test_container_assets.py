from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _dockerignore_patterns() -> set[str]:
    return {
        line.strip()
        for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_dockerignore_excludes_local_secrets_and_runtime_state() -> None:
    patterns = _dockerignore_patterns()

    assert ".env" in patterns
    assert ".env.*" in patterns
    assert ".venv" in patterns
    assert "node_modules" in patterns
    assert "data" in patterns
    assert "logs" in patterns
    assert "artifacts" in patterns
    assert "agent_runs" in patterns
    assert ".codex" in patterns
    assert "secrets" in patterns


def test_dockerignore_keeps_service_sources_and_env_examples_available() -> None:
    patterns = _dockerignore_patterns()

    assert "apps/services/api-gateway" not in patterns
    assert "apps/services/knowledge-base" not in patterns
    assert "packages/python" not in patterns
    assert "!.env.example" in patterns
    assert "!.env.production.example" in patterns
