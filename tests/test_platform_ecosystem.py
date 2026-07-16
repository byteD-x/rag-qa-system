"""测试平台化与生态扩展：幻觉检测、Python SDK。"""

from __future__ import annotations

import importlib
import sys
import json
from pathlib import Path

import pytest

from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"
SDK_SRC = REPO_ROOT / "sdk/python"


def _import_gateway(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://test.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("KB_SERVICE_URL", "http://localhost:8200")
    monkeypatch.setenv("GATEWAY_GRAPH_CHECKPOINTER", "memory")
    target = str(GATEWAY_SRC)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()


# ============================================================================
# 幻觉检测测试
# ============================================================================


class TestHallucinationDetector:
    """测试RAG幻觉检测。"""

    def test_citation_consistency_ok(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.hallucination_detector import _check_citation_consistency

        answer = "根据规定 [1]，退款流程共三步 [2]。"
        evidence = [
            {"document_title": "文档A", "quote": "退款流程包括..."},
            {"document_title": "文档B", "quote": "申请 → 审批..."},
        ]
        items, score = _check_citation_consistency(answer, evidence)
        assert score < 0.3  # 无虚构引用

    def test_citation_consistency_fake(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.hallucination_detector import _check_citation_consistency

        answer = "根据规定 [1] 和 [5]，退款流程..."
        evidence = [{"document_title": "文档A", "quote": "退款..."}]
        items, score = _check_citation_consistency(answer, evidence)
        assert score > 0.0
        assert any("5" in item.description for item in items)

    def test_number_consistency(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.hallucination_detector import _check_number_consistency

        answer = "退款需要3个工作日"
        evidence = [{"quote": "退款处理时间: 3个工作日"}]
        items, score = _check_number_consistency(answer, evidence)
        # 数字一致，不应有告警
        assert score < 0.3

    @pytest.mark.asyncio
    async def test_detect_empty_answer(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.hallucination_detector import HallucinationDetector

        detector = HallucinationDetector()
        report = await detector.detect(answer="", evidence=[], deep_check=False)
        assert report.passed
        assert report.hallucination_score == 0.0

    @pytest.mark.asyncio
    async def test_detect_rule_only(self, monkeypatch) -> None:
        _import_gateway(monkeypatch)
        from app.hallucination_detector import HallucinationDetector

        detector = HallucinationDetector()
        answer = "根据 [1] [2] [3] 退款需要5步。"
        evidence = [{"document_title": "退款文档", "quote": "退款流程包括申请、审批、打款三步"}]
        report = await detector.detect(answer=answer, evidence=evidence, deep_check=False)
        # [2] 和 [3] 是虚构引用
        assert report.hallucination_score > 0.0
        assert len(report.items) >= 1


# ============================================================================
# Python SDK 测试
# ============================================================================


class TestPythonSDK:
    """测试 Python SDK 类型系统。"""

    def test_import_types(self, monkeypatch) -> None:
        _import_sdk()
        from rag_qa_client.types import (
            ChatRequest,
            ChatResponse,
            Citation,
            KnowledgeBase,
            SceneTemplate,
        )

        req = ChatRequest(question="测试")
        assert req.question == "测试"
        assert req.execution_mode == "grounded"

        resp = ChatResponse(answer="答案")
        assert resp.answer == "答案"

        cite = Citation(index=1, document_title="文档A", quote="内容...", score=0.85)
        assert cite.score == 0.85

        kb = KnowledgeBase(id="kb:1", name="测试库")
        assert kb.name == "测试库"

        scene = SceneTemplate(key="test", name="测试", description="描述", icon="🧪")
        assert scene.icon == "🧪"

    def test_chat_request_fields(self, monkeypatch) -> None:
        _import_sdk()
        from rag_qa_client.types import ChatRequest

        req = ChatRequest(
            question="退款流程",
            scope={"corpus_ids": ["kb:abc"]},
            execution_mode="agent",
            agent_profile_id="profile-1",
            instruction_override={"language": "英文"},
        )
        assert req.execution_mode == "agent"
        assert req.scope["corpus_ids"] == ["kb:abc"]
        assert req.instruction_override["language"] == "英文"

    def test_chat_response_citations(self, monkeypatch) -> None:
        _import_sdk()
        from rag_qa_client.types import ChatResponse, Citation

        resp = ChatResponse(
            answer="退款需要3步",
            citations=[
                Citation(index=1, document_title="退款指南", quote="退款三步"),
                Citation(index=2, document_title="财务规定", quote="3个工作日"),
            ],
            latency={"total_ms": 500, "retrieval_ms": 200},
        )
        assert len(resp.citations) == 2
        assert resp.latency["total_ms"] == 500

    def test_document_type(self, monkeypatch) -> None:
        _import_sdk()
        from rag_qa_client.types import Document

        doc = Document(
            id="doc-1",
            file_name="退款流程v3.pdf",
            version_label="v3.0",
            is_current_version=True,
            corpus_id="kb:abc",
        )
        assert doc.is_current_version
        assert doc.version_label == "v3.0"


def _import_sdk() -> None:
    sdk_path = str(SDK_SRC)
    try:
        sys.path.remove(sdk_path)
    except ValueError:
        pass
    sys.path.insert(0, sdk_path)
    for name in list(sys.modules.keys()):
        if name.startswith("rag_qa_client"):
            sys.modules.pop(name, None)

