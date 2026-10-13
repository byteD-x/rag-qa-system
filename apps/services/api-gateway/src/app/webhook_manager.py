"""Webhook 管理器 —— 回调注册、触发、重试与签名验证。

核心能力：
- Webhook 注册（URL + 事件类型 + 密钥）
- 异步回调触发（支持重试 + 指数退避）
- HMAC-SHA256 签名验证
- 执行历史记录

使用方式::

    from .webhook_manager import WebhookManager

    mgr = WebhookManager()
    mgr.register("https://example.com/hook", events=["chat.completed"], secret="wh_xxx")
    await mgr.trigger("chat.completed", payload={"answer": "..."})
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class WebhookRegistration:
    """Webhook 注册条目。"""
    id: str
    url: str
    events: list[str] = field(default_factory=list)  # 监听的事件类型
    secret: str = ""  # HMAC 签名密钥
    is_active: bool = True
    description: str = ""
    created_at: float = field(default_factory=time.time)
    retry_count: int = 3  # 最大重试次数
    timeout_seconds: float = 30.0
    owner_user_id: str = ""


@dataclass
class WebhookDelivery:
    """Webhook 投递记录。"""
    id: str
    webhook_id: str
    event: str
    url: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending / success / failed
    http_status: int = 0
    response_body: str = ""
    error: str = ""
    attempt: int = 1
    duration_ms: float = 0.0
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Webhook 管理器
# ---------------------------------------------------------------------------


class WebhookManager:
    """Webhook 注册、触发、重试管理器。"""

    # 指数退避配置
    RETRY_BACKOFF_BASE = 2.0   # 秒
    RETRY_BACKOFF_MAX = 60.0   # 秒
    MAX_RETRY_ATTEMPTS = 3

    def __init__(self, db: Any | None = None) -> None:
        self._registrations: dict[str, WebhookRegistration] = {}
        self._delivery_history: dict[str, list[WebhookDelivery]] = {}  # webhook_id → deliveries
        self._db = db

    def register(
        self,
        url: str,
        *,
        events: list[str] | None = None,
        secret: str = "",
        description: str = "",
        retry_count: int = 3,
        timeout_seconds: float = 30.0,
        owner_user_id: str = "",
    ) -> WebhookRegistration:
        """注册一个新的 Webhook。"""
        webhook_id = f"wh_{uuid.uuid4().hex[:12]}"
        reg = WebhookRegistration(
            id=webhook_id,
            url=url.rstrip("/"),
            events=events or ["*"],
            secret=secret,
            description=description,
            retry_count=retry_count,
            timeout_seconds=timeout_seconds,
            owner_user_id=owner_user_id,
        )
        self._registrations[webhook_id] = reg
        self._delivery_history[webhook_id] = []
        if self._db is not None:
            from .db import to_json
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO platform_webhooks (id, owner_user_id, url, events_json, secret, description, retry_count, timeout_seconds)
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                        """,
                        (reg.id, reg.owner_user_id, reg.url, to_json(reg.events), reg.secret, reg.description, reg.retry_count, reg.timeout_seconds),
                    )
                conn.commit()
        logger.info("webhook_registered id=%s url=%s events=%s", webhook_id, url, events)
        return reg

    def unregister(self, webhook_id: str) -> bool:
        """注销 Webhook。"""
        if webhook_id not in self._registrations:
            if self._db is not None:
                with self._db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE platform_webhooks SET is_active = FALSE WHERE id = %s", (webhook_id,))
                        changed = cur.rowcount > 0
                    conn.commit()
                return changed
            return False
        self._registrations[webhook_id].is_active = False
        logger.info("webhook_unregistered id=%s", webhook_id)
        return True

    def update(self, webhook_id: str, *, owner_user_id: str, is_active: bool | None = None, description: str | None = None, events: list[str] | None = None) -> WebhookRegistration | None:
        """更新 Webhook 配置，调用方必须先完成资源归属校验。"""
        reg = self._registrations.get(webhook_id)
        if reg is None and self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM platform_webhooks WHERE id = %s AND owner_user_id = %s", (webhook_id, owner_user_id))
                    row = cur.fetchone()
            reg = self._row_to_registration(row) if row else None
        if reg is None or reg.owner_user_id != owner_user_id:
            return None
        if is_active is not None:
            reg.is_active = is_active
        if description is not None:
            reg.description = description
        if events is not None:
            reg.events = events or ["*"]
        if self._db is not None:
            from .db import to_json
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE platform_webhooks SET is_active = %s, description = %s, events_json = %s::jsonb WHERE id = %s AND owner_user_id = %s", (reg.is_active, reg.description, to_json(reg.events), reg.id, owner_user_id))
                conn.commit()
        return reg

    def list_hooks(self, user_id: str = "") -> list[WebhookRegistration]:
        """列出所有注册的 Webhook。"""
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    if user_id:
                        cur.execute("SELECT * FROM platform_webhooks WHERE owner_user_id = %s ORDER BY created_at DESC", (user_id,))
                    else:
                        cur.execute("SELECT * FROM platform_webhooks ORDER BY created_at DESC")
                    rows = cur.fetchall()
            return [self._row_to_registration(row) for row in rows]
        hooks = self._registrations.values()
        if user_id:
            hooks = [hook for hook in hooks if hook.owner_user_id == user_id]
        return list(hooks)

    async def trigger(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        webhook_id: str = "",
    ) -> list[WebhookDelivery]:
        """触发 Webhook 回调。

        参数:
            event: 事件类型
            payload: 回调载荷
            webhook_id: 指定 webhook（为空则触发所有匹配的）

        返回:
            投递记录列表
        """
        # 找到匹配的 webhooks
        targets = []
        if webhook_id:
            reg = self._registrations.get(webhook_id)
            if reg is None and self._db is not None:
                with self._db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT * FROM platform_webhooks WHERE id = %s", (webhook_id,))
                        row = cur.fetchone()
                reg = self._row_to_registration(row) if row else None
            if reg and reg.is_active:
                targets = [reg]
        else:
            registrations = self.list_hooks() if self._db is not None else self._registrations.values()
            targets = [
                reg for reg in registrations
                if reg.is_active and ("*" in reg.events or event in reg.events)
            ]

        if not targets:
            return []

        deliveries = []
        for reg in targets:
            delivery = await self._deliver(reg, event, payload)
            deliveries.append(delivery)

        return deliveries

    async def _deliver(
        self,
        reg: WebhookRegistration,
        event: str,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """执行单次 Webhook 投递（含重试）。"""
        delivery = WebhookDelivery(
            id=f"wd_{uuid.uuid4().hex[:8]}",
            webhook_id=reg.id,
            event=event,
            url=reg.url,
            payload=payload,
        )

        if self._db is not None:
            from .db import to_json
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO platform_webhook_deliveries (id, webhook_id, event, url, payload_json) VALUES (%s, %s, %s, %s, %s::jsonb)", (delivery.id, delivery.webhook_id, delivery.event, delivery.url, to_json(delivery.payload)))
                conn.commit()

        body = json.dumps({
            "event": event,
            "timestamp": time.time(),
            "data": payload,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": reg.id,
            "X-Webhook-Event": event,
        }

        if reg.secret:
            signature = self._sign(body, reg.secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        for attempt in range(1, reg.retry_count + 1):
            delivery.attempt = attempt
            started = time.perf_counter()

            try:
                async with httpx.AsyncClient(timeout=reg.timeout_seconds) as client:
                    response = await client.post(reg.url, content=body, headers=headers)
                    delivery.http_status = response.status_code
                    delivery.response_body = str(response.text)[:500]
                    delivery.duration_ms = round((time.perf_counter() - started) * 1000, 3)

                    if 200 <= response.status_code < 300:
                        delivery.status = "success"
                        break
                    else:
                        delivery.status = "failed"
                        delivery.error = f"HTTP {response.status_code}"
            except Exception as exc:
                delivery.duration_ms = round((time.perf_counter() - started) * 1000, 3)
                delivery.status = "failed"
                delivery.error = str(exc)

            if attempt < reg.retry_count:
                backoff = min(self.RETRY_BACKOFF_BASE ** attempt, self.RETRY_BACKOFF_MAX)
                logger.debug("webhook_retry id=%s attempt=%d backoff=%.1fs", reg.id, attempt, backoff)
                import asyncio
                await asyncio.sleep(backoff)

        # 记录历史
        if reg.id in self._delivery_history:
            self._delivery_history[reg.id].append(delivery)
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE platform_webhook_deliveries SET status = %s, http_status = %s, response_body = %s, error = %s, attempt = %s, duration_ms = %s WHERE id = %s", (delivery.status, delivery.http_status, delivery.response_body, delivery.error, delivery.attempt, delivery.duration_ms, delivery.id))
                conn.commit()

        if delivery.status == "success":
            logger.debug("webhook_delivered id=%s attempt=%d ms=%.1f", reg.id, delivery.attempt, delivery.duration_ms)
        else:
            logger.warning("webhook_failed id=%s error=%s", reg.id, delivery.error)

        return delivery

    def history(self, webhook_id: str, *, limit: int = 50) -> list[WebhookDelivery]:
        """获取 Webhook 投递历史。"""
        if self._db is not None:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM platform_webhook_deliveries WHERE webhook_id = %s ORDER BY created_at DESC LIMIT %s", (webhook_id, limit))
                    rows = cur.fetchall()
            return [self._row_to_delivery(row) for row in rows]
        deliveries = self._delivery_history.get(webhook_id, [])
        return deliveries[-limit:]

    @staticmethod
    def _row_to_registration(row: dict[str, Any]) -> WebhookRegistration:
        created = row.get("created_at")
        return WebhookRegistration(
            id=str(row["id"]), url=str(row.get("url") or ""), events=list(row.get("events_json") or ["*"]),
            secret=str(row.get("secret") or ""), is_active=bool(row.get("is_active", True)), description=str(row.get("description") or ""),
            created_at=created.timestamp() if hasattr(created, "timestamp") else float(created or time.time()), retry_count=int(row.get("retry_count") or 3),
            timeout_seconds=float(row.get("timeout_seconds") or 30), owner_user_id=str(row.get("owner_user_id") or ""),
        )

    @staticmethod
    def _row_to_delivery(row: dict[str, Any]) -> WebhookDelivery:
        created = row.get("created_at")
        return WebhookDelivery(
            id=str(row["id"]), webhook_id=str(row["webhook_id"]), event=str(row.get("event") or ""), url=str(row.get("url") or ""),
            payload=dict(row.get("payload_json") or {}), status=str(row.get("status") or "pending"), http_status=int(row.get("http_status") or 0),
            response_body=str(row.get("response_body") or ""), error=str(row.get("error") or ""), attempt=int(row.get("attempt") or 1),
            duration_ms=float(row.get("duration_ms") or 0), created_at=created.timestamp() if hasattr(created, "timestamp") else float(created or time.time()),
        )

    @staticmethod
    def _sign(payload: bytes, secret: str) -> str:
        """HMAC-SHA256 签名。"""
        return hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
        """验证 Webhook 签名。"""
        expected = WebhookManager._sign(payload, secret)
        return hmac.compare_digest(f"sha256={expected}", signature)
