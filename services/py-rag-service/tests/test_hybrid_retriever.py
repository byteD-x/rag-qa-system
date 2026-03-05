"""
混合检索器单元测试
测试 RRF 算法、权重配置和三种检索模式
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hybrid_retriever import HybridRetriever, RetrievalResult
from app.config import RAGOptimizationConfig


class TestRRFAlgorithm:
    """测试 RRF (Reciprocal Rank Fusion) 算法"""

    def test_rrf_basic_fusion(self):
        """测试基本的 RRF 融合"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk1",
                document_id="doc1",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content 1",
                score=0.9,
                retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk2",
                document_id="doc2",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content 2",
                score=0.8,
                retrieval_type="dense",
            ),
        ]
        
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk2",
                document_id="doc2",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content 2",
                score=0.95,
                retrieval_type="sparse",
            ),
            RetrievalResult(
                chunk_id="chunk3",
                document_id="doc3",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content 3",
                score=0.85,
                retrieval_type="sparse",
            ),
        ]
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=3)
        
        assert len(merged) == 3
        assert all(r.retrieval_type == "hybrid" for r in merged)
        
        chunk2 = next(r for r in merged if r.chunk_id == "chunk2")
        rank_dense = 2
        rank_sparse = 1
        expected_score = (1.0 / (rank_dense + 60)) * 0.7 + (1.0 / (rank_sparse + 60)) * 0.3
        assert abs(chunk2.score - expected_score) < 0.0001

    def test_rrf_empty_dense_results(self):
        """测试稠密结果为空的情况"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        dense_results = []
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk1",
                document_id="doc1",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content",
                score=0.9,
                retrieval_type="sparse",
            ),
        ]
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(merged) == 1
        assert merged[0].chunk_id == "chunk1"
        assert merged[0].retrieval_type == "hybrid"

    def test_rrf_empty_sparse_results(self):
        """测试稀疏结果为空的情况"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk1",
                document_id="doc1",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test content",
                score=0.9,
                retrieval_type="dense",
            ),
        ]
        sparse_results = []
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(merged) == 1
        assert merged[0].chunk_id == "chunk1"

    def test_rrf_no_overlap(self):
        """测试两个结果集没有重叠"""
        retriever = HybridRetriever(dense_weight=0.5, sparse_weight=0.5)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk1",
                document_id="doc1",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test 1",
                score=0.9,
                retrieval_type="dense",
            ),
        ]
        
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk2",
                document_id="doc2",
                corpus_id="corpus1",
                file_name="test.txt",
                page_or_loc="page1",
                text="test 2",
                score=0.95,
                retrieval_type="sparse",
            ),
        ]
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(merged) == 2
        chunk_ids = {r.chunk_id for r in merged}
        assert chunk_ids == {"chunk1", "chunk2"}

    def test_rrf_top_k_limit(self):
        """测试 top_k 限制"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        dense_results = [
            RetrievalResult(chunk_id=f"dense_{i}", document_id=f"doc{i}", corpus_id="c1",
                          file_name="test.txt", page_or_loc="p1", text=f"text{i}",
                          score=0.9 - i * 0.1, retrieval_type="dense")
            for i in range(10)
        ]
        
        sparse_results = [
            RetrievalResult(chunk_id=f"sparse_{i}", document_id=f"doc{i+10}", corpus_id="c1",
                          file_name="test.txt", page_or_loc="p1", text=f"text{i+10}",
                          score=0.9 - i * 0.1, retrieval_type="sparse")
            for i in range(10)
        ]
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(merged) == 5

    def test_rrf_score_ordering(self):
        """测试 RRF 分数排序正确性"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk1", document_id="doc1", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text1",
                score=0.95, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk2", document_id="doc2", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text2",
                score=0.8, retrieval_type="dense",
            ),
        ]
        
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk1", document_id="doc1", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text1",
                score=0.9, retrieval_type="sparse",
            ),
        ]
        
        merged = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert merged[0].chunk_id == "chunk1"
        assert merged[0].score > merged[1].score


