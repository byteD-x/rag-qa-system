from __future__ import annotations

import builtins
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = REPO_ROOT / "packages/python/shared/metrics.py"


def test_counter_reuses_registered_metric_with_total_suffix() -> None:
    pytest.importorskip("prometheus_client")
    from shared import metrics

    metric_name = f"rag_test_shared_metrics_{uuid.uuid4().hex}_total"
    first = metrics.Counter(metric_name, "Shared metrics wrapper test.", labelnames=("result",))
    second = metrics.Counter(metric_name, "Shared metrics wrapper test.", labelnames=("result",))

    assert second is first
    first.labels(result="ok").inc()
    text = metrics.generate_latest().decode("utf-8")
    assert f'{metric_name}{{result="ok"}} 1.0' in text


def test_histogram_and_gauge_reuse_registered_metrics() -> None:
    pytest.importorskip("prometheus_client")
    from shared import metrics

    histogram_name = f"rag_test_shared_histogram_{uuid.uuid4().hex}"
    first_histogram = metrics.Histogram(histogram_name, "Shared histogram wrapper test.")
    second_histogram = metrics.Histogram(histogram_name, "Shared histogram wrapper test.")

    gauge_name = f"rag_test_shared_gauge_{uuid.uuid4().hex}"
    first_gauge = metrics.Gauge(gauge_name, "Shared gauge wrapper test.", labelnames=("state",))
    second_gauge = metrics.Gauge(gauge_name, "Shared gauge wrapper test.", labelnames=("state",))

    assert second_histogram is first_histogram
    assert second_gauge is first_gauge
    first_histogram.observe(3.0)
    first_gauge.labels(state="ready").set(2.0)
    text = metrics.generate_latest().decode("utf-8")
    assert f"{histogram_name}_count 1.0" in text
    assert f'{gauge_name}{{state="ready"}} 2.0' in text


def test_metrics_fallback_noops_without_prometheus_client(monkeypatch) -> None:
    module_name = f"_shared_metrics_no_prometheus_{uuid.uuid4().hex}"
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "prometheus_client" or name.startswith("prometheus_client."):
            raise ImportError("blocked prometheus_client for fallback test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    spec = importlib.util.spec_from_file_location(module_name, METRICS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)

        counter = module.Counter("fallback_counter_total", "Fallback counter.", labelnames=("result",))
        assert counter.labels(result="ok") is counter
        assert counter.inc() is None

        histogram = module.Histogram("fallback_duration_ms", "Fallback histogram.")
        assert histogram.observe(1.0) is None

        gauge = module.Gauge("fallback_gauge", "Fallback gauge.")
        assert gauge.set(1.0) is None

        assert module.generate_latest() == b""
        assert module.start_http_server(0) is None
        assert module.CONTENT_TYPE_LATEST.startswith("text/plain")
    finally:
        sys.modules.pop(module_name, None)
