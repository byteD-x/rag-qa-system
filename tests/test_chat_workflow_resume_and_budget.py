from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared import auth as auth_module


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)


def _load_gateway_module(module_name: str):
    _prioritize_sys_path(GATEWAY_SRC)

    for name in (
        module_name,
        "app.main",
        "app.gateway_agent",
        "app.gateway_answering",
        "app.gateway_chat_routes",
        "app.gateway_chat_service",
        "app.gateway_runtime",
        "app.gateway_workflows",
        "app.gateway_scope",
        "app.gateway_sessions",
        "app.ai_client",
        "app.db",
        "app",
    ):
        sys.modules.pop(name, None)

    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_prepare_chat_message_restores_resume_checkpoint_without_retrieval(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    def load_session_fn(session_id: str, current_user, default_scope_fn=None):
        assert session_id == "session-1"
        assert current_user.user_id == "u-1"
        return {"id": session_id, "scope_json": {"mode": "single"}}

    async def fail_resolve_scope_snapshot(*args, **kwargs):
        raise AssertionError("resume path should not resolve scope again")

    def fail_recent_history_messages(*args, **kwargs):
        raise AssertionError("resume path should not fetch history again")

    async def fail_retrieve_scope_evidence(*args, **kwargs):
        raise AssertionError("resume path should not run retrieval again")

    resume_workflow_run = {
        "id": "run-1",
        "workflow_state": {
            "stage": "failed",
            "resume_checkpoint": {
                "scope_snapshot": {
                    "mode": "single",
                    "corpus_ids": ["kb:base-1"],
                    "document_ids": [],
                    "documents_by_corpus": {},
                    "allow_common_knowledge": False,
                    "execution_mode": "agent",
                },
                "execution_mode": "agent",
                "history": [{"role": "user", "content": "previous turn"}],
                "evidence": [{"unit_id": "chunk-1", "quote": "Need finance approval"}],
                "contextualized_question": "expense approval flow",
                "retrieval_meta": {"aggregate": {"selected_candidates": 1}},
                "answer_mode": "grounded",
                "evidence_status": "grounded",
                "grounding_score": 0.92,
                "refusal_reason": "",
                "safety": {"risk_level": "low", "reason_codes": []},
            },
        },
    }

    prepared = asyncio.run(
        gateway_chat_service.prepare_chat_message(
            session_id="session-1",
            payload=SimpleNamespace(question="What is the expense approval flow?", execution_mode="agent", scope=None),
            request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat/workflow-runs/run-1/retry")),
            request_scope="chat.workflow_run.retry",
            user=user,
            load_session_fn=load_session_fn,
            default_scope_fn=lambda: {"mode": "all"},
            resolve_scope_snapshot_fn=fail_resolve_scope_snapshot,
            recent_history_messages_fn=fail_recent_history_messages,
            retrieve_scope_evidence_fn=fail_retrieve_scope_evidence,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            session_cost_summary_fn=lambda sid, current_user: {"assistant_turns": 1, "estimated_cost_total": 0.01},
            resume_workflow_run=resume_workflow_run,
        )
    )

    assert prepared["resume"]["resumed"] is True
    assert prepared["resume"]["source_run_id"] == "run-1"
    assert prepared["resume"]["source_stage"] == "failed"
    assert prepared["resume"]["reused_retrieval"] is True
    assert prepared["contextualized_question"] == "expense approval flow"
    assert prepared["evidence"] == [{"unit_id": "chunk-1", "quote": "Need finance approval"}]
    assert prepared["timing"]["retrieval_ms"] == 0.0
    assert prepared["timing"]["resume_ms"] >= 0.0


def test_prepare_chat_message_restores_generation_checkpoint_for_persistence_resume(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    def load_session_fn(session_id: str, current_user, default_scope_fn=None):
        assert session_id == "session-1"
        assert current_user.user_id == "u-1"
        return {"id": session_id, "scope_json": {"mode": "single"}}

    async def fail_resolve_scope_snapshot(*args, **kwargs):
        raise AssertionError("resume path should not resolve scope again")

    def fail_recent_history_messages(*args, **kwargs):
        raise AssertionError("resume path should not fetch history again")

    async def fail_retrieve_scope_evidence(*args, **kwargs):
        raise AssertionError("resume path should not run retrieval again")

    resume_workflow_run = {
        "id": "run-2",
        "workflow_state": {
            "stage": "failed",
            "resume_checkpoint": {
                "scope_snapshot": {
                    "mode": "single",
                    "corpus_ids": ["kb:base-1"],
                    "document_ids": [],
                    "documents_by_corpus": {},
                    "allow_common_knowledge": False,
                    "execution_mode": "agent",
                },
                "execution_mode": "agent",
                "history": [{"role": "user", "content": "previous turn"}],
                "evidence": [{"unit_id": "chunk-1", "quote": "Need finance approval"}],
                "contextualized_question": "expense approval flow",
                "retrieval_meta": {"aggregate": {"selected_candidates": 1}},
                "answer_mode": "grounded",
                "evidence_status": "grounded",
                "grounding_score": 0.92,
                "refusal_reason": "",
                "safety": {"risk_level": "low", "reason_codes": []},
                "resume_target": "persist_message",
                "generation_checkpoint": {
                    "answer_payload": {
                        "answer": "Use [1]",
                        "provider": "mock",
                        "model": "mock-model",
                        "usage": {"prompt_tokens": 10},
                        "llm_trace": {"prompt_key": "chat_grounded_answer"},
                    },
                    "generation_ms": 18.5,
                },
            },
        },
    }

    prepared = asyncio.run(
        gateway_chat_service.prepare_chat_message(
            session_id="session-1",
            payload=SimpleNamespace(question="What is the expense approval flow?", execution_mode="agent", scope=None),
            request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat/workflow-runs/run-2/retry")),
            request_scope="chat.workflow_run.retry",
            user=user,
            load_session_fn=load_session_fn,
            default_scope_fn=lambda: {"mode": "all"},
            resolve_scope_snapshot_fn=fail_resolve_scope_snapshot,
            recent_history_messages_fn=fail_recent_history_messages,
            retrieve_scope_evidence_fn=fail_retrieve_scope_evidence,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            session_cost_summary_fn=lambda sid, current_user: {"assistant_turns": 1, "estimated_cost_total": 0.01},
            resume_workflow_run=resume_workflow_run,
        )
    )

    assert prepared["resume"]["resumed"] is True
    assert prepared["resume"]["resume_target"] == "persist_message"
    assert prepared["resume"]["reused_retrieval"] is True
    assert prepared["resume"]["reused_generation"] is True
    assert prepared["generation_checkpoint"]["answer_payload"]["answer"] == "Use [1]"
    assert prepared["generation_checkpoint"]["generation_ms"] == 18.5


def test_prepare_chat_message_rejects_when_session_cost_budget_exceeded(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_CHAT_SESSION_COST_BUDGET", "0.05")
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        gateway_chat_service,
        "write_gateway_audit_event",
        lambda **kwargs: audit_events.append(dict(kwargs)),
    )

    with pytest.raises(gateway_chat_service.HTTPException) as exc_info:
        asyncio.run(
            gateway_chat_service.prepare_chat_message(
                session_id="session-1",
                payload=SimpleNamespace(question="What is the expense approval flow?", execution_mode="grounded", scope=None),
                request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat/sessions/session-1/messages")),
                request_scope="chat.message.send",
                user=user,
                load_session_fn=lambda session_id, current_user, default_scope_fn=None: {"id": session_id, "scope_json": {"mode": "single"}},
                default_scope_fn=lambda: {"mode": "all"},
                resolve_scope_snapshot_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("budget rejection should stop before scope resolution")),
                recent_history_messages_fn=lambda *args, **kwargs: [],
                retrieve_scope_evidence_fn=lambda *args, **kwargs: None,
                fetch_corpus_documents_fn=lambda *args, **kwargs: [],
                session_cost_summary_fn=lambda sid, current_user: {"assistant_turns": 2, "estimated_cost_total": 0.05},
            )
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "chat_session_cost_budget_exceeded"
    assert exc_info.value.detail["budget_amount"] == 0.05
    assert audit_events[-1]["outcome"] == "budget_exceeded"
    assert audit_events[-1]["details"]["current_estimated_cost"] == 0.05


def test_retry_chat_workflow_run_passes_resume_run_when_scope_is_reused(monkeypatch) -> None:
    gateway_chat_routes = _load_gateway_module("app.gateway_chat_routes")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    captured: dict[str, object] = {}

    async def fake_handle_chat_message(**kwargs):
        captured.update(kwargs)
        return {
            "message": {"id": "message-2"},
            "workflow_run": {"id": "run-2"},
            "resume": {"resumed": True, "source_stage": "failed"},
            "answer": "Use [1]",
        }

    source_run = {
        "id": "run-1",
        "session_id": "session-1",
        "status": "failed",
        "question": "What is the expense approval flow?",
        "execution_mode": "agent",
        "scope_snapshot": {
            "mode": "single",
            "corpus_ids": ["kb:base-1"],
            "document_ids": [],
            "allow_common_knowledge": False,
        },
        "workflow_state": {
            "stage": "failed",
            "resume_checkpoint": {
                "scope_snapshot": {
                    "mode": "single",
                    "corpus_ids": ["kb:base-1"],
                    "document_ids": [],
                    "documents_by_corpus": {},
                    "allow_common_knowledge": False,
                    "execution_mode": "agent",
                },
                "execution_mode": "agent",
                "history": [],
                "evidence": [{"unit_id": "chunk-1"}],
                "contextualized_question": "expense approval flow",
                "retrieval_meta": {"aggregate": {"selected_candidates": 1}},
                "answer_mode": "grounded",
                "evidence_status": "grounded",
                "grounding_score": 0.91,
                "refusal_reason": "",
                "safety": {"risk_level": "low", "reason_codes": []},
            },
        },
    }

    monkeypatch.setattr(gateway_chat_routes, "require_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway_chat_routes, "load_workflow_run_for_user", lambda run_id, current_user: source_run)
    monkeypatch.setattr(
        gateway_chat_routes,
        "load_session_for_user",
        lambda session_id, current_user, default_scope_fn=None: {"id": session_id, "scope_json": {"execution_mode": "agent"}},
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "begin_gateway_idempotency",
        lambda request, current_user, request_scope, payload: SimpleNamespace(
            key="retry-key",
            request_scope=request_scope,
            request_hash="hash",
            replay_payload=None,
            enabled=True,
        ),
    )
    monkeypatch.setattr(gateway_chat_routes, "handle_chat_message", fake_handle_chat_message)
    monkeypatch.setattr(gateway_chat_routes, "complete_gateway_idempotency", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway_chat_routes, "fail_gateway_idempotency", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway_chat_routes, "write_gateway_audit_event", lambda **kwargs: None)
    monkeypatch.setattr(
        gateway_chat_routes.CHAT_INFLIGHT_LIMITER,
        "acquire",
        lambda **kwargs: SimpleNamespace(allowed=True, ticket="ticket-1", scope=""),
    )
    monkeypatch.setattr(gateway_chat_routes.CHAT_INFLIGHT_LIMITER, "release", lambda ticket: None)

    result = asyncio.run(
        gateway_chat_routes.retry_chat_workflow_run(
            "run-1",
            gateway_chat_routes.RetryWorkflowRunRequest(reuse_scope=True),
            SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/v1/chat/workflow-runs/run-1/retry")),
            user,
        )
    )

    assert result["retried_from_run_id"] == "run-1"
    assert captured["request_scope"] == "chat.workflow_run.retry"
    assert captured["resume_workflow_run"]["id"] == "run-1"
