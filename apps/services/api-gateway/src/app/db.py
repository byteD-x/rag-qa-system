from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


POSTGRES_DSN = os.getenv("GATEWAY_DATABASE_DSN", "postgresql://rag:rag@postgres:5432/gateway_app?sslmode=disable")
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"


class GatewayDatabase:
    def __init__(self, dsn: str, migrations_dir: Path):
        self._dsn = dsn
        self._migrations_dir = migrations_dir
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    @property
    def dsn(self) -> str:
        return self._dsn

    def _get_pool(self) -> ConnectionPool:
        # 懒创建:仅在首次真正用库时建池,避免 import 期或无库测试触发连接。
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    max_size = max(int(os.getenv("GATEWAY_DB_POOL_MAX_SIZE", "10") or "10"), 1)
                    pool = ConnectionPool(
                        self._dsn,
                        min_size=1,
                        max_size=max_size,
                        kwargs={"row_factory": dict_row},
                        open=False,
                    )
                    pool.open()  # 非阻塞后台预热,首个 connection() 再等待可用连接
                    self._pool = pool
        return self._pool

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        # 复用池内连接;成功提交、异常回滚由 pool.connection() 保证,与旧 psycopg.connect 语义一致。
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


def to_json(data: dict[str, Any] | list[Any] | None) -> str:
    payload: dict[str, Any] | list[Any]
    if data is None:
        payload = {}
    else:
        payload = data
    return json.dumps(payload, ensure_ascii=False)
