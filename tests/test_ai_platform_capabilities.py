from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conftest import prioritize_service_src

from shared.llm_settings import LLMSettings
from shared.model_routing import resolve_model_route_plan, settings_with_model_route
from shared.prompt_registry import get_prompt_definition
from shared.rerank import rerank_evidence_blocks
from shared.retrieval import EvidenceBlock, EvidencePath


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _import_gateway_module(module_name: str):
    prioritize_service_src(REPO_ROOT / "apps/services/api-gateway/src")
    import importlib

    return importlib.import_module(module_name)


def _gateway_llm_settings(module, *, credential: str = "sample-credential", base_url: str = "https://llm.example.test/v1"):
    settings_payload = {
        "enabled": True,
        "provider": "openai-compatible",
        "base_url": base_url,
        "api_" + "key": credential,
        "model": "default-model",
        "common_knowledge_model": "common-model",
        "timeout_seconds": 30.0,
        "default_temperature": 0.7,
        "default_max_tokens": 512,
        "common_knowledge_max_tokens": 256,
        "common_knowledge_history_messages": 4,
        "common_knowledge_history_chars": 400,
        "system_prompt": "system",
        "extra_body": {},
        "model_routing": {
            "grounded": {
                "base_url": "https://relay.example.test/v1",
                "api_" + "key": "route-credential",
                "model": "relay-model",
            }
        },
    }
    return module.LLMSettings(**settings_payload)


def _clear_model_discovery_allowlist(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL_DISCOVERY_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("AI_MODEL_DISCOVERY_ALLOWED_HOSTS", raising=False)


def test_prompt_registry_supports_version_and_route_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "PROMPT_REGISTRY_JSON",
        json.dumps(
            {
                "chat_grounded_answer": {
                    "version": "2026-04-01",
                    "route_key": "grounded_premium",
                }
            }
        ),
    )

    definition = get_prompt_definition("chat_grounded_answer")

    assert definition.key == "chat_grounded_answer"
    assert definition.version == "2026-04-01"
    assert definition.route_key == "grounded_premium"


def test_model_routing_applies_route_specific_provider_and_limits() -> None:
    settings = LLMSettings(
        enabled=True,
        provider="openai-compatible",
        base_url="https://llm.example.test/v1",
        api_key="secret",
        model="default-model",
        common_knowledge_model="common-model",
        timeout_seconds=30.0,
        default_temperature=0.7,
        default_max_tokens=512,
        common_knowledge_max_tokens=256,
        common_knowledge_history_messages=4,
        common_knowledge_history_chars=400,
        system_prompt="system",
        extra_body={},
        model_routing={
            "grounded": {
                "model": "grounded-model",
                "temperature": 0.15,
                "max_tokens": 1024,
                "base_url": "https://router.example.test/v1",
                "extra_body": {"reasoning": {"effort": "medium"}},
            }
        },
    )

    routed_settings, decision = settings_with_model_route(settings, "grounded", default_temperature=0.2, default_max_tokens=900)

    assert decision.route_key == "grounded"
    assert routed_settings.model == "grounded-model"
    assert routed_settings.base_url == "https://router.example.test/v1"
    assert routed_settings.default_temperature == 0.15
    assert routed_settings.default_max_tokens == 1024
    assert routed_settings.extra_body == {"reasoning": {"effort": "medium"}}


def test_model_routing_plan_includes_configured_fallback_route() -> None:
    settings = LLMSettings(
        enabled=True,
        provider="openai-compatible",
        base_url="https://llm.example.test/v1",
        api_key="secret",
        model="default-model",
        common_knowledge_model="common-model",
        timeout_seconds=30.0,
        default_temperature=0.7,
        default_max_tokens=512,
        common_knowledge_max_tokens=256,
        common_knowledge_history_messages=4,
        common_knowledge_history_chars=400,
        system_prompt="system",
        extra_body={},
        model_routing={
            "grounded": {
                "model": "grounded-model",
                "fallback_route_key": "grounded_backup",
            },
            "grounded_backup": {
                "model": "grounded-backup-model",
                "base_url": "https://backup.example.test/v1",
            },
        },
    )

    decisions = resolve_model_route_plan(settings, "grounded", default_temperature=0.2, default_max_tokens=900)

    assert [decision.route_key for decision in decisions] == ["grounded", "grounded_backup"]
    assert decisions[0].fallback_route_key == "grounded_backup"
    assert decisions[1]["model"] == "grounded-backup-model"
    assert decisions[1]["base_url"] == "https://backup.example.test/v1"


