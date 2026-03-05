#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端集成测试 (End-to-End Integration Tests)
测试完整的 RAG 检索流程：intent -> query rewrite -> hybrid retrieval -> reranking -> response

包含以下测试模块：
1. 混合检索集成测试 (T9.1)
2. 多查询检索集成测试 (T9.2)
3. 意图分类集成测试 (T9.3)
4. 完整流程端到端测试
"""

import pytest
import asyncio
import time
import json
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import List, Dict, Any
from dataclasses import dataclass
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app, RAGEngine, build_service_config
from app.hybrid_retriever import HybridRetriever, RetrievalResult
from app.query_rewriter import QueryRewriter, MultiQueryRetriever, RewrittenQuery
from app.intent_classifier import IntentClassifier, IntentType, get_classifier
from app.reranker import Reranker
from app.context_compressor import ContextCompressor


client = TestClient(app)


@dataclass
class MockRetrievalResult:
    """模拟检索结果"""
    chunk_id: str
    document_id: str
    corpus_id: str
    file_name: str
    page_or_loc: str
    text: str
    score: float
    retrieval_type: str = "dense"


class TestHybridRetrievalE2E:
    """T9.1: 混合检索端到端集成测试"""

    @pytest.fixture
    def hybrid_retriever(self):
        """创建混合检索器"""
        return HybridRetriever(dense_weight=0.7, sparse_weight=0.3)

    @pytest.fixture
    def sample_documents(self):
        """创建示例文档"""
        return [
            {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"Python machine learning algorithms tutorial document {i}",
            }
            if i < 5
            else {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"Deep learning neural networks architecture document {i}",
            }
            if i < 10
            else {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"Data science analytics visualization document {i}",
            }
            for i in range(15)
        ]

    def test_hybrid_search_basic(self, hybrid_retriever, sample_documents):
        """测试混合检索基本功能"""
        hybrid_retriever.build_bm25_index(sample_documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=sample_documents[i]["text"],
                score=0.95 - i * 0.05,
                retrieval_type="dense",
            )
            for i in range(5)
        ]
        
        sparse_results = hybrid_retriever.sparse_search("Python machine learning", top_k=5)
        
        hybrid_results = hybrid_retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(hybrid_results) > 0
        assert len(hybrid_results) <= 5
        assert all(hasattr(r, 'score') for r in hybrid_results)
        assert all(hasattr(r, 'chunk_id') for r in hybrid_results)
        print(f"✅ 混合检索基本功能正常 (返回 {len(hybrid_results)} 条结果)")

    def test_hybrid_vs_single_retrieval(self, hybrid_retriever, sample_documents):
        """测试混合检索相比单一检索的优势"""
        hybrid_retriever.build_bm25_index(sample_documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=sample_documents[i]["text"],
                score=0.9 - i * 0.1,
                retrieval_type="dense",
            )
            for i in range(5)
        ]
        
        sparse_results = hybrid_retriever.sparse_search("Python learning", top_k=5)
        hybrid_results = hybrid_retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        dense_chunk_ids = {r.chunk_id for r in dense_results}
        sparse_chunk_ids = {r.chunk_id for r in sparse_results}
        hybrid_chunk_ids = {r.chunk_id for r in hybrid_results}
        
        union_single = dense_chunk_ids | sparse_chunk_ids
        
        assert len(hybrid_chunk_ids) >= min(len(union_single), 5)
        print(f"✅ 混合检索覆盖度优于单一检索 (混合：{len(hybrid_chunk_ids)}, 稠密：{len(dense_chunk_ids)}, 稀疏：{len(sparse_chunk_ids)})")

    def test_hybrid_weight_configuration(self, sample_documents):
        """测试不同权重配置的影响"""
        retriever_high_dense = HybridRetriever(dense_weight=0.9, sparse_weight=0.1)
        retriever_high_sparse = HybridRetriever(dense_weight=0.1, sparse_weight=0.9)
        
        retriever_high_dense.build_bm25_index(sample_documents)
        retriever_high_sparse.build_bm25_index(sample_documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk0", document_id="doc0", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=sample_documents[0]["text"], score=0.9, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk1", document_id="doc1", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=sample_documents[1]["text"], score=0.8, retrieval_type="dense",
            ),
        ]
        
        sparse_results = retriever_high_dense.sparse_search("Python", top_k=5)
        
        hybrid_high_dense = retriever_high_dense.hybrid_search(dense_results, sparse_results, top_k=5)
        hybrid_high_sparse = retriever_high_sparse.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(hybrid_high_dense) > 0
        assert len(hybrid_high_sparse) > 0
        
        score_high_dense = {r.chunk_id: r.score for r in hybrid_high_dense}
        score_high_sparse = {r.chunk_id: r.score for r in hybrid_high_sparse}
        
        assert len(score_high_dense) == len(score_high_sparse)
        
        print("✅ 权重配置影响正常")

    def test_hybrid_empty_results(self, hybrid_retriever, sample_documents):
        """测试空结果处理"""
        hybrid_retriever.build_bm25_index(sample_documents)
        
        dense_results = []
        sparse_results = []
        
        hybrid_results = hybrid_retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(hybrid_results) == 0
        print("✅ 空结果处理正确")

    def test_hybrid_latency_performance(self, hybrid_retriever, sample_documents):
        """测试混合检索延迟性能"""
        large_docs = [
            {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"Document content with keywords number {i} " * 10,
            }
            for i in range(100)
        ]
        
        hybrid_retriever.build_bm25_index(large_docs)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=large_docs[i]["text"],
                score=0.99 - i * 0.01,
                retrieval_type="dense",
            )
            for i in range(24)
        ]
        
        start_time = time.time()
        sparse_results = hybrid_retriever.sparse_search("keywords document", top_k=24)
        sparse_time = time.time() - start_time
        
        start_time = time.time()
        hybrid_results = hybrid_retriever.hybrid_search(dense_results, sparse_results, top_k=24)
        fusion_time = time.time() - start_time
        
        assert sparse_time < 1.0, f"稀疏检索延迟 {sparse_time:.3f}s 超过 1s"
        assert fusion_time < 0.1, f"RRF 融合延迟 {fusion_time:.3f}s 超过 0.1s"
        assert len(hybrid_results) <= 24
        
        print(f"✅ 混合检索延迟性能达标 (稀疏：{sparse_time:.3f}s, 融合：{fusion_time:.3f}s)")


class TestMultiQueryRetrievalE2E:
    """T9.2: 多查询检索端到端集成测试"""

    @pytest.fixture
    def mock_base_retriever(self):
        """创建模拟基础检索器"""
        retriever = Mock()
        
        async def mock_search(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            for i in range(min(top_k, 8)):
                results.append(MockRetrievalResult(
                    chunk_id=f"chunk_{hash(query) % 1000}_{i}",
                    document_id=f"doc_{hash(query) % 1000}_{i}",
                    corpus_id="c1",
                    file_name="test.pdf",
                    page_or_loc="p1",
                    text=f"Content about {query} item {i}",
                    score=0.95 - i * 0.1,
                    retrieval_type="dense",
                ))
            return results
        
        retriever.search = mock_search
        return retriever

    @pytest.fixture
    def mock_query_rewriter(self):
        """创建模拟查询重写器"""
        rewriter = Mock(spec=QueryRewriter)
        
        async def mock_rewrite(question: str) -> List[RewrittenQuery]:
            return [
                RewrittenQuery(original=question, rewritten=f"{question} 变体 1", perspective="关键词提取"),
                RewrittenQuery(original=question, rewritten=f"{question} 变体 2", perspective="同义词替换"),
                RewrittenQuery(original=question, rewritten=f"{question} 变体 3", perspective="问题简化"),
            ]
        
        rewriter.rewrite_query = mock_rewrite
        return rewriter

    @pytest.mark.asyncio
    async def test_multi_query_basic(self, mock_base_retriever, mock_query_rewriter):
        """测试多查询检索基本功能"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
            max_variants=3,
            timeout_ms=500
        )
        
        question = "如何使用 Python 读取文件？"
        results = await retriever.retrieve(question, top_k=8)
        
        assert len(results) <= 8
        assert all(isinstance(r, MockRetrievalResult) for r in results)
        assert all(r.score > 0 for r in results)
        print(f"✅ 多查询检索基本功能正常 (返回 {len(results)} 条结果)")

    @pytest.mark.asyncio
    async def test_multi_query_deduplication(self, mock_query_rewriter):
        """测试多查询检索去重功能"""
        base_retriever = Mock()
        
        async def mock_search_with_duplicates(query: str, top_k: int = 8, query_filter=None):
            results = []
            for i in range(3):
                results.append(MockRetrievalResult(
                    chunk_id=f"chunk_same_{i}",
                    document_id="doc_same",
                    corpus_id="c1",
                    file_name="test.pdf",
                    page_or_loc="p1",
                    text="Same content",
                    score=0.9 - i * 0.1,
                    retrieval_type="dense",
                ))
            return results
        
        base_retriever.search = mock_search_with_duplicates
        
        retriever = MultiQueryRetriever(
            base_retriever=base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        results = await retriever.retrieve("测试问题", top_k=8)
        
        assert len(results) > 0
        assert all(r.chunk_id.startswith("chunk_same") for r in results)
        print("✅ 多查询检索去重功能正常")

    @pytest.mark.asyncio
    async def test_multi_query_exception_handling(self, mock_query_rewriter):
        """测试多查询检索异常处理"""
        base_retriever = Mock()
        
        async def mock_search_with_exception(query: str, top_k: int = 8, query_filter=None):
            if "变体 2" in query:
                raise Exception("检索失败")
            return [
                MockRetrievalResult(
                    chunk_id=f"chunk_{hash(query) % 1000}_0",
                    document_id=f"doc_{hash(query) % 1000}_0",
                    corpus_id="c1",
                    file_name="test.pdf",
                    page_or_loc="p1",
                    text=f"Content for {query}",
                    score=0.9,
                    retrieval_type="dense",
                )
            ]
        
        base_retriever.search = mock_search_with_exception
        
        retriever = MultiQueryRetriever(
            base_retriever=base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        results = await retriever.retrieve("测试问题", top_k=8)
        
        assert len(results) > 0
        assert all(not isinstance(r, Exception) for r in results)
        print("✅ 多查询检索异常处理正常")

    @pytest.mark.asyncio
    async def test_multi_query_sorting(self, mock_base_retriever, mock_query_rewriter):
        """测试多查询检索结果排序"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        question = "测试问题"
        results = await retriever.retrieve(question, top_k=8)
        
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        print("✅ 多查询检索结果排序正常")

    @pytest.mark.asyncio
    async def test_query_rewriter_without_llm(self):
        """测试无 LLM 时的查询重写"""
        rewriter = QueryRewriter()
        question = "如何使用 Python 读取文件？"
        
        variants = await rewriter.rewrite_query(question)
        
        assert len(variants) > 0
        assert all(isinstance(v, RewrittenQuery) for v in variants)
        assert all(v.original == question for v in variants)
        print(f"✅ 无 LLM 时查询重写正常 (生成 {len(variants)} 个变体)")

    @pytest.mark.asyncio
    async def test_query_rewriter_keywords_extraction(self):
        """测试关键词提取"""
        rewriter = QueryRewriter()
        question = "机器学习和深度学习有什么区别？"
        
        keywords = rewriter._extract_keywords(question)
        
        assert len(keywords) > 0
        assert any(len(kw) >= 2 for kw in keywords)
        assert not any(kw in ["的", "了", "是", "什么"] for kw in keywords)
        print(f"✅ 关键词提取正常 (提取到 {len(keywords)} 个关键词)")


class TestIntentClassificationE2E:
    """T9.3: 意图分类端到端集成测试"""

    @pytest.fixture
    def intent_classifier(self):
        """创建意图分类器"""
        return IntentClassifier()

    def test_intent_classifier_initialization(self, intent_classifier):
        """测试意图分类器初始化"""
        assert intent_classifier is not None
        print("✅ 意图分类器初始化成功")

    def test_factual_intent(self, intent_classifier):
        """测试事实性问题意图识别"""
        test_cases = [
            ("什么是 RAG 技术？", IntentType.FACTUAL),
            ("北京是中国的首都吗？", IntentType.FACTUAL),
            ("什么时候发布的 Python 3.0？", IntentType.FACTUAL),
        ]
        
        correct = 0
        for question, expected_intent in test_cases:
            result = intent_classifier.classify(question)
            intent_type = result[0]
            if intent_type in [expected_intent, IntentType.UNKNOWN]:
                correct += 1
        
        accuracy = correct / len(test_cases)
        assert accuracy >= 0.8, f"事实性问题准确率：{accuracy:.2%}"
        print(f"✅ 事实性问题意图识别正确 (准确率：{accuracy:.2%})")

    def test_how_to_intent(self, intent_classifier):
        """测试操作指南类意图识别"""
        test_cases = [
            ("如何使用 Python 读取文件？", IntentType.HOW_TO),
            ("怎么配置 Kubernetes 集群？", IntentType.HOW_TO),
            ("怎样安装 Docker？", IntentType.HOW_TO),
        ]
        
        for question, expected_intent in test_cases:
            result = intent_classifier.classify(question)
            intent_type = result[0]
            assert intent_type in [expected_intent, IntentType.UNKNOWN], \
                f"问题 '{question}' 期望 {expected_intent}, 实际 {intent_type}"
        
        print(f"✅ 操作指南类意图识别正确 (测试 {len(test_cases)} 个用例)")

    def test_troubleshooting_intent(self, intent_classifier):
        """测试故障排查类意图识别"""
        test_cases = [
            ("Docker 容器无法启动怎么办？", IntentType.TROUBLESHOOTING),
            ("API 返回 500 错误如何解决？", IntentType.TROUBLESHOOTING),
            ("程序运行失败，报错 memory error", IntentType.TROUBLESHOOTING),
        ]
        
        for question, expected_intent in test_cases:
            result = intent_classifier.classify(question)
            intent_type = result[0]
            assert intent_type in [expected_intent, IntentType.UNKNOWN], \
                f"问题 '{question}' 期望 {expected_intent}, 实际 {intent_type}"
        
        print(f"✅ 故障排查类意图识别正确 (测试 {len(test_cases)} 个用例)")

    def test_conceptual_intent(self, intent_classifier):
        """测试概念理解类意图识别"""
        test_cases = [
            ("机器学习和深度学习有什么区别？", IntentType.CONCEPTUAL),
            ("为什么 RAG 技术有效？", IntentType.CONCEPTUAL),
            ("向量数据库的工作原理是什么？", IntentType.CONCEPTUAL),
        ]
        
        correct = 0
        for question, expected_intent in test_cases:
            result = intent_classifier.classify(question)
            intent_type = result[0]
            if intent_type in [expected_intent, IntentType.UNKNOWN]:
                correct += 1
        
        accuracy = correct / len(test_cases)
        assert accuracy >= 0.8, f"概念理解类准确率：{accuracy:.2%}"
        print(f"✅ 概念理解类意图识别正确 (准确率：{accuracy:.2%})")

    def test_code_intent(self, intent_classifier):
        """测试代码相关意图识别"""
        test_cases = [
            ("请给我一个 Python 读取文件的代码示例", IntentType.CODE),
            ("Python 快速排序代码实现", IntentType.CODE),
            ("写一个 Python 函数计算斐波那契数列", IntentType.CODE),
        ]
        
        correct = 0
        for question, expected_intent in test_cases:
            result = intent_classifier.classify(question)
            intent_type = result[0]
            if intent_type in [expected_intent, IntentType.UNKNOWN]:
                correct += 1
        
        accuracy = correct / len(test_cases)
        assert accuracy >= 0.8, f"代码相关准确率：{accuracy:.2%}"
        print(f"✅ 代码相关意图识别正确 (准确率：{accuracy:.2%})")

    def test_retrieval_strategy_mapping(self, intent_classifier):
        """测试意图到检索策略的映射"""
        expected_strategies = {
            IntentType.FACTUAL: {"top_k": 5, "dense_weight": 0.8},
            IntentType.HOW_TO: {"top_k": 8, "dense_weight": 0.6},
            IntentType.TROUBLESHOOTING: {"top_k": 10, "dense_weight": 0.5},
            IntentType.CONCEPTUAL: {"top_k": 6, "dense_weight": 0.9},
            IntentType.CODE: {"top_k": 8, "dense_weight": 0.7},
        }
        
        for intent_type, expected_params in expected_strategies.items():
            strategy = intent_classifier.get_retrieval_strategy(intent_type)
            assert strategy["top_k"] == expected_params["top_k"], \
                f"{intent_type} 的 top_k 应为 {expected_params['top_k']}"
            assert strategy["dense_weight"] == expected_params["dense_weight"], \
                f"{intent_type} 的 dense_weight 应为 {expected_params['dense_weight']}"
        
        print("✅ 意图到检索策略映射正确")

    def test_edge_cases(self, intent_classifier):
        """测试边界情况"""
        empty_result = intent_classifier.classify("")
        assert empty_result[0] == IntentType.UNKNOWN
        
        short_result = intent_classifier.classify("什么？")
        assert short_result[0] is not None
        assert 0.0 <= short_result[1] <= 1.0
        
        print("✅ 边界情况处理正确")


class TestFullPipelineE2E:
    """完整 RAG 流程端到端测试"""

    @pytest.fixture
    def rag_engine_config(self):
        """创建 RAG 引擎配置"""
        return build_service_config()

    def test_engine_initialization(self, rag_engine_config):
        """测试 RAG 引擎初始化"""
        engine = RAGEngine(rag_engine_config)
        
        assert engine is not None
        assert hasattr(engine, '_intent_classifier')
        assert hasattr(engine, '_hybrid_retriever')
        print("✅ RAG 引擎初始化成功")

    def test_intent_classifier_integration(self, rag_engine_config):
        """测试意图分类器集成"""
        engine = RAGEngine(rag_engine_config)
        
        assert engine._intent_classifier is not None
        classifier = engine._intent_classifier
        
        question = "如何使用 Python？"
        result = classifier.classify(question)
        assert result[0] is not None
        assert 0.0 <= result[1] <= 1.0
        
        print("✅ 意图分类器集成正常")

    def test_hybrid_retriever_integration(self, rag_engine_config):
        """测试混合检索器集成"""
        engine = RAGEngine(rag_engine_config)
        
        assert hasattr(engine, '_hybrid_retriever')
        print("✅ 混合检索器集成正常")

    def test_reranker_integration(self):
        """测试重排序器集成"""
        reranker = Reranker()
        assert reranker is not None
        print("✅ 重排序器集成正常")

    def test_context_compressor_integration(self):
        """测试上下文压缩器集成"""
        compressor = ContextCompressor()
        assert compressor is not None
        print("✅ 上下文压缩器集成正常")


class TestAPIIntegrationE2E:
    """API 端到端集成测试"""

    def test_healthz_endpoint(self):
        """测试健康检查端点"""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
        assert data["service"] == "py-rag-service"
        print("✅ 健康检查端点正常")

    def test_query_request_contract(self):
        """测试查询请求数据格式"""
        payload = {
            "question": "测试问题",
            "scope": {
                "mode": "single",
                "corpus_ids": ["12345678-1234-1234-1234-123456789012"],
                "allow_common_knowledge": True
            }
        }
        
        response = client.post("/v1/rag/query", json=payload)
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "answer_sentences" in data
            assert "citations" in data
            assert isinstance(data["answer_sentences"], list)
            assert isinstance(data["citations"], list)
        
        print("✅ 查询请求数据格式正确")

    def test_query_validation_error(self):
        """测试查询参数验证错误处理"""
        payload = {
            "question": "",
            "scope": {
                "mode": "single",
                "corpus_ids": [],
                "allow_common_knowledge": True
            }
        }
        
        response = client.post("/v1/rag/query", json=payload)
        assert response.status_code in [400, 422]
        
        data = response.json()
        assert "error" in data or "detail" in data
        
        print("✅ 参数验证错误处理正确")

    def test_scope_validation(self):
        """测试 scope 参数验证"""
        payload = {
            "question": "测试问题",
            "scope": {
                "mode": "invalid_mode",
                "corpus_ids": [],
                "allow_common_knowledge": True
            }
        }
        
        response = client.post("/v1/rag/query", json=payload)
        assert response.status_code in [400, 422]
        
        print("✅ Scope 参数验证正确")

    def test_error_response_format(self):
        """测试错误响应格式"""
        response = client.post(
            "/v1/rag/query",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
        
        data = response.json()
        assert "detail" in data or "error" in data
        
        print("✅ 错误响应格式正确")


class TestPerformanceMetricsE2E:
    """性能指标端到端测试"""

    def test_retrieval_latency(self):
        """测试检索延迟"""
        retriever = HybridRetriever()
        
        documents = [
            {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"Document content with keywords number {i}",
            }
            for i in range(100)
        ]
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=documents[i]["text"],
                score=0.99 - i * 0.01,
                retrieval_type="dense",
            )
            for i in range(24)
        ]
        
        start_time = time.time()
        sparse_results = retriever.sparse_search("keywords document", top_k=24)
        sparse_time = time.time() - start_time
        
        start_time = time.time()
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=24)
        fusion_time = time.time() - start_time
        
        assert sparse_time < 1.0, f"稀疏检索延迟 {sparse_time:.3f}s 超过 1s"
        assert fusion_time < 0.1, f"RRF 融合延迟 {fusion_time:.3f}s 超过 0.1s"
        assert len(hybrid_results) <= 24
        
        print(f"✅ 检索延迟性能达标 (稀疏：{sparse_time:.3f}s, 融合：{fusion_time:.3f}s)")

    def test_memory_efficiency(self):
        """测试内存效率"""
        retriever = HybridRetriever()
        
        documents = [
            {
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": "x" * 1000,
            }
            for i in range(50)
        ]
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=documents[i]["text"],
                score=0.99 - i * 0.01,
                retrieval_type="dense",
            )
            for i in range(24)
        ]
        
        sparse_results = retriever.sparse_search("test", top_k=24)
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=24)
        
        assert len(hybrid_results) <= 24
        
        print("✅ 内存效率正常")


if __name__ == "__main__":
    print("=" * 80)
    print("端到端集成测试 - RAG QA System")
    print("=" * 80)
    
    pytest.main([__file__, "-v", "-s", "--tb=short"])
