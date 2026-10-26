from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator
from uuid import uuid4


TRACE_ID_HEADER = "X-Trace-Id"
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def _otel_tracer() -> Any:
    """Return an optional OpenTelemetry tracer without a hard dependency."""
    if str(os.getenv("RAG_OTEL_ENABLED", "false")).strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        from opentelemetry import trace

        return trace.get_tracer("rag-qa")
    except Exception:
        return None


@contextmanager
def trace_span(name: str, *, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Emit a local timing record and an optional OpenTelemetry span."""
    started = time.perf_counter()
    record: dict[str, Any] = {
        "name": str(name),
        "trace_id": current_trace_id(),
        "attributes": dict(attributes or {}),
    }
    tracer = _otel_tracer()
    if tracer is None:
        try:
            yield record
        finally:
            record["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return
    with tracer.start_as_current_span(str(name)) as span:
        for key, value in record["attributes"].items():
            try:
                span.set_attribute(str(key), value if isinstance(value, (str, int, float, bool)) else str(value))
            except Exception:
                continue
        try:
            yield record
        finally:
            record["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
            try:
                span.set_attribute("rag.duration_ms", record["duration_ms"])
                span.set_attribute("rag.trace_id", record["trace_id"])
            except Exception:
                pass


def trace_event(name: str, *, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a serializable event for trace-to-dataset evaluation."""
    return {"name": str(name), "trace_id": current_trace_id(), "attributes": dict(attributes or {})}


def _clean_trace_id(value: str) -> str:
    return "".join(char for char in (value or "").strip() if char.isalnum() or char in {"-", "_", "."})[:96]


def ensure_trace_id(candidate: str | None = None, *, prefix: str = "") -> str:
    cleaned = _clean_trace_id(candidate or "")
    if cleaned:
        return cleaned
    base = uuid4().hex
    return f"{prefix}{base}" if prefix else base


def set_trace_id(trace_id: str) -> Token[str]:
    return _trace_id_var.set(ensure_trace_id(trace_id))


def reset_trace_id(token: Token[str]) -> None:
    _trace_id_var.reset(token)


def current_trace_id() -> str:
    return _trace_id_var.get("")


def trace_headers(trace_id: str | None = None) -> dict[str, str]:
    value = ensure_trace_id(trace_id or current_trace_id())
    return {TRACE_ID_HEADER: value} if value else {}