class TestWeightConfiguration:
    """测试权重配置"""

    def test_default_weights(self):
        """测试默认权重"""
        retriever = HybridRetriever()
        
        assert retriever.dense_weight == 0.7
        assert retriever.sparse_weight == 0.3

    def test_custom_weights(self):
        """测试自定义权重"""
        retriever = HybridRetriever(dense_weight=0.6, sparse_weight=0.4)
        
        assert retriever.dense_weight == 0.6
        assert retriever.sparse_weight == 0.4

    def test_invalid_weights_sum(self):
        """测试权重和验证"""
        with pytest.raises(ValueError, match="dense_weight \\+ sparse_weight must equal 1.0"):
            HybridRetriever(dense_weight=0.5, sparse_weight=0.6)

    def test_config_from_env(self):
        """测试从环境变量加载配置"""
        with patch.dict(os.environ, {
            "HYBRID_SEARCH_DENSE_WEIGHT": "0.8",
            "HYBRID_SEARCH_SPARSE_WEIGHT": "0.2",
        }):
            config = RAGOptimizationConfig.from_env()
            retriever = HybridRetriever(config=config)
            
            assert retriever.dense_weight == 0.8
            assert retriever.sparse_weight == 0.2

    def test_config_object_priority(self):
        """测试配置对象优先级高于直接参数"""
        config = RAGOptimizationConfig(
            hybrid_search_dense_weight=0.9,
            hybrid_search_sparse_weight=0.1,
        )
        
        retriever = HybridRetriever(
            dense_weight=0.5,
            sparse_weight=0.5,
            config=config,
        )
        
        assert retriever.dense_weight == 0.9
        assert retriever.sparse_weight == 0.1

    def test_weight_influence_on_scores(self):
        """测试权重对最终分数的影响"""
        retriever_high_dense = HybridRetriever(dense_weight=0.9, sparse_weight=0.1)
        retriever_balanced = HybridRetriever(dense_weight=0.5, sparse_weight=0.5)
        
        # 创建不同排名的结果
        dense_results = [
            RetrievalResult(
                chunk_id="chunk_a", document_id="doc_a", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text a",
                score=0.95, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk_b", document_id="doc_b", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text b",
                score=0.80, retrieval_type="dense",
            ),
        ]
        
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk_b", document_id="doc_b", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text b",
                score=0.90, retrieval_type="sparse",
            ),
            RetrievalResult(
                chunk_id="chunk_c", document_id="doc_c", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1", text="text c",
                score=0.85, retrieval_type="sparse",
            ),
        ]
        
        merged_high_dense = retriever_high_dense.hybrid_search(dense_results, sparse_results, top_k=3)
        merged_balanced = retriever_balanced.hybrid_search(dense_results, sparse_results, top_k=3)
        
        # 验证不同权重会导致不同的排序或分数
        high_dense_scores = {r.chunk_id: r.score for r in merged_high_dense}
        balanced_scores = {r.chunk_id: r.score for r in merged_balanced}
        
        # chunk_b 在两种权重下应该有不同分数
        assert abs(high_dense_scores["chunk_b"] - balanced_scores["chunk_b"]) > 0.0001


