from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4


TRACE_ID_HEADER = "X-Trace-Id"
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


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