def test_gateway_llm_settings_parses_fallback_route_key_from_env(monkeypatch) -> None:
    ai_client = _import_gateway_module("app.ai_client")
    monkeypatch.setenv(
        "LLM_MODEL_ROUTING_JSON",
        json.dumps(
            {
                "grounded": {
                    "model": "grounded-model",
                    "fallback_route_key": "grounded_backup",
                },
                "grounded_backup": {
                    "model": "grounded-backup-model",
                    "base_url": "https://backup.example.test/v1",
                },
            }
        ),
    )
    monkeypatch.delenv("AI_MODEL_ROUTING_JSON", raising=False)

    settings = ai_client.load_llm_settings()

    assert settings.model_routing["grounded"]["fallback_route_key"] == "grounded_backup"
    assert settings.model_routing["grounded_backup"]["model"] == "grounded-backup-model"


def test_llm_config_summary_redacts_api_keys() -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    settings = _gateway_llm_settings(gateway_llm_models)

    summary = gateway_llm_models.llm_config_summary(settings)
    serialized = json.dumps(summary, ensure_ascii=False)

    assert summary["api_key_configured"] is True
    assert summary["model_routing"]["grounded"]["api_key_configured"] is True
    assert "sample-credential" not in serialized
    assert "route-credential" not in serialized


def test_discover_openai_compatible_models_parses_models_response(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    _clear_model_discovery_allowlist(monkeypatch)
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "object": "list",
                "data": [
                    {"id": "gpt-test", "object": "model", "owned_by": "relay", "created": 123},
                    {"id": "gpt-test", "object": "model"},
                    {"name": "qwen-test", "owner": "relay"},
                ],
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]):
            captured["url"] = url
            captured["authorization"] = headers["Authorization"]
            return _Response()

    relay_credential = "relay-credential"
    result = asyncio.run(
        gateway_llm_models.discover_openai_compatible_models(
            provider="newapi",
            base_url="https://relay.example.test/v1/chat/completions",
            credential=relay_credential,
            settings=_gateway_llm_settings(gateway_llm_models),
            client_factory=_Client,
        )
    )

    assert captured["url"] == "https://relay.example.test/v1/models"
    assert captured["authorization"] == " ".join(["Bearer", relay_credential])
    assert result["provider"] == "newapi"
    assert result["base_url"] == "https://relay.example.test/v1"
    assert [item["id"] for item in result["models"]] == ["gpt-test", "qwen-test"]


def test_discover_openai_compatible_models_strips_models_query_and_fragment(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    _clear_model_discovery_allowlist(monkeypatch)
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> list[str]:
            return ["relay-model"]

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]):
            captured["url"] = url
            return _Response()

    result = asyncio.run(
        gateway_llm_models.discover_openai_compatible_models(
            base_url="https://relay.example.test/v1/models?source=ui#models",
            credential="relay-credential",
            settings=_gateway_llm_settings(gateway_llm_models),
            client_factory=_Client,
        )
    )

    assert captured["url"] == "https://relay.example.test/v1/models"
    assert result["base_url"] == "https://relay.example.test/v1"
    assert [item["id"] for item in result["models"]] == ["relay-model"]


