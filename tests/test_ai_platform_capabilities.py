from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_visual_layout_regions_are_promoted_to_region_units() -> None:
    kb_src = REPO_ROOT / "apps/services/knowledge-base/src"
    sys.path.insert(0, str(kb_src))
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)
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
