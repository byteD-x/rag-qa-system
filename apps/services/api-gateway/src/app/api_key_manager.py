"""API Key 生命周期管理器。

核心能力：
- API Key 创建（带权限和配额）
- Key 轮换（保留旧 Key 一段时间后自动失效）
- Key 验证与速率限制
- Key 过期与自动撤销
- 使用统计（调用次数、Token 消耗）

使用方式::

    from .api_key_manager import APIKeyManager

    mgr = APIKeyManager()
    key = mgr.create_key(user_id="user-1", permissions=["chat.use"], quota_tokens=10000)
    valid, identity = mgr.validate(key.raw_key)
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class KeyStatus(str, Enum):
    ACTIVE = "active"
    ROTATING = "rotating"  # 旧 Key 轮换中
    REVOKED = "revoked"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"


@dataclass
class APIKey:
    """API Key 条目。"""
    id: str                          # 内部 ID
    key_prefix: str                  # 前缀（存储用）: "rag_sk_AbCd..."
    key_hash: str                    # SHA256 哈希（安全存储）
    user_id: str
    name: str = ""                   # 用户可读名称
    permissions: list[str] = field(default_factory=list)
    status: str = "active"           # KeyStatus
    quota_tokens: int = 0            # Token 配额（0=无限）
    tokens_used: int = 0
    rate_limit_per_minute: int = 60
    request_count_this_minute: int = 0
    rate_limit_reset_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0          # 过期时间（0=永不过期）
    last_used_at: float = 0.0
    rotated_from: str = ""            # 来源于哪个 Key 的轮换
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API Key 管理器
# ---------------------------------------------------------------------------


class APIKeyManager:
    """API Key 生命周期管理器。"""

    KEY_PREFIX = "rag_sk_"
    DEFAULT_QUOTA_TOKENS = 100_000
    DEFAULT_RATE_LIMIT = 60  # 每分钟
    ROTATION_GRACE_SECONDS = 24 * 60 * 60

    def __init__(self, db: Any | None = None) -> None:
        self._keys: dict[str, APIKey] = {}  # id → APIKey
        self._hash_index: dict[str, str] = {}  # hash → id
        self._db = db

    def create_key(
        self,
        user_id: str,
        *,
        name: str = "",
        permissions: list[str] | None = None,
        quota_tokens: int = 0,
        rate_limit_per_minute: int = 60,
        expires_in_days: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建新的 API Key。

        返回包含 raw_key 的字典（raw_key 仅在创建时返回，不可二次获取）。
        """
        raw_key = self.KEY_PREFIX + secrets.token_urlsafe(32)
        key_hash = self._hash(raw_key)
        key_id = f"key_{uuid.uuid4().hex[:12]}"

        api_key = APIKey(
            id=key_id,
            key_prefix=raw_key[:12] + "...",
            key_hash=key_hash,
            user_id=user_id,
            name=name or f"Key-{uuid.uuid4().hex[:4]}",
            permissions=permissions or ["chat.use"],
            quota_tokens=quota_tokens or self.DEFAULT_QUOTA_TOKENS,
            rate_limit_per_minute=rate_limit_per_minute,
            expires_at=time.time() + expires_in_days * 86400 if expires_in_days > 0 else 0,
            metadata=metadata or {},
        )

        if self._db is not None:
            from .db import to_json
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO platform_api_keys
                        (id, user_id, name, key_prefix, key_hash, permissions_json, quota_tokens, rate_limit_per_minute, expires_at, rotated_from, metadata_json)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, to_timestamp(NULLIF(%s, 0)), %s, %s::jsonb)
                        """,
                        (api_key.id, api_key.user_id, api_key.name, api_key.key_prefix, api_key.key_hash, to_json(api_key.permissions), api_key.quota_tokens, api_key.rate_limit_per_minute, api_key.expires_at, str((api_key.metadata or {}).get("rotated_from") or "") or None, to_json(api_key.metadata)),
                    )
                conn.commit()
        else:
            self._keys[key_id] = api_key
            self._hash_index[key_hash] = key_id

        logger.info("apikey_created id=%s user=%s permissions=%s", key_id, user_id, permissions)

        return {
            "id": key_id,
            "name": api_key.name,
            "prefix": api_key.key_prefix,
            "raw_key": raw_key,  # 仅在创建时返回！
            "permissions": api_key.permissions,
            "quota_tokens": api_key.quota_tokens,
            "rate_limit_per_minute": api_key.rate_limit_per_minute,
            "created_at": api_key.created_at,
            "expires_at": api_key.expires_at if api_key.expires_at > 0 else None,
        }

    def validate(self, raw_key: str) -> tuple[bool, dict[str, Any]]:
        """验证 API Key。

        返回:
            (是否有效, 身份信息)
        """
        if not raw_key or not raw_key.startswith(self.KEY_PREFIX):
            return False, {"reason": "无效的 Key 格式"}

        key_hash = self._hash(raw_key)
        key_id = self._hash_index.get(key_hash)
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM platform_api_keys WHERE key_hash = %s FOR UPDATE", (key_hash,))
                    row = cur.fetchone()
                    if row is None:
                        return False, {"reason": "Key 不存在"}
                    key_id = str(row["id"])
                    api_key = self._row_to_api_key(row)
                    valid, identity = self._validate_loaded(api_key)
                    if valid:
                        cur.execute("UPDATE platform_api_keys SET request_count_this_minute = %s, rate_limit_reset_at = %s, last_used_at = NOW(), status = %s WHERE id = %s", (api_key.request_count_this_minute, api_key.rate_limit_reset_at, api_key.status, api_key.id))
                    elif api_key.status != str(row.get("status") or ""):
                        cur.execute("UPDATE platform_api_keys SET status = %s, metadata_json = %s::jsonb WHERE id = %s", (api_key.status, __import__("json").dumps(api_key.metadata), api_key.id))
                conn.commit()
            return valid, identity
        if key_id is None:
            return False, {"reason": "Key 不存在"}

        api_key = self._keys.get(key_id)
        if api_key is None:
            return False, {"reason": "Key 数据异常"}

        return self._validate_loaded(api_key, key_id=key_id)

    def _validate_loaded(self, api_key: APIKey, *, key_id: str | None = None) -> tuple[bool, dict[str, Any]]:
        key_id = key_id or api_key.id
        # 状态检查
        if api_key.status == KeyStatus.REVOKED.value:
            return False, {"reason": "Key 已撤销"}
        if api_key.status == KeyStatus.ROTATING.value:
            rotating_until = float(api_key.metadata.get("rotating_until") or 0)
            if rotating_until and time.time() > rotating_until:
                api_key.status = KeyStatus.REVOKED.value
                return False, {"reason": "Key 轮换宽限期已结束"}
        if api_key.status == KeyStatus.EXPIRED.value:
            return False, {"reason": "Key 已过期"}
        if api_key.expires_at > 0 and time.time() > api_key.expires_at:
            api_key.status = KeyStatus.EXPIRED.value
            return False, {"reason": "Key 已过期"}

        # 配额检查
        if api_key.quota_tokens > 0 and api_key.tokens_used >= api_key.quota_tokens:
            return False, {"reason": "Token 配额已用尽"}

        # 速率限制
        now = time.time()
        if now > api_key.rate_limit_reset_at:
            api_key.request_count_this_minute = 0
            api_key.rate_limit_reset_at = now + 60

        if api_key.request_count_this_minute >= api_key.rate_limit_per_minute:
            api_key.status = KeyStatus.RATE_LIMITED.value
            return False, {"reason": f"速率限制 ({api_key.rate_limit_per_minute}/min)"}

        api_key.request_count_this_minute += 1
        api_key.last_used_at = now
        if api_key.status == KeyStatus.RATE_LIMITED.value:
            api_key.status = KeyStatus.ACTIVE.value

        return True, {
            "key_id": key_id,
            "user_id": api_key.user_id,
            "permissions": api_key.permissions,
            "quota_remaining": max(api_key.quota_tokens - api_key.tokens_used, 0) if api_key.quota_tokens > 0 else -1,
        }

    @staticmethod
    def _row_to_api_key(row: dict[str, Any]) -> APIKey:
        expires = row.get("expires_at")
        expires_at = expires.timestamp() if hasattr(expires, "timestamp") else float(expires or 0)
        last_used = row.get("last_used_at")
        last_used_at = last_used.timestamp() if hasattr(last_used, "timestamp") else float(last_used or 0)
        created = row.get("created_at")
        created_at = created.timestamp() if hasattr(created, "timestamp") else float(created or time.time())
        return APIKey(
            id=str(row["id"]), user_id=str(row["user_id"]), name=str(row.get("name") or ""),
            key_prefix=str(row.get("key_prefix") or ""), key_hash=str(row.get("key_hash") or ""),
            permissions=list(row.get("permissions_json") or []), status=str(row.get("status") or "active"),
            quota_tokens=int(row.get("quota_tokens") or 0), tokens_used=int(row.get("tokens_used") or 0),
            rate_limit_per_minute=int(row.get("rate_limit_per_minute") or 60),
            request_count_this_minute=int(row.get("request_count_this_minute") or 0),
            rate_limit_reset_at=float(row.get("rate_limit_reset_at") or 0), created_at=created_at, expires_at=expires_at,
            last_used_at=last_used_at, rotated_from=str(row.get("rotated_from") or ""), metadata=dict(row.get("metadata_json") or {}),
        )

    def record_usage(self, key_id: str, tokens: int) -> None:
        """记录 API Key 使用量。"""
        api_key = self._keys.get(key_id)
        if api_key is not None:
            api_key.tokens_used += tokens
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE platform_api_keys SET tokens_used = tokens_used + %s WHERE id = %s", (max(int(tokens), 0), key_id))
                conn.commit()

    def rotate_key(self, key_id: str) -> dict[str, Any] | None:
        """轮换 API Key（创建新 Key，标记旧 Key 为 rotating）。"""
        old_key = self._keys.get(key_id)
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM platform_api_keys WHERE id = %s FOR UPDATE", (key_id,))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    old_key = self._row_to_api_key(row)
                    old_key.status = KeyStatus.ROTATING.value
                    old_key.metadata["rotating_until"] = time.time() + self.ROTATION_GRACE_SECONDS
                    from .db import to_json
                    cur.execute("UPDATE platform_api_keys SET status = %s, metadata_json = %s::jsonb WHERE id = %s", (old_key.status, to_json(old_key.metadata), key_id))
                conn.commit()
        if old_key is None:
            return None

        old_key.status = KeyStatus.ROTATING.value
        old_key.metadata["rotating_until"] = time.time() + self.ROTATION_GRACE_SECONDS

        # 创建新 Key
        new = self.create_key(
            user_id=old_key.user_id,
            name=f"{old_key.name}-rotated",
            permissions=list(old_key.permissions),
            quota_tokens=max(old_key.quota_tokens - old_key.tokens_used, 0),
            rate_limit_per_minute=old_key.rate_limit_per_minute,
            metadata={"rotated_from": key_id},
        )

        logger.info("apikey_rotated old=%s new=%s", key_id, new["id"])
        return new

    def revoke(self, key_id: str) -> bool:
        """撤销 API Key。"""
        api_key = self._keys.get(key_id)
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE platform_api_keys SET status = 'revoked' WHERE id = %s", (key_id,))
                    changed = cur.rowcount > 0
                conn.commit()
            return changed
        if api_key is None:
            return False
        api_key.status = KeyStatus.REVOKED.value
        logger.info("apikey_revoked id=%s", key_id)
        return True

    def list_keys(self, user_id: str = "") -> list[dict[str, Any]]:
        """列出 API Keys。"""
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    if user_id:
                        cur.execute("SELECT * FROM platform_api_keys WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
                    else:
                        cur.execute("SELECT * FROM platform_api_keys ORDER BY created_at DESC")
                    rows = cur.fetchall()
            return [self._serialize(self._row_to_api_key(row)) for row in rows]
        keys = self._keys.values()
        if user_id:
            keys = [k for k in keys if k.user_id == user_id]
        return [
            {
                "id": k.id,
                "name": k.name,
                "prefix": k.key_prefix,
                "user_id": k.user_id,
                "permissions": k.permissions,
                "status": k.status,
                "quota_tokens": k.quota_tokens,
                "tokens_used": k.tokens_used,
                "created_at": k.created_at,
                "expires_at": k.expires_at if k.expires_at > 0 else None,
                "last_used_at": k.last_used_at,
            }
            for k in keys
        ]

    def stats(self, key_id: str) -> dict[str, Any] | None:
        """获取 API Key 使用统计。"""
        api_key = self._keys.get(key_id)
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM platform_api_keys WHERE id = %s", (key_id,))
                    row = cur.fetchone()
            api_key = self._row_to_api_key(row) if row else None
        if api_key is None:
            return None
        return {
            "tokens_used": api_key.tokens_used,
            "quota_tokens": api_key.quota_tokens,
            "quota_usage_pct": round(api_key.tokens_used / api_key.quota_tokens * 100, 2) if api_key.quota_tokens > 0 else 0,
            "requests_this_minute": api_key.request_count_this_minute,
            "rate_limit": api_key.rate_limit_per_minute,
            "last_used_at": api_key.last_used_at,
        }

    @staticmethod
    def _serialize(k: APIKey) -> dict[str, Any]:
        return {"id": k.id, "name": k.name, "prefix": k.key_prefix, "user_id": k.user_id, "permissions": k.permissions, "status": k.status, "quota_tokens": k.quota_tokens, "tokens_used": k.tokens_used, "created_at": k.created_at, "expires_at": k.expires_at if k.expires_at > 0 else None, "last_used_at": k.last_used_at}

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
