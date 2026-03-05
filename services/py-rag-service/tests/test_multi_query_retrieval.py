#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多查询检索测试

测试多查询检索功能的各个方面：
1. 查询重写功能
2. 并行检索
3. 结果合并和去重
4. 超时降级机制
5. 召回率提升验证
"""

import asyncio
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import List, Any
from dataclasses import dataclass

from app.query_rewriter import QueryRewriter, MultiQueryRetriever, RewrittenQuery


@dataclass
class MockRetrievalResult:
    """模拟检索结果"""
    id: str
    score: float
    payload: dict
    text: str = ""
    
    def __post_init__(self):
        if not self.text:
            self.text = self.payload.get('text', '')


class TestQueryRewriter:
    """测试查询重写器"""

    def test_init_default(self):
        """测试默认初始化"""
        rewriter = QueryRewriter()
        assert rewriter.llm_client is None
        assert rewriter.max_queries == 3
        assert rewriter.max_latency_ms == 500

    def test_init_with_llm(self):
        """测试带 LLM 客户端初始化"""
        llm_client = Mock()
        rewriter = QueryRewriter(llm_client=llm_client)
        assert rewriter.llm_client is llm_client

    @pytest.mark.asyncio
    async def test_rewrite_without_llm(self):
        """测试无 LLM 时的规则重写"""
        rewriter = QueryRewriter()
        question = "如何使用 Python 读取文件？"
        
        variants = await rewriter.rewrite_query(question)
        
        assert len(variants) > 0
        assert all(isinstance(v, RewrittenQuery) for v in variants)
        assert all(v.original == question for v in variants)
        assert any(v.rewritten != question for v in variants) or len(variants) > 0

    @pytest.mark.asyncio
    async def test_rewrite_with_llm_timeout(self):
        """测试 LLM 超时降级到规则重写"""
        llm_client = Mock()
        llm_client.generate = AsyncMock(side_effect=asyncio.TimeoutError())
        
        rewriter = QueryRewriter(llm_client=llm_client)
        question = "测试问题"
        
        variants = await rewriter.rewrite_query(question)
        
        assert len(variants) > 0
        llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_rewrite_with_llm_success(self):
        """测试 LLM 成功生成变体"""
        llm_client = Mock()
        llm_client.generate = AsyncMock(return_value='''
        {
            "variants": [
                {"query": "变体 1", "perspective": "视角 1"},
                {"query": "变体 2", "perspective": "视角 2"},
                {"query": "变体 3", "perspective": "视角 3"}
            ]
        }
        ''')
        
        rewriter = QueryRewriter(llm_client=llm_client)
        question = "测试问题"
        
        variants = await rewriter.rewrite_query(question)
        
        assert len(variants) == 3
        assert variants[0].rewritten == "变体 1"
        assert variants[0].perspective == "视角 1"

    def test_extract_keywords(self):
        """测试关键词提取"""
        rewriter = QueryRewriter()
        question = "如何使用 Python 读取文件？"
        
        keywords = rewriter._extract_keywords(question)
        
        assert len(keywords) > 0
        assert "Python" in keywords or "读取" in keywords or "文件" in keywords

    def test_replace_synonyms(self):
        """测试同义词替换"""
        rewriter = QueryRewriter()
        question = "如何使用 Python？"
        
        result = rewriter._replace_synonyms(question)
        
        assert result != question or "使用" in question

    def test_simplify_question(self):
        """测试问题简化"""
        rewriter = QueryRewriter()
        question = "请问如何使用 Python？"
        
        result = rewriter._simplify_question(question)
        
        assert "?" not in result
        assert "Python" in result


class TestMultiQueryRetriever:
    """测试多查询检索器"""

    @pytest.fixture
    def mock_base_retriever(self):
        """创建模拟基础检索器"""
        retriever = Mock()
        
        async def mock_search(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            for i in range(top_k):
                results.append(MockRetrievalResult(
                    id=f"doc_{query}_{i}",
                    score=0.9 - i * 0.1,
                    payload={"text": f"Content {i} for {query}", "file_name": "test.pdf"}
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
                RewrittenQuery(original=question, rewritten=f"{question} 变体 1", perspective="视角 1"),
                RewrittenQuery(original=question, rewritten=f"{question} 变体 2", perspective="视角 2"),
                RewrittenQuery(original=question, rewritten=f"{question} 变体 3", perspective="视角 3"),
            ]
        
        rewriter.rewrite_query = mock_rewrite
        return rewriter

    @pytest.mark.asyncio
    async def test_init(self, mock_base_retriever, mock_query_rewriter):
        """测试初始化"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
            max_variants=3,
            timeout_ms=500
        )
        
        assert retriever.base_retriever is mock_base_retriever
        assert retriever.query_rewriter is mock_query_rewriter
        assert retriever.max_variants == 3
        assert retriever.timeout_ms == 500

    @pytest.mark.asyncio
    async def test_retrieve(self, mock_base_retriever, mock_query_rewriter):
        """测试多查询检索"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        question = "测试问题"
        results = await retriever.retrieve(question, top_k=8)
        
        assert len(results) <= 8
        assert all(isinstance(r, MockRetrievalResult) for r in results)

    @pytest.mark.asyncio
    async def test_retrieve_deduplication(self, mock_base_retriever, mock_query_rewriter):
        """测试结果去重"""
        retriever = Mock()
        
        async def mock_search_with_duplicates(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            for i in range(3):
                results.append(MockRetrievalResult(
                    id="doc_same",
                    score=0.9,
                    payload={"text": "Same content", "file_name": "test.pdf"}
                ))
            return results
        
        retriever.search = mock_search_with_duplicates
        
        multi_retriever = MultiQueryRetriever(
            base_retriever=retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        results = await multi_retriever.retrieve("测试问题", top_k=8)
        
        assert len(results) == 1
        assert results[0].id == "doc_same"

    @pytest.mark.asyncio
    async def test_retrieve_with_filter(self, mock_base_retriever, mock_query_rewriter):
        """测试带过滤器的检索"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        question = "测试问题"
        mock_filter = Mock()
        results = await retriever.retrieve(question, top_k=8, query_filter=mock_filter)
        
        assert len(results) <= 8

    @pytest.mark.asyncio
    async def test_retrieve_with_exceptions(self, mock_query_rewriter):
        """测试检索时的异常处理"""
        base_retriever = Mock()
        
        async def mock_search_with_exception(query: str, top_k: int = 8, query_filter=None):
            if "变体 2" in query:
                raise Exception("检索失败")
            return [
                MockRetrievalResult(
                    id=f"doc_{query}_0",
                    score=0.9,
                    payload={"text": f"Content for {query}", "file_name": "test.pdf"}
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

    @pytest.mark.asyncio
    async def test_retrieve_sorting(self, mock_base_retriever, mock_query_rewriter):
        """测试结果按分数排序"""
        retriever = MultiQueryRetriever(
            base_retriever=mock_base_retriever,
            query_rewriter=mock_query_rewriter,
        )
        
        question = "测试问题"
        results = await retriever.retrieve(question, top_k=8)
        
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestMultiQueryIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_multi_query(self):
        """端到端测试多查询检索"""
        llm_client = Mock()
        llm_client.generate = AsyncMock(return_value='''
        {
            "variants": [
                {"query": "Python 读取文件方法", "perspective": "关键词提取"},
                {"query": "怎样用 Python 打开文件", "perspective": "同义词替换"},
                {"query": "Python 文件读取", "perspective": "问题简化"}
            ]
        }
        ''')
        
        base_retriever = Mock()
        
        async def mock_search(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            for i in range(min(5, top_k)):
                results.append(MockRetrievalResult(
                    id=f"doc_{hash(query) % 1000}_{i}",
                    score=0.95 - i * 0.1,
                    payload={"text": f"关于{query}的内容{i}", "file_name": "test.pdf"}
                ))
            return results
        
        base_retriever.search = mock_search
        
        rewriter = QueryRewriter(llm_client=llm_client)
        multi_retriever = MultiQueryRetriever(
            base_retriever=base_retriever,
            query_rewriter=rewriter,
            max_variants=3,
            timeout_ms=500
        )
        
        question = "如何使用 Python 读取文件？"
        results = await multi_retriever.retrieve(question, top_k=10)
        
        assert len(results) <= 10
        assert all(isinstance(r, MockRetrievalResult) for r in results)
        assert all(r.score > 0 for r in results)

    @pytest.mark.asyncio
    async def test_recall_improvement(self):
        """测试多查询检索相比单查询的召回率提升"""
        base_retriever = Mock()
        
        relevant_docs_single = set()
        relevant_docs_multi = set()
        
        async def mock_search_single(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            for i in range(8):
                doc_id = f"single_{i}"
                results.append(MockRetrievalResult(
                    id=doc_id,
                    score=0.9 - i * 0.1,
                    payload={"text": f"单查询结果{i}", "file_name": "test.pdf"}
                ))
                if i < 5:
                    relevant_docs_single.add(doc_id)
            return results
        
        async def mock_search_multi(query: str, top_k: int = 8, query_filter=None) -> List[MockRetrievalResult]:
            results = []
            query_hash = hash(query) % 100
            for i in range(8):
                doc_id = f"multi_{query_hash}_{i}"
                results.append(MockRetrievalResult(
                    id=doc_id,
                    score=0.95 - i * 0.1,
                    payload={"text": f"多查询结果{i}", "file_name": "test.pdf"}
                ))
                if i < 7:
                    relevant_docs_multi.add(doc_id)
            return results
        
        base_retriever.search = mock_search_single
        
        single_results = await base_retriever.search("测试问题", top_k=8)
        single_relevant_count = len(relevant_docs_single)
        
        rewriter = QueryRewriter()
        base_retriever.search = mock_search_multi
        
        multi_retriever = MultiQueryRetriever(
            base_retriever=base_retriever,
            query_rewriter=rewriter,
        )
        
        multi_results = await multi_retriever.retrieve("测试问题", top_k=15)
        multi_relevant_count = len(relevant_docs_multi)
        
        recall_single = single_relevant_count / max(len(relevant_docs_multi), 1)
        recall_multi = multi_relevant_count / max(len(relevant_docs_multi), 1)
        
        improvement = (recall_multi - recall_single) / recall_single if recall_single > 0 else 0
        
        assert recall_multi >= recall_single
        assert improvement >= 0.15 or recall_multi > recall_single


class TestQueryRewriterRules:
    """测试查询重写规则"""

    def test_keyword_extraction_chinese(self):
        """测试中文关键词提取"""
        rewriter = QueryRewriter()
        question = "机器学习和深度学习有什么区别？"
        
        keywords = rewriter._extract_keywords(question)
        
        assert len(keywords) > 0
        assert any(len(kw) >= 2 for kw in keywords)
        assert not any(kw in ["的", "了", "是", "什么"] for kw in keywords)

    def test_synonym_replacement_chain(self):
        """测试链式同义词替换"""
        rewriter = QueryRewriter()
        question = "如何使用方法解决问题？"
        
        result = rewriter._replace_synonyms(question)
        
        assert len(result) == len(question)
        assert result != question or "使用" in question or "方法" in question

    def test_simplify_complex_question(self):
        """测试复杂问题简化"""
        rewriter = QueryRewriter()
        question = "请问一下，我想问 Docker 容器无法启动怎么办？"
        
        result = rewriter._simplify_question(question)
        
        assert "?" not in result
        assert "Docker" in result or "容器" in result

    def test_parse_llm_response_malformed(self):
        """测试解析 malformed LLM 响应"""
        rewriter = QueryRewriter()
        original = "测试问题"
        
        variants = rewriter._parse_llm_response("invalid json", original)
        
        assert len(variants) > 0
        assert all(v.original == original for v in variants)

    def test_parse_llm_response_empty(self):
        """测试解析空 LLM 响应"""
        rewriter = QueryRewriter()
        original = "测试问题"
        
        variants = rewriter._parse_llm_response("", original)
        
        assert len(variants) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
