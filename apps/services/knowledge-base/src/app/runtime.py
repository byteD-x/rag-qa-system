from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from shared.storage import ObjectStorageClient

from .db import KBDatabase


POSTGRES_DSN = os.getenv("KB_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/kb_app?sslmode=disable")
BLOB_ROOT = Path(os.getenv("KB_BLOB_ROOT", "/data/kb")).resolve()
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"

db = KBDatabase(POSTGRES_DSN, MIGRATIONS_DIR)
storage = ObjectStorageClient()


@dataclass(frozen=True)
class KBChunkingSettings:
    max_tokens: int | None = None
    token_overlap: int | None = None

    @property
    def enabled(self) -> bool:
        return self.max_tokens is not None

    def as_kwargs(self) -> dict[str, int]:
        if self.max_tokens is None:
            return {}
        kwargs = {"max_tokens": self.max_tokens}
        if self.token_overlap is not None:
            kwargs["token_overlap"] = self.token_overlap
        return kwargs

    def summary(self) -> dict[str, int | str | bool | None]:
        return {
            "enabled": self.enabled,
            "mode": "token_budget" if self.enabled else "character_window",
            "max_tokens": self.max_tokens,
            "token_overlap": self.token_overlap,
        }


def load_chunking_settings() -> KBChunkingSettings:
    max_tokens = _optional_int_env("KB_CHUNK_MAX_TOKENS", minimum=1)
    token_overlap = _optional_int_env("KB_CHUNK_TOKEN_OVERLAP", minimum=0)
    if max_tokens is None and token_overlap is not None:
        raise ValueError("KB_CHUNK_TOKEN_OVERLAP requires KB_CHUNK_MAX_TOKENS")
    return KBChunkingSettings(max_tokens=max_tokens, token_overlap=token_overlap)


def load_chunking_summary() -> dict[str, int | str | bool | None]:
    return load_chunking_settings().summary()


def prepare_runtime() -> None:
    BLOB_ROOT.mkdir(parents=True, exist_ok=True)


def _optional_int_env(name: str, *, minimum: int) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value
