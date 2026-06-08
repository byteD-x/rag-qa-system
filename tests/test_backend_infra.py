from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from pydantic import ValidationError

from shared import auth as auth_module
from shared import embeddings as embeddings_module
from shared.embeddings import EmbeddingSettings, clear_query_embedding_cache, embed_query_text
from shared.idempotency import build_request_hash, normalize_idempotency_key
from shared.qdrant_store import check_qdrant_runtime_config, qdrant_point_id
from shared.stack_init import _load_migration_files, _migration_checksum, _select_pending_migrations

from conftest import clear_app_modules

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"
KB_SRC = REPO_ROOT / "apps/services/knowledge-base/src"


def test_select_pending_migrations_returns_only_unapplied(tmp_path: Path) -> None:
    migration_a = tmp_path / "001_init.sql"
    migration_b = tmp_path / "002_extra.sql"
    migration_a.write_text("CREATE TABLE a(id INT);\n", encoding="utf-8")
    migration_b.write_text("CREATE TABLE b(id INT);\n", encoding="utf-8")

    files = _load_migration_files(tmp_path)
    applied = {files[0].version: files[0].checksum}

    pending = _select_pending_migrations(files, applied)
    assert [item.version for item in pending] == ["002_extra.sql"]


def test_select_pending_migrations_rejects_checksum_mismatch(tmp_path: Path) -> None:
    migration = tmp_path / "001_init.sql"
    migration.write_text("CREATE TABLE a(id INT);\n", encoding="utf-8")

    files = _load_migration_files(tmp_path)
    mismatched = {"001_init.sql": _migration_checksum("CREATE TABLE broken(id INT);\n")}

    try:
        _select_pending_migrations(files, mismatched)
    except RuntimeError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("expected checksum mismatch to raise RuntimeError")


def test_query_embedding_cache_reuses_previous_result(monkeypatch) -> None:
    clear_query_embedding_cache()
    calls = {"count": 0}

    def fake_embed_texts(texts: list[str], *, settings=None):
        calls["count"] += 1
        return [[0.25, 0.75]]

    monkeypatch.setattr(embeddings_module, "embed_texts", fake_embed_texts)
    settings = EmbeddingSettings(
        provider="local",
        api_url="",
        api_key="",
        model="local-projection-512",
        timeout_seconds=60.0,
        batch_size=64,
        local_backend="projection",
    )

    first = embed_query_text("expense approval flow", settings=settings)
    second = embed_query_text("expense approval flow", settings=settings)

    assert first == [0.25, 0.75]
    assert second == [0.25, 0.75]
    assert calls["count"] == 1


def test_gateway_to_json_preserves_empty_list() -> None:
    gateway_db = _load_gateway_module("app.db")

    assert gateway_db.to_json([]) == "[]"
    assert gateway_db.to_json(None) == "{}"


def test_message_feedback_request_normalizes_fields() -> None:
    gateway_schemas = _load_gateway_module("app.gateway_schemas")

    payload = gateway_schemas.MessageFeedbackRequest(verdict=" Down ", reason_code="Low Confidence", notes="  needs citations  ")

    assert payload.verdict == "down"
    assert payload.reason_code == "low_confidence"
    assert payload.notes == "needs citations"


def test_provider_billing_import_request_normalizes_records() -> None:
    gateway_schemas = _load_gateway_module("app.gateway_schemas")

    payload = gateway_schemas.ProviderBillingImportRequest(
        records=[
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "external_id": " bill-001 ",
                "tenant_id": " tenant-a ",
                "user_id": " user-1 ",
                "provider": " openai ",
                "model": " gpt-4.1-mini ",
                "route_key": " grounded ",
                "prompt_key": " chat_grounded_answer ",
                "currency": " usd ",
                "billed_cost_cents": 123,
                "input_tokens": 1000,
                "output_tokens": 200,
                "billed_at": " 2026-06-07T10:00:00Z ",
                "metadata": {"invoice": "inv-1"},
            }
        ]
    )

    record = payload.records[0]
    assert record.id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert record.external_id == "bill-001"
    assert record.tenant_id == "tenant-a"
    assert record.user_id == "user-1"
    assert record.provider == "openai"
    assert record.model == "gpt-4.1-mini"
    assert record.route_key == "grounded"
    assert record.prompt_key == "chat_grounded_answer"
    assert record.currency == "USD"
    assert record.billed_at == "2026-06-07T10:00:00Z"
    assert record.metadata == {"invoice": "inv-1"}


def test_import_provider_billing_route_requires_platform_admin(monkeypatch) -> None:
    gateway_admin_routes = _load_gateway_module("app.gateway_admin_routes")
    audit_events: list[dict[str, object]] = []
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/admin/costs/provider-billing-records"))
    payload = gateway_admin_routes.ProviderBillingImportRequest(
        records=[
            {
                "provider": "openai",
                "billed_cost_cents": 12,
            }
        ]
    )

    monkeypatch.setattr(gateway_admin_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(dict(kwargs)))
    monkeypatch.setattr(
        gateway_admin_routes,
        "import_provider_billing_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("non-admin should not import billing records")),
    )

    try:
        asyncio.run(gateway_admin_routes.import_provider_billing(payload, request, user))
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["code"] == "permission_denied"
    else:
        raise AssertionError("expected non-admin billing import to be rejected")

    assert audit_events[-1]["action"] == "admin.cost.provider_billing.import"
    assert audit_events[-1]["outcome"] == "denied"
    assert audit_events[-1]["details"]["required_role"] == "platform_admin"


def test_import_provider_billing_route_imports_records_and_audits(monkeypatch) -> None:
    gateway_admin_routes = _load_gateway_module("app.gateway_admin_routes")
    audit_events: list[dict[str, object]] = []
    captured: dict[str, object] = {}
    user = auth_module.AuthUser(
        user_id="admin-1",
        email="admin@local",
        role="platform_admin",
        permissions=auth_module.permissions_for_role("platform_admin"),
    )
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/admin/costs/provider-billing-records"))
    payload = gateway_admin_routes.ProviderBillingImportRequest(
        records=[
            {
                "external_id": " bill-001 ",
                "provider": " openai ",
                "model": " gpt-4.1-mini ",
                "route_key": " grounded ",
                "currency": " usd ",
                "billed_cost_cents": 456,
                "input_tokens": 1200,
                "output_tokens": 300,
            }
        ]
    )

    def fake_import(records, *, imported_by_user_id: str):
        captured["records"] = records
        captured["imported_by_user_id"] = imported_by_user_id
        return {"imported": len(records), "record_ids": ["record-1"]}

    monkeypatch.setattr(gateway_admin_routes, "import_provider_billing_records", fake_import)
    monkeypatch.setattr(gateway_admin_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(dict(kwargs)))

    result = asyncio.run(gateway_admin_routes.import_provider_billing(payload, request, user))

    assert result == {"imported": 1, "record_ids": ["record-1"]}
    assert captured["imported_by_user_id"] == "admin-1"
    record = captured["records"][0]
    assert record["external_id"] == "bill-001"
    assert record["provider"] == "openai"
    assert record["currency"] == "USD"
    assert record["billed_cost_cents"] == 456
    assert audit_events[-1]["action"] == "admin.cost.provider_billing.import"
    assert audit_events[-1]["outcome"] == "success"
    assert audit_events[-1]["details"]["imported"] == 1


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()


def _load_gateway_main(monkeypatch):
    _prioritize_sys_path(GATEWAY_SRC)

    for name in (
        "app.main",
        "app.ai_client",
        "app.db",
        "app.gateway_admin_routes",
        "app.gateway_chat_routes",
        "app.gateway_chat_service",
        "app.gateway_mcp_adapter",
        "app.gateway_mcp_routes",
        "app.gateway_platform_routes",
        "app.gateway_schemas",
        "app.gateway_workflows",
        "app",
    ):
        sys.modules.pop(name, None)

    module = importlib.import_module("app.main")
    return importlib.reload(module)


