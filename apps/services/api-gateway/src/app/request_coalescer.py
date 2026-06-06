"""请求合并器 —— 短时间窗口内合并相同/相似请求，减少重复 LLM 调用。

适用场景：
- 短时间内多个用户问相似/相同问题
- 批量处理场景（如批量文档摘要）
- 高并发时对同一知识库的重复检索

架构:
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ 请求 A    │  │ 请求 B    │  │ 请求 C    │  (100ms 窗口内)
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │              │              │
         └──────────────┼──────────────┘
                        ▼
              ┌─────────────────┐
              │ RequestCoalescer │
              │  • 哈希匹配     │
              │  • 窗口聚合     │
              │  • 结果广播     │
              └────────┬────────┘
                       ▼
              单次 LLM 调用 → 分发给 A, B, C

集成方式::

    coalescer = RequestCoalescer(window_ms=100)
    async with coalescer.coalesce("问题+知识库") as result:
        if result.is_leader:
            # 真正执行 LLM 调用
            answer = await llm_call(question)
            result.set_response(answer)
        else:
            # follower 等待 leader 的结果
            answer = result.response
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class CoalescedRequest:
    """合并请求上下文"""

    key: str
    created_at: float
    is_leader: bool
    _response: Any = None
    _response_set: bool = False
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _error: Exception | None = None
    _leader: "CoalescedRequest | None" = field(default=None, repr=False, compare=False)

    def set_response(self, response: Any) -> None:
        """leader 设置响应，通知所有 follower。"""
        self._response = response
        self._response_set = True
        self._event.set()

    def set_error(self, error: Exception) -> None:
        """leader 设置错误。"""
        self._error = error
        self._response_set = True
        self._event.set()

    @property
    def response(self) -> Any:
        """等待并获取响应（follower 调用）。"""
        source = self._leader or self
        return source._response

    @property
    def error(self) -> Exception | None:
        source = self._leader or self
        return source._error


# ---------------------------------------------------------------------------
# 请求合并器
# ---------------------------------------------------------------------------


class RequestCoalescer:
    """请求合并器 —— 在指定时间窗口内合并相同请求。

    使用 async context manager 模式：
        async with coalescer.coalesce(key) as result:
            if result.is_leader:
                result.set_response(await do_work())
            else:
                await result._event.wait()
    """

    def __init__(
        self,
        *,
        window_ms: float = 100.0,
        max_pending: int = 100,
        enable_metrics: bool = True,
    ) -> None:
        self._window = window_ms / 1000.0
        self._max_pending = max_pending
        self._enable_metrics = enable_metrics

        # key → CoalescedRequest
        self._pending: dict[str, CoalescedRequest] = {}
        self._lock = asyncio.Lock()

        # 统计
        self._total_requests = 0
        self._coalesced_requests = 0
        self._total_wait_ms = 0.0

    def coalesce(self, key: str) -> "_CoalesceContextManager":
        """返回一个 async context manager。

        用法::

            async with coalescer.coalesce(my_key) as cr:
                if cr.is_leader:
                    result = await expensive_call()
                    cr.set_response(result)
                else:
                    result = cr.response

        参数:
            key: 合并键（相同键的请求会在窗口内合并）
        """
        return _CoalesceContextManager(self, key)

    async def _acquire(self, key: str) -> CoalescedRequest:
        """获取或创建一个合并请求。"""
        async with self._lock:
            self._total_requests += 1

            existing = self._pending.get(key)
            if existing is not None:
                self._coalesced_requests += 1
                logger.debug("request_coalesced key=%s", key[:40])
                return CoalescedRequest(
                    key=key,
                    created_at=time.time(),
                    is_leader=False,
                    _event=existing._event,  # 共享 event
                    _leader=existing,
                )

            # 成为 leader
            if len(self._pending) >= self._max_pending:
                # 驱逐最旧的
                oldest_key = min(self._pending.keys(), key=lambda k: self._pending[k].created_at)
                self._pending.pop(oldest_key, None)

            cr = CoalescedRequest(key=key, created_at=time.time(), is_leader=True)
            self._pending[key] = cr
            return cr

    async def _release(self, key: str, cr: CoalescedRequest) -> None:
        """释放合并请求。"""
        async with self._lock:
            if cr.is_leader:
                wait_ms = (time.time() - cr.created_at) * 1000.0
                self._total_wait_ms += wait_ms
                if self._pending.get(key) is cr:
                    self._pending.pop(key, None)

    def stats(self) -> dict[str, Any]:
        """返回合并器统计。"""
        return {
            "total_requests": self._total_requests,
            "coalesced_requests": self._coalesced_requests,
            "coalesce_rate": round(
                self._coalesced_requests / max(self._total_requests, 1), 4
            ),
            "pending_count": len(self._pending),
            "avg_wait_ms": round(
                self._total_wait_ms / max(self._total_requests, 1), 2
            ),
            "window_ms": self._window * 1000,
        }


class _CoalesceContextManager:
    """请求合并的 async context manager。"""

    def __init__(self, coalescer: RequestCoalescer, key: str) -> None:
        self._coalescer = coalescer
        self._key = key
        self._cr: CoalescedRequest | None = None

    async def __aenter__(self) -> CoalescedRequest:
        self._cr = await self._coalescer._acquire(self._key)
        if not self._cr.is_leader:
            # follower：等待 leader 完成
            await asyncio.wait_for(
                self._cr._event.wait(),
                timeout=self._coalescer._window * 2 + 5.0,  # 额外容错
            )
        return self._cr

    async def __aexit__(self, *args: Any) -> None:
        if self._cr is not None:
            await self._coalescer._release(self._key, self._cr)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def coalesce_key(
    question: str,
    corpus_ids: list[str] | None = None,
    model_name: str = "",
    prefix: str = "qa",
) -> str:
    """生成请求合并键。

    合并策略: 完全相同的「问题+知识库+模型」才会合并。
    """
    raw = json.dumps(
        {
            "q": question.strip().lower(),
            "c": ",".join(sorted(corpus_ids or [])),
            "m": model_name,
        },
        sort_keys=True,
    )
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

request_coalescer = RequestCoalescer(window_ms=100.0)
