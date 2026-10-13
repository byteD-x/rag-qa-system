from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class KBDatabase:
    def __init__(self, dsn: str, migrations_dir: Path):
        self._dsn = dsn
        self._migrations_dir = migrations_dir
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> ConnectionPool:
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    max_size = max(int(os.getenv("KB_DB_POOL_MAX_SIZE", "10") or "10"), 1)
                    pool = ConnectionPool(
                        self._dsn,
                        min_size=1,
                        max_size=max_size,
                        kwargs={"row_factory": dict_row},
                        open=False,
                    )
                    pool.open()
                    self._pool = pool
        return self._pool

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        with self._get_pool().connection() as conn:
            yield conn

    def close(self) -> None:
        if self._pool is not None:
            with self._pool_lock:
                if self._pool is not None:
                    self._pool.close()
                    self._pool = None

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                for migration in sorted(self._migrations_dir.glob("*.sql")):
                    cur.execute(migration.read_text(encoding="utf-8"))
            conn.commit()


def _json_default(value: Any) -> str:
    """psycopg 的 timestamptz 返回 datetime,序列化前归一为 ISO 字符串。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def to_json(data: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False, default=_json_default)
