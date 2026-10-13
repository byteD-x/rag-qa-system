from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from threading import Event
from typing import Any, Callable


def _read_float(name: str, default: float) -> float:
    try:
        return max(float(os.getenv(name, str(default)) or default), 0.0)
    except (TypeError, ValueError):
        return default


def _read_int(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default)) or default), 0)
    except (TypeError, ValueError):
        return default


def build_retrieval_cache_key(
    *,
    base_id: str,
    question: str,
    document_ids: list[str] | None,
    limit: int,
    user_department: str = "",
    is_admin: bool = False,
    metadata_filter: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic, permission-aware key without storing raw questions."""
    payload = {
        "v": 1,
        "base_id": str(base_id).strip(),
        "question": " ".join(str(question).split()).casefold(),
        "document_ids": sorted({str(item).strip() for item in (document_ids or []) if str(item).strip()}),
        "limit": max(int(limit), 1),
        "user_department": str(user_department or "").strip().casefold(),
        "is_admin": bool(is_admin),
        "metadata_filter": _normalize_metadata_filter(metadata_filter),
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_metadata_filter(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "job_position_id": str(raw.get("job_position_id") or "").strip(),
        "content_kind": str(raw.get("content_kind") or "").strip().lower(),
        "question_type": str(raw.get("question_type") or "").strip().lower(),
        "difficulties": sorted({str(item).strip().lower() for item in (raw.get("difficulties") or []) if str(item).strip()}),
        "tags": sorted({str(item).strip().lower() for item in (raw.get("tags") or []) if str(item).strip()}),
    }


class RetrievalCacheStats:
    def __init__(self, *, hits: int, misses: int, coalesced: int, evictions: int, timeouts: int, size: int) -> None:
        self.hits = hits
        self.misses = misses
        self.coalesced = coalesced
        self.evictions = evictions
        self.timeouts = timeouts
        self.size = size


class RetrievalResultCache:
    """Small process-local TTL/LRU cache with single-flight request coalescing.

    The cache is deliberately bounded and short-lived. The key includes the ACL
    context, and callers can disable it by setting TTL to zero. A waiting request
    reuses the first in-flight computation instead of opening another DB/Qdrant
    fanout, which protects tail latency during traffic bursts.
    """

    def __init__(self, *, ttl_seconds: float, max_entries: int, wait_seconds: float = 2.0) -> None:
        self.ttl_seconds = max(float(ttl_seconds), 0.0)
        self.max_entries = max(int(max_entries), 0)
        self.wait_seconds = max(float(wait_seconds), 0.0)
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[str, Event] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._coalesced = 0
        self._evictions = 0
        self._timeouts = 0

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0 and self.max_entries > 0

    def get_or_compute(self, key: str, compute: Callable[[], Any]) -> tuple[Any, bool]:
        """Return ``(value, cache_hit)`` and coalesce identical in-flight work."""
        if not self.enabled:
            return compute(), False

        waited = False
        while True:
            with self._lock:
                now = time.monotonic()
                cached = self._entries.get(key)
                if cached is not None:
                    created_at, value = cached
                    if now - created_at <= self.ttl_seconds:
                        self._entries.move_to_end(key)
                        self._hits += 1
                        if waited:
                            self._coalesced += 1
                        return copy.deepcopy(value), True
                    self._entries.pop(key, None)

                event = self._inflight.get(key)
                if event is None:
                    event = Event()
                    self._inflight[key] = event
                    owner = True
                else:
                    owner = False

            if owner:
                break
            waited = True
            if event.wait(self.wait_seconds):
                continue
            with self._lock:
                self._timeouts += 1
            # The owner is still responsible for publishing its result. Compute
            # independently after a bounded wait so a stuck dependency cannot
            # block the request forever.
            break

        try:
            value = compute()
        except Exception:
            with self._lock:
                if self._inflight.get(key) is event:
                    self._inflight.pop(key, None)
                    event.set()
            raise

        with self._lock:
            self._misses += 1
            if self.enabled:
                self._entries[key] = (time.monotonic(), copy.deepcopy(value))
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
                    self._evictions += 1
            if self._inflight.get(key) is event:
                self._inflight.pop(key, None)
                event.set()
            if waited:
                self._coalesced += 1
        return value, False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> RetrievalCacheStats:
        with self._lock:
            return RetrievalCacheStats(
                hits=self._hits,
                misses=self._misses,
                coalesced=self._coalesced,
                evictions=self._evictions,
                timeouts=self._timeouts,
                size=len(self._entries),
            )


retrieval_result_cache = RetrievalResultCache(
    ttl_seconds=_read_float("KB_RETRIEVAL_CACHE_TTL_SECONDS", 5.0),
    max_entries=_read_int("KB_RETRIEVAL_CACHE_MAX_ENTRIES", 2048),
    wait_seconds=_read_float("KB_RETRIEVAL_CACHE_WAIT_SECONDS", 2.0),
)


__all__ = [
    "RetrievalCacheStats",
    "RetrievalResultCache",
    "build_retrieval_cache_key",
    "retrieval_result_cache",
]