class TestRetrievalModes:
    """测试三种检索模式"""

    def test_sparse_mode(self):
        """测试稀疏检索模式"""
        retriever = HybridRetriever()
        
        # BM25 需要足够大的文档集合才能正常工作
        documents = []
        for i in range(20):
            if i < 5:
                text = "python programming language tutorial"
            elif i < 10:
                text = "java programming language guide"
            else:
                text = "web development javascript frontend"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        results = retriever.search(
            query="python programming",
            mode="sparse",
            top_k=5,
        )
        
        assert len(results) >= 1
        assert all(r.retrieval_type == "sparse" for r in results)
        assert any("python" in r.text.lower() for r in results)

    def test_dense_mode(self):
        """测试稠密检索模式"""
        retriever = HybridRetriever()
        
        mock_client = MagicMock()
        mock_point = MagicMock()
        mock_point.id = "chunk1"
        mock_point.score = 0.9
        mock_point.payload = {
            "document_id": "doc1",
            "corpus_id": "c1",
            "file_name": "test.txt",
            "page_or_loc": "p1",
            "text": "test content",
        }
        mock_client.query_points.return_value = MagicMock(points=[mock_point])
        
        results = retriever.search(
            query="test",
            mode="dense",
            qdrant_client=mock_client,
            collection_name="test_collection",
            query_vector=[0.1, 0.2, 0.3],
            top_k=5,
        )
        
        assert len(results) == 1
        assert results[0].retrieval_type == "dense"
        assert results[0].score == 0.9

    def test_hybrid_mode(self):
        """测试混合检索模式"""
        retriever = HybridRetriever()
        
        documents = [
            {"chunk_id": "chunk1", "document_id": "doc1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "python programming"},
        ]
        retriever.build_bm25_index(documents)
        
        mock_client = MagicMock()
        mock_point = MagicMock()
        mock_point.id = "chunk1"
        mock_point.score = 0.85
        mock_point.payload = {
            "document_id": "doc1",
            "corpus_id": "c1",
            "file_name": "test.txt",
            "page_or_loc": "p1",
            "text": "python programming",
        }
        mock_client.query_points.return_value = MagicMock(points=[mock_point])
        
        results = retriever.search(
            query="python",
            mode="hybrid",
            qdrant_client=mock_client,
            collection_name="test_collection",
            query_vector=[0.1, 0.2, 0.3],
            top_k=5,
        )
        
        assert len(results) == 1
        assert results[0].retrieval_type == "hybrid"

    def test_dense_mode_missing_params(self):
        """测试稠密模式缺少必要参数"""
        retriever = HybridRetriever()
        
        with pytest.raises(ValueError, match="dense mode requires"):
            retriever.search(query="test", mode="dense")

    def test_hybrid_mode_missing_params(self):
        """测试混合模式缺少必要参数"""
        retriever = HybridRetriever()
        
        with pytest.raises(ValueError, match="hybrid mode requires"):
            retriever.search(query="test", mode="hybrid")

    def test_invalid_mode(self):
        """测试无效模式"""
        retriever = HybridRetriever()
        
        with pytest.raises(ValueError, match="Invalid mode"):
            retriever.search(query="test", mode="invalid")


class TestBM25Index:
    """测试 BM25 索引构建"""

    def test_build_bm25_index(self):
        """测试 BM25 索引构建"""
        retriever = HybridRetriever()
        
        documents = [
            {"chunk_id": "chunk1", "text": "python programming language"},
            {"chunk_id": "chunk2", "text": "java programming language"},
            {"chunk_id": "chunk3", "text": "rust programming language"},
        ]
        
        retriever.build_bm25_index(documents)
        
        assert retriever._bm25_index is not None
        assert len(retriever._documents) == 3

    def test_sparse_search_empty_index(self):
        """测试空索引的稀疏检索"""
        retriever = HybridRetriever()
        
        results = retriever.sparse_search("test query")
        
        assert len(results) == 0

    def test_sparse_search_results(self):
        """测试稀疏检索结果"""
        retriever = HybridRetriever()
        
        documents = [
            {"chunk_id": "chunk1", "document_id": "doc1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "machine learning algorithms"},
            {"chunk_id": "chunk2", "document_id": "doc2", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "deep learning neural networks"},
            {"chunk_id": "chunk3", "document_id": "doc3", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "data structures algorithms"},
        ]
        
        retriever.build_bm25_index(documents)
        
        results = retriever.sparse_search("learning algorithms", top_k=2)
        
        assert len(results) <= 2
        assert all("learning" in r.text.lower() or "algorithms" in r.text.lower() for r in results)


class TestRetrievalResult:
    """测试 RetrievalResult 数据类"""

    def test_result_creation(self):
        """测试检索结果创建"""
        result = RetrievalResult(
            chunk_id="chunk1",
            document_id="doc1",
            corpus_id="corpus1",
            file_name="test.txt",
            page_or_loc="page1",
            text="test content",
            score=0.95,
            retrieval_type="hybrid",
        )
        
        assert result.chunk_id == "chunk1"
        assert result.score == 0.95
        assert result.retrieval_type == "hybrid"

    def test_result_immutability(self):
        """测试检索结果不可变性"""
        result = RetrievalResult(
            chunk_id="chunk1", document_id="doc1", corpus_id="c1",
            file_name="test.txt", page_or_loc="p1", text="text",
            score=0.9, retrieval_type="dense",
        )
        
        with pytest.raises(Exception):
            result.score = 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
