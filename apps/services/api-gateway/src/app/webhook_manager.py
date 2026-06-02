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

    def __init__(self) -> None:
        self._registrations: dict[str, WebhookRegistration] = {}
        self._delivery_history: dict[str, list[WebhookDelivery]] = {}  # webhook_id → deliveries

    def register(
        self,
        url: str,
        *,
        events: list[str] | None = None,
        secret: str = "",
        description: str = "",
        retry_count: int = 3,
        timeout_seconds: float = 30.0,
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
        )
        self._registrations[webhook_id] = reg
        self._delivery_history[webhook_id] = []
        logger.info("webhook_registered id=%s url=%s events=%s", webhook_id, url, events)
        return reg

    def unregister(self, webhook_id: str) -> bool:
        """注销 Webhook。"""
        if webhook_id not in self._registrations:
            return False
        self._registrations[webhook_id].is_active = False
        logger.info("webhook_unregistered id=%s", webhook_id)
        return True

    def list_hooks(self) -> list[WebhookRegistration]:
        """列出所有注册的 Webhook。"""
        return list(self._registrations.values())

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
            if reg and reg.is_active:
                targets = [reg]
        else:
            targets = [
                reg for reg in self._registrations.values()
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

        if delivery.status == "success":
            logger.debug("webhook_delivered id=%s attempt=%d ms=%.1f", reg.id, delivery.attempt, delivery.duration_ms)
        else:
            logger.warning("webhook_failed id=%s error=%s", reg.id, delivery.error)

        return delivery

    def history(self, webhook_id: str, *, limit: int = 50) -> list[WebhookDelivery]:
        """获取 Webhook 投递历史。"""
        deliveries = self._delivery_history.get(webhook_id, [])
        return deliveries[-limit:]

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
