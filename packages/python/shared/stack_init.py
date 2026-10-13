from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .qdrant_store import ensure_qdrant_collection
from .storage import create_object_storage_client


REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_MIGRATIONS_DIR = REPO_ROOT / "apps" / "services" / "api-gateway" / "database" / "migrations"
KB_MIGRATIONS_DIR = REPO_ROOT / "apps" / "services" / "knowledge-base" / "database" / "migrations"
GATEWAY_DATABASE_DSN = os.getenv("GATEWAY_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/gateway_app?sslmode=disable")
KB_DATABASE_DSN = os.getenv("KB_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/kb_app?sslmode=disable")
KB_BLOB_ROOT = Path(os.getenv("KB_BLOB_ROOT", "/data/kb")).resolve()
KB_SRC = REPO_ROOT / "apps" / "services" / "knowledge-base" / "src"
KB_VECTOR_PAYLOAD_SCHEMA_VERSION = "1"
INIT_RETRY_SECONDS = max(float(os.getenv("STACK_INIT_RETRY_SECONDS", "2")), 0.5)
INIT_RETRY_COUNT = max(int(os.getenv("STACK_INIT_RETRY_COUNT", "30")), 1)


@dataclass(frozen=True)
class MigrationFile:
    version: str
    checksum: str
    sql: str


def _wait_for_database(name: str, dsn: str) -> None:
    last_error = ""
    for _ in range(INIT_RETRY_COUNT):
        try:
            with psycopg.connect(dsn, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                conn.commit()
            return
        except psycopg.Error as exc:
            last_error = str(exc)
            time.sleep(INIT_RETRY_SECONDS)
    raise RuntimeError(f"{name} database is unavailable: {last_error}")


def _wait_for_vector_store() -> dict[str, object]:
    last_error = ""
    for _ in range(INIT_RETRY_COUNT):
        try:
            return ensure_qdrant_collection()
        except Exception as exc:
            last_error = str(exc)
            time.sleep(INIT_RETRY_SECONDS)
    raise RuntimeError(f"qdrant vector store is unavailable: {last_error}")


def _migration_checksum(raw_sql: str) -> str:
    return hashlib.sha256(raw_sql.encode("utf-8")).hexdigest()


def _load_migration_files(migrations_dir: Path) -> list[MigrationFile]:
    files: list[MigrationFile] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        raw_sql = path.read_text(encoding="utf-8")
        files.append(
            MigrationFile(
                version=path.name,
                checksum=_migration_checksum(raw_sql),
                sql=raw_sql,
            )
        )
    return files


def _ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _load_applied_migrations(cur) -> dict[str, str]:
    cur.execute(
        """
        SELECT version, checksum
        FROM schema_migrations
        ORDER BY version ASC
        """
    )
    return {str(row["version"]): str(row["checksum"]) for row in cur.fetchall()}


def _select_pending_migrations(files: list[MigrationFile], applied: dict[str, str]) -> list[MigrationFile]:
    pending: list[MigrationFile] = []
    for migration in files:
        applied_checksum = applied.get(migration.version)
        if applied_checksum is None:
            pending.append(migration)
            continue
        if applied_checksum != migration.checksum:
            raise RuntimeError(
                f"migration checksum mismatch for {migration.version}: expected {applied_checksum}, got {migration.checksum}"
            )
    return pending


def _apply_migrations(dsn: str, migrations_dir: Path) -> dict[str, object]:
    files = _load_migration_files(migrations_dir)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            _ensure_migration_table(cur)
        conn.commit()

        with conn.cursor() as cur:
            applied = _load_applied_migrations(cur)
        pending = _select_pending_migrations(files, applied)

        for migration in pending:
            with conn.cursor() as cur:
                cur.execute(migration.sql)
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (migration.version, migration.checksum),
                )
            conn.commit()
    return {
        "available": len(files),
        "applied": len(pending),
        "already_applied": len(files) - len(pending),
        "applied_versions": [migration.version for migration in pending],
    }


def _auto_rebuild_kb_vectors_if_needed() -> dict[str, object]:
    """Rebuild existing Qdrant payloads once after a vector payload migration.

    New documents are indexed by the normal ingest worker. Existing documents
    need one explicit pass because their stored Qdrant payload predates the
    generic knowledge-base metadata fields.
    """
    if os.getenv("KB_AUTO_REINDEX_AFTER_MIGRATION", "true").strip().lower() in {"0", "false", "no", "off"}:
        return {"status": "skipped", "reason": "disabled_by_config"}
    sys.path.insert(0, str(KB_SRC))
    runtime = importlib.import_module("app.runtime")
    vector_store = importlib.import_module("app.vector_store")
    with runtime.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state_value FROM kb_vector_index_state WHERE state_key = 'payload_schema_version' FOR UPDATE"
            )
            state = cur.fetchone()
            if state is None:
                return {"status": "not_required", "reason": "state_not_registered"}
            current = str(state.get("state_value") or "")
            if current == KB_VECTOR_PAYLOAD_SCHEMA_VERSION:
                return {"status": "already_ready", "version": current, "documents": 0}
            cur.execute(
                """
                SELECT id::text AS document_id
                FROM kb_documents
                WHERE source_deleted_at IS NULL
                  AND (query_ready = TRUE OR status = 'ready')
                ORDER BY created_at ASC
                """
            )
            document_ids = [str(row["document_id"]) for row in cur.fetchall()]

    vector_store.ensure_vector_store()
    rebuilt = 0
    indexed_sections = 0
    indexed_chunks = 0
    for document_id in document_ids:
        vector_store.delete_document_vectors(document_id)
        section_stats = vector_store.index_document_sections(document_id)
        chunk_stats = vector_store.index_document_chunks(document_id)
        rebuilt += 1
        indexed_sections += int(section_stats.get("indexed") or 0)
        indexed_chunks += int(chunk_stats.get("indexed") or 0)

    with runtime.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_vector_index_state
                SET state_value = %s, updated_at = NOW()
                WHERE state_key = 'payload_schema_version'
                """,
                (KB_VECTOR_PAYLOAD_SCHEMA_VERSION,),
            )
        conn.commit()
    return {
        "status": "rebuilt",
        "version": KB_VECTOR_PAYLOAD_SCHEMA_VERSION,
        "documents": rebuilt,
        "indexed_sections": indexed_sections,
        "indexed_chunks": indexed_chunks,
    }


def main() -> int:
    _wait_for_database("gateway", GATEWAY_DATABASE_DSN)
    _wait_for_database("knowledge-base", KB_DATABASE_DSN)

    gateway_migrations = _apply_migrations(GATEWAY_DATABASE_DSN, GATEWAY_MIGRATIONS_DIR)
    kb_migrations = _apply_migrations(KB_DATABASE_DSN, KB_MIGRATIONS_DIR)

    KB_BLOB_ROOT.mkdir(parents=True, exist_ok=True)
    storage = create_object_storage_client()
    storage.ensure_bucket()
    vector_store = _wait_for_vector_store()
    vector_rebuild = _auto_rebuild_kb_vectors_if_needed()

    print(
        json.dumps(
            {
                "status": "ok",
                "gateway_migrations": gateway_migrations,
                "kb_migrations": kb_migrations,
                "blob_root": str(KB_BLOB_ROOT),
                "bucket": getattr(storage.settings, "bucket", "filesystem"),
                "vector_store": vector_store,
                "vector_rebuild": vector_rebuild,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
