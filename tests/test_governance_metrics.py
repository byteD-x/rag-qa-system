from __future__ import annotations

import importlib
import sys
from pathlib import Path

from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _load_governance_metrics(monkeypatch):
    target = str(GATEWAY_SRC)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()
    module = importlib.import_module("app.governance_metrics")
    return importlib.reload(module)


def test_runtime_governance_metrics_aggregates_safe_in_memory_state(monkeypatch) -> None:
    governance_metrics = _load_governance_metrics(monkeypatch)
    metrics = governance_metrics.RuntimeGovernanceMetrics()

    metrics.record_tool_workflow(success=True, duration_ms=12.3456)
    metrics.record_tool_workflow(success=False, duration_ms=4.0, failure_reason="tool workflow failed: raw detail")
    metrics.record_prompt_rollback(success=False, duration_ms=-5, failure_reason="Prompt-Revision Not Found")

    status = metrics.get_status()

    workflow = status["events"]["tool_workflow"]
    assert workflow["total"] == 2
    assert workflow["success"] == 1
    assert workflow["failure"] == 1
    assert workflow["success_rate"] == 0.5
    assert workflow["total_duration_ms"] == 16.346
    assert workflow["avg_duration_ms"] == 8.173
    assert workflow["last_duration_ms"] == 4.0
    assert workflow["failure_reasons"] == {"tool_workflow_failed": 1}

    rollback = status["events"]["prompt_rollback"]
    assert rollback["total"] == 1
    assert rollback["failure"] == 1
    assert rollback["last_duration_ms"] == 0.0
    assert rollback["failure_reasons"] == {"prompt_revision_not_found": 1}

    metrics.record_tool_workflow(success=False, duration_ms=1.0, failure_reason="raw provider timeout detail")
    assert metrics.get_status()["events"]["tool_workflow"]["failure_reasons"]["unknown"] == 1

    metrics.reset()
    reset_status = metrics.get_status()
    assert reset_status["events"]["tool_workflow"]["total"] == 0
    assert reset_status["events"]["prompt_rollback"]["failure_reasons"] == {}


def test_governance_metrics_singleton_can_reset_after_use(monkeypatch) -> None:
    governance_metrics = _load_governance_metrics(monkeypatch)
    metrics = governance_metrics.get_governance_metrics()
    metrics.reset()

    metrics.record_prompt_rollback(success=True, duration_ms=3.5)

    assert metrics.get_status()["events"]["prompt_rollback"]["success"] == 1
    metrics.reset()
    assert metrics.get_status()["events"]["prompt_rollback"]["total"] == 0


def test_governance_metrics_export_uses_sanitized_failure_reason(monkeypatch) -> None:
    governance_metrics = _load_governance_metrics(monkeypatch)
    shared_metrics = importlib.import_module("shared.metrics")
    metrics = governance_metrics.RuntimeGovernanceMetrics()
    raw_reason = "provider timeout opaque-marker-raw-detail-123 raw prompt text"

    metrics.record_tool_workflow(success=False, duration_ms=1.0, failure_reason=raw_reason)

    text = shared_metrics.generate_latest().decode("utf-8")
    assert 'rag_gateway_governance_failure_reasons_total{event="tool_workflow",reason="unknown"}' in text
    assert "opaque-marker-raw-detail-123" not in text
    assert "raw_prompt_text" not in text