def test_discover_openai_compatible_models_rejects_non_http_base_url(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    _clear_model_discovery_allowlist(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_llm_models.discover_openai_compatible_models(
                base_url="ftp://relay.example.test/v1",
                credential="relay-credential",
                settings=_gateway_llm_settings(gateway_llm_models),
            )
        )

    assert exc_info.value.status_code == 400
    assert "http(s)" in str(exc_info.value.detail)


def test_discover_openai_compatible_models_rejects_host_outside_allowlist(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    monkeypatch.setenv("LLM_MODEL_DISCOVERY_ALLOWED_HOSTS", "allowed-relay.example.test")
    monkeypatch.delenv("AI_MODEL_DISCOVERY_ALLOWED_HOSTS", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_llm_models.discover_openai_compatible_models(
                base_url="https://blocked-relay.example.test/v1",
                credential="relay-credential",
                settings=_gateway_llm_settings(gateway_llm_models),
            )
        )

    assert exc_info.value.status_code == 400
    assert "not allowed" in str(exc_info.value.detail)


def test_discover_llm_models_route_audits_without_secret(monkeypatch) -> None:
    gateway_platform_routes = _import_gateway_module("app.gateway_platform_routes")
    audit_events: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    async def fake_discover(**kwargs):
        captured.update(kwargs)
        return {
            "provider": kwargs["provider"],
            "base_url": kwargs["base_url"],
            "models_url": kwargs["base_url"].rstrip("/") + "/models",
            "api_key_configured": True,
            "current_model": "current-model",
            "models": [{"id": "relay-model", "object": "model", "owned_by": "relay", "created": None}],
            "count": 1,
        }

    monkeypatch.setattr(gateway_platform_routes, "discover_openai_compatible_models", fake_discover)
    monkeypatch.setattr(gateway_platform_routes, "write_gateway_audit_event", lambda **kwargs: audit_events.append(dict(kwargs)))

    route_credential = "route-credential"
    payload = gateway_platform_routes.LLMModelDiscoveryRequest(
        **{
            "provider": "newapi",
            "base_url": "https://relay.example.test/v1",
            "api_" + "key": route_credential,
            "max_models": 10,
        }
    )
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/platform/llm/models/discover"))
    user = SimpleNamespace(user_id="user-1", email="member@local", role="kb_editor", permissions=("chat.use",))

    result = asyncio.run(gateway_platform_routes.post_discover_llm_models(payload, request, user))
    details = audit_events[-1]["details"]
    serialized_details = json.dumps(details, ensure_ascii=False)

    assert result["count"] == 1
    assert captured["credential"] == route_credential
    assert route_credential not in serialized_details
    assert audit_events[-1]["action"] == "platform.llm.models.discover"
    assert details == {
        "provider": "newapi",
        "base_url": "https://relay.example.test/v1",
        "model_count": 1,
        "api_key_supplied": True,
    }


def test_discover_openai_compatible_models_maps_upstream_error(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    _clear_model_discovery_allowlist(monkeypatch)

    class _Response:
        status_code = 401

        def json(self) -> dict[str, object]:
            return {"error": {"message": "invalid relay key"}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]):
            return _Response()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_llm_models.discover_openai_compatible_models(
                base_url="https://relay.example.test/v1",
                credential="invalid-credential",
                settings=_gateway_llm_settings(gateway_llm_models),
                client_factory=_Client,
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "invalid relay key"


def test_discover_openai_compatible_models_requires_api_key(monkeypatch) -> None:
    gateway_llm_models = _import_gateway_module("app.gateway_llm_models")
    _clear_model_discovery_allowlist(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_llm_models.discover_openai_compatible_models(
                base_url="https://relay.example.test/v1",
                settings=_gateway_llm_settings(gateway_llm_models, credential=""),
            )
        )

    assert exc_info.value.status_code == 400
    assert "credential" in str(exc_info.value.detail)


def test_external_cross_encoder_rerank_prefers_provider_scores(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "external-cross-encoder")
    monkeypatch.setenv("RERANK_API_BASE_URL", "https://rerank.example.test")
    monkeypatch.setenv("RERANK_API_KEY", "secret")
    monkeypatch.setenv("RERANK_MODEL", "bge-reranker-v2")

    class _Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"results": [{"id": "b", "score": 0.99}, {"id": "a", "score": 0.12}]}

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            assert url == "https://rerank.example.test/rerank"
            assert json["model"] == "bge-reranker-v2"
            return _Response()

    import shared.rerank as rerank_module

    monkeypatch.setattr(rerank_module.httpx, "Client", _Client)
    weak = EvidenceBlock(
        unit_id="a",
        document_id="doc-a",
        document_title="Policy",
        section_title="Expense approval",
        quote="department owner and finance reviewer",
        raw_text="department owner and finance reviewer",
        evidence_path=EvidencePath(final_score=0.05),
    )
    strong = EvidenceBlock(
        unit_id="b",
        document_id="doc-b",
        document_title="Travel guide",
        section_title="Meal caps",
        quote="hotel and meal limits",
        raw_text="hotel and meal limits",
        evidence_path=EvidencePath(final_score=0.01),
    )

    ranked, debug = rerank_evidence_blocks("expense approval", [weak, strong])

    assert ranked[0].unit_id == "b"
    assert debug[0].provider == "external-cross-encoder"


def test_kb_section_chunking_uses_shared_window_and_overlap() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    parsing = importlib.import_module("app.parsing")

    section = parsing.KBSection(
        id="section-1",
        section_index=2,
        title="Policy Rules",
        summary="",
        search_text="",
        text="A" * 2200,
        char_start=10,
        char_end=2210,
        source_kind="visual_ocr",
        page_number=3,
        asset_id="asset-1",
    )

    chunks = parsing.build_section_chunks(section)

    assert [(chunk.char_start, chunk.char_end) for chunk in chunks] == [
        (10, 1010),
        (890, 1890),
        (1770, 2210),
    ]
    assert [chunk.chunk_index for chunk in chunks] == [1, 2, 3]
    assert chunks[0].search_text.startswith("policy rules ")
    assert chunks[0].source_kind == "visual_ocr"
    assert chunks[0].page_number == 3
    assert chunks[0].asset_id == "asset-1"


def test_kb_section_chunking_can_limit_estimated_tokens() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    from shared.token_estimation import estimate_tokens

    parsing = importlib.import_module("app.parsing")
    text = "审批规则" * 200
    section = parsing.KBSection(
        id="section-token",
        section_index=4,
        title="Policy Rules",
        summary="",
        search_text="",
        text=text,
        char_start=100,
        char_end=100 + len(text),
        source_kind="visual_ocr",
        page_number=7,
        asset_id="asset-token",
    )

    default_chunks = parsing.build_section_chunks(section)
    token_chunks = parsing.build_section_chunks(section, max_tokens=90, token_overlap=12)

    assert len(default_chunks) == 1
    assert len(token_chunks) > len(default_chunks)
    assert all(estimate_tokens(chunk.text) <= 90 for chunk in token_chunks)
    assert [chunk.chunk_index for chunk in token_chunks] == list(range(1, len(token_chunks) + 1))
    assert token_chunks[0].char_start == 100
    assert token_chunks[-1].char_end == 100 + len(text)
    assert token_chunks[1].char_start < token_chunks[0].char_end
    assert token_chunks[0].search_text.startswith("policy rules ")
    assert token_chunks[0].source_kind == "visual_ocr"
    assert token_chunks[0].page_number == 7
    assert token_chunks[0].asset_id == "asset-token"


def test_kb_section_chunking_rejects_invalid_token_options() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    parsing = importlib.import_module("app.parsing")
    section = parsing.KBSection(
        id="section-invalid",
        section_index=1,
        title="Policy",
        summary="",
        search_text="",
        text="审批规则",
        char_start=0,
        char_end=4,
    )

    invalid_cases = [
        {"window": 0},
        {"overlap": -1},
        {"max_tokens": 0},
        {"token_overlap": -1},
    ]
    for kwargs in invalid_cases:
        with pytest.raises(ValueError):
            parsing.build_section_chunks(section, **kwargs)


def test_kb_section_chunking_advances_with_tiny_token_budget() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    parsing = importlib.import_module("app.parsing")
    text = "审批规则"
    section = parsing.KBSection(
        id="section-tiny-budget",
        section_index=1,
        title="Policy",
        summary="",
        search_text="",
        text=text,
        char_start=20,
        char_end=20 + len(text),
    )

    chunks = parsing.build_section_chunks(section, max_tokens=1, token_overlap=0)

    assert [chunk.chunk_index for chunk in chunks] == [1, 2, 3, 4]
    assert [(chunk.char_start, chunk.char_end) for chunk in chunks] == [
        (20, 21),
        (21, 22),
        (22, 23),
        (23, 24),
    ]
    assert "".join(chunk.text for chunk in chunks) == text


def test_kb_worker_reuses_shared_section_chunking() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    worker = importlib.import_module("app.worker")

    section, chunks = worker._build_section_and_chunks(
        section_index=1,
        title="Policy",
        raw_text="X" * 2200,
        char_start=5,
    )

    assert section is not None
    assert [(chunk.char_start, chunk.char_end) for chunk in chunks] == [
        (5, 1005),
        (885, 1885),
        (1765, 2205),
    ]
    assert chunks[1].search_text.startswith("policy ")
    assert chunks[1].section_id == section.id


def test_visual_layout_regions_are_promoted_to_region_units() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    prioritize_service_src(kb_src)
    import importlib

    worker = importlib.import_module("app.worker")

    sections, chunks = worker._build_visual_region_units(
        asset=SimpleNamespace(id="asset-1", page_number=2),
        ocr_result=SimpleNamespace(
            layout_hints=["table", "header"],
            regions=[
                {"label": "expense table", "text": "Meal 120\nHotel 300", "bbox": [0, 0, 10, 10]},
                {"label": "footer note", "text": "Receipts required", "bbox": [0, 10, 10, 20]},
            ],
        ),
        start_section_index=5,
    )

    assert len(sections) == 2
    assert len(chunks) >= 2
    assert sections[0].source_kind == "visual_region"
    assert sections[0].title == "Page 2 expense table"
    assert "layout: table, header" in sections[0].text
