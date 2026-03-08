from __future__ import annotations

import os
from pathlib import Path

from shared.storage import ObjectStorageClient

from .db import KBDatabase


POSTGRES_DSN = os.getenv("KB_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/kb_app?sslmode=disable")
BLOB_ROOT = Path(os.getenv("KB_BLOB_ROOT", "/data/kb")).resolve()
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"

db = KBDatabase(POSTGRES_DSN, MIGRATIONS_DIR)
storage = ObjectStorageClient()


def ensure_runtime() -> None:
    BLOB_ROOT.mkdir(parents=True, exist_ok=True)
    db.ensure_schema()
    storage.ensure_bucket()