def _load_gateway_module(module_name: str):
    _prioritize_sys_path(GATEWAY_SRC)

    for name in (
        module_name,
        "app.main",
        "app.gateway_agent",
        "app.gateway_answering",
        "app.gateway_admin_routes",
        "app.gateway_chat_routes",
        "app.gateway_chat_service",
        "app.gateway_workflows",
        "app.gateway_scope",
        "app.ai_client",
        "app.db",
        "app",
    ):
        sys.modules.pop(name, None)

    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_gateway_runtime_settings_answer_verifier_env_defaults_and_invalid_action(monkeypatch) -> None:
    monkeypatch.delenv("GATEWAY_FINAL_ANSWER_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("GATEWAY_RESPONSE_CACHE_SEMANTIC_ENABLED", raising=False)
    monkeypatch.delenv("GATEWAY_RESPONSE_CACHE_SEMANTIC_THRESHOLD", raising=False)
    monkeypatch.delenv("GATEWAY_ANSWER_VERIFIER_ENABLED", raising=False)
    monkeypatch.delenv("GATEWAY_ANSWER_VERIFIER_ACTION", raising=False)
    gateway_config = _load_gateway_module("app.gateway_config")

    defaults = gateway_config.load_gateway_runtime_settings()
    assert defaults.final_answer_tools_enabled is False
    assert defaults.response_cache_semantic_enabled is False
    assert defaults.response_cache_semantic_threshold == 0.92
    assert defaults.answer_verifier_enabled is False
    assert defaults.answer_verifier_action == "fallback"

    monkeypatch.setenv("GATEWAY_FINAL_ANSWER_TOOLS_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_RESPONSE_CACHE_SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_RESPONSE_CACHE_SEMANTIC_THRESHOLD", "1.5")
    monkeypatch.setenv("GATEWAY_ANSWER_VERIFIER_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_ANSWER_VERIFIER_ACTION", "invalid")

    settings = gateway_config.load_gateway_runtime_settings()
    assert settings.final_answer_tools_enabled is True
    assert settings.response_cache_semantic_enabled is True
    assert settings.response_cache_semantic_threshold == 1.0
    assert settings.answer_verifier_enabled is True
    assert settings.answer_verifier_action == "fallback"


def _load_kb_module(module_name: str):
    _prioritize_sys_path(KB_SRC)

    for name in (
        module_name,
        "app.main",
        "app.kb_auto_index",
        "app.kb_auto_index_routes",
        "app.kb_batch_dry_run",
        "app.kb_batch_dry_run_routes",
        "app.kb_batch_ingest",
        "app.kb_batch_ingest_routes",
        "app.kb_index",
        "app.kb_index_routes",
        "app.kb_job_queue",
        "app.kb_job_queue_routes",
        "app.kb_query_routes",
        "app.kb_query_helpers",
        "app.kb_rebuild",
        "app.kb_rebuild_routes",
        "app.parsing",
        "app.retrieve",
        "app.runtime",
        "app.db",
        "app.query",
        "app.worker",
        "app.vector_store",
        "app",
    ):
        sys.modules.pop(name, None)

    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _auth_headers(user: auth_module.AuthUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_module.create_access_token(user)}"}


def test_resolve_scope_snapshot_persists_documents_by_corpus(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    async def fake_fetch_corpora(current_user, *, include_counts: bool):
        assert current_user == user
        assert include_counts is False
        return [
            {"corpus_id": "kb:base-1"},
            {"corpus_id": "kb:base-2"},
        ]

    async def fake_fetch_corpus_documents(client, *, user, corpus_id):
        assert user.user_id == "u-1"
        if corpus_id == "kb:base-1":
            return [{"document_id": "doc-a", "corpus_id": corpus_id}]
        return [{"document_id": "doc-b", "corpus_id": corpus_id}]

    monkeypatch.setattr(gateway_main, "_fetch_corpora", fake_fetch_corpora)
    monkeypatch.setattr(gateway_main, "_fetch_corpus_documents", fake_fetch_corpus_documents)

    payload = gateway_main.ChatScopePayload(
        mode="multi",
        corpus_ids=["kb:base-1", "kb:base-2"],
        document_ids=["doc-b", "doc-a"],
        allow_common_knowledge=True,
    )
    snapshot = asyncio.run(gateway_main._resolve_scope_snapshot(user, payload))

    assert snapshot["document_ids"] == ["doc-b", "doc-a"]
    assert snapshot["documents_by_corpus"] == {
        "kb:base-1": ["doc-a"],
        "kb:base-2": ["doc-b"],
    }
    assert snapshot["allow_common_knowledge"] is True


def test_retrieve_scope_evidence_uses_cached_document_scope(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    fetch_calls = {"count": 0}

    async def fail_if_fetch_documents(*args, **kwargs):
        fetch_calls["count"] += 1
        raise AssertionError("document lookup should be skipped when documents_by_corpus is cached")

    async def fake_request_service_json(client, method, url, *, headers, json_body=None):
        return {
            "items": [
                {
                    "corpus_id": f"kb:{json_body['base_id']}",
                    "document_id": json_body["document_ids"][0] if json_body["document_ids"] else "",
                    "evidence_path": {"final_score": 0.91},
                }
            ],
            "retrieval": {"retrieval_ms": 8.5, "original_query": "expense approval flow"},
            "trace_id": "kb-trace-1",
        }

    monkeypatch.setattr(gateway_main, "_fetch_corpus_documents", fail_if_fetch_documents)
    monkeypatch.setattr(gateway_main, "_request_service_json", fake_request_service_json)

    scope_snapshot = {
        "mode": "multi",
        "corpus_ids": ["kb:base-1", "kb:base-2"],
        "document_ids": ["doc-a", "doc-b"],
        "documents_by_corpus": {
            "kb:base-1": ["doc-a"],
            "kb:base-2": ["doc-b"],
        },
        "allow_common_knowledge": False,
    }

    evidence, contextualized_question, retrieval_meta = asyncio.run(
        gateway_main._retrieve_scope_evidence(
            user=user,
            scope_snapshot=scope_snapshot,
            question="What is the expense approval flow?",
            history=[],
        )
    )

    assert fetch_calls["count"] == 0
    assert contextualized_question == "What is the expense approval flow?"
    assert len(evidence) == 2
    assert retrieval_meta["aggregate"]["document_scope_cache_hit"] is True


def test_retrieve_scope_evidence_tolerates_partial_service_failure(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    async def fake_request_service_json(client, method, url, *, headers, json_body=None):
        if json_body["base_id"] == "base-2":
            raise gateway_main.HTTPException(
                status_code=502,
                detail={"detail": "kb retrieve unavailable", "code": "upstream_unavailable"},
            )
        return {
            "items": [
                {
                    "corpus_id": "kb:base-1",
                    "document_id": "doc-a",
                    "evidence_path": {"final_score": 0.88},
                }
            ],
            "retrieval": {"retrieval_ms": 6.0, "original_query": "expense approval flow"},
            "trace_id": "kb-trace-ok",
        }

    monkeypatch.setattr(gateway_main, "_request_service_json", fake_request_service_json)

    scope_snapshot = {
        "mode": "multi",
        "corpus_ids": ["kb:base-1", "kb:base-2"],
        "document_ids": ["doc-a", "doc-b"],
        "documents_by_corpus": {
            "kb:base-1": ["doc-a"],
            "kb:base-2": ["doc-b"],
        },
        "allow_common_knowledge": False,
    }

    evidence, _, retrieval_meta = asyncio.run(
        gateway_main._retrieve_scope_evidence(
            user=user,
            scope_snapshot=scope_snapshot,
            question="What is the expense approval flow?",
            history=[],
        )
    )

    assert len(evidence) == 1
    assert retrieval_meta["aggregate"]["partial_failure"] is True
    assert retrieval_meta["aggregate"]["failed_service_count"] == 1
    assert retrieval_meta["services"][1]["status"] == "failed"


def test_classify_evidence_returns_common_knowledge_without_evidence_when_allowed() -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")

    answer_mode, evidence_status, grounding_score, refusal_reason = gateway_answering.classify_evidence(
        [],
        allow_common_knowledge=True,
    )

    assert answer_mode == "common_knowledge"
    assert evidence_status == "ungrounded"
    assert grounding_score == 0.0
    assert refusal_reason == ""


def test_classify_evidence_prefers_common_knowledge_over_weak_grounding_when_allowed() -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")

    answer_mode, evidence_status, grounding_score, refusal_reason = gateway_answering.classify_evidence(
        [{"evidence_path": {"final_score": 0.015}}],
        allow_common_knowledge=True,
    )

    assert answer_mode == "common_knowledge"
    assert evidence_status == "ungrounded"
    assert grounding_score == 0.0
    assert refusal_reason == ""


def test_classify_evidence_refuses_without_evidence_in_strict_mode() -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")

    answer_mode, evidence_status, grounding_score, refusal_reason = gateway_answering.classify_evidence(
        [],
        allow_common_knowledge=False,
    )

    assert answer_mode == "refusal"
    assert evidence_status == "insufficient"
    assert grounding_score == 0.0
    assert refusal_reason == "insufficient_evidence"


def test_generate_grounded_answer_uses_general_llm_path_for_common_knowledge(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    captured: dict[str, object] = {}

    class _Settings:
        configured = True
        system_prompt = "custom system prompt"
        default_max_tokens = 900
        common_knowledge_model = "mock-common-model"
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24

    async def fake_create_llm_completion(*, settings, prompt, inputs, prompt_key=None, prompt_version=None, model, temperature, max_tokens):
        captured["settings"] = settings
        captured["prompt"] = prompt
        captured["inputs"] = inputs
        captured["prompt_key"] = prompt_key
        captured["prompt_version"] = prompt_version
        captured["model"] = model
        captured["temperature"] = temperature
        captured["max_tokens"] = max_tokens
        return {
            "answer": "The sun releases energy through nuclear fusion.",
            "provider": "mock-provider",
            "model": "mock-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "llm_trace": {"llm_call_id": "llm-1", "prompt_key": "chat_common_knowledge", "prompt_version": "2026-03-10"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="Why does the sun shine?",
            history=[
                {"role": "user", "content": "outdated history should be removed"},
                {"role": "assistant", "content": "This assistant reply is intentionally longer than the history truncation limit."},
            ],
            evidence=[],
            answer_mode="common_knowledge",
        )
    )

    prompt = captured["prompt"]
    inputs = captured["inputs"]
    messages = prompt.format_messages(**inputs)
    rendered = [str(getattr(item, "content", "")) for item in messages]
    assert any("Why does the sun shine?" in item for item in rendered)
    assert not any("outdated history" in item for item in rendered)
    assert any("This assistant reply is" in item for item in rendered)
    assert not any("history truncation limit" in item for item in rendered)
    assert captured["model"] == "mock-common-model"
    assert captured["prompt_key"] == "chat_common_knowledge"
    assert captured["prompt_version"] == "2026-03-10"
    assert captured["temperature"] == 0.4
    assert captured["max_tokens"] == 256
    assert result["provider"] == "mock-provider"
    assert result["model"] == "mock-model"
    assert gateway_answering.COMMON_KNOWLEDGE_DISCLAIMER in result["answer"]
    assert "nuclear fusion" in result["answer"]
    assert result["llm_trace"]["prompt_key"] == "chat_common_knowledge"


def test_generate_grounded_answer_short_ambiguous_common_knowledge_skips_llm(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")

    class _Settings:
        configured = True
        system_prompt = ""
        model = "mock-model"
        common_knowledge_model = ""
        default_max_tokens = 900
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24

    async def fail_create_llm_completion(**kwargs):
        raise AssertionError("LLM should be skipped for low-signal common knowledge prompts")

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fail_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="1",
            history=[],
            evidence=[],
            answer_mode="common_knowledge",
        )
    )

    assert result["provider"] == ""
    assert result["model"] == ""
    assert result["usage"] == {}
    assert result["llm_trace"] == {}
    assert "信息不足" in result["answer"]


def test_generate_grounded_answer_retries_with_fallback_route(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=False))
    attempts: list[tuple[str, str]] = []

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://primary.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = "custom system prompt"
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {
            "grounded": {
                "model": "primary-grounded-model",
                "fallback_route_key": "grounded_backup",
                "temperature": 0.2,
                "max_tokens": 800,
            },
            "grounded_backup": {
                "model": "backup-grounded-model",
                "base_url": "https://backup.example.test/v1",
                "temperature": 0.2,
                "max_tokens": 800,
            },
        }

    async def fake_create_llm_completion(*, settings, prompt, inputs, prompt_key=None, prompt_version=None, model, temperature, max_tokens):
        attempts.append((settings.base_url, model))
        if model == "primary-grounded-model":
            raise gateway_answering.HTTPException(status_code=502, detail="primary unavailable")
        return {
            "answer": "Expense approvals require owner sign-off. [1]",
            "provider": "mock-provider",
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "llm_trace": {"llm_call_id": "llm-2", "prompt_key": "chat_grounded_answer", "prompt_version": "2026-03-10"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="What approvals are needed for expense reimbursement?",
            history=[],
            evidence=[
                {
                    "document_title": "Expense policy",
                    "section_title": "Approval",
                    "quote": "Department owner approval is required before reimbursement.",
                    "raw_text": "Department owner approval is required before reimbursement.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    assert attempts == [
        ("https://primary.example.test/v1", "primary-grounded-model"),
        ("https://backup.example.test/v1", "backup-grounded-model"),
    ]
    assert result["model"] == "backup-grounded-model"
    assert result["llm_trace"]["route_key"] == "grounded_backup"
    assert result["llm_trace"]["route_attempts"] == ["grounded", "grounded_backup"]
    assert result["llm_trace"]["fallback_used"] is True


def test_generate_grounded_answer_final_tools_default_off_keeps_plain_llm_call(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=False))
    calls: list[dict[str, object]] = []

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://llm.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = ""
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {}

    async def fake_create_llm_completion(**kwargs):
        calls.append(dict(kwargs))
        return {
            "answer": "Expense approvals require owner sign-off. [1]",
            "provider": "mock-provider",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "llm_trace": {"llm_call_id": "llm-plain", "prompt_key": "chat_grounded_answer"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="What approvals are needed for expense reimbursement?",
            history=[],
            evidence=[
                {
                    "document_title": "Expense policy",
                    "section_title": "Approval",
                    "quote": "Department owner approval is required before reimbursement.",
                    "raw_text": "Department owner approval is required before reimbursement.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    assert len(calls) == 1
    assert "tools" not in calls[0]
    assert "extra_messages" not in calls[0]
    assert "final_answer_tools" not in result["llm_trace"]
    assert "owner sign-off" in result["answer"]


def test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=True))
    calls: list[dict[str, object]] = []

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://llm.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = ""
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {}

    async def fake_create_llm_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("tools") is not None:
            tool_calls = [
                {
                    "id": "call-stats",
                    "name": "tool_registry_stats",
                    "args": {},
                }
            ]
            return {
                "answer": "",
                "provider": "mock-provider",
                "model": kwargs["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
                "tool_calls": tool_calls,
                "_raw_message": gateway_answering.AIMessage(content="", tool_calls=tool_calls),
                "llm_trace": {"llm_call_id": "llm-before-tools", "prompt_key": "chat_grounded_answer"},
            }
        extra_messages = list(kwargs.get("extra_messages") or [])
        assert any(isinstance(item, gateway_answering.ToolMessage) for item in extra_messages)
        return {
            "answer": "The registry exposes read-only tool statistics for diagnostics. [1]",
            "provider": "mock-provider",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 20, "completion_tokens": 12},
            "llm_trace": {"llm_call_id": "llm-after-tools", "prompt_key": "chat_grounded_answer"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="Summarize available diagnostics.",
            history=[],
            evidence=[
                {
                    "document_title": "Diagnostics",
                    "section_title": "Tools",
                    "quote": "Tool statistics can be used for diagnostics.",
                    "raw_text": "Tool statistics can be used for diagnostics.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    exposed_names = {tool["function"]["name"] for tool in calls[0]["tools"]}
    assert exposed_names == {"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"}
    assert len(calls) == 2
    trace = result["llm_trace"]["final_answer_tools"]
    assert trace["rounds"] == 1
    assert trace["requested"] == 1
    assert trace["executed"] == 1
    assert len(trace["events"]) == 1
    assert trace["events"][0]["tool"] == "tool_registry_stats"
    assert trace["events"][0]["status"] == "success"
    assert trace["events"][0]["from_cache"] is False
    assert trace["events"][0]["result_keys"] == [
        "cache_entries",
        "categories",
        "enabled_tools",
        "mcp_servers",
        "registered_tools",
        "tools",
    ]
    assert "prompt_preview" not in str(trace)
    assert "_raw_message" not in result


def test_generate_grounded_answer_normalizes_non_object_final_tools_args_without_trace_leak(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=True))
    calls: list[dict[str, object]] = []
    leaked_arg = "C:/private/prompt_preview/source.txt"

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://llm.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = ""
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {}

    async def fake_create_llm_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("tools") is not None:
            tool_calls = [
                {
                    "id": "call-stats",
                    "name": "tool_registry_stats",
                    "args": ["prompt_preview", leaked_arg],
                }
            ]
            return {
                "answer": "",
                "provider": "mock-provider",
                "model": kwargs["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
                "tool_calls": tool_calls,
                "_raw_message": gateway_answering.AIMessage(
                    content="",
                    tool_calls=[{"id": "call-stats", "name": "tool_registry_stats", "args": {}}],
                ),
                "llm_trace": {"llm_call_id": "llm-before-tools", "prompt_key": "chat_grounded_answer"},
            }
        extra_messages = list(kwargs.get("extra_messages") or [])
        tool_payloads = [
            json.loads(str(item.content))
            for item in extra_messages
            if isinstance(item, gateway_answering.ToolMessage)
        ]
        assert tool_payloads[0]["success"] is True
        return {
            "answer": "The final tool call used safe default arguments. [1]",
            "provider": "mock-provider",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 20, "completion_tokens": 12},
            "llm_trace": {"llm_call_id": "llm-after-tools", "prompt_key": "chat_grounded_answer"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="Summarize available diagnostics.",
            history=[],
            evidence=[
                {
                    "document_title": "Diagnostics",
                    "section_title": "Tools",
                    "quote": "Tool statistics can be used for diagnostics.",
                    "raw_text": "Tool statistics can be used for diagnostics.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    assert len(calls) == 2
    trace = result["llm_trace"]["final_answer_tools"]
    assert trace["requested"] == 1
    assert trace["executed"] == 1
    assert trace["events"][0]["tool"] == "tool_registry_stats"
    assert trace["events"][0]["status"] == "success"
    trace_text = json.dumps(trace, ensure_ascii=False)
    assert "prompt_preview" not in trace_text
    assert leaked_arg not in trace_text


def test_generate_grounded_answer_rejects_non_whitelisted_final_tool_call(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=True))
    calls: list[dict[str, object]] = []
    leaked_tool_name = "prompt_preview C:/private/source.txt"

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://llm.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = ""
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {}

    async def fake_create_llm_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("tools") is not None:
            tool_calls = [
                {
                    "id": "call-forbidden",
                    "name": leaked_tool_name,
                    "args": {"document_id": "secret-doc"},
                }
            ]
            return {
                "answer": "",
                "provider": "mock-provider",
                "model": kwargs["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
                "tool_calls": tool_calls,
                "_raw_message": gateway_answering.AIMessage(content="", tool_calls=tool_calls),
                "llm_trace": {"llm_call_id": "llm-before-tools", "prompt_key": "chat_grounded_answer"},
            }
        extra_messages = list(kwargs.get("extra_messages") or [])
        tool_messages = [
            item
            for item in extra_messages
            if isinstance(item, gateway_answering.ToolMessage)
        ]
        assert tool_messages[0].name == "not_allowed"
        return {
            "answer": "The requested operation is outside the final-answer tool boundary. [1]",
            "provider": "mock-provider",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 20, "completion_tokens": 12},
            "llm_trace": {"llm_call_id": "llm-after-tools", "prompt_key": "chat_grounded_answer"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="Delete a document before answering.",
            history=[],
            evidence=[
                {
                    "document_title": "Safety",
                    "section_title": "Boundaries",
                    "quote": "Final answer tools are read-only.",
                    "raw_text": "Final answer tools are read-only.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    assert len(calls) == 2
    trace = result["llm_trace"]["final_answer_tools"]
    assert trace["requested"] == 1
    assert trace["executed"] == 0
    assert trace["rejected"] == 1
    assert trace["events"] == [{"tool": "not_allowed", "status": "rejected", "reason": "tool_not_allowed"}]
    trace_text = str(trace)
    assert "prompt_preview" not in trace_text
    assert "C:/private/source.txt" not in trace_text
    assert "secret-doc" not in trace_text


def test_generate_grounded_answer_blocks_second_round_final_tool_calls(monkeypatch) -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")
    monkeypatch.setattr(gateway_answering, "runtime_settings", SimpleNamespace(final_answer_tools_enabled=True))
    calls: list[dict[str, object]] = []

    class _Settings:
        configured = True
        provider = "openai-compatible"
        base_url = "https://llm.example.test/v1"
        api_key = ""
        model = "default-model"
        system_prompt = ""
        default_temperature = 0.7
        default_max_tokens = 900
        common_knowledge_model = ""
        common_knowledge_max_tokens = 256
        common_knowledge_history_messages = 1
        common_knowledge_history_chars = 24
        timeout_seconds = 30.0
        extra_body = {}
        model_routing = {}

    async def fake_create_llm_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("tools") is not None:
            tool_calls = [{"id": "call-stats", "name": "tool_registry_stats", "args": {}}]
            return {
                "answer": "",
                "provider": "mock-provider",
                "model": kwargs["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
                "tool_calls": tool_calls,
                "_raw_message": gateway_answering.AIMessage(content="", tool_calls=tool_calls),
                "llm_trace": {"llm_call_id": "llm-before-tools", "prompt_key": "chat_grounded_answer"},
            }
        return {
            "answer": "",
            "provider": "mock-provider",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 20, "completion_tokens": 0},
            "tool_calls": [{"id": "call-again", "name": "tool_registry_stats", "args": {}}],
            "llm_trace": {"llm_call_id": "llm-after-tools", "prompt_key": "chat_grounded_answer"},
        }

    monkeypatch.setattr(gateway_answering, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_answering, "create_llm_completion", fake_create_llm_completion)

    result = asyncio.run(
        gateway_answering.generate_grounded_answer(
            question="Summarize diagnostics.",
            history=[],
            evidence=[
                {
                    "document_title": "Diagnostics",
                    "section_title": "Tools",
                    "quote": "Tool statistics can be used for diagnostics.",
                    "raw_text": "Tool statistics can be used for diagnostics.",
                    "evidence_path": {"final_score": 0.82},
                }
            ],
            answer_mode="grounded",
        )
    )

    assert len(calls) == 2
    trace = result["llm_trace"]["final_answer_tools"]
    assert trace["executed"] == 1
    assert trace["final_tool_calls_blocked"] == 1
    assert "根据检索到的证据" in result["answer"]
    assert "Tool statistics can be used for diagnostics" in result["answer"]


def test_create_llm_completion_stream_yields_live_deltas(monkeypatch) -> None:
    ai_client = _load_gateway_module("app.ai_client")
    captured: dict[str, object] = {}

    class _FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            yield 'data: {"model":"stream-model","choices":[{"delta":{"content":"Hello"},"finish_reason":""}]}'
            yield 'data: {"choices":[{"delta":{"content":" world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2}}'
            yield 'data: [DONE]'

        async def aread(self):
            return b""

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            return _FakeStreamResponse()

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", _FakeAsyncClient)

    settings = ai_client.LLMSettings(
        enabled=True,
        provider="mock-provider",
        base_url="https://example.invalid/v1",
        api_key="secret",
        model="default-model",
        common_knowledge_model="",
        timeout_seconds=30.0,
        default_temperature=0.7,
        default_max_tokens=512,
        common_knowledge_max_tokens=256,
        common_knowledge_history_messages=4,
        common_knowledge_history_chars=400,
        system_prompt="",
        extra_body={},
    )
    snapshots: list[str] = []

    result = asyncio.run(
        ai_client.create_llm_completion_stream(
            settings=settings,
            messages=[{"role": "user", "content": "Say hello"}],
            model="stream-model",
            temperature=0.3,
            max_tokens=128,
            on_text_delta=lambda _delta, answer_text: snapshots.append(answer_text),
        )
    )

    assert snapshots == ["Hello", "Hello world"]
    assert captured["method"] == "POST"
    assert isinstance(captured["json"], dict)
    assert captured["json"]["stream"] is True
    assert captured["json"]["model"] == "stream-model"
    assert result["answer"] == "Hello world"
    assert result["model"] == "stream-model"
    assert result["usage"] == {"prompt_tokens": 5, "completion_tokens": 2}


def test_default_scope_disables_common_knowledge_fallback() -> None:
    gateway_scope = _load_gateway_module("app.gateway_scope")

    scope = gateway_scope.default_scope()

    assert scope["allow_common_knowledge"] is False
    assert scope["execution_mode"] == "grounded"


def test_prepare_chat_message_uses_agent_execution_mode(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    captured: dict[str, object] = {}

    async def fake_run_agent_search(**kwargs):
        captured.update(kwargs)
        return (
            [{"unit_id": "chunk-1", "evidence_path": {"final_score": 0.87}}],
            "expense approval flow",
            {"aggregate": {"selected_candidates": 1, "execution_mode": "agent"}},
        )

    async def fail_retrieve_scope_evidence(**kwargs):
        raise AssertionError("grounded retriever should be skipped in agent mode")

    async def fake_resolve_scope_snapshot(current_user, scope_payload):
        assert current_user == user
        return {
            "mode": "single",
            "corpus_ids": ["kb:base-1"],
            "document_ids": [],
            "documents_by_corpus": {},
            "allow_common_knowledge": False,
        }

    monkeypatch.setattr(gateway_chat_service, "run_agent_search", fake_run_agent_search)

    prepared = asyncio.run(
        gateway_chat_service.prepare_chat_message(
            session_id="session-1",
            payload=SimpleNamespace(question="What is the expense approval flow?", scope=None, execution_mode=None),
            user=user,
            load_session_fn=lambda sid, actor: {"id": sid, "scope_json": {"execution_mode": "agent"}},
            default_scope_fn=lambda: {"mode": "all", "execution_mode": "grounded"},
            resolve_scope_snapshot_fn=fake_resolve_scope_snapshot,
            recent_history_messages_fn=lambda sid, actor, limit=8: [],
            retrieve_scope_evidence_fn=fail_retrieve_scope_evidence,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
        )
    )

    assert prepared["execution_mode"] == "agent"
    assert prepared["scope_snapshot"]["execution_mode"] == "agent"
    assert prepared["contextualized_question"] == "expense approval flow"
    assert prepared["retrieval_meta"]["aggregate"]["execution_mode"] == "agent"
    assert captured["scope_snapshot"]["execution_mode"] == "agent"


def test_run_agent_retrieval_uses_enhanced_runtime(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    calls: list[dict[str, object]] = []

    async def fake_run_enhanced_agent(**kwargs):
        calls.append(dict(kwargs))
        return (
            [{"unit_id": "chunk-enhanced", "evidence_path": {"final_score": 0.91}}],
            "enhanced expense flow",
            {"aggregate": {"selected_candidates": 1}, "agent": {"events": []}},
        )

    async def fail_run_agent_search(**kwargs):
        raise AssertionError("simple agent should not run when enhanced succeeds")

    monkeypatch.setattr(
        gateway_chat_service,
        "runtime_settings",
        SimpleNamespace(agent_runtime="enhanced", kb_service_url="http://kb-service:8200"),
    )
    monkeypatch.setattr(gateway_chat_service, "run_enhanced_agent", fake_run_enhanced_agent)
    monkeypatch.setattr(gateway_chat_service, "run_agent_search", fail_run_agent_search)

    evidence, contextualized_question, retrieval_meta = asyncio.run(
        gateway_chat_service._run_agent_retrieval(
            user=user,
            scope_snapshot={"corpus_ids": ["kb:base-1"], "execution_mode": "agent"},
            question="What is the expense flow?",
            history=[],
            focus_hint={},
            agent_profile={},
            prompt_template={},
            retrieve_scope_evidence_fn=lambda **kwargs: None,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
        )
    )

    assert calls
    assert evidence[0]["unit_id"] == "chunk-enhanced"
    assert contextualized_question == "enhanced expense flow"
    assert retrieval_meta["aggregate"]["execution_mode"] == "agent"
    assert retrieval_meta["aggregate"]["agent_runtime"] == "enhanced"
    assert retrieval_meta["aggregate"]["agent_runtime_fallback"] is False
    assert retrieval_meta["agent"]["enhanced"] is True
    assert retrieval_meta["agent"]["enhanced_requested"] is True


def test_run_agent_retrieval_falls_back_when_enhanced_runtime_fails(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    fallback_calls: list[dict[str, object]] = []

    async def fail_run_enhanced_agent(**kwargs):
        raise RuntimeError("planner unavailable")

    async def fake_run_agent_search(**kwargs):
        fallback_calls.append(dict(kwargs))
        return (
            [{"unit_id": "chunk-simple", "evidence_path": {"final_score": 0.82}}],
            "simple expense flow",
            {"aggregate": {"selected_candidates": 1, "execution_mode": "agent"}, "agent": {"events": []}},
        )

    monkeypatch.setattr(
        gateway_chat_service,
        "runtime_settings",
        SimpleNamespace(agent_runtime="enhanced", kb_service_url="http://kb-service:8200"),
    )
    monkeypatch.setattr(gateway_chat_service, "run_enhanced_agent", fail_run_enhanced_agent)
    monkeypatch.setattr(gateway_chat_service, "run_agent_search", fake_run_agent_search)

    evidence, contextualized_question, retrieval_meta = asyncio.run(
        gateway_chat_service._run_agent_retrieval(
            user=user,
            scope_snapshot={"corpus_ids": ["kb:base-1"], "execution_mode": "agent"},
            question="What is the expense flow?",
            history=[],
            focus_hint={},
            agent_profile={},
            prompt_template={},
            retrieve_scope_evidence_fn=lambda **kwargs: None,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
        )
    )

    assert fallback_calls
    assert evidence[0]["unit_id"] == "chunk-simple"
    assert contextualized_question == "simple expense flow"
    assert retrieval_meta["aggregate"]["agent_runtime"] == "simple"
    assert retrieval_meta["aggregate"]["requested_agent_runtime"] == "enhanced"
    assert retrieval_meta["aggregate"]["agent_runtime_fallback"] is True
    assert retrieval_meta["aggregate"]["agent_runtime_fallback_reason"] == "RuntimeError"
    assert retrieval_meta["agent"]["fallback"] is True
    assert retrieval_meta["agent"]["fallback_reason"] == "RuntimeError"


def test_handle_chat_message_persists_workflow_run(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    workflow_updates: list[dict[str, object]] = []

    async def fake_prepare_chat_message(**kwargs):
        return {
            "session_id": "session-1",
            "payload": SimpleNamespace(question="What is the expense approval flow?"),
            "trace_id": "gateway-trace-1",
            "scope_snapshot": {"mode": "single", "execution_mode": "agent"},
            "execution_mode": "agent",
            "history": [],
            "evidence": [{"unit_id": "chunk-1"}],
            "contextualized_question": "expense approval flow",
            "retrieval_meta": {
                "aggregate": {"selected_candidates": 1, "partial_failure": False},
                "agent": {"tool_calls": [{"tool": "search_scope", "result_count": 1}]},
            },
            "answer_mode": "grounded",
            "evidence_status": "grounded",
            "grounding_score": 0.91,
            "refusal_reason": "",
            "safety": {"risk_level": "low", "reason_codes": []},
            "timing": {"total_started": 0.0, "scope_ms": 1.0, "retrieval_ms": 2.0},
        }

    async def fake_generate_grounded_answer(**kwargs):
        return {"answer": "Use [1]", "provider": "mock", "model": "mock-model", "usage": {"prompt_tokens": 10}}

    def fake_build_chat_response_payload(**kwargs):
        return {
            "answer": "Use [1]",
            "answer_mode": "grounded",
            "strategy_used": "agent_grounded_qa",
            "citations": [{"unit_id": "chunk-1"}],
            "provider": "mock",
            "model": "mock-model",
            "usage": {"prompt_tokens": 10},
            "llm_trace": {"llm_call_id": "llm-1", "prompt_key": "chat_grounded_answer", "prompt_version": "2026-03-10"},
            "latency": {"total_ms": 12.0},
            "cost": {"estimated_cost": 0.01},
        }

    def fake_finalize_chat_message(**kwargs):
        response_payload = dict(kwargs["response_payload"])
        response_payload["message"] = {"id": "message-1", "content": "Use [1]"}
        return response_payload

    def fake_start_workflow_run_fn(**kwargs):
        return {"id": "run-1", "status": "running", "stage": "retrieval_completed"}

    def fake_update_workflow_run_fn(**kwargs):
        workflow_updates.append(dict(kwargs))
        state = dict(kwargs["workflow_state"])
        return {
            "id": kwargs["run_id"],
            "status": kwargs["status"],
            "stage": state.get("stage", ""),
            "message_id": kwargs.get("message_id", ""),
            "workflow_state": state,
            "workflow_events": list(kwargs.get("workflow_events") or []),
            "tool_calls": list(kwargs.get("tool_calls") or []),
        }

    monkeypatch.setattr(gateway_chat_service, "prepare_chat_message", fake_prepare_chat_message)
    monkeypatch.setattr(gateway_chat_service, "generate_grounded_answer", fake_generate_grounded_answer)
    monkeypatch.setattr(gateway_chat_service, "build_chat_response_payload", fake_build_chat_response_payload)
    monkeypatch.setattr(gateway_chat_service, "finalize_chat_message", fake_finalize_chat_message)

    result = asyncio.run(
        gateway_chat_service.handle_chat_message(
            session_id="session-1",
            payload=SimpleNamespace(question="What is the expense approval flow?"),
            request=SimpleNamespace(),
            user=user,
            load_session_fn=lambda *args, **kwargs: {},
            default_scope_fn=lambda: {"mode": "all"},
            resolve_scope_snapshot_fn=lambda *args, **kwargs: {},
            recent_history_messages_fn=lambda *args, **kwargs: [],
            retrieve_scope_evidence_fn=lambda *args, **kwargs: None,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            persist_chat_turn_fn=lambda *args, **kwargs: {},
            start_workflow_run_fn=fake_start_workflow_run_fn,
            update_workflow_run_fn=fake_update_workflow_run_fn,
        )
    )

    assert result["workflow_run"]["status"] == "completed"
    assert result["workflow_run"]["message_id"] == "message-1"
    assert workflow_updates[0]["status"] == "running"
    assert workflow_updates[0]["workflow_state"]["stage"] == "generation_completed"
    assert workflow_updates[0]["workflow_state"]["response"]["llm_trace"]["prompt_key"] == "chat_grounded_answer"
    assert workflow_updates[1]["status"] == "completed"
    assert workflow_updates[1]["message_id"] == "message-1"
    assert workflow_updates[1]["workflow_events"][-1]["stage"] == "persisted"
    assert workflow_updates[1]["tool_calls"] == [{"tool": "search_scope", "result_count": 1}]


def test_handle_chat_message_reuses_generation_checkpoint_for_persistence_resume(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    started_runs: list[dict[str, object]] = []
    workflow_updates: list[dict[str, object]] = []
    build_payload_calls: list[dict[str, object]] = []

    async def fake_prepare_chat_message(**kwargs):
        return {
            "session_id": "session-1",
            "payload": SimpleNamespace(question="What is the expense approval flow?"),
            "trace_id": "gateway-trace-2",
            "scope_snapshot": {"mode": "single", "execution_mode": "agent"},
            "execution_mode": "agent",
            "history": [],
            "evidence": [{"unit_id": "chunk-1"}],
            "contextualized_question": "expense approval flow",
            "retrieval_meta": {
                "aggregate": {"selected_candidates": 1, "partial_failure": False},
                "agent": {"tool_calls": [{"tool": "search_scope", "result_count": 1}]},
            },
            "answer_mode": "grounded",
            "evidence_status": "grounded",
            "grounding_score": 0.91,
            "refusal_reason": "",
            "safety": {"risk_level": "low", "reason_codes": []},
            "timing": {"total_started": 0.0, "scope_ms": 1.0, "retrieval_ms": 0.0, "resume_ms": 0.1},
            "resume": {
                "resumed": True,
                "source_run_id": "run-0",
                "source_stage": "failed",
                "resume_target": "persist_message",
                "reused_retrieval": True,
                "reused_generation": True,
            },
            "generation_checkpoint": {
                "answer_payload": {
                    "answer": "Use [1]",
                    "provider": "mock",
                    "model": "mock-model",
                    "usage": {"prompt_tokens": 10},
                    "llm_trace": {"llm_call_id": "llm-2", "prompt_key": "chat_grounded_answer", "prompt_version": "2026-03-10"},
                },
                "generation_ms": 18.5,
            },
        }

    async def fail_generate_grounded_answer(**kwargs):
        raise AssertionError("generation should be reused from checkpoint")

    def fake_build_chat_response_payload(**kwargs):
        build_payload_calls.append(dict(kwargs))
        return {
            "answer": kwargs["answer_payload"]["answer"],
            "answer_mode": "grounded",
            "strategy_used": "agent_grounded_qa",
            "citations": [{"unit_id": "chunk-1"}],
            "provider": kwargs["answer_payload"]["provider"],
            "model": kwargs["answer_payload"]["model"],
            "usage": dict(kwargs["answer_payload"]["usage"]),
            "llm_trace": dict(kwargs["answer_payload"]["llm_trace"]),
            "latency": {"total_ms": 12.0, "generation_ms": kwargs["generation_ms"]},
            "cost": {"estimated_cost": 0.01},
        }

    def fake_finalize_chat_message(**kwargs):
        response_payload = dict(kwargs["response_payload"])
        response_payload["message"] = {"id": "message-2", "content": response_payload["answer"]}
        return response_payload

    def fake_start_workflow_run_fn(**kwargs):
        started_runs.append(dict(kwargs))
        return {"id": "run-2", "status": "running", "stage": "persistence_resumed"}

    def fake_update_workflow_run_fn(**kwargs):
        workflow_updates.append(dict(kwargs))
        state = dict(kwargs["workflow_state"])
        return {
            "id": kwargs["run_id"],
            "status": kwargs["status"],
            "stage": state.get("stage", ""),
            "message_id": kwargs.get("message_id", ""),
            "workflow_state": state,
            "workflow_events": list(kwargs.get("workflow_events") or []),
            "tool_calls": list(kwargs.get("tool_calls") or []),
        }

    monkeypatch.setattr(gateway_chat_service, "prepare_chat_message", fake_prepare_chat_message)
    monkeypatch.setattr(gateway_chat_service, "generate_grounded_answer", fail_generate_grounded_answer)
    monkeypatch.setattr(gateway_chat_service, "build_chat_response_payload", fake_build_chat_response_payload)
    monkeypatch.setattr(gateway_chat_service, "finalize_chat_message", fake_finalize_chat_message)

    result = asyncio.run(
        gateway_chat_service.handle_chat_message(
            session_id="session-1",
            payload=SimpleNamespace(question="What is the expense approval flow?"),
            request=SimpleNamespace(),
            user=user,
            load_session_fn=lambda *args, **kwargs: {},
            default_scope_fn=lambda: {"mode": "all"},
            resolve_scope_snapshot_fn=lambda *args, **kwargs: {},
            recent_history_messages_fn=lambda *args, **kwargs: [],
            retrieve_scope_evidence_fn=lambda *args, **kwargs: None,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            persist_chat_turn_fn=lambda *args, **kwargs: {},
            start_workflow_run_fn=fake_start_workflow_run_fn,
            update_workflow_run_fn=fake_update_workflow_run_fn,
        )
    )

    assert result["workflow_run"]["status"] == "completed"
    assert result["workflow_run"]["message_id"] == "message-2"
    assert started_runs[0]["workflow_state"]["stage"] == "persistence_resumed"
    assert started_runs[0]["workflow_state"]["resume_target"] == "persist_message"
    assert started_runs[0]["workflow_state"]["resume_checkpoint"]["generation_checkpoint"]["generation_ms"] == 18.5
    assert build_payload_calls[0]["generation_ms"] == 18.5
    assert len(workflow_updates) == 1
    assert workflow_updates[0]["status"] == "completed"
    assert workflow_updates[0]["workflow_state"]["stage"] == "persisted"


def test_retry_chat_workflow_run_uses_idempotency_and_audit(monkeypatch) -> None:
    gateway_chat_routes = _load_gateway_module("app.gateway_chat_routes")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    captured: dict[str, object] = {}
    audit_events: list[dict[str, object]] = []
    released_tickets: list[object] = []

    async def fake_handle_chat_message(**kwargs):
        return {
            "message": {"id": "message-2"},
            "workflow_run": {"id": "run-2"},
            "answer": "Use [1]",
        }

    monkeypatch.setattr(gateway_chat_routes, "require_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        gateway_chat_routes,
        "load_workflow_run_for_user",
        lambda run_id, current_user: {
            "id": run_id,
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
        },
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "load_session_for_user",
        lambda session_id, current_user, default_scope_fn=None: {"id": session_id, "scope_json": {"execution_mode": "agent"}},
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "begin_gateway_idempotency",
        lambda request, current_user, request_scope, payload: (
            captured.update({"request_scope": request_scope, "payload": payload}) or SimpleNamespace(
                key="retry-key",
                request_scope=request_scope,
                request_hash="hash",
                replay_payload=None,
                enabled=True,
            )
        ),
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "handle_chat_message",
        fake_handle_chat_message,
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "complete_gateway_idempotency",
        lambda state, current_user, response_payload, resource_id="": captured.update(
            {"completed_resource_id": resource_id, "completed_payload": response_payload}
        ),
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "fail_gateway_idempotency",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("retry should not mark idempotency as failed")),
    )
    monkeypatch.setattr(
        gateway_chat_routes,
        "write_gateway_audit_event",
        lambda **kwargs: audit_events.append(dict(kwargs)),
    )
    monkeypatch.setattr(
        gateway_chat_routes.CHAT_INFLIGHT_LIMITER,
        "acquire",
        lambda **kwargs: SimpleNamespace(allowed=True, ticket="ticket-1", scope=""),
    )
    monkeypatch.setattr(
        gateway_chat_routes.CHAT_INFLIGHT_LIMITER,
        "release",
        lambda ticket: released_tickets.append(ticket),
    )

    result = asyncio.run(
        gateway_chat_routes.retry_chat_workflow_run(
            "run-1",
            gateway_chat_routes.RetryWorkflowRunRequest(reuse_scope=True),
            SimpleNamespace(headers={}),
            user,
        )
    )

    assert result["retried_from_run_id"] == "run-1"
    assert captured["request_scope"] == "chat.workflow_run.retry"
    assert captured["payload"] == {
        "run_id": "run-1",
        "session_id": "session-1",
        "question": "What is the expense approval flow?",
        "execution_mode": "agent",
        "reuse_scope": True,
        "scope": {
            "mode": "single",
            "corpus_ids": ["kb:base-1"],
            "document_ids": [],
            "allow_common_knowledge": False,
        },
    }
    assert captured["completed_resource_id"] == "message-2"
    assert released_tickets == ["ticket-1"]
    assert audit_events[-1]["action"] == "chat.workflow_run.retry"
    assert audit_events[-1]["outcome"] == "success"
    assert audit_events[-1]["details"]["new_workflow_run_id"] == "run-2"


def test_build_chat_workflow_state_includes_agent_events() -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")

    prepared = {
        "execution_mode": "agent",
        "answer_mode": "grounded",
        "payload": SimpleNamespace(question="What is the expense approval flow?"),
        "contextualized_question": "expense approval flow",
        "scope_snapshot": {"mode": "single"},
        "evidence": [{"unit_id": "chunk-1"}],
        "retrieval_meta": {
            "aggregate": {"selected_candidates": 1, "partial_failure": False},
            "agent": {"events": [{"type": "tool_request", "tool": "search_scope"}]},
        },
        "safety": {"risk_level": "low"},
        "timing": {"retrieval_ms": 4.0},
    }

    state = gateway_chat_service.build_chat_workflow_state(prepared=prepared, stage="retrieval_completed")

    assert state["agent_events"] == [{"type": "tool_request", "tool": "search_scope"}]


def test_handle_chat_message_marks_workflow_failed_on_generation_error(monkeypatch) -> None:
    gateway_chat_service = _load_gateway_module("app.gateway_chat_service")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    workflow_updates: list[dict[str, object]] = []

    async def fake_prepare_chat_message(**kwargs):
        return {
            "session_id": "session-1",
            "payload": SimpleNamespace(question="What is the expense approval flow?"),
            "trace_id": "gateway-trace-1",
            "scope_snapshot": {"mode": "single", "execution_mode": "agent"},
            "execution_mode": "agent",
            "history": [],
            "evidence": [],
            "contextualized_question": "expense approval flow",
            "retrieval_meta": {"aggregate": {"selected_candidates": 0, "partial_failure": False}, "agent": {"tool_calls": []}},
            "answer_mode": "refusal",
            "evidence_status": "insufficient",
            "grounding_score": 0.0,
            "refusal_reason": "insufficient_evidence",
            "safety": {"risk_level": "low", "reason_codes": []},
            "timing": {"total_started": 0.0, "scope_ms": 1.0, "retrieval_ms": 2.0},
        }

    async def fail_generate_grounded_answer(**kwargs):
        raise RuntimeError("llm failed")

    def fake_start_workflow_run_fn(**kwargs):
        return {"id": "run-1", "status": "running", "stage": "retrieval_completed"}

    def fake_update_workflow_run_fn(**kwargs):
        workflow_updates.append(dict(kwargs))
        return {
            "id": kwargs["run_id"],
            "status": kwargs["status"],
            "stage": kwargs["workflow_state"].get("stage", ""),
            "workflow_events": list(kwargs.get("workflow_events") or []),
        }

    monkeypatch.setattr(gateway_chat_service, "prepare_chat_message", fake_prepare_chat_message)
    monkeypatch.setattr(gateway_chat_service, "generate_grounded_answer", fail_generate_grounded_answer)

    try:
        asyncio.run(
            gateway_chat_service.handle_chat_message(
                session_id="session-1",
                payload=SimpleNamespace(question="What is the expense approval flow?"),
                request=SimpleNamespace(),
                user=user,
                load_session_fn=lambda *args, **kwargs: {},
                default_scope_fn=lambda: {"mode": "all"},
                resolve_scope_snapshot_fn=lambda *args, **kwargs: {},
                recent_history_messages_fn=lambda *args, **kwargs: [],
                retrieve_scope_evidence_fn=lambda *args, **kwargs: None,
                fetch_corpus_documents_fn=lambda *args, **kwargs: [],
                persist_chat_turn_fn=lambda *args, **kwargs: {},
                start_workflow_run_fn=fake_start_workflow_run_fn,
                update_workflow_run_fn=fake_update_workflow_run_fn,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "llm failed"
    else:
        raise AssertionError("expected generation failure to propagate")

    assert workflow_updates[-1]["status"] == "failed"
    assert workflow_updates[-1]["workflow_state"]["stage"] == "failed"
    assert workflow_updates[-1]["workflow_state"]["error"]["type"] == "RuntimeError"
    assert workflow_updates[-1]["workflow_events"][-1]["status"] == "failed"


def test_run_agent_search_degrades_to_grounded_when_tool_calling_fails(monkeypatch) -> None:
    gateway_agent = _load_gateway_module("app.gateway_agent")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    class _Settings:
        configured = True
        model = "mock-model"
        default_max_tokens = 512

    class _BrokenModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("quota exhausted")

    async def fake_retrieve_scope_evidence_fn(**kwargs):
        return (
            [{"unit_id": "chunk-1", "evidence_path": {"final_score": 0.91}}],
            "expense approval flow",
            {"aggregate": {"selected_candidates": 1}, "services": []},
        )

    monkeypatch.setattr(gateway_agent, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_agent, "build_chat_model", lambda **kwargs: _BrokenModel())

    evidence, contextualized_question, retrieval_meta = asyncio.run(
        gateway_agent.run_agent_search(
            user=user,
            scope_snapshot={
                "mode": "single",
                "corpus_ids": ["kb:base-1"],
                "document_ids": [],
                "documents_by_corpus": {},
                "allow_common_knowledge": False,
                "execution_mode": "agent",
            },
            question="What is the expense approval flow?",
            history=[],
            retrieve_scope_evidence_fn=fake_retrieve_scope_evidence_fn,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            kb_service_url="http://kb-service:8200",
        )
    )

    assert len(evidence) == 1
    assert contextualized_question == "expense approval flow"
    assert retrieval_meta["aggregate"]["execution_mode"] == "agent"
    assert retrieval_meta["aggregate"]["agent_fallback"] is True
    assert retrieval_meta["aggregate"]["tool_budget"] == 3
    assert retrieval_meta["agent"]["fallback"] is True
    assert retrieval_meta["agent"]["tool_budget"]["max_tool_calls"] == 3
    assert retrieval_meta["agent"]["allowed_tools"] == ["search_scope", "list_scope_documents", "search_corpus"]
    assert retrieval_meta["agent"]["tool_calls_used"] == 0


def test_run_agent_search_records_agent_events(monkeypatch) -> None:
    gateway_agent = _load_gateway_module("app.gateway_agent")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")

    class _Settings:
        configured = True
        model = "mock-model"
        default_max_tokens = 512

    class _FakeModel:
        def bind_tools(self, tools):
            self._tools = tools
            return self

        async def ainvoke(self, messages):
            if not any(isinstance(item, gateway_agent.ToolMessage) for item in messages):
                return gateway_agent.AIMessage(
                    content="Searching scope first.",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "name": "search_scope",
                            "args": {"search_question": "expense approval flow", "limit": 3},
                        }
                    ],
                )
            return gateway_agent.AIMessage(content="Enough evidence found.")

    async def fake_retrieve_scope_evidence_fn(**kwargs):
        return (
            [{"unit_id": "chunk-1", "document_title": "Policy", "section_title": "Approval", "quote": "Need finance approval", "evidence_path": {"final_score": 0.91}}],
            "expense approval flow",
            {"aggregate": {"selected_candidates": 1}, "services": []},
        )

    monkeypatch.setattr(gateway_agent, "load_llm_settings", lambda: _Settings())
    monkeypatch.setattr(gateway_agent, "build_chat_model", lambda **kwargs: _FakeModel())

    evidence, _, retrieval_meta = asyncio.run(
        gateway_agent.run_agent_search(
            user=user,
            scope_snapshot={
                "mode": "single",
                "corpus_ids": ["kb:base-1"],
                "document_ids": [],
                "documents_by_corpus": {},
                "allow_common_knowledge": False,
                "execution_mode": "agent",
            },
            question="What is the expense approval flow?",
            history=[],
            retrieve_scope_evidence_fn=fake_retrieve_scope_evidence_fn,
            fetch_corpus_documents_fn=lambda *args, **kwargs: [],
            kb_service_url="http://kb-service:8200",
        )
    )

    assert len(evidence) == 1
    agent_events = retrieval_meta["agent"]["events"]
    assert agent_events[0]["type"] == "agent_started"
    assert any(event["type"] == "tool_request" and event["tool"] == "search_scope" for event in agent_events)
    assert any(event["type"] == "tool_result" and event["tool"] == "search_scope" for event in agent_events)
    assert retrieval_meta["aggregate"]["tool_calls_used"] == 1
    assert retrieval_meta["agent"]["allowed_tools"] == ["search_scope", "list_scope_documents", "search_corpus"]
    assert retrieval_meta["agent"]["tool_calls_used"] == 1


def test_common_knowledge_answers_are_prefixed_with_disclaimer() -> None:
    gateway_answering = _load_gateway_module("app.gateway_answering")

    answer = gateway_answering.ensure_common_knowledge_disclaimer("The sun releases energy through nuclear fusion.")

    assert gateway_answering.COMMON_KNOWLEDGE_DISCLAIMER in answer
    assert "nuclear fusion" in answer


def test_search_vector_evidence_degrades_when_qdrant_query_fails(monkeypatch) -> None:
    kb_vector_store = _load_kb_module("app.vector_store")

    def fail_build_vector_retriever(*, base_id, document_ids, limit):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(kb_vector_store, "build_vector_retriever", fail_build_vector_retriever)

    evidence, degraded_signals, warnings = kb_vector_store.search_vector_evidence(
        base_id="base-1",
        question="expense approval flow",
        document_ids=["doc-1"],
        limit=4,
    )

    assert evidence == []
    assert degraded_signals == ["vector"]
    assert warnings == ["vector retrieval disabled because qdrant query execution failed"]


def test_gateway_readiness_checks_degrade_llm_without_failing(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)

    class _Cursor:
        def execute(self, query):
            return None

        def fetchone(self):
            return {"ok": 1}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            class _Response:
                status_code = 200

            return _Response()

    monkeypatch.setattr(gateway_main.gateway_db, "connect", lambda: _Connection())
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "")

    checks = asyncio.run(gateway_main._gateway_readiness_checks())

    assert checks["database"]["status"] == "ok"
    assert checks["kb_service"]["status"] == "ok"
    assert checks["llm"]["status"] == "fallback"


def test_kb_readiness_checks_require_storage(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")

    class _Cursor:
        def execute(self, query):
            return None

        def fetchone(self):
            return {"ok": 1}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_main.db, "connect", lambda: _Connection())
    monkeypatch.setattr(kb_main.storage, "check_bucket_access", lambda: (_ for _ in ()).throw(RuntimeError("bucket missing")))
    monkeypatch.setitem(kb_main._kb_readiness_checks.__globals__, "check_vector_store", lambda: {"collection": "kb-evidence"})
    monkeypatch.setitem(
        kb_main._kb_readiness_checks.__globals__,
        "check_vector_runtime_config",
        lambda: {"collection": "kb-evidence", "api_key_configured": False},
    )

    checks = kb_main._kb_readiness_checks()

    assert checks["database"]["status"] == "ok"
    assert checks["object_storage"]["status"] == "failed"
    assert checks["vector_store"]["status"] == "ok"
    assert checks["qdrant_runtime_config"]["status"] == "ok"
    assert checks["qdrant_runtime_config"]["api_key_configured"] is False


def test_qdrant_runtime_config_uses_safe_defaults(monkeypatch) -> None:
    for name in (
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_COLLECTION",
        "QDRANT_PREFER_GRPC",
        "QDRANT_TIMEOUT_SECONDS",
        "FASTEMBED_MODEL_NAME",
        "FASTEMBED_SPARSE_MODEL_NAME",
        "FASTEMBED_VECTOR_SIZE",
        "FASTEMBED_THREADS",
        "FASTEMBED_CACHE_DIR",
        "FASTEMBED_BATCH_SIZE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = check_qdrant_runtime_config()

    assert config["status"] == "ok"
    assert config["endpoint"] == "http://qdrant:6333"
    assert config["collection"] == "kb-evidence"
    assert config["prefer_grpc"] is False
    assert config["timeout_seconds"] == 10.0
    assert config["api_key_configured"] is False
    assert config["fastembed_model"] == "BAAI/bge-small-zh-v1.5"
    assert config["fastembed_sparse_model"] == "Qdrant/bm25"
    assert config["fastembed_vector_size"] == 0
    assert config["fastembed_threads"] == 4
    assert config["fastembed_cache_dir_configured"] is False
    assert config["index_batch_size"] == 64


def test_qdrant_runtime_config_masks_sensitive_endpoint_and_key(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "https://user:credential@example.test:6333/private?debug=hidden")
    monkeypatch.setenv("QDRANT_API_KEY", "opaque-qdrant-key")
    monkeypatch.setenv("QDRANT_COLLECTION", "finance-kb")
    monkeypatch.setenv("QDRANT_PREFER_GRPC", "yes")
    monkeypatch.setenv("QDRANT_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("FASTEMBED_MODEL_NAME", "custom-dense")
    monkeypatch.setenv("FASTEMBED_SPARSE_MODEL_NAME", "custom-sparse")
    monkeypatch.setenv("FASTEMBED_VECTOR_SIZE", "768")
    monkeypatch.setenv("FASTEMBED_THREADS", "8")
    monkeypatch.setenv("FASTEMBED_CACHE_DIR", "E:\\fastembed-cache")
    monkeypatch.setenv("FASTEMBED_BATCH_SIZE", "32")

    config = check_qdrant_runtime_config()

    assert config["endpoint"] == "https://example.test:6333/private"
    assert config["collection"] == "finance-kb"
    assert config["prefer_grpc"] is True
    assert config["timeout_seconds"] == 2.5
    assert config["api_key_configured"] is True
    assert config["fastembed_model"] == "custom-dense"
    assert config["fastembed_sparse_model"] == "custom-sparse"
    assert config["fastembed_vector_size"] == 768
    assert config["fastembed_threads"] == 8
    assert config["fastembed_cache_dir_configured"] is True
    assert config["index_batch_size"] == 32
    assert "opaque-qdrant-key" not in str(config)
    assert "credential" not in config["endpoint"]


def test_qdrant_runtime_config_falls_back_for_invalid_numbers(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_TIMEOUT_SECONDS", "bad")
    monkeypatch.setenv("FASTEMBED_VECTOR_SIZE", "bad")
    monkeypatch.setenv("FASTEMBED_THREADS", "bad")
    monkeypatch.setenv("FASTEMBED_BATCH_SIZE", "bad")

    config = check_qdrant_runtime_config()

    assert config["timeout_seconds"] == 10.0
    assert config["fastembed_vector_size"] == 0
    assert config["fastembed_threads"] == 4
    assert config["index_batch_size"] == 64


def test_auth_configuration_allows_default_credentials_in_local_runtime(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("JWT_SECRET", auth_module.DEFAULT_JWT_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD", auth_module.DEFAULT_LOCAL_PASSWORD)
    monkeypatch.setenv("MEMBER_PASSWORD", auth_module.DEFAULT_LOCAL_PASSWORD)

    warnings = auth_module.ensure_auth_configuration_ready()

    assert len(warnings) == 3


def test_auth_configuration_rejects_default_credentials_outside_local(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", auth_module.DEFAULT_JWT_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD", auth_module.DEFAULT_LOCAL_PASSWORD)
    monkeypatch.setenv("MEMBER_PASSWORD", auth_module.DEFAULT_LOCAL_PASSWORD)

    try:
        auth_module.ensure_auth_configuration_ready()
    except RuntimeError as exc:
        assert "insecure auth configuration" in str(exc)
    else:
        raise AssertionError("expected insecure non-local auth configuration to raise RuntimeError")


def test_upsert_chat_message_feedback_snapshots_llm_metadata(monkeypatch) -> None:
    gateway_sessions = _load_gateway_module("app.gateway_sessions")
    user = auth_module.AuthUser(user_id="user-1", email="member@local", role="member")
    message_row = {
        "id": "msg-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "role": "assistant",
        "answer_mode": "grounded",
        "provider": "openai-compatible",
        "model": "gpt-4.1-mini",
        "scope_snapshot_json": {"execution_mode": "agent"},
        "usage_json": {
            "_meta": {
                "trace_id": "gateway-trace-1",
                "cost": {"estimated_cost": 0.0123, "currency": "USD"},
                "llm_trace": {
                    "prompt_key": "chat_grounded_answer",
                    "prompt_version": "2026-03-10",
                    "route_key": "grounded",
                    "model_resolved": "gpt-4.1-mini",
                },
            }
        },
    }

    class _Cursor:
        def __init__(self) -> None:
            self._row = None

        def execute(self, query, params=None):
            if "FROM chat_messages" in query:
                self._row = message_row
            elif "INSERT INTO chat_message_feedback" in query:
                self._row = {
                    "id": "feedback-1",
                    "session_id": params[1],
                    "message_id": params[2],
                    "user_id": params[3],
                    "verdict": params[4],
                    "reason_code": params[5],
                    "notes": params[6],
                    "trace_id": params[7],
                    "prompt_key": params[8],
                    "prompt_version": params[9],
                    "route_key": params[10],
                    "model": params[11],
                    "provider": params[12],
                    "execution_mode": params[13],
                    "answer_mode": params[14],
                    "cost_json": {"estimated_cost": 0.0123, "currency": "USD"},
                    "llm_trace_json": {"prompt_key": "chat_grounded_answer", "prompt_version": "2026-03-10", "route_key": "grounded"},
                    "created_at": None,
                    "updated_at": None,
                }
            return None

        def fetchone(self):
            return self._row

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gateway_sessions.gateway_db, "connect", lambda: _Connection())

    feedback = gateway_sessions.upsert_chat_message_feedback(
        session_id="session-1",
        message_id="msg-1",
        user=user,
        verdict="down",
        reason_code="low_confidence",
        notes="needs citations",
    )

    assert feedback["verdict"] == "down"
    assert feedback["reason_code"] == "low_confidence"
    assert feedback["trace_id"] == "gateway-trace-1"
    assert feedback["prompt_key"] == "chat_grounded_answer"
    assert feedback["prompt_version"] == "2026-03-10"
    assert feedback["route_key"] == "grounded"
    assert feedback["model"] == "gpt-4.1-mini"
    assert feedback["provider"] == "openai-compatible"
    assert feedback["execution_mode"] == "agent"
    assert feedback["cost"]["estimated_cost"] == 0.0123


def test_list_session_messages_attaches_feedback_payload(monkeypatch) -> None:
    gateway_sessions = _load_gateway_module("app.gateway_sessions")
    user = auth_module.AuthUser(user_id="user-1", email="member@local", role="member")
    message_row = {
        "id": "msg-1",
        "session_id": "session-1",
        "role": "assistant",
        "question": "",
        "answer": "approved",
        "answer_mode": "grounded",
        "evidence_status": "grounded",
        "grounding_score": 0.9,
        "refusal_reason": "",
        "citations_json": [],
        "evidence_path_json": [],
        "scope_snapshot_json": {"execution_mode": "grounded"},
        "provider": "openai-compatible",
        "model": "gpt-4.1-mini",
        "usage_json": {"_meta": {"trace_id": "gateway-trace-1", "cost": {}, "llm_trace": {}}},
        "created_at": None,
    }
    feedback_row = {
        "id": "feedback-1",
        "session_id": "session-1",
        "message_id": "msg-1",
        "verdict": "up",
        "reason_code": "helpful",
        "notes": "",
        "trace_id": "gateway-trace-1",
        "prompt_key": "chat_grounded_answer",
        "prompt_version": "2026-03-10",
        "route_key": "grounded",
        "model": "gpt-4.1-mini",
        "provider": "openai-compatible",
        "execution_mode": "grounded",
        "answer_mode": "grounded",
        "cost_json": {},
        "llm_trace_json": {},
        "created_at": None,
        "updated_at": None,
    }

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            if "FROM chat_messages" in query:
                self._rows = [message_row]
            elif "FROM chat_message_feedback" in query:
                self._rows = [feedback_row]
            return None

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gateway_sessions.gateway_db, "connect", lambda: _Connection())

    messages = gateway_sessions.list_session_messages("session-1", user, load_session_fn=lambda *_args, **_kwargs: None)

    assert len(messages) == 1
    assert messages[0]["id"] == "msg-1"
    assert messages[0]["feedback"]["verdict"] == "up"


def test_local_handoff_queue_claims_highest_priority_matching_skill_group(monkeypatch) -> None:
    gateway_handoff = _load_gateway_module("app.gateway_handoff")
    rows = [
        {
            "id": "session-low",
            "user_id": "user-1",
            "title": "低优先级",
            "scope_json": {
                "handoff": {
                    "status": "pending",
                    "tenant_id": "tenant-a",
                    "skill_group": "billing",
                    "priority": 1,
                    "requested_at": "2026-06-06T10:00:00+00:00",
                }
            },
            "created_at": "2026-06-06T10:00:00+00:00",
            "updated_at": "2026-06-06T10:00:00+00:00",
        },
        {
            "id": "session-wrong-skill",
            "user_id": "user-2",
            "title": "技术问题",
            "scope_json": {
                "handoff": {
                    "status": "pending",
                    "tenant_id": "tenant-a",
                    "skill_group": "technical",
                    "priority": 99,
                    "requested_at": "2026-06-06T09:00:00+00:00",
                }
            },
            "created_at": "2026-06-06T09:00:00+00:00",
            "updated_at": "2026-06-06T09:00:00+00:00",
        },
        {
            "id": "session-high",
            "user_id": "user-3",
            "title": "高优先级",
            "scope_json": {
                "handoff": {
                    "status": "pending",
                    "tenant_id": "tenant-a",
                    "skill_group": "Billing",
                    "priority": 8,
                    "requested_at": "2026-06-06T11:00:00+00:00",
                }
            },
            "created_at": "2026-06-06T11:00:00+00:00",
            "updated_at": "2026-06-06T11:00:00+00:00",
        },
    ]

    class _Cursor:
        def __init__(self) -> None:
            self._row = None

        def execute(self, query, params=None):
            if "SELECT *" in query:
                self._rows = [row for row in rows if row["scope_json"]["handoff"]["tenant_id"] == params[0]]
            elif "UPDATE chat_sessions" in query:
                session_id = params[1]
                tenant_id = params[2]
                for row in rows:
                    handoff = row["scope_json"]["handoff"]
                    if row["id"] == session_id and handoff["tenant_id"] == tenant_id and handoff["status"] == "pending":
                        row["scope_json"] = json.loads(params[0])
                        self._row = row
                        return None
                self._row = None

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._row

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def __init__(self) -> None:
            self.commit_count = 0

        def cursor(self):
            return _Cursor()

        def commit(self):
            self.commit_count += 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    connection = _Connection()
    monkeypatch.setattr(gateway_handoff.gateway_db, "connect", lambda: connection)

    claimed = gateway_handoff.local_handoff_queue.claim_next(
        tenant_id="tenant-a",
        skill_group="billing",
        operator_id="operator-1",
    )

    assert claimed is not None
    assert claimed["session_id"] == "session-high"
    assert claimed["handoff"]["status"] == "claimed"
    assert claimed["handoff"]["claimed_by"] == "operator-1"
    assert claimed["handoff"]["claim_backend"] == "local_session_scope"
    assert rows[1]["scope_json"]["handoff"]["status"] == "pending"


def test_local_handoff_queue_does_not_claim_same_session_twice(monkeypatch) -> None:
    gateway_handoff = _load_gateway_module("app.gateway_handoff")
    rows = [
        {
            "id": "session-1",
            "user_id": "user-1",
            "title": "待接管",
            "scope_json": {
                "handoff": {
                    "status": "pending",
                    "tenant_id": "tenant-a",
                    "skill_group": "general",
                    "priority": 1,
                    "requested_at": "2026-06-06T10:00:00+00:00",
                }
            },
            "created_at": "2026-06-06T10:00:00+00:00",
            "updated_at": "2026-06-06T10:00:00+00:00",
        }
    ]

    class _Cursor:
        def __init__(self) -> None:
            self._row = None

        def execute(self, query, params=None):
            if "SELECT *" in query:
                self._rows = [
                    row
                    for row in rows
                    if row["scope_json"]["handoff"]["tenant_id"] == params[0]
                    and row["scope_json"]["handoff"]["status"] == "pending"
                ]
            elif "UPDATE chat_sessions" in query:
                for row in rows:
                    handoff = row["scope_json"]["handoff"]
                    if row["id"] == params[1] and handoff["status"] == "pending":
                        handoff["status"] = "claimed"
                        handoff["claimed_by"] = "operator-1"
                        self._row = row
                        return None
                self._row = None

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._row

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gateway_handoff.gateway_db, "connect", lambda: _Connection())

    first = gateway_handoff.local_handoff_queue.claim_next(
        tenant_id="tenant-a",
        skill_group="general",
        operator_id="operator-1",
    )
    second = gateway_handoff.local_handoff_queue.claim_next(
        tenant_id="tenant-a",
        skill_group="general",
        operator_id="operator-2",
    )

    assert first is not None
    assert first["session_id"] == "session-1"
    assert second is None


def test_claim_next_handoff_route_returns_claim_result_and_audit(monkeypatch) -> None:
    gateway_chat_routes = _load_gateway_module("app.gateway_chat_routes")
    user = auth_module.AuthUser(user_id="u-1", email="member@local", role="member")
    audit_events: list[dict[str, object]] = []

    monkeypatch.setattr(gateway_chat_routes, "require_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        gateway_chat_routes.local_handoff_queue,
        "claim_next",
        lambda **kwargs: {
            "session_id": "session-1",
            "id": "session-1",
            "handoff": {
                "tenant_id": kwargs["tenant_id"],
                "skill_group": kwargs["skill_group"],
                "claimed_by": kwargs["operator_id"],
            },
        },
    )
    monkeypatch.setattr(gateway_chat_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(dict(kwargs)))

    result = asyncio.run(
        gateway_chat_routes.claim_next_handoff_session(
            gateway_chat_routes.ClaimHandoffSessionRequest(
                tenant_id="tenant-a",
                skill_group=" Billing ",
                operator_id="operator-1",
            ),
            SimpleNamespace(url=SimpleNamespace(path="/api/v1/chat/handoff/claim-next")),
            user,
        )
    )

    assert result["claimed"] is True
    assert result["session"]["session_id"] == "session-1"
    assert result["backend"] == "local_session_scope"
    assert audit_events[-1]["action"] == "chat.handoff.claim_next"
    assert audit_events[-1]["resource_id"] == "session-1"
    assert audit_events[-1]["details"]["skill_group"] == "billing"


def test_kb_analytics_dashboard_payload_aggregates_ingest_health(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="user-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    class _Cursor:
        def __init__(self) -> None:
            self._row = None
            self._rows = []

        def execute(self, query, params=None):
            if "FROM kb_bases" in query:
                self._row = {"total_count": 2}
                self._rows = []
            elif "COUNT(*) AS uploaded_count" in query:
                self._row = {"uploaded_count": 6}
                self._rows = []
            elif "COUNT(*) AS ready_count" in query:
                self._row = {"ready_count": 4}
                self._rows = []
            elif "AVG(EXTRACT(EPOCH FROM (ready_at - created_at))" in query:
                self._row = {
                    "sample_count": 4,
                    "avg_ms": 82000.0,
                    "p50_ms": 78000.0,
                    "p95_ms": 110000.0,
                    "max_ms": 120000.0,
                }
                self._rows = []
            elif "COUNT(*) AS total_documents" in query:
                self._row = {
                    "total_documents": 8,
                    "ready_documents": 4,
                    "queryable_documents": 5,
                    "failed_documents": 1,
                    "unfinished_documents": 4,
                    "stalled_documents": 1,
                    "dead_letter_documents": 1,
                    "in_progress_documents": 2,
                }
                self._rows = []
            elif "COALESCE(NULLIF(enhancement_status, ''), 'none')" in query:
                self._rows = [
                    {"key": "chunk_vectors_ready", "total_count": 4},
                    {"key": "visual_ready", "total_count": 2},
                    {"key": "failed", "total_count": 1},
                ]
                self._row = None
            elif "COALESCE(NULLIF(status, ''), 'missing')" in query:
                self._rows = [
                    {"key": "done", "total_count": 4},
                    {"key": "processing", "total_count": 2},
                    {"key": "dead_letter", "total_count": 1},
                ]
                self._row = None
            elif "COALESCE(NULLIF(status, ''), 'unknown')" in query:
                self._rows = [
                    {"key": "ready", "total_count": 4},
                    {"key": "enhancing", "total_count": 2},
                    {"key": "failed", "total_count": 1},
                ]
                self._row = None
            else:
                raise AssertionError(f"unexpected query: {query}")

        def fetchone(self):
            return self._row

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_analytics.db, "connect", lambda: _Connection())

    payload = kb_analytics._dashboard_payload(user, view="personal", days=14)

    assert payload["funnel"]["knowledge_bases_created"] == 2
    assert payload["funnel"]["documents_uploaded"] == 6
    assert payload["funnel"]["documents_ready"] == 4
    assert payload["ingest_health"]["summary"]["dead_letter_documents"] == 1
    assert payload["ingest_health"]["summary"]["stalled_documents"] == 1
    assert payload["ingest_health"]["upload_to_ready_latency_ms"]["p95_ms"] == 110000.0


def test_kb_operations_payload_aggregates_sections_and_health(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="ops-1",
        email="ops@local",
        role="kb_admin",
        permissions=auth_module.permissions_for_role("kb_admin"),
    )

    monkeypatch.setattr(kb_analytics, "check_readiness", lambda: {"database": {"status": "ok"}, "object_storage": {"status": "ok"}})
    monkeypatch.setattr(
        kb_analytics,
        "_ingest_operations_payload",
        lambda current_user, *, view: {
            "summary": {"failed_documents": 2, "stalled_documents": 1},
            "retryable_jobs": [{"job_id": "job-1"}],
            "stalled_documents": [{"document_id": "doc-1"}],
        },
    )
    monkeypatch.setattr(
        kb_analytics,
        "_connector_operations_payload",
        lambda current_user, *, view, days: {
            "summary": {"due_connectors": 1, "recent_failed_runs": 2},
            "items": [{"connector_id": "conn-1"}],
        },
    )
    monkeypatch.setattr(
        kb_analytics,
        "_incident_feed_payload",
        lambda current_user, *, view, days: {"items": [{"id": "evt-1", "action": "kb.ingest.dead_lettered"}]},
    )

    payload = kb_analytics._operations_payload(user, view="personal", days=14)

    assert payload["service_health"]["status"] == "ok"
    assert payload["ingest_ops"]["retryable_jobs"][0]["job_id"] == "job-1"
    assert payload["ingest_ops"]["stalled_documents"][0]["document_id"] == "doc-1"
    assert payload["connector_ops"]["summary"]["due_connectors"] == 1
    assert payload["incident_feed"]["items"][0]["id"] == "evt-1"
    assert payload["data_quality"]["degraded_sections"] == []


def test_kb_operations_payload_marks_degraded_sections_without_failing_page(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="ops-1",
        email="ops@local",
        role="kb_admin",
        permissions=auth_module.permissions_for_role("kb_admin"),
    )

    monkeypatch.setattr(kb_analytics, "check_readiness", lambda: {"database": {"status": "ok"}})
    monkeypatch.setattr(kb_analytics, "_ingest_operations_payload", lambda current_user, *, view: kb_analytics._empty_ingest_ops())
    monkeypatch.setattr(
        kb_analytics,
        "_connector_operations_payload",
        lambda current_user, *, view, days: (_ for _ in ()).throw(RuntimeError("connector query failed")),
    )
    monkeypatch.setattr(kb_analytics, "_incident_feed_payload", lambda current_user, *, view, days: {"items": []})

    payload = kb_analytics._operations_payload(user, view="personal", days=14)

    assert payload["service_health"]["status"] == "degraded"
    assert payload["connector_ops"]["summary"]["total_connectors"] == 0
    assert payload["connector_ops"]["items"] == []
    assert payload["data_quality"]["degraded_sections"][0]["key"] == "connector_ops"
    assert payload["data_quality"]["degraded_sections"][0]["error_type"] == "RuntimeError"


def test_kb_operations_incident_feed_uses_personal_scope(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    captured: dict[str, object] = {}
    user = auth_module.AuthUser(
        user_id="ops-1",
        email="ops@local",
        role="kb_admin",
        permissions=auth_module.permissions_for_role("kb_admin"),
    )

    def fake_list_audit_events(**kwargs):
        captured.update(kwargs)
        return [
            {"id": "evt-1", "action": "kb.ingest.dead_lettered", "outcome": "failed", "trace_id": "trace-1", "resource_type": "ingest_job", "resource_id": "job-1", "details": {}, "created_at": "2026-03-22T10:00:00+00:00"},
            {"id": "evt-2", "action": "kb.document.update", "outcome": "success", "trace_id": "trace-2", "resource_type": "document", "resource_id": "doc-1", "details": {}, "created_at": "2026-03-22T09:00:00+00:00"},
        ]

    monkeypatch.setattr(kb_analytics, "list_audit_events", fake_list_audit_events)

    payload = kb_analytics._incident_feed_payload(user, view="personal", days=7)

    assert captured["actor_user_id"] == "ops-1"
    assert payload["items"] == [
        {
            "id": "evt-1",
            "trace_id": "trace-1",
            "resource_type": "ingest_job",
            "resource_id": "job-1",
            "action": "kb.ingest.dead_lettered",
            "outcome": "failed",
            "created_at": "2026-03-22T10:00:00+00:00",
            "details": {},
        }
    ]


def test_kb_governance_payload_aggregates_enterprise_queues(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="user-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    now = datetime(2026, 3, 20, tzinfo=timezone.utc)

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []
            self._row = None

        def execute(self, query, params=None):
            if "COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = 'approved'" in query:
                self._rows = [
                    {
                        "document_id": "doc-approved",
                        "base_id": "base-1",
                        "base_name": "Ops KB",
                        "file_name": "policy-approved.pdf",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "ops-policy",
                        "version_label": "2026-Q3",
                        "version_number": 5,
                        "version_status": "draft",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 0,
                        "owner_user_id": "owner-1",
                        "review_status": "approved",
                        "reviewer_note": "approved by kb admin",
                        "reviewed_at": now,
                        "reviewed_by_user_id": "reviewer-1",
                        "reviewed_by_email": "reviewer@local",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "COALESCE(NULLIF(d.stats_json->>'review_status', ''), '') = 'rejected'" in query:
                self._rows = [
                    {
                        "document_id": "doc-rejected",
                        "base_id": "base-1",
                        "base_name": "Ops KB",
                        "file_name": "policy-rejected.pdf",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "ops-policy",
                        "version_label": "2026-Q0",
                        "version_number": 1,
                        "version_status": "draft",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 0,
                        "owner_user_id": "owner-2",
                        "review_status": "rejected",
                        "reviewer_note": "missing rollback steps",
                        "reviewed_at": now,
                        "reviewed_by_user_id": "reviewer-2",
                        "reviewed_by_email": "rejector@local",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "COALESCE(d.version_status, '') = 'draft'" in query:
                self._rows = [
                    {
                        "document_id": "doc-draft",
                        "base_id": "base-1",
                        "base_name": "Ops KB",
                        "file_name": "policy-draft.pdf",
                        "status": "uploaded",
                        "enhancement_status": "visual_pending",
                        "version_family_key": "ops-policy",
                        "version_label": "v3-draft",
                        "version_number": 3,
                        "version_status": "draft",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 2,
                        "owner_user_id": "owner-3",
                        "review_status": "review_pending",
                        "reviewer_note": "need owner signoff",
                        "reviewed_at": now,
                        "reviewed_by_user_id": "",
                        "reviewed_by_email": "",
                        "total_count": 2,
                    },
                    {
                        "document_id": "doc-scheduled",
                        "base_id": "base-1",
                        "base_name": "Ops KB",
                        "file_name": "policy-q2.pdf",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "ops-policy",
                        "version_label": "2026-Q2",
                        "version_number": 4,
                        "version_status": "active",
                        "is_current_version": True,
                        "effective_from": datetime(2026, 4, 1, tzinfo=timezone.utc),
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 0,
                        "owner_user_id": "owner-3",
                        "review_status": "",
                        "reviewer_note": "",
                        "reviewed_at": None,
                        "reviewed_by_user_id": "",
                        "reviewed_by_email": "",
                        "total_count": 2,
                    },
                ]
                self._row = None
            elif "d.effective_to IS NOT NULL AND d.effective_to < NOW()" in query:
                self._rows = [
                    {
                        "document_id": "doc-expired",
                        "base_id": "base-2",
                        "base_name": "HR KB",
                        "file_name": "handbook-2024.pdf",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "employee-handbook",
                        "version_label": "2024",
                        "version_number": 2,
                        "version_status": "superseded",
                        "is_current_version": False,
                        "effective_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
                        "effective_to": datetime(2025, 12, 31, tzinfo=timezone.utc),
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 0,
                        "owner_user_id": "owner-4",
                        "review_status": "approved",
                        "reviewer_note": "",
                        "reviewed_at": now,
                        "reviewed_by_user_id": "reviewer-3",
                        "reviewed_by_email": "approver@local",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "NOT IN ('visual_ready', 'summary_vectors_ready', 'chunk_vectors_ready')" in query:
                self._rows = [
                    {
                        "document_id": "doc-visual",
                        "base_id": "base-3",
                        "base_name": "Infra KB",
                        "file_name": "terminal-shot.png",
                        "status": "enhancing",
                        "enhancement_status": "visual_pending",
                        "version_family_key": "",
                        "version_label": "",
                        "version_number": None,
                        "version_status": "active",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 3,
                        "owner_user_id": "owner-5",
                        "review_status": "",
                        "reviewer_note": "",
                        "reviewed_at": None,
                        "reviewed_by_user_id": "",
                        "reviewed_by_email": "",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "region.confidence <" in query:
                self._rows = [
                    {
                        "document_id": "doc-visual-low-confidence",
                        "base_id": "base-3",
                        "base_name": "Infra KB",
                        "file_name": "terminal-shot.png",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "",
                        "version_label": "",
                        "version_number": None,
                        "version_status": "active",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 3,
                        "low_confidence_region_count": 2,
                        "low_confidence_asset_id": "asset-visual-1",
                        "low_confidence_region_id": "region-low-1",
                        "low_confidence_region_label": "terminal config",
                        "low_confidence_region_confidence": 0.42,
                        "low_confidence_region_bbox": [0.1, 0.2, 0.8, 0.6],
                        "owner_user_id": "owner-5",
                        "review_status": "",
                        "reviewer_note": "",
                        "reviewed_at": None,
                        "reviewed_by_user_id": "",
                        "reviewed_by_email": "",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "d.supersedes_document_id IS NOT NULL" in query:
                self._rows = [
                    {
                        "document_id": "doc-missing-family",
                        "base_id": "base-4",
                        "base_name": "Finance KB",
                        "file_name": "expense-v2.pdf",
                        "status": "ready",
                        "enhancement_status": "chunk_vectors_ready",
                        "version_family_key": "",
                        "version_label": "v2",
                        "version_number": 2,
                        "version_status": "active",
                        "is_current_version": False,
                        "effective_from": None,
                        "effective_to": None,
                        "created_at": now,
                        "updated_at": now,
                        "visual_asset_count": 0,
                        "owner_user_id": "owner-6",
                        "review_status": "",
                        "reviewer_note": "",
                        "reviewed_at": None,
                        "reviewed_by_user_id": "",
                        "reviewed_by_email": "",
                        "total_count": 1,
                    }
                ]
                self._row = None
            elif "HAVING COUNT(*) FILTER (WHERE d.is_current_version = TRUE) > 1" in query:
                self._rows = [
                    {
                        "base_id": "base-5",
                        "base_name": "Support KB",
                        "version_family_key": "faq",
                        "current_version_count": 2,
                        "active_version_count": 2,
                        "total_versions": 3,
                        "latest_version_number": 5,
                        "current_document_ids": ["doc-a", "doc-b"],
                        "current_labels": ["2026-Q1", "2026-Q2"],
                        "total_count": 1,
                    }
                ]
                self._row = None
            else:
                raise AssertionError(f"unexpected query: {query}")

        def fetchone(self):
            return self._row

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_analytics.db, "connect", lambda: _Connection())

    payload = kb_analytics._governance_payload(user, view="personal", limit=5)

    assert isinstance(payload["generated_at"], str) and payload["generated_at"]
    assert payload["summary"]["pending_review"] == 2
    assert payload["summary"]["approved_ready"] == 1
    assert payload["summary"]["rejected_documents"] == 1
    assert payload["summary"]["expired_documents"] == 1
    assert payload["summary"]["visual_attention"] == 1
    assert payload["summary"]["visual_low_confidence"] == 1
    assert payload["summary"]["missing_version_family"] == 1
    assert payload["summary"]["version_conflicts"] == 1
    assert payload["queues"]["pending_review"][0]["reason"] == "review_pending"
    assert payload["queues"]["pending_review"][1]["reason"] == "scheduled_publish"
    assert payload["queues"]["pending_review"][0]["review_status"] == "review_pending"
    assert payload["queues"]["pending_review"][0]["owner_user_id"] == "owner-3"
    assert payload["queues"]["approved_ready"][0]["reason"] == "approved_ready"
    assert payload["queues"]["approved_ready"][0]["reviewed_by_email"] == "reviewer@local"
    assert payload["queues"]["rejected_documents"][0]["reason"] == "rejected_review"
    assert payload["queues"]["rejected_documents"][0]["reviewer_note"] == "missing rollback steps"
    assert payload["queues"]["rejected_documents"][0]["reviewed_by_user_id"] == "reviewer-2"
    assert payload["queues"]["expired_documents"][0]["effective_now"] is False
    assert payload["queues"]["visual_attention"][0]["reason"] == "visual_pipeline_visual_pending"
    assert payload["queues"]["visual_low_confidence"][0]["reason"] == "visual_pipeline_low_confidence"
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_region_count"] == 2
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_asset_id"] == "asset-visual-1"
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_region_id"] == "region-low-1"
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_region_label"] == "terminal config"
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_region_confidence"] == 0.42
    assert payload["queues"]["visual_low_confidence"][0]["low_confidence_region_bbox"] == [0.1, 0.2, 0.8, 0.6]
    assert payload["queues"]["missing_version_family"][0]["reason"] == "version_metadata_without_family"
    assert payload["queues"]["version_conflicts"][0]["current_document_ids"] == ["doc-a", "doc-b"]


def test_gateway_qa_quality_stats_handles_empty_window(monkeypatch) -> None:
    gateway_analytics = _load_gateway_module("app.gateway_analytics_routes")
    user = auth_module.AuthUser(
        user_id="user-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    class _Cursor:
        def __init__(self) -> None:
            self._row = None
            self._rows = []

        def execute(self, query, params=None):
            if "COUNT(*) AS assistant_answers" in query:
                self._row = {
                    "assistant_answers": 0,
                    "refusal_answers": 0,
                    "weak_grounded_answers": 0,
                    "grounded_answers": 0,
                    "selected_candidates_zero": 0,
                    "missing_citations": 0,
                    "missing_citations_non_refusal": 0,
                    "zero_hit_non_refusal": 0,
                    "grounding_score_lt_0_5": 0,
                    "partial_evidence": 0,
                    "low_quality_answers": 0,
                }
                self._rows = []
            elif "COUNT(*) AS clarification_runs" in query:
                self._row = {
                    "clarification_runs": 0,
                    "clarification_completed_runs": 0,
                    "clarification_pending_runs": 0,
                    "clarification_with_free_text_runs": 0,
                    "clarification_with_selection_runs": 0,
                }
                self._rows = []
            elif "workflow_state_json #>> '{retrieval,aggregate,clarification_kind}'" in query:
                self._rows = []
                self._row = None
            elif "COALESCE(NULLIF(answer_mode, ''), 'unknown')" in query or "COALESCE(NULLIF(evidence_status, ''), 'unknown')" in query:
                self._rows = []
                self._row = None
            else:
                raise AssertionError(f"unexpected query: {query}")

        def fetchone(self):
            return self._row

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gateway_analytics.gateway_db, "connect", lambda: _Connection())

    payload = gateway_analytics._qa_quality_stats(user, view="personal", days=14)

    assert payload["summary"]["assistant_answers"] == 0
    assert payload["zero_hit"]["selected_candidates_zero_rate"] == 0.0
    assert payload["low_quality"]["rate"] == 0.0
    assert payload["clarification"]["triggered_runs"] == 0
    assert payload["clarification"]["completion_rate"] == 0.0
    assert payload["answer_mode_distribution"] == []
    assert payload["evidence_status_distribution"] == []
    assert payload["clarification"]["kind_distribution"] == []


def test_gateway_usage_stats_includes_provider_billing(monkeypatch) -> None:
    gateway_analytics = _load_gateway_module("app.gateway_analytics_routes")
    user = auth_module.AuthUser(
        user_id="user-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    executed: list[tuple[str, tuple[object, ...]]] = []

    class _Cursor:
        def __init__(self) -> None:
            self._row = None
            self._rows = []

        def execute(self, query, params=None):
            normalized = " ".join(str(query).split())
            params_tuple = tuple(params or ())
            executed.append((normalized, params_tuple))
            if "DATE(created_at) AS day" in query:
                assert params_tuple == ("user-1", 14)
                self._rows = [
                    {
                        "day": "2026-06-07",
                        "prompt_tokens": 1200,
                        "completion_tokens": 300,
                        "estimated_cost": 0.42,
                    }
                ]
                self._row = None
            elif "COUNT(*) AS assistant_turns" in query:
                assert params_tuple == ("user-1", 14)
                self._row = {
                    "assistant_turns": 2,
                    "prompt_tokens": 1200,
                    "completion_tokens": 300,
                    "estimated_cost": 0.42,
                }
                self._rows = []
            elif "COUNT(*) AS provider_billing_records" in query:
                assert params_tuple == ("user-1", 14)
                self._row = {
                    "provider_billing_records": 3,
                    "provider_billed_cost_cents": 987,
                    "provider_input_tokens": 2200,
                    "provider_output_tokens": 500,
                }
                self._rows = []
            elif "GROUP BY provider, currency" in query:
                assert params_tuple == ("user-1", 14)
                self._rows = [
                    {
                        "provider": "openai",
                        "currency": "USD",
                        "record_count": 2,
                        "billed_cost_cents": 700,
                        "input_tokens": 1800,
                        "output_tokens": 420,
                    }
                ]
                self._row = None
            elif "GROUP BY route_key, currency" in query:
                assert params_tuple == ("user-1", 14)
                self._rows = [
                    {
                        "route_key": "grounded",
                        "currency": "USD",
                        "record_count": 2,
                        "billed_cost_cents": 700,
                    }
                ]
                self._row = None
            elif "DATE(billed_at) AS day" in query:
                assert params_tuple == ("user-1", 14)
                self._rows = [
                    {
                        "day": "2026-06-07",
                        "currency": "USD",
                        "record_count": 3,
                        "billed_cost_cents": 987,
                    }
                ]
                self._row = None
            elif "GROUP BY currency" in query:
                assert params_tuple == ("user-1", 14)
                self._rows = [
                    {
                        "currency": "USD",
                        "record_count": 3,
                        "billed_cost_cents": 987,
                    }
                ]
                self._row = None
            else:
                raise AssertionError(f"unexpected query: {query}")

        def fetchone(self):
            return self._row

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gateway_analytics.gateway_db, "connect", lambda: _Connection())

    payload = gateway_analytics._usage_stats(user, view="personal", days=14)

    assert len(executed) == 7
    assert payload["summary"]["assistant_turns"] == 2
    assert payload["summary"]["estimated_cost"] == 0.42
    assert payload["summary"]["provider_billing_records"] == 3
    assert payload["summary"]["provider_billed_cost_cents"] == 987
    assert payload["summary"]["provider_billed_cost"] == 9.87
    assert payload["summary"]["provider_input_tokens"] == 2200
    assert payload["summary"]["provider_output_tokens"] == 500
    assert payload["summary"]["cost_source_counts"] == {"chat_estimated": 2, "provider_billing": 3}
    assert payload["provider_billing"]["by_provider"][0]["provider"] == "openai"
    assert payload["provider_billing"]["by_provider"][0]["billed_cost"] == 7.0
    assert payload["provider_billing"]["by_route"][0]["route_key"] == "grounded"
    assert payload["provider_billing"]["trend"][0]["billed_cost"] == 9.87
    assert payload["provider_billing"]["by_currency"][0]["currency"] == "USD"


def test_gateway_dashboard_route_returns_extended_payload(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_analytics = importlib.import_module("app.gateway_analytics_routes")
    user = auth_module.AuthUser(
        user_id="admin-1",
        email="admin@local",
        role="platform_admin",
        permissions=auth_module.permissions_for_role("platform_admin"),
    )

    monkeypatch.setattr(gateway_analytics, "_hot_terms", lambda *_args, **_kwargs: [{"term": "expense", "count": 3}])
    monkeypatch.setattr(gateway_analytics, "_zero_hit_stats", lambda *_args, **_kwargs: {"trend": [], "top_queries": []})
    monkeypatch.setattr(gateway_analytics, "_satisfaction_stats", lambda *_args, **_kwargs: {"trend": []})
    monkeypatch.setattr(
        gateway_analytics,
        "_usage_stats",
        lambda *_args, **_kwargs: {"currency": "USD", "summary": {"assistant_turns": 8, "prompt_tokens": 1200.0, "completion_tokens": 480.0, "estimated_cost": 0.52}, "trend": []},
    )
    monkeypatch.setattr(
        gateway_analytics,
        "_chat_funnel_stats",
        lambda *_args, **_kwargs: {
            "chat_sessions_with_questions": 5,
            "questions_asked": 11,
            "answer_outcomes": {"grounded": 7, "weak_grounded": 2, "refusal": 1, "other": 0},
            "feedback": {"up": 4, "down": 1, "flag": 0},
        },
    )
    monkeypatch.setattr(
        gateway_analytics,
        "_qa_quality_stats",
        lambda *_args, **_kwargs: {
            "summary": {"assistant_answers": 10, "grounded_answers": 7, "weak_grounded_answers": 2, "refusal_answers": 1},
            "answer_mode_distribution": [{"key": "grounded", "count": 7}],
            "evidence_status_distribution": [{"key": "grounded", "count": 7}],
            "zero_hit": {"selected_candidates_zero": 1, "selected_candidates_zero_rate": 0.1, "missing_citations": 2, "missing_citations_rate": 0.2},
            "low_quality": {"count": 2, "rate": 0.2, "score_threshold": 0.5, "reason_breakdown": [{"key": "partial_evidence", "count": 2}]},
            "clarification": {
                "triggered_runs": 3,
                "completed_runs": 2,
                "pending_runs": 1,
                "completion_rate": 0.6667,
                "free_text_runs": 1,
                "selection_runs": 2,
                "kind_distribution": [{"key": "version_conflict", "count": 2}, {"key": "visual_ambiguity", "count": 1}],
            },
        },
    )

    async def _fake_kb_dashboard_snapshot(current_user, *, view: str, days: int):
        assert current_user.user_id == "admin-1"
        assert view == "admin"
        assert days == 30
        return (
            {
                "funnel": {
                    "knowledge_bases_created": 2,
                    "documents_uploaded": 6,
                    "documents_ready": 4,
                },
                "ingest_health": {
                    "summary": {"total_documents": 8, "ready_documents": 4},
                    "document_status_distribution": [{"key": "ready", "count": 4}],
                    "latest_job_status_distribution": [{"key": "done", "count": 4}],
                    "enhancement_status_distribution": [{"key": "chunk_vectors_ready", "count": 4}],
                    "upload_to_ready_latency_ms": {"count": 4, "avg_ms": 82000.0, "p50_ms": 78000.0, "p95_ms": 110000.0, "max_ms": 120000.0, "unsupported": False},
                },
                "data_quality": {"unsupported_fields": [], "degraded_sections": []},
            },
            [],
        )

    monkeypatch.setattr(gateway_analytics, "_kb_dashboard_snapshot", _fake_kb_dashboard_snapshot)
    monkeypatch.setattr(gateway_analytics, "write_gateway_audit_event", lambda **_kwargs: None)

    client = TestClient(gateway_main.app)
    response = client.get("/api/v1/analytics/dashboard?view=admin&days=30", headers=_auth_headers(user))

    assert response.status_code == 200
    payload = response.json()
    assert payload["funnel"]["knowledge_bases_created"] == 2
    assert payload["funnel"]["questions_asked"] == 11
    assert payload["qa_quality"]["zero_hit"]["selected_candidates_zero"] == 1
    assert payload["qa_quality"]["clarification"]["triggered_runs"] == 3
    assert payload["ingest_health"]["summary"]["ready_documents"] == 4
    assert payload["data_quality"]["unsupported_fields"] == []


def test_gateway_dashboard_route_rejects_invalid_days(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    user = auth_module.AuthUser(
        user_id="admin-1",
        email="admin@local",
        role="platform_admin",
        permissions=auth_module.permissions_for_role("platform_admin"),
    )

    client = TestClient(gateway_main.app)
    response = client.get("/api/v1/analytics/dashboard?days=0", headers=_auth_headers(user))

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "validation_error"


def test_gateway_dashboard_route_requires_chat_permission(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_audit_support = importlib.import_module("app.gateway_audit_support")
    monkeypatch.setattr(gateway_audit_support, "write_gateway_audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="audit-1",
        email="audit@local",
        role="audit_viewer",
        permissions=auth_module.permissions_for_role("audit_viewer"),
    )

    client = TestClient(gateway_main.app)
    response = client.get("/api/v1/analytics/dashboard", headers=_auth_headers(user))

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_gateway_tool_workflow_route_passes_workflow_mode(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_platform_routes = importlib.import_module("app.gateway_platform_routes")
    governance_metrics = importlib.import_module("app.governance_metrics")
    gateway_system_routes = importlib.import_module("app.gateway_system_routes")
    governance_metrics.get_governance_metrics().reset()
    audit_events: list[dict[str, object]] = []
    monkeypatch.setattr(gateway_platform_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(kwargs))
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/agents/tool-workflow",
        headers=_auth_headers(user),
        json={
            "tool_name": "data_controls_dry_run",
            "workflow_mode": "plan_reflect_repair",
            "payload": {"scopes": [], "action": "audit"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow_mode"] == "plan_reflect_repair"
    assert payload["metadata"]["repair_count"] == 1
    assert payload["planning"]["tool_name"] == "data_controls_dry_run"
    assert payload["reflection"]["repairable"] is True
    assert payload["repair"]["applied"] is True
    assert payload["data"]["scopes"] == ["memory", "usage", "export_rag"]
    assert audit_events
    assert audit_events[0]["action"] == "agent.tool_workflow.run"
    assert audit_events[0]["outcome"] == "success"
    assert audit_events[0]["resource_type"] == "tool_workflow"
    assert audit_events[0]["resource_id"] == "data_controls_dry_run"
    assert audit_events[0]["scope"] == "plan_reflect_repair"
    assert audit_events[0]["details"] == {"repair_count": 1}
    metrics = gateway_system_routes.get_metrics_summary()["governance_metrics"]["events"]["tool_workflow"]
    assert metrics["total"] == 1
    assert metrics["success"] == 1
    assert metrics["failure"] == 0
    assert metrics["last_duration_ms"] >= 0
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "rag_gateway_governance_events_total" in metrics_response.text


def test_gateway_tool_workflow_route_records_failure_metrics(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_platform_routes = importlib.import_module("app.gateway_platform_routes")
    governance_metrics = importlib.import_module("app.governance_metrics")
    gateway_system_routes = importlib.import_module("app.gateway_system_routes")
    governance_metrics.get_governance_metrics().reset()
    monkeypatch.setattr(gateway_platform_routes, "write_gateway_audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/agents/tool-workflow",
        headers=_auth_headers(user),
        json={
            "tool_name": "unknown_tool",
            "workflow_mode": "plan_reflect_repair",
            "payload": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    metrics = gateway_system_routes.get_metrics_summary()["governance_metrics"]["events"]["tool_workflow"]
    assert metrics["total"] == 1
    assert metrics["success"] == 0
    assert metrics["failure"] == 1
    assert metrics["failure_reasons"] == {"tool_not_allowed": 1}
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    metrics_text = metrics_response.text
    failure_reason_metric = (
        'rag_gateway_governance_failure_reasons_total{event="tool_workflow",reason="tool_not_allowed"}'
    )
    assert failure_reason_metric in metrics_text
    assert "rag_gateway_governance_event_duration_ms_bucket" in metrics_text


def test_gateway_tool_workflow_route_requires_chat_permission(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_audit_support = importlib.import_module("app.gateway_audit_support")
    monkeypatch.setattr(gateway_audit_support, "write_gateway_audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="audit-1",
        email="audit@local",
        role="audit_viewer",
        permissions=auth_module.permissions_for_role("audit_viewer"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/agents/tool-workflow",
        headers=_auth_headers(user),
        json={"tool_name": "data_controls_dry_run", "payload": {}},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_gateway_tool_workflow_route_rejects_blank_tool_name(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/agents/tool-workflow",
        headers=_auth_headers(user),
        json={"tool_name": "   ", "payload": {}},
    )

    assert response.status_code == 422


def test_gateway_mcp_route_lists_readonly_tools_and_writes_audit(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_mcp_routes = importlib.import_module("app.gateway_mcp_routes")
    audit_events: list[dict[str, object]] = []
    monkeypatch.setattr(gateway_mcp_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(kwargs))
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/mcp",
        headers=_auth_headers(user),
        json={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == "list-1"
    names = {tool["name"] for tool in payload["result"]["tools"]}
    assert names == {"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"}
    assert "data_controls_dry_run" not in names
    assert "prompt_preview" not in str(payload)
    assert audit_events
    assert audit_events[0]["action"] == "mcp.request"
    assert audit_events[0]["outcome"] == "success"
    assert audit_events[0]["resource_type"] == "mcp_adapter"
    assert audit_events[0]["resource_id"] == "tools/list"


def test_gateway_mcp_route_calls_tool_and_blocks_non_object_arguments(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_mcp_routes = importlib.import_module("app.gateway_mcp_routes")
    monkeypatch.setattr(gateway_mcp_routes, "write_gateway_audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(gateway_main.app)
    success = client.post(
        "/api/v1/mcp",
        headers=_auth_headers(user),
        json={
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "tool_registry_stats", "arguments": {}},
        },
    )
    assert success.status_code == 200
    success_payload = success.json()
    assert success_payload["result"]["isError"] is False
    assert "structuredContent" in success_payload["result"]
    assert "prompt_preview" not in str(success_payload)

    invalid = client.post(
        "/api/v1/mcp",
        headers=_auth_headers(user),
        json={
            "jsonrpc": "2.0",
            "id": "bad-args",
            "method": "tools/call",
            "params": {"name": "tool_registry_stats", "arguments": []},
        },
    )
    assert invalid.status_code == 200
    invalid_payload = invalid.json()
    assert invalid_payload["error"]["code"] == -32602
    assert invalid_payload["error"]["data"]["reason"] == "arguments must be an object"


def test_gateway_mcp_route_requires_chat_permission(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_audit_support = importlib.import_module("app.gateway_audit_support")
    monkeypatch.setattr(gateway_audit_support, "write_gateway_audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="audit-1",
        email="audit@local",
        role="audit_viewer",
        permissions=auth_module.permissions_for_role("audit_viewer"),
    )

    client = TestClient(gateway_main.app)
    response = client.post(
        "/api/v1/mcp",
        headers=_auth_headers(user),
        json={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_kb_analytics_dashboard_route_requires_kb_read_permission(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_api_support = importlib.import_module("app.kb_api_support")
    monkeypatch.setattr(kb_api_support, "audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="audit-1",
        email="audit@local",
        role="audit_viewer",
        permissions=auth_module.permissions_for_role("audit_viewer"),
    )

    client = TestClient(kb_main.app)
    response = client.get("/api/v1/kb/analytics/dashboard", headers=_auth_headers(user))

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_kb_operations_route_requires_kb_manage_permission(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_api_support = importlib.import_module("app.kb_api_support")
    monkeypatch.setattr(kb_api_support, "audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(kb_main.app)
    response = client.get("/api/v1/kb/analytics/operations", headers=_auth_headers(user))

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_kb_governance_route_requires_kb_manage_permission(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_api_support = importlib.import_module("app.kb_api_support")
    monkeypatch.setattr(kb_api_support, "audit_event", lambda **_kwargs: None)
    user = auth_module.AuthUser(
        user_id="member-1",
        email="member@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    client = TestClient(kb_main.app)
    response = client.get("/api/v1/kb/analytics/governance", headers=_auth_headers(user))

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"


def test_kb_metrics_route_refreshes_snapshot_and_exports_shared_metrics(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_system_routes = importlib.import_module("app.kb_system_routes")
    refresh_calls: list[bool] = []

    monkeypatch.setattr(kb_system_routes, "refresh_metrics_snapshot", lambda: refresh_calls.append(True))
    monkeypatch.setattr(kb_system_routes, "generate_latest", lambda: b"rag_kb_upload_requests_total 1.0\n")

    client = TestClient(kb_main.app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert refresh_calls == [True]
    assert "rag_kb_upload_requests_total 1.0" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_auth_permissions_are_derived_from_role_aliases() -> None:
    admin_permissions = auth_module.permissions_for_role("admin")
    member_permissions = auth_module.permissions_for_role("member")

    assert "kb.manage" in admin_permissions
    assert "audit.read" in admin_permissions
    assert "kb.write" in member_permissions
    assert "chat.use" in member_permissions


def test_decode_access_token_backfills_permissions_for_legacy_role(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    token = auth_module.jwt.encode(
        {
            "sub": "u-1",
            "email": "member@local",
            "role": "member",
            "iat": 100,
            "exp": 9999999999,
        },
        "test-secret",
        algorithm="HS256",
    )

    user = auth_module.decode_access_token(token)

    assert user.role == "kb_editor"
    assert "kb.write" in user.permissions
    assert "chat.use" in user.permissions


def test_merge_audit_event_lists_orders_by_created_at(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)

    merged = gateway_main._merge_audit_event_lists(
        [
            {"id": "1", "created_at": "2026-03-09T10:00:00+00:00", "service": "gateway"},
            {"id": "2", "created_at": "2026-03-09T08:00:00+00:00", "service": "gateway"},
        ],
        [
            {"id": "3", "created_at": "2026-03-09T09:00:00+00:00", "service": "kb-service"},
        ],
        limit=2,
        offset=0,
    )

    assert [item["id"] for item in merged] == ["1", "3"]


def test_idempotency_hash_is_stable_for_equivalent_payloads() -> None:
    left = build_request_hash(
        "chat.message.send",
        {"question": "expense approval", "scope": {"mode": "single", "document_ids": ["a", "b"]}},
    )
    right = build_request_hash(
        "chat.message.send",
        {"scope": {"document_ids": ["a", "b"], "mode": "single"}, "question": "expense approval"},
    )

    assert left == right
    assert normalize_idempotency_key("  key-123 \n") == "key-123"


def test_qdrant_point_id_is_stable_uuid() -> None:
    left = qdrant_point_id(unit_type="section", unit_id="11111111-1111-1111-1111-111111111111")
    right = qdrant_point_id(unit_type="section", unit_id="11111111-1111-1111-1111-111111111111")
    other = qdrant_point_id(unit_type="chunk", unit_id="11111111-1111-1111-1111-111111111111")

    assert left == right
    assert other != left
    assert len(left) == 36


def test_worker_retry_delay_uses_bounded_backoff() -> None:
    kb_worker = _load_kb_module("app.worker")

    assert kb_worker._retry_delay_seconds(1) == 5
    assert kb_worker._retry_delay_seconds(2) == 15
    assert kb_worker._retry_delay_seconds(9) == 300


def test_create_upload_request_accepts_image_types() -> None:
    _prioritize_sys_path(KB_SRC)
    kb_schemas = importlib.import_module("app.kb_schemas")

    payload = kb_schemas.CreateUploadRequest(
        base_id="base-1",
        file_name="evidence.png",
        file_type=".PNG",
        size_bytes=12,
        category="images",
    )

    assert payload.file_type == "png"


def test_create_upload_request_rejects_unknown_type() -> None:
    _prioritize_sys_path(KB_SRC)
    kb_schemas = importlib.import_module("app.kb_schemas")

    try:
        kb_schemas.CreateUploadRequest(
            base_id="base-1",
            file_name="sheet.xlsx",
            file_type="xlsx",
            size_bytes=12,
            category="images",
        )
    except ValidationError as exc:
        assert "unsupported kb file type" in str(exc)
    else:
        raise AssertionError("expected invalid file type to raise ValidationError")


def test_extract_visual_assets_supports_standalone_png(tmp_path: Path) -> None:
    _prioritize_sys_path(KB_SRC)
    kb_vision = importlib.import_module("app.vision")
    image_path = tmp_path / "sample.png"
    from PIL import Image

    Image.new("RGB", (32, 16), color=(255, 255, 255)).save(image_path)

    assets = kb_vision.extract_visual_assets(image_path, "png", max_assets=8)

    assert len(assets) == 1
    assert assets[0].source_kind == "standalone"
    assert assets[0].page_number == 1
    assert assets[0].mime_type in {"image/png", "image/jpeg"}


def test_worker_merge_ingest_stats_combines_visual_counts() -> None:
    kb_worker = _load_kb_module("app.worker")

    merged = kb_worker._merge_ingest_stats(
        {"section_count": 2, "chunk_count": 3, "section_preview": ["a"]},
        {
            "visual_asset_count": 4,
            "visual_ocr_section_count": 1,
            "visual_ocr_chunk_count": 2,
            "visual_provider": "local-http",
            "section_preview": ["a", "b"],
            "visual_ms": 12.5,
        },
    )

    assert merged["section_count"] == 3
    assert merged["chunk_count"] == 5
    assert merged["visual_asset_count"] == 4
    assert merged["visual_region_low_confidence_count"] == 0
    assert merged["visual_provider"] == "local-http"


def test_retrieve_merge_documents_include_visual_metadata() -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    results: dict[str, object] = {}
    signal_lists: dict[str, list[str]] = {}

    kb_retrieve._merge_documents(
        results,
        signal_lists,
        [
            Document(
                page_content="approval amount limit",
                metadata={
                    "unit_id": "chunk-1",
                    "document_id": "doc-1",
                    "document_title": "Policy",
                    "section_title": "Page 3 screenshot 1",
                    "source_kind": "visual_ocr",
                    "page_number": 3,
                    "asset_id": "asset-1",
                    "thumbnail_url": "/api/v1/kb/visual-assets/asset-1/thumbnail",
                    "char_range": "0-20",
                    "quote": "approval amount limit",
                    "raw_text": "approval amount limit",
                    "base_id": "base-1",
                    "signal_scores": {"fts": 0.88},
                    "evidence_path": {"fts_rank": 1},
                },
            )
        ],
        "fts",
    )

    item = results["chunk-1"]
    assert item.evidence_kind == "image_asset"
    assert item.page_number == 3
    assert item.asset_id == "asset-1"
    assert item.thumbnail_url == "/api/v1/kb/visual-assets/asset-1/thumbnail"


def test_retrieve_merge_documents_marks_visual_region_evidence() -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    results: dict[str, object] = {}
    signal_lists: dict[str, list[str]] = {}

    kb_retrieve._merge_documents(
        results,
        signal_lists,
        [
            Document(
                page_content="region: terminal config\nset FOO=bar",
                metadata={
                    "unit_id": "chunk-region-1",
                    "document_id": "doc-1",
                    "document_title": "Runbook",
                    "section_title": "Page 2 terminal config",
                    "region_label": "terminal config",
                    "source_kind": "visual_region",
                    "page_number": 2,
                    "asset_id": "asset-2",
                    "thumbnail_url": "/api/v1/kb/visual-assets/asset-2/thumbnail",
                    "bbox": [0.1, 0.2, 0.9, 0.7],
                    "confidence": 0.72,
                    "char_range": "0-30",
                    "quote": "set FOO=bar",
                    "raw_text": "region: terminal config\nset FOO=bar",
                    "base_id": "base-1",
                    "signal_scores": {"fts": 0.91},
                    "evidence_path": {"fts_rank": 1},
                },
            )
        ],
        "fts",
    )

    item = results["chunk-region-1"]
    assert item.evidence_kind == "visual_region"
    assert item.source_kind == "visual_region"
    assert item.region_label == "terminal config"
    assert item.bbox == [0.1, 0.2, 0.9, 0.7]
    assert item.confidence == 0.72


def test_list_visual_asset_regions_parses_layout_and_region_text(monkeypatch) -> None:
    kb_store = _load_kb_module("app.kb_resource_store")
    user = auth_module.AuthUser(user_id="owner-1", email="owner@local", role="kb_editor", permissions=auth_module.permissions_for_role("kb_editor"))

    monkeypatch.setattr(
        kb_store,
        "load_visual_asset",
        lambda asset_id, **kwargs: {"id": asset_id, "document_id": "doc-1", "page_number": 3},
    )

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            if "FROM kb_visual_asset_regions" in query:
                self._rows = []
            else:
                self._rows = [
                    {
                        "region_id": "section-1",
                        "title": "Page 3 terminal config",
                        "summary": "",
                        "text": "layout: terminal, config\nregion: terminal config\nset FOO=bar\nset BAZ=qux",
                        "page_number": 3,
                        "asset_id": "asset-1",
                        "section_index": 6,
                    }
                ]

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_store.db, "connect", lambda: _Connection())

    items = kb_store.list_visual_asset_regions("asset-1", user=user)

    assert len(items) == 1
    assert items[0]["region_label"] == "terminal config"
    assert items[0]["layout_hints"] == ["terminal", "config"]
    assert items[0]["ocr_text"] == "set FOO=bar\nset BAZ=qux"
    assert items[0]["thumbnail_url"] == "/api/v1/kb/visual-assets/asset-1/thumbnail"
    assert items[0]["bbox"] == []
    assert items[0]["confidence"] is None


def test_list_visual_asset_regions_prefers_stored_region_metadata(monkeypatch) -> None:
    kb_store = _load_kb_module("app.kb_resource_store")
    user = auth_module.AuthUser(user_id="owner-1", email="owner@local", role="kb_editor", permissions=auth_module.permissions_for_role("kb_editor"))

    monkeypatch.setattr(
        kb_store,
        "load_visual_asset",
        lambda asset_id, **kwargs: {"id": asset_id, "document_id": "doc-1", "page_number": 5},
    )

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            if "FROM kb_visual_asset_regions" in query:
                self._rows = [
                    {
                        "region_id": "region-1",
                        "asset_id": "asset-9",
                        "document_id": "doc-1",
                        "region_index": 1,
                        "page_number": 5,
                        "region_label": "red box config",
                        "layout_hints_json": ["terminal", "highlight"],
                        "bbox_json": [0.1, 0.2, 0.8, 0.6],
                        "confidence": 0.91,
                        "summary": "需要修改环境变量配置。",
                        "ocr_text": "export FOO=bar",
                    }
                ]
            else:
                raise AssertionError("fallback query should not run when stored region rows exist")

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_store.db, "connect", lambda: _Connection())

    items = kb_store.list_visual_asset_regions("asset-9", user=user)

    assert len(items) == 1
    assert items[0]["region_label"] == "red box config"
    assert items[0]["layout_hints"] == ["terminal", "highlight"]
    assert items[0]["bbox"] == [0.1, 0.2, 0.8, 0.6]
    assert items[0]["confidence"] == 0.91


def test_resolve_document_ids_defaults_to_current_active_effective_versions(monkeypatch) -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    executed_queries: list[str] = []

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            executed_queries.append(query)
            self._rows = [{"id": "doc-current"}]

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_retrieve.db, "connect", lambda: _Connection())

    resolved = kb_retrieve._resolve_document_ids(base_id="base-1", document_ids=[])

    assert resolved == ["doc-current"]
    assert len(executed_queries) == 1
    assert "version_status = 'active'" in executed_queries[0]
    assert "is_current_version = TRUE" in executed_queries[0]
    assert "effective_from IS NULL OR effective_from <= NOW()" in executed_queries[0]


def test_resolve_document_ids_keeps_explicit_version_selection(monkeypatch) -> None:
    kb_retrieve = _load_kb_module("app.retrieve")
    executed_queries: list[str] = []

    class _Cursor:
        def __init__(self) -> None:
            self._rows = []

        def execute(self, query, params=None):
            executed_queries.append(query)
            self._rows = [{"id": "doc-legacy"}]

        def fetchall(self):
            return list(self._rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_retrieve.db, "connect", lambda: _Connection())

    resolved = kb_retrieve._resolve_document_ids(base_id="base-1", document_ids=["doc-legacy"])

    assert resolved == ["doc-legacy"]
    assert len(executed_queries) == 1
    assert "id = ANY" in executed_queries[0]
    assert "version_status = 'active'" not in executed_queries[0]


def test_create_upload_request_normalizes_version_metadata() -> None:
    kb_schemas = _load_kb_module("app.kb_schemas")

    payload = kb_schemas.CreateUploadRequest(
        base_id="base-1",
        file_name="policy.pdf",
        file_type=".PDF",
        size_bytes=1024,
        category="policy",
        version_family_key=" expense-policy ",
        version_label=" 2026-Q1 ",
        version_number=3,
        version_status=" Active ",
        is_current_version=True,
        supersedes_document_id=" doc-old ",
    )

    assert payload.file_type == "pdf"
    assert payload.version_family_key == "expense-policy"
    assert payload.version_label == "2026-Q1"
    assert payload.version_status == "active"
    assert payload.supersedes_document_id == "doc-old"


def test_update_document_request_rejects_non_active_current_version() -> None:
    kb_schemas = _load_kb_module("app.kb_schemas")

    try:
        kb_schemas.UpdateDocumentRequest(version_status="archived", is_current_version=True)
    except ValidationError as exc:
        assert "current version must use active status" in str(exc)
    else:
        raise AssertionError("expected invalid current version status to raise ValidationError")


def test_update_document_request_normalizes_review_fields() -> None:
    kb_schemas = _load_kb_module("app.kb_schemas")

    payload = kb_schemas.UpdateDocumentRequest(
        owner_user_id=" owner-1 ",
        review_status=" APPROVED ",
        reviewer_note="  ship it  ",
    )

    assert payload.owner_user_id == "owner-1"
    assert payload.review_status == "approved"
    assert payload.reviewer_note == "ship it"


def test_batch_update_documents_request_normalizes_ids_and_patch() -> None:
    kb_schemas = _load_kb_module("app.kb_schemas")

    payload = kb_schemas.BatchUpdateDocumentsRequest(
        document_ids=[" doc-1 ", "doc-1", "doc-2 "],
        task_id=" task-1 ",
        retry_of_task_id=" task-0 ",
        patch=kb_schemas.UpdateDocumentRequest(review_status=" APPROVED ", reviewer_note=" ok "),
    )

    assert payload.document_ids == ["doc-1", "doc-2"]
    assert payload.task_id == "task-1"
    assert payload.retry_of_task_id == "task-0"
    assert payload.patch.review_status == "approved"
    assert payload.patch.reviewer_note == "ok"


def test_batch_update_documents_request_rejects_empty_patch() -> None:
    kb_schemas = _load_kb_module("app.kb_schemas")

    try:
        kb_schemas.BatchUpdateDocumentsRequest(document_ids=["doc-1"], patch=kb_schemas.UpdateDocumentRequest())
    except ValidationError as exc:
        assert "patch must contain at least one field" in str(exc)
    else:
        raise AssertionError("expected empty patch to raise ValidationError")


def test_knowledge_batch_dry_run_builds_sanitized_summary() -> None:
    kb_batch = _load_kb_module("app.kb_batch_dry_run")
    secret_sentence = "The payroll password is swordfish and should stay private."
    full_doc_id = r"C:\secret\finance\doc-1"
    full_path = r"C:\secret\finance\expense-policy.txt"

    payload = kb_batch.build_knowledge_batch_dry_run_payload(
        {
            "documents": [
                {
                    "doc_id": f" {full_doc_id} ",
                    "file_name": full_path,
                    "content": "Overview\n" + secret_sentence + "\n" + ("approval rule " * 120),
                },
                {
                    "document_id": "doc-2",
                    "file_name": "/private/legal/handbook.txt",
                    "content": "Rules\n" + ("travel limit " * 90),
                },
            ]
        }
    )

    assert payload["dry_run"] is True
    assert payload["document_count"] == 2
    assert payload["total_chunks"] == sum(item["chunk_count"] for item in payload["documents"])
    assert payload["total_content_chars"] == sum(item["content_chars"] for item in payload["documents"])
    assert payload["documents"][0]["doc_id"] == "doc-1"
    assert payload["documents"][0]["file_name"] == "expense-policy.txt"
    assert payload["documents"][0]["chunk_count"] >= 2
    assert payload["documents"][1]["file_name"] == "handbook.txt"
    assert payload["documents"][1]["section_count"] >= 1
    assert payload["documents"][0]["sections"][0]["chunk_count"] >= 1
    response_text = json.dumps(payload, ensure_ascii=False)
    assert secret_sentence not in response_text
    assert full_doc_id not in response_text
    assert full_path not in response_text
    assert "/private/legal" not in response_text
    assert "chunk_text" not in response_text
    assert "embedding" not in response_text


def test_knowledge_batch_dry_run_route_rejects_invalid_payloads(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_batch_routes = importlib.import_module("app.kb_batch_dry_run_routes")
    monkeypatch.setattr(kb_batch_routes, "require_kb_permission", lambda *args, **kwargs: None)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)
    too_many_documents = [{"doc_id": f"doc-{index}", "content": "x"} for index in range(21)]
    oversized_documents = [{"doc_id": "large", "content": "x" * 300_001}]
    cases = [
        ({}, "knowledge_batch_documents_required"),
        ([], "knowledge_batch_payload_invalid"),
        ({"documents": "bad"}, "knowledge_batch_documents_required"),
        ({"documents": []}, "knowledge_batch_documents_required"),
        ({"documents": ["bad"]}, "knowledge_batch_document_invalid"),
        ({"documents": [{"doc_id": "blank", "content": "  "}]}, "knowledge_batch_content_required"),
        ({"documents": [{"doc_id": "path", "content": "x", "source_path": "/tmp/source.txt"}]}, "knowledge_batch_field_not_allowed"),
        ({"documents": too_many_documents}, "knowledge_batch_too_many_documents"),
        ({"documents": oversized_documents}, "knowledge_batch_content_too_large"),
    ]

    for body, expected_code in cases:
        response = client.post("/api/knowledge_base/batch-dry-run", json=body, headers=_auth_headers(user))
        assert response.status_code == 400
        assert response.json()["code"] == expected_code


def test_knowledge_batch_dry_run_route_requires_write_permission() -> None:
    kb_main = _load_kb_module("app.main")
    user = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/batch-dry-run",
        json={"documents": [{"doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_knowledge_batch_dry_run_route_returns_summary_without_raw_content(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_batch_routes = importlib.import_module("app.kb_batch_dry_run_routes")
    monkeypatch.setattr(kb_batch_routes, "require_kb_permission", lambda *args, **kwargs: None)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/batch-dry-run",
        json={
            "documents": [
                {
                    "doc_id": "doc-policy",
                    "file_name": r"D:\company\restricted\policy.txt",
                    "content": "Policy\nSensitive reimbursement sentence.\n" + ("finance approval " * 80),
                }
            ]
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_count"] == 1
    assert payload["documents"][0]["doc_id"] == "doc-policy"
    assert payload["documents"][0]["file_name"] == "policy.txt"
    assert payload["documents"][0]["chunk_count"] >= 1
    response_text = response.text
    assert "Sensitive reimbursement sentence" not in response_text
    assert "D:\\company\\restricted" not in response_text
    assert "chunk_text" not in response_text
    assert "embedding" not in response_text


def test_gateway_knowledge_batch_dry_run_uses_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(gateway_main.app)

    allowed = client.post(
        "/api/knowledge_base/batch-dry-run",
        json={"documents": [{"doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )
    blocked = client.post(
        "/api/knowledge_base/delete",
        json={},
        headers=_auth_headers(user),
    )

    assert allowed.status_code == 200
    assert allowed.json()["service_path"] == "/api/knowledge_base/batch-dry-run"
    assert calls == [
        {
            "service_base_url": gateway_admin_routes.runtime_settings.kb_service_url,
            "service_path": "/api/knowledge_base/batch-dry-run",
            "request_path": "/api/knowledge_base/batch-dry-run",
        }
    ]
    assert blocked.status_code == 404


def test_knowledge_auto_index_preview_summarizes_fixed_inbox_without_raw_content(tmp_path: Path, monkeypatch) -> None:
    kb_auto_index = _load_kb_module("app.kb_auto_index")
    data_root = tmp_path / "data"
    inbox = data_root / "knowledge_base" / "inbox"
    inbox.mkdir(parents=True)
    secret_sentence = "The auto index secret should not be returned."
    (inbox / "runbook.md").write_text("# Runbook\n" + secret_sentence + "\n" + ("approval flow " * 90), encoding="utf-8")
    (inbox / "notes.txt").write_text("\ufeffNotes\n" + ("travel policy " * 80), encoding="utf-8")
    (inbox / "manual.pdf").write_bytes(b"%PDF-1.4")
    (inbox / "bad.txt").write_bytes(b"\xff\xfe\x00")
    (inbox / "nested").mkdir()
    monkeypatch.setattr(kb_auto_index, "BLOB_ROOT", data_root)

    payload = kb_auto_index.build_knowledge_auto_index_preview_payload()

    assert payload["dry_run"] is True
    assert payload["source"] == "fixed_inbox"
    assert payload["inbox"] == "knowledge_base/inbox"
    assert payload["exists"] is True
    assert payload["document_count"] == 2
    assert payload["skipped_count"] == 3
    assert payload["chunk_count"] == sum(item["chunk_count"] for item in payload["documents"])
    assert payload["char_count"] == sum(item["content_chars"] for item in payload["documents"])
    assert [item["file_name"] for item in payload["documents"]] == ["notes.txt", "runbook.md"]
    assert {item["reason"] for item in payload["skipped"]} == {"unsupported_extension", "utf8_decode_failed", "directory_ignored"}
    assert payload["documents"][0]["sections"][0]["chunk_count"] >= 1
    response_text = json.dumps(payload, ensure_ascii=False)
    assert secret_sentence not in response_text
    assert str(tmp_path) not in response_text
    assert "chunk_text" not in response_text
    assert "embedding" not in response_text


def test_knowledge_auto_index_preview_reports_missing_inbox_without_path_leak(tmp_path: Path, monkeypatch) -> None:
    kb_auto_index = _load_kb_module("app.kb_auto_index")
    data_root = tmp_path / "data"
    monkeypatch.setattr(kb_auto_index, "BLOB_ROOT", data_root)

    payload = kb_auto_index.build_knowledge_auto_index_preview_payload()

    assert payload == {
        "dry_run": True,
        "source": "fixed_inbox",
        "inbox": "knowledge_base/inbox",
        "exists": False,
        "document_count": 0,
        "skipped_count": 0,
        "chunk_count": 0,
        "char_count": 0,
        "documents": [],
        "skipped": [],
        "limits": {
            "max_files": kb_auto_index.AUTO_INDEX_MAX_FILES,
            "max_file_bytes": kb_auto_index.AUTO_INDEX_MAX_FILE_BYTES,
            "max_total_chars": kb_auto_index.AUTO_INDEX_MAX_TOTAL_CHARS,
            "allowed_extensions": sorted(kb_auto_index.AUTO_INDEX_ALLOWED_EXTENSIONS),
        },
    }
    assert str(tmp_path) not in json.dumps(payload, ensure_ascii=False)


def test_knowledge_auto_index_preview_route_uses_fixed_inbox_and_write_permission(tmp_path: Path, monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_auto_index = importlib.import_module("app.kb_auto_index")
    data_root = tmp_path / "data"
    inbox = data_root / "knowledge_base" / "inbox"
    inbox.mkdir(parents=True)
    secret_sentence = "The API auto index secret should not be returned."
    (inbox / "runbook.md").write_text("# Runbook\n" + secret_sentence + "\n" + ("approval flow " * 90), encoding="utf-8")
    monkeypatch.setattr(kb_auto_index, "BLOB_ROOT", data_root)
    editor = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    viewer = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(kb_main.app)

    allowed = client.get("/api/knowledge_base/auto-index/preview", headers=_auth_headers(editor))
    forbidden = client.get("/api/knowledge_base/auto-index/preview", headers=_auth_headers(viewer))

    assert allowed.status_code == 200
    assert allowed.json()["source"] == "fixed_inbox"
    assert allowed.json()["documents"][0]["file_name"] == "runbook.md"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "permission_denied"
    assert secret_sentence not in allowed.text
    assert str(tmp_path) not in allowed.text
    assert "chunk_text" not in allowed.text
    assert "embedding" not in allowed.text


def test_gateway_knowledge_auto_index_preview_uses_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(gateway_main.app)

    allowed = client.get("/api/knowledge_base/auto-index/preview", headers=_auth_headers(user))
    blocked = client.get("/api/knowledge_base/auto-index/preview/delete", headers=_auth_headers(user))

    assert allowed.status_code == 200
    assert allowed.json()["service_path"] == "/api/knowledge_base/auto-index/preview"
    assert calls == [
        {
            "service_base_url": gateway_admin_routes.runtime_settings.kb_service_url,
            "service_path": "/api/knowledge_base/auto-index/preview",
            "request_path": "/api/knowledge_base/auto-index/preview",
        }
    ]
    assert blocked.status_code == 404


def test_knowledge_batch_ingest_route_writes_inline_documents_without_raw_content(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_batch_ingest = importlib.import_module("app.kb_batch_ingest")
    kb_batch_ingest_routes = importlib.import_module("app.kb_batch_ingest_routes")
    executed: list[tuple[str, object]] = []

    class _Cursor:
        def execute(self, query, params=None):
            executed.append((str(query), params))

        def executemany(self, query, params_seq):
            executed.append((str(query), list(params_seq)))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            executed.append(("COMMIT", None))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_batch_ingest_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_batch_ingest, "ensure_vector_store", lambda: {"collection": "kb-evidence"})
    monkeypatch.setattr(kb_batch_ingest, "ensure_base_exists", lambda *args, **kwargs: {"id": "base-1"})
    monkeypatch.setattr(kb_batch_ingest, "index_document_sections", lambda document_id: {"indexed": 1})
    monkeypatch.setattr(kb_batch_ingest, "index_document_chunks", lambda document_id: {"indexed": 2})
    monkeypatch.setattr(kb_batch_ingest.db, "connect", lambda: _Connection())
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    secret_sentence = "The import secret should not be returned."
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/batch-ingest",
        json={
            "documents": [
                {
                    "base_id": "base-1",
                    "doc_id": r"C:\secret\finance\doc-1",
                    "file_name": r"C:\secret\finance\expense-policy.txt",
                    "content": "Overview\n" + secret_sentence + "\n" + ("approval rule " * 120),
                },
                {
                    "base_id": "base-1",
                    "document_id": "doc-2",
                    "file_name": "/private/legal/handbook.txt",
                    "content": "Rules\n" + ("travel limit " * 90),
                },
            ]
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["document_count"] == 2
    assert payload["succeeded_documents"] == 2
    assert payload["failed_documents"] == 0
    assert payload["chunk_count"] >= 2
    assert payload["indexed_chunks"] == 4
    assert payload["documents"][0]["input_doc_id"] == "doc-1"
    assert payload["documents"][0]["file_name"] == "expense-policy.txt"
    assert payload["documents"][1]["file_name"] == "handbook.txt"
    response_text = response.text
    assert secret_sentence not in response_text
    assert "C:\\secret\\finance" not in response_text
    assert "/private/legal" not in response_text
    assert "chunk_text" not in response_text
    assert "embedding" not in response_text
    assert any("INSERT INTO kb_documents" in query for query, _params in executed)
    assert any("INSERT INTO kb_sections" in query for query, _params in executed)
    assert any("INSERT INTO kb_chunks" in query for query, _params in executed)


def test_knowledge_batch_ingest_route_rejects_invalid_payloads(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_batch_ingest_routes = importlib.import_module("app.kb_batch_ingest_routes")
    monkeypatch.setattr(kb_batch_ingest_routes, "require_kb_permission", lambda *args, **kwargs: None)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)
    cases = [
        ([], "knowledge_batch_payload_invalid"),
        ({"documents": [{"base_id": "", "content": "x"}]}, "knowledge_batch_base_required"),
        ({"documents": [{"base_id": "base-1", "content": "x", "source_file": r"C:\secret\doc.txt"}]}, "knowledge_batch_field_not_allowed"),
        ({"documents": [{"base_id": "base-1", "content": "x", "embedding": [0.1]}]}, "knowledge_batch_field_not_allowed"),
    ]

    for body, expected_code in cases:
        response = client.post("/api/knowledge_base/batch-ingest", json=body, headers=_auth_headers(user))
        assert response.status_code == 400
        assert response.json()["code"] == expected_code


def test_knowledge_batch_ingest_route_requires_write_permission() -> None:
    kb_main = _load_kb_module("app.main")
    user = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/batch-ingest",
        json={"documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_knowledge_batch_ingest_route_reports_vector_runtime_unavailable(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_batch_ingest = importlib.import_module("app.kb_batch_ingest")
    kb_batch_ingest_routes = importlib.import_module("app.kb_batch_ingest_routes")
    monkeypatch.setattr(kb_batch_ingest_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_batch_ingest, "ensure_vector_store", lambda: (_ for _ in ()).throw(RuntimeError("qdrant down")))
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/batch-ingest",
        json={"documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "knowledge_batch_vector_unavailable"


def test_gateway_knowledge_batch_ingest_uses_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(gateway_main.app)

    allowed = client.post(
        "/api/knowledge_base/batch-ingest",
        json={"documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )
    blocked = client.post(
        "/api/knowledge_base/delete",
        json={},
        headers=_auth_headers(user),
    )

    assert allowed.status_code == 200
    assert allowed.json()["service_path"] == "/api/knowledge_base/batch-ingest"
    assert calls == [
        {
            "service_base_url": gateway_admin_routes.runtime_settings.kb_service_url,
            "service_path": "/api/knowledge_base/batch-ingest",
            "request_path": "/api/knowledge_base/batch-ingest",
        }
    ]
    assert blocked.status_code == 404


def test_knowledge_rebuild_route_reindexes_existing_units_without_path_access(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_rebuild = importlib.import_module("app.kb_rebuild")
    kb_rebuild_routes = importlib.import_module("app.kb_rebuild_routes")
    executed: list[tuple[str, object]] = []

    class _Cursor:
        def execute(self, query, params=None):
            executed.append((str(query), params))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            executed.append(("COMMIT", None))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    audit_events: list[dict[str, object]] = []
    monkeypatch.setattr(kb_rebuild_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        kb_rebuild,
        "load_document",
        lambda doc_id, **kwargs: {
            "id": doc_id,
            "version_label": "v1",
            "section_count": 2,
            "chunk_count": 3,
            "created_by": "editor-1",
        },
    )
    monkeypatch.setattr(kb_rebuild, "ensure_vector_store", lambda: {"collection": "kb-evidence"})
    monkeypatch.setattr(kb_rebuild, "delete_document_vectors", lambda document_id: executed.append(("DELETE_VECTORS", document_id)))
    monkeypatch.setattr(kb_rebuild, "index_document_sections", lambda document_id: {"rows": 2, "indexed": 2})
    monkeypatch.setattr(kb_rebuild, "index_document_chunks", lambda document_id: {"rows": 3, "indexed": 3})
    monkeypatch.setattr(kb_rebuild, "audit_event", lambda **kwargs: audit_events.append(dict(kwargs)))
    monkeypatch.setattr(kb_rebuild.db, "connect", lambda: _Connection())
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)
    signature = kb_rebuild.build_knowledge_rebuild_signature("doc-1")

    dry_run = client.post(
        "/api/knowledge_base/rebuild",
        json={"doc_id": "doc-1", "dry_run": True, "signature": signature},
        headers=_auth_headers(user),
    )
    rebuild = client.post(
        "/api/knowledge_base/rebuild",
        json={"doc_id": "doc-1", "dry_run": False, "signature": signature},
        headers=_auth_headers(user),
    )

    assert dry_run.status_code == 200
    assert dry_run.json() == {
        "doc_id": "doc-1",
        "version": "v1",
        "section_count": 2,
        "chunk_count": 3,
        "dry_run": True,
        "signature": signature,
    }
    assert rebuild.status_code == 200
    payload = rebuild.json()
    assert payload["doc_id"] == "doc-1"
    assert payload["dry_run"] is False
    assert payload["indexed_sections"] == 2
    assert payload["indexed_chunks"] == 3
    assert "source_path" not in rebuild.text
    assert "storage_path" not in rebuild.text
    assert ("DELETE_VECTORS", "doc-1") in executed
    assert any("UPDATE kb_documents" in query for query, _params in executed)
    assert any("INSERT INTO kb_document_events" in query for query, _params in executed)
    assert [event["action"] for event in audit_events] == ["kb.rebuild.dry_run", "kb.rebuild"]


def test_knowledge_rebuild_route_rejects_invalid_payloads(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_rebuild_routes = importlib.import_module("app.kb_rebuild_routes")
    monkeypatch.setattr(kb_rebuild_routes, "require_kb_permission", lambda *args, **kwargs: None)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)
    cases = [
        ({}, "knowledge_rebuild_doc_required"),
        ({"doc_id": "doc-1", "source_path": "/tmp/source.txt"}, "knowledge_rebuild_field_not_allowed"),
        ({"doc_id": "doc-1", "dry_run": False, "signature": "stale"}, "knowledge_rebuild_signature_mismatch"),
    ]

    for body, expected_code in cases:
        response = client.post("/api/knowledge_base/rebuild", json=body, headers=_auth_headers(user))
        assert response.status_code == 400
        assert response.json()["code"] == expected_code


def test_knowledge_rebuild_route_requires_write_permission() -> None:
    kb_main = _load_kb_module("app.main")
    user = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/knowledge_base/rebuild",
        json={"doc_id": "doc-1", "dry_run": True},
        headers=_auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_gateway_knowledge_rebuild_uses_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(gateway_main.app)

    allowed = client.post(
        "/api/knowledge_base/rebuild",
        json={"doc_id": "doc-1", "dry_run": True},
        headers=_auth_headers(user),
    )
    blocked = client.post(
        "/api/knowledge_base/rebuild/delete",
        json={},
        headers=_auth_headers(user),
    )

    assert allowed.status_code == 200
    assert allowed.json()["service_path"] == "/api/knowledge_base/rebuild"
    assert calls == [
        {
            "service_base_url": gateway_admin_routes.runtime_settings.kb_service_url,
            "service_path": "/api/knowledge_base/rebuild",
            "request_path": "/api/knowledge_base/rebuild",
        }
    ]
    assert blocked.status_code == 404


def test_knowledge_job_queue_enqueues_ingest_and_sanitizes_public_snapshot() -> None:
    kb_job_queue = _load_kb_module("app.kb_job_queue")
    job_ids = iter(["job-1"])
    queue = kb_job_queue.KnowledgeBaseJobQueue(max_jobs=5, job_id_factory=lambda: next(job_ids))
    calls: list[tuple[str, dict[str, object]]] = []
    secret_sentence = "The inline queue secret should not be returned."

    async def runner(mode: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((mode, payload))
        return {
            "success": True,
            "documents": [
                {
                    "document_id": "stored-doc-1",
                    "file_name": r"C:\secret\finance\expense-policy.txt",
                    "source_uri": "https://example.test/private/expense-policy.txt",
                    "storage_path": r"C:\secret\storage\doc.bin",
                    "storage_key": "private-storage-key",
                    "embedding": [0.1],
                    "content": secret_sentence,
                }
            ],
            "source_path": r"C:\secret\finance\expense-policy.txt",
            "chunk_text": secret_sentence,
        }

    async def scenario() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        created = await queue.enqueue(
            mode="ingest",
            payload={
                "documents": [
                    {
                        "base_id": "base-1",
                        "doc_id": r"C:\secret\finance\doc-1",
                        "file_name": r"C:\secret\finance\expense-policy.txt",
                        "category": "policy",
                        "content": "Overview\n" + secret_sentence + "\n" + ("approval rule " * 80),
                    }
                ]
            },
            runner=runner,
        )
        await queue.wait_idle()
        completed = await queue.get("job-1")
        summary = await queue.summary()
        assert completed is not None
        return created, completed, summary

    created, completed, summary = asyncio.run(scenario())

    assert created["job_id"] == "job-1"
    assert created["mode"] == "ingest"
    assert created["status"] == "queued"
    assert created["document_count"] == 1
    assert created["documents"][0] == {
        "index": 0,
        "doc_id": "doc-1",
        "file_name": "expense-policy.txt",
        "base_id": "base-1",
        "category": "policy",
        "content_chars": len("Overview\n" + secret_sentence + "\n" + ("approval rule " * 80)),
    }
    assert calls[0][0] == "ingest"
    assert calls[0][1]["documents"][0]["content"].startswith("Overview")
    assert completed["status"] == "completed"
    assert completed["result"]["documents"][0]["file_name"] == "expense-policy.txt"
    assert completed["result"]["documents"][0]["source_uri"] == "example.test"
    assert summary["counts"]["completed"] == 1
    assert summary["modes"]["ingest"] == 1
    public_text = json.dumps({"created": created, "completed": completed, "summary": summary}, ensure_ascii=False)
    assert secret_sentence not in public_text
    assert "C:\\secret" not in public_text
    assert "private/expense-policy" not in public_text
    assert "private-storage-key" not in public_text
    assert "chunk_text" not in public_text
    assert "embedding" not in public_text
    assert "storage_path" not in public_text
    assert "storage_key" not in public_text


def test_knowledge_job_queue_runs_jobs_serially_and_rejects_when_active_queue_is_full() -> None:
    kb_job_queue = _load_kb_module("app.kb_job_queue")
    job_ids = iter(["job-1", "job-2"])
    queue = kb_job_queue.KnowledgeBaseJobQueue(max_jobs=1, job_id_factory=lambda: next(job_ids))
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    async def runner(_mode: str, payload: dict[str, object]) -> dict[str, object]:
        doc_id = str(payload["documents"][0]["doc_id"])
        events.append(f"start:{doc_id}")
        if doc_id == "doc-1":
            first_started.set()
            await release_first.wait()
        events.append(f"finish:{doc_id}")
        return {"document_id": doc_id}

    async def scenario() -> tuple[dict[str, object], dict[str, object] | None]:
        await queue.enqueue(
            mode="ingest",
            payload={"documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
            runner=runner,
        )
        await first_started.wait()
        try:
            await queue.enqueue(
                mode="ingest",
                payload={"documents": [{"base_id": "base-1", "doc_id": "doc-2", "content": "hello"}]},
                runner=runner,
            )
        except kb_job_queue.KnowledgeJobQueueError as exc:
            error = {"code": exc.code, "detail": exc.detail}
        else:
            raise AssertionError("expected active full queue to reject enqueue")
        release_first.set()
        await queue.wait_idle()
        return error, await queue.get("job-1")

    error, completed = asyncio.run(scenario())

    assert error["code"] == "knowledge_job_queue_full"
    assert completed is not None
    assert completed["status"] == "completed"
    assert events == ["start:doc-1", "finish:doc-1"]


def test_knowledge_job_queue_serial_execution_keeps_second_job_queued_until_first_finishes() -> None:
    kb_job_queue = _load_kb_module("app.kb_job_queue")
    job_ids = iter(["job-1", "job-2"])
    queue = kb_job_queue.KnowledgeBaseJobQueue(max_jobs=3, job_id_factory=lambda: next(job_ids))
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    async def runner(_mode: str, payload: dict[str, object]) -> dict[str, object]:
        doc_id = str(payload["documents"][0]["doc_id"])
        events.append(f"start:{doc_id}")
        if doc_id == "doc-1":
            first_started.set()
            await release_first.wait()
        events.append(f"finish:{doc_id}")
        return {"document_id": doc_id}

    async def scenario() -> tuple[dict[str, object] | None, dict[str, object], dict[str, object]]:
        await queue.enqueue(
            mode="ingest",
            payload={"documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
            runner=runner,
        )
        await first_started.wait()
        await queue.enqueue(
            mode="ingest",
            payload={"documents": [{"base_id": "base-1", "doc_id": "doc-2", "content": "hello"}]},
            runner=runner,
        )
        second_while_first_runs = await queue.get("job-2")
        release_first.set()
        await queue.wait_idle()
        summary = await queue.summary()
        return second_while_first_runs, await queue.get("job-1") or {}, summary

    queued_second, first, summary = asyncio.run(scenario())

    assert queued_second is not None
    assert queued_second["status"] == "queued"
    assert first["status"] == "completed"
    assert summary["counts"]["completed"] == 2
    assert events == ["start:doc-1", "finish:doc-1", "start:doc-2", "finish:doc-2"]


def test_knowledge_job_queue_failed_job_hides_sensitive_error_detail() -> None:
    kb_job_queue = _load_kb_module("app.kb_job_queue")
    queue = kb_job_queue.KnowledgeBaseJobQueue(max_jobs=5, job_id_factory=lambda: "job-failed")
    secret_sentence = "The failed queue secret should not be returned."

    async def runner(_mode: str, _payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError(f"{secret_sentence} from C:\\secret\\finance\\doc.txt storage-key")

    async def scenario() -> dict[str, object]:
        await queue.enqueue(
            mode="ingest",
            payload={
                "documents": [
                    {
                        "base_id": "base-1",
                        "doc_id": r"C:\secret\finance\doc-1",
                        "file_name": r"C:\secret\finance\expense-policy.txt",
                        "content": secret_sentence,
                    }
                ]
            },
            runner=runner,
        )
        await queue.wait_idle()
        failed = await queue.get("job-failed")
        assert failed is not None
        return failed

    failed = asyncio.run(scenario())

    assert failed["status"] == "failed"
    assert failed["error"] == {"code": "RuntimeError", "detail": "knowledge job failed"}
    public_text = json.dumps(failed, ensure_ascii=False)
    assert secret_sentence not in public_text
    assert "C:\\secret" not in public_text
    assert "storage-key" not in public_text


def test_knowledge_job_queue_normalizes_rebuild_payload_and_rejects_invalid_mode() -> None:
    kb_job_queue = _load_kb_module("app.kb_job_queue")
    kb_rebuild = importlib.import_module("app.kb_rebuild")
    signature = kb_rebuild.build_knowledge_rebuild_signature("doc-1")

    payload, documents = kb_job_queue.normalize_knowledge_job_payload(
        "rebuild",
        {"doc_id": " doc-1 ", "dry_run": True, "signature": signature},
    )

    assert payload == {"doc_id": "doc-1", "dry_run": True, "signature": signature}
    assert documents == [{"index": 0, "doc_id": "doc-1", "dry_run": True, "signature": signature}]
    try:
        kb_job_queue.normalize_knowledge_job_payload("delete", {"doc_id": "doc-1"})
    except kb_job_queue.KnowledgeJobQueueError as exc:
        assert exc.code == "knowledge_job_mode_invalid"
    else:
        raise AssertionError("expected invalid job mode to raise")


def test_knowledge_jobs_api_enqueues_and_reports_queue_without_raw_content(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_job_queue = importlib.import_module("app.kb_job_queue")
    kb_job_queue_routes = importlib.import_module("app.kb_job_queue_routes")
    job_ids = iter(["job-api-1"])
    queue = kb_job_queue.KnowledgeBaseJobQueue(max_jobs=5, job_id_factory=lambda: next(job_ids))
    secret_sentence = "The api queue secret should not be returned."

    monkeypatch.setattr(kb_job_queue_routes, "require_kb_permission", lambda *args, **kwargs: None)
    kb_job_queue_routes.set_knowledge_job_queue(queue)

    def fake_build_result(mode: str, payload: dict[str, object], *, request, user) -> dict[str, object]:
        assert mode == "ingest"
        assert str(request.url.path) == "/api/knowledge_base/jobs"
        return {
            "success": True,
            "documents": [
                {
                    "document_id": "stored-doc-1",
                    "file_name": r"C:\secret\finance\expense-policy.txt",
                    "source_path": r"C:\secret\finance\expense-policy.txt",
                    "content": secret_sentence,
                    "embedding": [0.1],
                    "storage_key": "private-storage-key",
                }
            ],
            "chunk_text": secret_sentence,
        }

    monkeypatch.setattr(kb_job_queue_routes, "build_knowledge_job_result", fake_build_result)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    created = client.post(
        "/api/knowledge_base/jobs",
        json={
            "mode": "ingest",
            "documents": [
                {
                    "base_id": "base-1",
                    "doc_id": r"C:\secret\finance\doc-1",
                    "file_name": r"C:\secret\finance\expense-policy.txt",
                    "content": "Overview\n" + secret_sentence + "\n" + ("approval rule " * 80),
                }
            ],
        },
        headers=_auth_headers(user),
    )
    assert created.status_code == 200
    assert created.json()["job_id"] == "job-api-1"
    assert created.json()["status"] == "queued"
    assert created.json()["documents"][0]["file_name"] == "expense-policy.txt"

    asyncio.run(queue.wait_idle())
    fetched = client.get("/api/knowledge_base/jobs/job-api-1", headers=_auth_headers(user))
    status = client.get("/api/knowledge_base/status", headers=_auth_headers(user))

    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"
    assert fetched.json()["result"]["documents"][0]["file_name"] == "expense-policy.txt"
    assert status.status_code == 200
    assert status.json()["queue"]["counts"]["completed"] == 1
    response_text = fetched.text + status.text + created.text
    assert secret_sentence not in response_text
    assert "C:\\secret" not in response_text
    assert "private-storage-key" not in response_text
    assert "chunk_text" not in response_text
    assert "embedding" not in response_text
    assert "storage_key" not in response_text


def test_knowledge_jobs_api_rejects_invalid_payloads_and_requires_read_permission(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_job_queue = importlib.import_module("app.kb_job_queue")
    kb_job_queue_routes = importlib.import_module("app.kb_job_queue_routes")
    kb_job_queue_routes.set_knowledge_job_queue(kb_job_queue.KnowledgeBaseJobQueue(job_id_factory=lambda: "job-1"))
    monkeypatch.setattr(kb_job_queue_routes, "build_knowledge_job_result", lambda *args, **kwargs: {"success": True})
    editor = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    viewer = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(kb_main.app)

    invalid_mode = client.post(
        "/api/knowledge_base/jobs",
        json={"mode": "delete", "doc_id": "doc-1"},
        headers=_auth_headers(editor),
    )
    forbidden_create = client.post(
        "/api/knowledge_base/jobs",
        json={"mode": "ingest", "documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(viewer),
    )
    missing = client.get("/api/knowledge_base/jobs/missing", headers=_auth_headers(viewer))

    assert invalid_mode.status_code == 400
    assert invalid_mode.json()["code"] == "knowledge_job_mode_invalid"
    assert forbidden_create.status_code == 403
    assert forbidden_create.json()["code"] == "permission_denied"
    assert missing.status_code == 404
    assert missing.json()["code"] == "knowledge_job_not_found"


def test_gateway_knowledge_jobs_use_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(gateway_main.app)

    created = client.post(
        "/api/knowledge_base/jobs",
        json={"mode": "ingest", "documents": [{"base_id": "base-1", "doc_id": "doc-1", "content": "hello"}]},
        headers=_auth_headers(user),
    )
    fetched = client.get("/api/knowledge_base/jobs/job-1", headers=_auth_headers(user))
    status = client.get("/api/knowledge_base/status", headers=_auth_headers(user))
    blocked = client.get("/api/knowledge_base/jobs/job-1/delete", headers=_auth_headers(user))

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert status.status_code == 200
    assert blocked.status_code == 404
    assert [call["service_path"] for call in calls] == [
        "/api/knowledge_base/jobs",
        "/api/knowledge_base/jobs/job-1",
        "/api/knowledge_base/status",
    ]


def test_knowledge_index_route_returns_metadata_summary_without_path_or_content(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_index = importlib.import_module("app.kb_index")
    kb_index_routes = importlib.import_module("app.kb_index_routes")
    executed: list[tuple[str, object]] = []

    class _Cursor:
        def __init__(self):
            self._rows: list[dict[str, object]] = []
            self._row: dict[str, object] | None = None

        def execute(self, query, params=None):
            query_text = str(query)
            executed.append((query_text, params))
            if "COUNT(*) AS document_count" in query_text:
                self._row = {"document_count": 2, "chunk_count": 7}
                self._rows = []
                return
            self._row = None
            self._rows = [
                {
                    "document_id": "doc-1",
                    "base_id": "base-1",
                    "base_name": "Finance",
                    "file_name": r"C:\secret\finance\expense-policy.txt",
                    "file_type": "txt",
                    "status": "ready",
                    "query_ready": True,
                    "enhancement_status": "chunk_vectors_ready",
                    "section_count": 2,
                    "chunk_count": 7,
                    "stats_json": {
                        "category": "policy",
                        "raw_text": "Department owner and finance reviewer signatures are required.",
                        "embedding": [0.1, 0.2],
                    },
                    "source_type": "batch_ingest",
                    "source_uri": r"C:\secret\finance\expense-policy.txt",
                    "version_family_key": "doc-1",
                    "version_label": "v1",
                    "version_number": 1,
                    "version_status": "active",
                    "is_current_version": True,
                    "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
                }
            ]

        def fetchone(self):
            return self._row

        def fetchall(self):
            return self._rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Connection:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(kb_index_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_index, "check_vector_store", lambda: {"status": "ok"})
    monkeypatch.setattr(kb_index.db, "connect", lambda: _Connection())
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.get("/api/knowledge_base/index?limit=1", headers=_auth_headers(user))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["vector_memory_available"] is True
    assert payload["supports_index"] is True
    assert payload["source"] == "knowledge_base"
    assert payload["chunk_count"] == 7
    assert payload["document_count"] == 2
    assert payload["truncated"] is True
    assert payload["documents"] == [
        {
            "document_id": "doc-1",
            "base_id": "base-1",
            "base_name": "Finance",
            "file_name": "expense-policy.txt",
            "file_type": "txt",
            "status": "ready",
            "query_ready": True,
            "enhancement_status": "chunk_vectors_ready",
            "section_count": 2,
            "chunk_count": 7,
            "category": "policy",
            "source_type": "batch_ingest",
            "source_ref": "expense-policy.txt",
            "version_family_key": "doc-1",
            "version_label": "v1",
            "version_number": 1,
            "version_status": "active",
            "is_current_version": True,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        }
    ]
    assert "text_content" not in response.text
    assert "raw_text" not in response.text
    assert "embedding" not in response.text
    assert "storage_path" not in response.text
    assert "C:\\secret" not in response.text
    assert all("text_content" not in query for query, _params in executed)
    assert all("embedding" not in query.lower() for query, _params in executed)
    assert all("storage_path" not in query for query, _params in executed)


def test_knowledge_index_route_degrades_when_metadata_index_is_unsupported(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_index = importlib.import_module("app.kb_index")
    kb_index_routes = importlib.import_module("app.kb_index_routes")

    monkeypatch.setattr(kb_index_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_index, "check_vector_store", lambda: (_ for _ in ()).throw(RuntimeError("qdrant down")))
    monkeypatch.setattr(
        kb_index,
        "load_knowledge_index_counts",
        lambda **_kwargs: (_ for _ in ()).throw(kb_index.KnowledgeIndexUnsupported()),
    )
    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.get("/api/knowledge_base/index", headers=_auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "vector_memory_available": False,
        "supports_index": False,
        "source": "knowledge_base",
        "chunk_count": 0,
        "document_count": 0,
        "documents": [],
        "truncated": False,
    }


def test_knowledge_index_route_requires_read_permission() -> None:
    kb_main = _load_kb_module("app.main")
    user = auth_module.AuthUser(
        user_id="audit-1",
        email="audit@local",
        role="audit_viewer",
        permissions=auth_module.permissions_for_role("audit_viewer"),
    )
    client = TestClient(kb_main.app)

    response = client.get("/api/knowledge_base/index", headers=_auth_headers(user))

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_gateway_knowledge_index_uses_exact_proxy(monkeypatch) -> None:
    gateway_main = _load_gateway_main(monkeypatch)
    gateway_admin_routes = importlib.import_module("app.gateway_admin_routes")
    calls: list[dict[str, str]] = []

    async def fake_proxy_request(request, *, service_base_url: str, service_path: str):
        calls.append({"service_base_url": service_base_url, "service_path": service_path, "request_path": request.url.path})
        return JSONResponse({"proxied": True, "service_path": service_path})

    monkeypatch.setattr(gateway_admin_routes, "proxy_request", fake_proxy_request)
    user = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_viewer",
        permissions=auth_module.permissions_for_role("kb_viewer"),
    )
    client = TestClient(gateway_main.app)

    allowed = client.get("/api/knowledge_base/index?limit=10", headers=_auth_headers(user))
    blocked = client.get("/api/knowledge_base/index/delete", headers=_auth_headers(user))

    assert allowed.status_code == 200
    assert allowed.json()["service_path"] == "/api/knowledge_base/index"
    assert calls == [
        {
            "service_base_url": gateway_admin_routes.runtime_settings.kb_service_url,
            "service_path": "/api/knowledge_base/index",
            "request_path": "/api/knowledge_base/index",
        }
    ]
    assert blocked.status_code == 404


def test_retrieve_debug_route_serializes_evidence_and_debug_meta(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_query_routes = importlib.import_module("app.kb_query_routes")
    from shared.retrieval import EvidenceBlock, EvidencePath, RetrievalResult, RetrievalStats

    captured: dict[str, object] = {}

    def fake_retrieve_kb_result(*, base_id: str, question: str, document_ids: list[str], limit: int):
        captured.update(
            {
                "base_id": base_id,
                "question": question,
                "document_ids": document_ids,
                "limit": limit,
            }
        )
        return RetrievalResult(
            items=[
                EvidenceBlock(
                    unit_id="unit-approval",
                    document_id="doc-policy",
                    document_title="Expense Policy",
                    section_title="Approval",
                    quote="Department owner and finance reviewer signatures are required.",
                    raw_text="Department owner and finance reviewer signatures are required before reimbursement.",
                    signal_scores={"structure": 1.0, "fts": 0.82, "vector": 0.61, "rerank": 9.4},
                    evidence_path=EvidencePath(structure_hit=True, fts_rank=1, vector_rank=2, final_rank=1, final_score=0.91),
                )
            ],
            stats=RetrievalStats(
                original_query="Who signs expense approvals?",
                focus_query="expense approvals signs",
                structure_candidates=1,
                fts_candidates=2,
                vector_candidates=3,
                fused_candidates=3,
                reranked_candidates=1,
                selected_candidates=1,
                retrieval_ms=8.5,
                rerank_applied=True,
                rerank_provider="heuristic",
            ),
        )

    monkeypatch.setattr(kb_query_routes, "require_kb_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_query_routes, "ensure_base_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(kb_query_routes, "retrieve_kb_result", fake_retrieve_kb_result)

    user = auth_module.AuthUser(
        user_id="viewer-1",
        email="viewer@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/v1/kb/retrieve/debug",
        json={
            "base_id": "base-1",
            "question": "Who signs expense approvals?",
            "document_ids": ["doc-policy"],
            "limit": 5,
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured == {
        "base_id": "base-1",
        "question": "Who signs expense approvals?",
        "document_ids": ["doc-policy"],
        "limit": 5,
    }
    assert payload["query"] == "Who signs expense approvals?"
    assert payload["trace_id"].startswith("kb-")
    assert payload["retrieval"]["selected_candidates"] == 1
    assert payload["retrieval"]["rerank_provider"] == "heuristic"
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["corpus_id"] == "kb:base-1"
    assert item["service_type"] == "kb"
    assert item["document_title"] == "Expense Policy"
    assert item["section_title"] == "Approval"
    assert item["unit_id"] == "unit-approval"
    assert item["quote"].startswith("Department owner")
    assert item["raw_text"].startswith("Department owner")
    assert item["signal_scores"]["fts"] == 0.82
    assert item["evidence_path"]["fts_rank"] == 1
    assert item["debug"]["rank"] == 1
    assert item["debug"]["score"] == 0.91
    assert item["debug"]["rerank_score"] == 9.4
    assert item["debug"]["signal_scores"]["vector"] == 0.61


def test_batch_update_documents_route_returns_partial_results(monkeypatch) -> None:
    kb_main = _load_kb_module("app.main")
    kb_base_routes = importlib.import_module("app.kb_base_routes")
    audit_calls: list[dict[str, object]] = []

    def fake_apply_document_update(document_id: str, payload, *, request, user):
        assert payload.review_status == "approved"
        if document_id == "doc-2":
            raise HTTPException(status_code=400, detail={"detail": "document locked", "code": "document_locked"})
        return {"id": document_id, "file_name": f"{document_id}.pdf"}

    monkeypatch.setattr(kb_base_routes, "_apply_document_update", fake_apply_document_update)
    monkeypatch.setattr(kb_base_routes, "audit_event", lambda **kwargs: audit_calls.append(kwargs))

    user = auth_module.AuthUser(
        user_id="editor-1",
        email="editor@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )
    client = TestClient(kb_main.app)

    response = client.post(
        "/api/v1/kb/documents/batch-update",
        json={
            "document_ids": ["doc-1", "doc-2"],
            "patch": {"review_status": "approved"},
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"]
    assert payload["status"] == "completed"
    assert payload["summary"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert payload["items"][0]["ok"] is True
    assert payload["items"][0]["document"]["id"] == "doc-1"
    assert payload["items"][1]["ok"] is False
    assert payload["items"][1]["code"] == "document_locked"
    assert payload["items"][1]["status_code"] == 400
    assert audit_calls[-1]["action"] == "kb.document.batch_update"
    assert audit_calls[-1]["outcome"] == "partial_success"
    assert audit_calls[-1]["resource_id"] == payload["task_id"]
    assert audit_calls[-1]["details"]["task_id"] == payload["task_id"]
    assert audit_calls[-1]["details"]["patch"] == {"review_status": "approved"}
    assert audit_calls[-1]["details"]["success_document_ids"] == ["doc-1"]
    assert audit_calls[-1]["details"]["failed_items"][0]["document_id"] == "doc-2"
    assert audit_calls[-1]["details"]["failed_items"][0]["code"] == "document_locked"


def test_governance_batch_events_payload_filters_personal_and_action(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    captured: dict[str, object] = {}
    user = auth_module.AuthUser(
        user_id="owner-1",
        email="owner@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    def fake_list_audit_events(**kwargs):
        captured.update(kwargs)
        return [{"id": "evt-1", "action": "kb.document.batch_update", "details": {"failed": 1}}]

    monkeypatch.setattr(kb_analytics, "list_audit_events", fake_list_audit_events)

    payload = kb_analytics._governance_batch_events_payload(user, view="personal", limit=6)

    assert payload["view"] == "personal"
    assert payload["limit"] == 6
    assert payload["items"][0]["id"] == "evt-1"
    assert captured["actor_user_id"] == "owner-1"
    assert captured["resource_type"] == "document_batch"
    assert captured["action"] == "kb.document.batch_update"


def test_governance_batch_event_detail_payload_includes_retry_timeline(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="owner-1",
        email="owner@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    def fake_list_audit_events(**kwargs):
        resource_id = kwargs.get("resource_id")
        if resource_id == "task-2":
            return [
                {
                    "id": "evt-2",
                    "resource_id": "task-2",
                    "action": "kb.document.batch_update",
                    "created_at": "2026-03-20T09:00:00+00:00",
                    "details": {"task_id": "task-2", "retry_of_task_id": "task-1", "failed": 0},
                }
            ]
        return [
            {
                "id": "evt-2",
                "resource_id": "task-2",
                "action": "kb.document.batch_update",
                "created_at": "2026-03-20T09:00:00+00:00",
                "details": {"task_id": "task-2", "retry_of_task_id": "task-1", "failed": 0},
            },
            {
                "id": "evt-1",
                "resource_id": "task-1",
                "action": "kb.document.batch_update",
                "created_at": "2026-03-20T08:00:00+00:00",
                "details": {"task_id": "task-1", "failed": 1},
            },
            {
                "id": "evt-3",
                "resource_id": "task-3",
                "action": "kb.document.batch_update",
                "created_at": "2026-03-20T10:00:00+00:00",
                "details": {"task_id": "task-3", "retry_of_task_id": "task-2", "failed": 0},
            },
        ]

    monkeypatch.setattr(kb_analytics, "list_audit_events", fake_list_audit_events)

    payload = kb_analytics._governance_batch_event_detail_payload(
        user,
        view="personal",
        task_id="task-2",
        timeline_limit=10,
        timeline_offset=0,
        timeline_filter="all",
    )

    assert payload["task_id"] == "task-2"
    assert payload["item"]["resource_id"] == "task-2"
    assert payload["retry_summary"]["parent_task_id"] == "task-1"
    assert payload["retry_summary"]["retry_count"] == 1
    assert payload["retry_summary"]["latest_retry_task_id"] == "task-3"
    assert payload["timeline"]["items"][0]["resource_id"] == "task-3"
    assert payload["timeline"]["items"][1]["resource_id"] == "task-2"
    assert payload["timeline"]["items"][2]["resource_id"] == "task-1"
    assert payload["timeline"]["total"] == 3
    assert payload["timeline"]["has_more"] is False


def test_governance_batch_event_detail_payload_supports_filter_and_pagination(monkeypatch) -> None:
    kb_analytics = _load_kb_module("app.kb_analytics_routes")
    user = auth_module.AuthUser(
        user_id="owner-1",
        email="owner@local",
        role="kb_editor",
        permissions=auth_module.permissions_for_role("kb_editor"),
    )

    def fake_list_audit_events(**kwargs):
        resource_id = kwargs.get("resource_id")
        if resource_id == "task-2":
            return [
                {
                    "id": "evt-task-2",
                    "resource_id": "task-2",
                    "created_at": "2026-03-20T09:00:00+00:00",
                    "details": {"retry_of_task_id": "task-1", "failed": 1, "succeeded": 2},
                    "outcome": "partial_success",
                }
            ]
        return [
            {
                "id": "evt-task-1",
                "resource_id": "task-1",
                "created_at": "2026-03-20T08:00:00+00:00",
                "details": {"failed": 2, "succeeded": 0},
                "outcome": "partial_success",
            },
            {
                "id": "evt-task-3",
                "resource_id": "task-3",
                "created_at": "2026-03-20T10:00:00+00:00",
                "details": {"retry_of_task_id": "task-2", "failed": 1, "succeeded": 1},
                "outcome": "partial_success",
            },
            {
                "id": "evt-task-4",
                "resource_id": "task-4",
                "created_at": "2026-03-20T11:00:00+00:00",
                "details": {"retry_of_task_id": "task-2", "failed": 0, "succeeded": 1},
                "outcome": "success",
            },
        ]

    monkeypatch.setattr(kb_analytics, "list_audit_events", fake_list_audit_events)

    payload = kb_analytics._governance_batch_event_detail_payload(
        user,
        view="personal",
        task_id="task-2",
        timeline_limit=1,
        timeline_offset=1,
        timeline_filter="retries",
    )

    assert payload["retry_summary"]["retry_count"] == 2
    assert payload["retry_summary"]["failed_retry_count"] == 1
    assert payload["retry_summary"]["latest_retry_task_id"] == "task-4"
    assert payload["timeline"]["filter"] == "retries"
    assert payload["timeline"]["total"] == 3
    assert payload["timeline"]["offset"] == 1
    assert payload["timeline"]["limit"] == 1
    assert payload["timeline"]["has_more"] is True
    assert [item["resource_id"] for item in payload["timeline"]["items"]] == ["task-4"]


def test_build_version_diff_payload_summarizes_changes() -> None:
    kb_base_routes = _load_kb_module("app.kb_base_routes")

    source_chunks = [
        {"section_index": 0, "chunk_index": 0, "section_title": "Overview", "text_content": "line-a", "disabled": False},
        {"section_index": 1, "chunk_index": 0, "section_title": "Rules", "text_content": "old-rule", "disabled": False},
    ]
    target_chunks = [
        {"section_index": 0, "chunk_index": 0, "section_title": "Overview", "text_content": "line-a", "disabled": False},
        {"section_index": 1, "chunk_index": 0, "section_title": "Rules", "text_content": "new-rule", "disabled": False},
        {"section_index": 2, "chunk_index": 0, "section_title": "Appendix", "text_content": "extra", "disabled": False},
    ]

    payload = kb_base_routes._build_version_diff_payload(
        source_document={"id": "doc-v1", "version_label": "v1", "file_name": "policy-v1.pdf"},
        source_chunks=source_chunks,
        target_document={"id": "doc-v2", "version_label": "v2", "file_name": "policy-v2.pdf"},
        target_chunks=target_chunks,
    )

    assert payload["summary"]["added_chunks"] == 1
    assert payload["summary"]["removed_chunks"] == 0
    assert payload["summary"]["modified_chunks"] == 1
    assert "--- v1" in payload["diff_text"]
    assert "+++ v2" in payload["diff_text"]
    assert "new-rule" in payload["diff_text"]


def test_connector_scheduler_manager_runs_only_when_active() -> None:
    kb_scheduler = _load_kb_module("app.kb_connector_scheduler")
    active = {"value": False}
    calls: list[dict[str, object]] = []

    def has_active() -> bool:
        return bool(active["value"])

    def run_due_batch(*, limit: int, dry_run: bool, user) -> dict[str, object]:
        calls.append({"limit": limit, "dry_run": dry_run, "user_id": user.user_id})
        active["value"] = False
        return {"items": [], "count": 0}

    async def scenario() -> None:
        manager = kb_scheduler.ConnectorSchedulerManager(
            has_active_schedules=has_active,
            run_due_batch=run_due_batch,
            min_poll_seconds=5,
            max_batch_size=3,
        )
        manager.bind_loop(asyncio.get_running_loop())
        manager.reconcile()
        await asyncio.sleep(0.05)
        assert calls == []
        active["value"] = True
        manager.reconcile()
        await asyncio.sleep(0.1)
        assert len(calls) == 1
        assert calls[0]["limit"] == 3
        assert calls[0]["dry_run"] is False
        await manager.shutdown()

    asyncio.run(scenario())


def test_request_service_json_preserves_upstream_4xx() -> None:
    gateway_transport = _load_gateway_module("app.gateway_transport")

    class FakeClient:
        async def request(self, method, url, *, headers=None, json=None, params=None):
            return httpx.Response(
                404,
                json={"detail": "kb base not found", "code": "kb_base_not_found"},
                request=httpx.Request(method, url),
            )

    try:
        asyncio.run(
            gateway_transport.request_service_json(
                FakeClient(),
                "GET",
                "http://kb-service:8200/api/v1/kb/bases/base-1",
                headers={},
            )
        )
    except gateway_transport.HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail["detail"] == "kb base not found"
        assert exc.detail["code"] == "kb_base_not_found"
        assert exc.detail["upstream_status"] == 404
    else:
        raise AssertionError("expected upstream 404 to be preserved")


def test_request_service_json_wraps_upstream_5xx_as_502() -> None:
    gateway_transport = _load_gateway_module("app.gateway_transport")

    class FakeClient:
        async def request(self, method, url, *, headers=None, json=None, params=None):
            return httpx.Response(
                503,
                json={"detail": "kb analytics unavailable", "code": "kb_not_ready"},
                request=httpx.Request(method, url),
            )

    try:
        asyncio.run(
            gateway_transport.request_service_json(
                FakeClient(),
                "GET",
                "http://kb-service:8200/api/v1/kb/analytics/dashboard",
                headers={},
            )
        )
    except gateway_transport.HTTPException as exc:
        assert exc.status_code == 502
        assert exc.detail["detail"] == "kb analytics unavailable"
        assert exc.detail["code"] == "kb_not_ready"
        assert exc.detail["upstream_status"] == 503
    else:
        raise AssertionError("expected upstream 503 to be wrapped as 502")


