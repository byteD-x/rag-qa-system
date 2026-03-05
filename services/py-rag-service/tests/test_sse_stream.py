"""SSE 流式响应测试"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.main import (
    RAGEngine,
    Scope,
    ServiceConfig,
    build_no_evidence_response,
    build_weak_evidence_response,
)


@pytest.fixture
def mock_config():
    """模拟配置"""
    return ServiceConfig(
        qdrant_url="http://localhost:6333",
        qdrant_collection="rag_chunks",
        embedding_dim=256,
        retrieval_top_n=10,
        rerank_top_k=5,
        source_sentence_limit=3,
        evidence_min_score=0.05,
        common_knowledge_max_ratio=0.15,
        llm_provider="openai",
        llm_base_url="https://api.openai.com/v1",
        llm_api_key="test-key",
        llm_embedding_model="text-embedding-ada-002",
        llm_chat_model="gpt-3.5-turbo",
        llm_timeout_seconds=30,
        llm_max_retries=2,
        llm_retry_delay_milliseconds=600,
        hybrid_dense_weight=0.7,
        hybrid_sparse_weight=0.3,
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        query_cache_enabled=True,
        query_cache_ttl_hours=24,
        query_cache_max_size=10000,
        multi_query_enabled=False,
        multi_query_max_variants=3,
        multi_query_timeout_ms=500,
    )


@pytest.fixture
def test_scope():
    """测试范围"""
    return Scope(
        mode="single",
        corpus_ids=["550e8400-e29b-41d4-a716-446655440000"],
        document_ids=[],
        allow_common_knowledge=True,
    )


@pytest.fixture
def mock_llm():
    """创建 mock LLM 实例"""
    mock = MagicMock()
    mock.embed.return_value = [0.1] * 256
    mock.generate_summary.return_value = "这是测试答案"
    return mock


@pytest.mark.asyncio
async def test_query_stream_format(mock_config, test_scope, mock_llm):
    """测试 SSE 流式响应格式"""
    with patch("app.main.QdrantClient") as mock_qdrant, \
         patch("app.main.LLMGateway", return_value=mock_llm):
        
        mock_qdrant_instance = MagicMock()
        mock_qdrant.return_value = mock_qdrant_instance
        
        mock_point = MagicMock()
        mock_point.id = "chunk-1"
        mock_point.score = 0.85
        mock_point.payload = {
            "document_id": "doc-1",
            "corpus_id": "corpus-1",
            "file_name": "test.txt",
            "page_or_loc": "page-1",
            "text": "这是测试文本",
        }
        
        mock_qdrant_instance.query_points.return_value = MagicMock(points=[mock_point])
        
        # 创建引擎实例
        engine = RAGEngine(mock_config)
        
        # 替换 LLM 实例为 mock
        engine._llm = mock_llm
        
        events = []
        async for event in engine.query_stream("测试问题", test_scope):
            events.append(event)
        
        assert len(events) > 0
        
        # 去掉 "data: " 前缀再解析 JSON
        def parse_sse_event(event_str):
            """解析 SSE 事件，去掉 'data: ' 前缀"""
            if event_str.startswith("data: "):
                return json.loads(event_str[6:].strip())
            return json.loads(event_str.strip())
        
        first_event = parse_sse_event(events[0])
        assert "type" in first_event
        assert first_event["type"] in ["sentence", "citation"]
        
        last_event = parse_sse_event(events[-1])
        assert last_event["type"] == "done"
        
        for event in events:
            assert event.endswith("\n\n")
            data = parse_sse_event(event)
            assert "type" in data
            assert data["type"] in ["sentence", "citation", "done", "error"]


@pytest.mark.asyncio
async def test_query_stream_error_handling(mock_config, test_scope, mock_llm):
    """测试 SSE 流式错误处理"""
    with patch("app.main.QdrantClient") as mock_qdrant, \
         patch("app.main.LLMGateway", return_value=mock_llm):
        
        mock_qdrant_instance = MagicMock()
        mock_qdrant.return_value = mock_qdrant_instance
        
        mock_qdrant_instance.query_points.side_effect = Exception("连接失败")
        
        engine = RAGEngine(mock_config)
        engine._llm = mock_llm
        
        events = []
        async for event in engine.query_stream("测试问题", test_scope):
            events.append(event)
        
        assert len(events) >= 2
        
        def parse_sse_event(event_str):
            """解析 SSE 事件，去掉 'data: ' 前缀"""
            if event_str.startswith("data: "):
                return json.loads(event_str[6:].strip())
            return json.loads(event_str.strip())
        
        # 错误情况下，最后一个事件应该是 error 类型
        last_event = parse_sse_event(events[-1])
        assert last_event["type"] in ["error", "done"]
        
        # 验证包含错误信息
        has_error = False
        for event in events:
            data = parse_sse_event(event)
            if data["type"] == "error":
                has_error = True
                assert "message" in data
                assert "连接失败" in data["message"]
        
        assert has_error, "Should have at least one error event"


@pytest.mark.asyncio
async def test_query_stream_no_evidence(mock_config, test_scope, mock_llm):
    """测试 SSE 流式响应无证据情况"""
    with patch("app.main.QdrantClient") as mock_qdrant, \
         patch("app.main.LLMGateway", return_value=mock_llm):
        
        mock_qdrant_instance = MagicMock()
        mock_qdrant.return_value = mock_qdrant_instance
        
        mock_qdrant_instance.query_points.return_value = MagicMock(points=[])
        
        engine = RAGEngine(mock_config)
        engine._llm = mock_llm
        
        events = []
        async for event in engine.query_stream("测试问题", test_scope):
            events.append(event)
        
        assert len(events) > 0
        
        def parse_sse_event(event_str):
            """解析 SSE 事件，去掉 'data: ' 前缀"""
            if event_str.startswith("data: "):
                return json.loads(event_str[6:].strip())
            return json.loads(event_str.strip())
        
        has_sentence = False
        has_done = False
        
        for event in events:
            data = parse_sse_event(event)
            if data["type"] == "sentence":
                has_sentence = True
                assert "data" in data
                assert "text" in data["data"]
            elif data["type"] == "done":
                has_done = True
        
        assert has_sentence, "Should have at least one sentence"
        assert has_done, "Should end with done event"


def test_format_sse_output(mock_config, mock_llm):
    """测试 SSE 格式化输出"""
    with patch("app.main.QdrantClient"), \
         patch("app.main.LLMGateway", return_value=mock_llm):
        engine = RAGEngine(mock_config)
        
        event_str = engine._format_sse("sentence", {"text": "测试", "confidence": 0.9})
        assert event_str.endswith("\n\n")
        
        data = json.loads(event_str.strip().replace("data: ", ""))
        assert data["type"] == "sentence"
        assert data["data"]["text"] == "测试"
        assert data["data"]["confidence"] == 0.9
        
        event_done = engine._format_sse("done")
        data_done = json.loads(event_done.strip().replace("data: ", ""))
        assert data_done["type"] == "done"
        assert "data" not in data_done
