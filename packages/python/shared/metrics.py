from __future__ import annotations

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter as PromCounter, Gauge as PromGauge, Histogram as PromHistogram, REGISTRY, generate_latest, start_http_server
except ImportError:  # pragma: no cover - fallback for local environments without prometheus-client
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, amount: float = 1.0) -> None:
            return None

        def observe(self, value: float) -> None:
            return None

        def set(self, value: float) -> None:
            return None

    class Counter(_NoopMetric):
        def __init__(self, *args, **kwargs):
            return None

    class Histogram(_NoopMetric):
        def __init__(self, *args, **kwargs):
            return None

    class Gauge(_NoopMetric):
        def __init__(self, *args, **kwargs):
            return None

    def generate_latest() -> bytes:
        return b""

    def start_http_server(*args, **kwargs) -> None:
        return None
else:
    def _lookup_metric(name: str):
        candidates = [name]
        if name.endswith("_total"):
            candidates.append(name[:-6])
        for candidate in candidates:
            collector = getattr(REGISTRY, "_names_to_collectors", {}).get(candidate)
            if collector is not None:
                return collector
        return None

    def Counter(name: str, documentation: str, labelnames=(), **kwargs):
        existing = _lookup_metric(name)
        if existing is not None:
            return existing
        return PromCounter(name, documentation, labelnames=labelnames, **kwargs)

    def Histogram(name: str, documentation: str, labelnames=(), **kwargs):
        existing = _lookup_metric(name)
        if existing is not None:
            return existing
        return PromHistogram(name, documentation, labelnames=labelnames, **kwargs)

    def Gauge(name: str, documentation: str, labelnames=(), **kwargs):
        existing = _lookup_metric(name)
        if existing is not None:
            return existing
        return PromGauge(name, documentation, labelnames=labelnames, **kwargs)
