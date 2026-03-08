from __future__ import annotations

import os
from pathlib import Path

from shared.storage import ObjectStorageClient

from .db import NovelDatabase


POSTGRES_DSN = os.getenv("NOVEL_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/novel_app?sslmode=disable")
BLOB_ROOT = Path(os.getenv("NOVEL_BLOB_ROOT", "/data/novel")).resolve()
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

db = NovelDatabase(POSTGRES_DSN, MIGRATIONS_DIR)
storage = ObjectStorageClient()


def ensure_runtime() -> None:
    BLOB_ROOT.mkdir(parents=True, exist_ok=True)
    db.ensure_schema()
    storage.ensure_bucket()
