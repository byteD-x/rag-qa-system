from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from shared.metrics import Counter, Histogram


_EVENT_NAMES = ("prompt_rollback", "tool_workflow")
_DEFAULT_FAILURE_REASON = "unknown"
_KNOWN_FAILURE_REASONS = {
    _DEFAULT_FAILURE_REASON,
    "bad_request",
    "bad_workflow",
    "confirmation_required",
    "prompt_revision_not_found",
    "tool_not_allowed",
    "tool_not_found",
    "tool_workflow_failed",
}

GOVERNANCE_EVENTS_TOTAL = Counter(
    "rag_gateway_governance_events_total",
    "Gateway governance event outcomes.",
    labelnames=("event", "result"),
)
GOVERNANCE_EVENT_DURATION_MS = Histogram(
    "rag_gateway_governance_event_duration_ms",
    "Gateway governance event duration in milliseconds.",
    labelnames=("event", "result"),
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)
GOVERNANCE_FAILURE_REASONS_TOTAL = Counter(
    "rag_gateway_governance_failure_reasons_total",
    "Gateway governance failure reasons.",
    labelnames=("event", "reason"),
)


@dataclass
class _EventStats:
    total: int = 0
    success: int = 0
    failure: int = 0
    total_duration_ms: float = 0.0
    last_duration_ms: float = 0.0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def record(self, *, success: bool, duration_ms: float, failure_reason: str = "") -> None:
        safe_duration = max(float(duration_ms or 0.0), 0.0)
        self.total += 1
        self.total_duration_ms += safe_duration
        self.last_duration_ms = safe_duration
        if success:
            self.success += 1
            return
        self.failure += 1
        reason = _normalize_failure_reason(failure_reason)
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1

    def as_dict(self) -> dict[str, object]:
        avg_duration_ms = self.total_duration_ms / self.total if self.total else 0.0
        success_rate = self.success / self.total if self.total else 0.0
        return {
            "total": self.total,
            "success": self.success,
            "failure": self.failure,
            "success_rate": round(success_rate, 4),
            "total_duration_ms": round(self.total_duration_ms, 3),
            "avg_duration_ms": round(avg_duration_ms, 3),
            "last_duration_ms": round(self.last_duration_ms, 3),
            "failure_reasons": dict(sorted(self.failure_reasons.items())),
        }


class RuntimeGovernanceMetrics:
    """In-memory governance metrics without payload, prompt, or tool output data."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events = {name: _EventStats() for name in _EVENT_NAMES}

    def record_prompt_rollback(self, *, success: bool, duration_ms: float, failure_reason: str = "") -> None:
        self._record("prompt_rollback", success=success, duration_ms=duration_ms, failure_reason=failure_reason)

    def record_tool_workflow(self, *, success: bool, duration_ms: float, failure_reason: str = "") -> None:
        self._record("tool_workflow", success=success, duration_ms=duration_ms, failure_reason=failure_reason)

    def get_status(self) -> dict[str, object]:
        with self._lock:
            return {
                "events": {name: stats.as_dict() for name, stats in self._events.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._events = {name: _EventStats() for name in _EVENT_NAMES}

    def _record(self, event: str, *, success: bool, duration_ms: float, failure_reason: str = "") -> None:
        if event not in self._events:
            return
        result = "success" if success else "failure"
        safe_duration = max(float(duration_ms or 0.0), 0.0)
        reason = _normalize_failure_reason(failure_reason)
        with self._lock:
            self._events[event].record(success=success, duration_ms=safe_duration, failure_reason=reason)
        GOVERNANCE_EVENTS_TOTAL.labels(event=event, result=result).inc()
        GOVERNANCE_EVENT_DURATION_MS.labels(event=event, result=result).observe(safe_duration)
        if not success:
            GOVERNANCE_FAILURE_REASONS_TOTAL.labels(event=event, reason=reason).inc()


def _normalize_failure_reason(value: str) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in raw)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    if cleaned in _KNOWN_FAILURE_REASONS:
        return cleaned
    for reason in _KNOWN_FAILURE_REASONS:
        if reason != _DEFAULT_FAILURE_REASON and cleaned.startswith(f"{reason}_"):
            return reason
    return _DEFAULT_FAILURE_REASON


_GOVERNANCE_METRICS = RuntimeGovernanceMetrics()


def get_governance_metrics() -> RuntimeGovernanceMetrics:
    return _GOVERNANCE_METRICS
