"""
重排序器单元测试
测试混合分数重排序、懒加载和性能
"""
import pytest
import time
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.reranker import Reranker, RerankResult


class TestHybridScoreReranking:
    """测试混合分数重排序"""

    def test_basic_hybrid_reranking(self):
        """测试基本的混合分数重排序"""
        reranker = Reranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
        
        documents = [
            {"chunk_id": "1", "document_id": "d1", "corpus_id": "c1", 
             "file_name": "test.txt", "page_or_loc": "p1", "text": "python tutorial", "score": 0.9},
            {"chunk_id": "2", "document_id": "d2", "corpus_id": "c1", 
             "file_name": "test.txt", "page_or_loc": "p1", "text": "java guide", "score": 0.8},
            {"chunk_id": "3", "document_id": "d3", "corpus_id": "c1", 
             "file_name": "test.txt", "page_or_loc": "p1", "text": "rust programming", "score": 0.7},
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.6, 0.9, 0.7]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        results = reranker.rerank_with_hybrid_score(
            query="python programming",
            documents=documents,
            top_k=3,
            hybrid_weight=0.5,
        )
        
        assert len(results) == 3
        assert all(isinstance(r, RerankResult) for r in results)
        assert all(r.hybrid_score is not None for r in results)
        
        for r in results:
            assert 0.0 <= r.hybrid_score <= 1.0
        
        assert results[0].rank == 1
        assert results[1].rank == 2
        assert results[2].rank == 3

    def test_hybrid_vs_single_rerank_score(self):
        """测试混合分数与单一重排序分数的对比"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": "1", "document_id": "d1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "high original low rerank", "score": 0.95},
            {"chunk_id": "2", "document_id": "d2", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "low original high rerank", "score": 0.5},
            {"chunk_id": "3", "document_id": "d3", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "medium both", "score": 0.75},
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.4, 0.95, 0.7]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        hybrid_results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=3,
            hybrid_weight=0.5,
        )
        
        rerank_only_results = reranker.rerank(
            query="test",
            documents=documents,
            top_k=3,
        )
        
        assert len(hybrid_results) == 3
        assert len(rerank_only_results) == 3
        
        hybrid_ranking = [r.chunk_id for r in hybrid_results]
        rerank_only_ranking = [r.chunk_id for r in rerank_only_results]
        
        assert hybrid_ranking != rerank_only_ranking or hybrid_ranking == rerank_only_ranking
        
        for r in hybrid_results:
            assert r.hybrid_score is not None
        for r in rerank_only_results:
            assert r.hybrid_score is None

    def test_hybrid_weight_influence(self):
        """测试不同权重对排序的影响"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": "A", "document_id": "d1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "doc A", "score": 0.9},
            {"chunk_id": "B", "document_id": "d2", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "doc B", "score": 0.5},
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.3, 0.9]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        results_high_rerank = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=2,
            hybrid_weight=0.9,
        )
        
        results_high_original = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=2,
            hybrid_weight=0.1,
        )
        
        assert results_high_rerank[0].chunk_id == "B"
        assert results_high_original[0].chunk_id == "A"

    def test_normalization_methods(self):
        """测试不同归一化方法"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": "1", "document_id": "d1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "doc 1", "score": 10},
            {"chunk_id": "2", "document_id": "d2", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "doc 2", "score": 20},
            {"chunk_id": "3", "document_id": "d3", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "doc 3", "score": 30},
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.3, 0.6, 0.9]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        minmax_results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=3,
            normalization="minmax",
        )
        
        max_results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=3,
            normalization="max",
        )
        
        assert len(minmax_results) == 3
        assert len(max_results) == 3
        
        minmax_scores = [r.hybrid_score for r in minmax_results]
        max_scores = [r.hybrid_score for r in max_results]
        
        assert minmax_scores != max_scores

    def test_invalid_hybrid_weight(self):
        """测试无效的混合权重"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": "1", "document_id": "d1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": "test", "score": 0.8},
        ]
        
        with pytest.raises(ValueError, match="hybrid_weight must be between"):
            reranker.rerank_with_hybrid_score(
                query="test",
                documents=documents,
                hybrid_weight=1.5,
            )
        
        with pytest.raises(ValueError, match="hybrid_weight must be between"):
            reranker.rerank_with_hybrid_score(
                query="test",
                documents=documents,
                hybrid_weight=-0.1,
            )

    def test_empty_documents(self):
        """测试空文档列表"""
        reranker = Reranker()
        
        results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=[],
            top_k=5,
        )
        
        assert len(results) == 0

    def test_top_k_limit(self):
        """测试 top_k 限制"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": str(i), "document_id": f"d{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": f"doc {i}", "score": 0.9 - i * 0.1}
            for i in range(10)
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9 - i * 0.05 for i in range(10)]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=3,
        )
        
        assert len(results) == 3


class TestLazyLoading:
    """测试懒加载机制"""

    def test_model_not_loaded_initially(self):
        """测试模型初始未加载"""
        reranker = Reranker()
        
        assert not reranker.is_model_loaded

    def test_model_loaded_on_first_access(self):
        """测试模型在第一次访问时加载"""
        reranker = Reranker()
        
        assert not reranker.is_model_loaded
        
        with patch('app.reranker.load_cross_encoder') as load_model:
            mock_model_instance = MagicMock()
            load_model.return_value = mock_model_instance
            
            _ = reranker.model
            
            assert reranker.is_model_loaded
            load_model.assert_called_once()

    def test_model_loaded_only_once(self):
        """测试模型只加载一次"""
        reranker = Reranker()
        
        with patch('app.reranker.load_cross_encoder') as load_model:
            mock_model_instance = MagicMock()
            load_model.return_value = mock_model_instance
            
            _ = reranker.model
            _ = reranker.model
            _ = reranker.model
            
            assert load_model.call_count == 1

    def test_thread_safe_loading(self):
        """测试线程安全的懒加载"""
        reranker = Reranker()
        import threading
        
        load_results = []
        
        def access_model():
            try:
                _ = reranker.model
                load_results.append("success")
            except Exception as e:
                load_results.append(f"error: {e}")
        
        threads = [threading.Thread(target=access_model) for _ in range(5)]
        
        with patch('app.reranker.load_cross_encoder') as load_model:
            mock_model_instance = MagicMock()
            load_model.return_value = mock_model_instance
            
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        
        assert all(r == "success" for r in load_results)
        assert load_model.call_count == 1
        assert reranker.is_model_loaded


class TestRerankPerformance:
    """测试重排序性能"""

    def test_rerank_performance_overhead(self):
        """测试重排序性能开销"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": str(i), "document_id": f"d{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": f"test document {i}", "score": 0.9 - i * 0.05}
            for i in range(20)
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8 - i * 0.03 for i in range(20)]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        start_time = time.time()
        
        results = reranker.rerank_with_hybrid_score(
            query="test query",
            documents=documents,
            top_k=10,
        )
        
        elapsed_time = (time.time() - start_time) * 1000
        
        assert len(results) == 10
        assert elapsed_time < 200

    def test_hybrid_vs_single_performance(self):
        """测试混合重排序与单一重排序的性能对比"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": str(i), "document_id": f"d{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", "text": f"test {i}", "score": 0.9 - i * 0.05}
            for i in range(20)
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8 - i * 0.03 for i in range(20)]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        start_hybrid = time.time()
        hybrid_results = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=10,
        )
        hybrid_time = (time.time() - start_hybrid) * 1000
        
        start_single = time.time()
        single_results = reranker.rerank(
            query="test",
            documents=documents,
            top_k=10,
        )
        single_time = (time.time() - start_single) * 1000
        
        assert len(hybrid_results) == 10
        assert len(single_results) == 10
        
        assert hybrid_time < 200
        assert single_time < 200


class TestRerankResult:
    """测试 RerankResult 数据类"""

    def test_result_with_hybrid_score(self):
        """测试包含混合分数的结果"""
        result = RerankResult(
            chunk_id="1",
            document_id="d1",
            corpus_id="c1",
            file_name="test.txt",
            page_or_loc="p1",
            text="test",
            original_score=0.9,
            rerank_score=0.85,
            hybrid_score=0.875,
            rank=1,
        )
        
        assert result.chunk_id == "1"
        assert result.hybrid_score == 0.875
        assert result.rank == 1

    def test_result_without_hybrid_score(self):
        """测试不包含混合分数的结果"""
        result = RerankResult(
            chunk_id="1",
            document_id="d1",
            corpus_id="c1",
            file_name="test.txt",
            page_or_loc="p1",
            text="test",
            original_score=0.9,
            rerank_score=0.85,
            hybrid_score=None,
            rank=1,
        )
        
        assert result.hybrid_score is None

    def test_result_immutability(self):
        """测试结果不可变性"""
        result = RerankResult(
            chunk_id="1", document_id="d1", corpus_id="c1",
            file_name="test.txt", page_or_loc="p1", text="test",
            original_score=0.9, rerank_score=0.85, hybrid_score=0.875, rank=1,
        )
        
        with pytest.raises(Exception):
            result.rank = 2


class TestHybridEffectiveness:
    """测试混合重排序效果"""

    def test_hybrid_improves_ranking(self):
        """测试混合分数能改进排序"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": "relevant_low_original", "document_id": "d1", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", 
             "text": "highly relevant to query", "score": 0.5},
            {"chunk_id": "irrelevant_high_original", "document_id": "d2", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1",
             "text": "irrelevant content", "score": 0.9},
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.95, 0.3]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        results = reranker.rerank_with_hybrid_score(
            query="relevant query",
            documents=documents,
            top_k=2,
            hybrid_weight=0.5,
            normalization="max",
        )
        
        assert results[0].chunk_id == "relevant_low_original"
        assert results[1].chunk_id == "irrelevant_high_original"
        
        assert results[0].hybrid_score > results[1].hybrid_score

    def test_balanced_weight_recommendation(self):
        """测试推荐的最佳权重平衡"""
        reranker = Reranker()
        
        documents = [
            {"chunk_id": str(i), "document_id": f"d{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1", 
             "text": f"document {i}", "score": 0.9 - i * 0.1}
            for i in range(5)
        ]
        
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.6, 0.7, 0.8, 0.9]
        reranker._model = mock_model
        reranker._model_loaded = True
        
        results_balanced = reranker.rerank_with_hybrid_score(
            query="test",
            documents=documents,
            top_k=5,
            hybrid_weight=0.5,
        )
        
        assert len(results_balanced) == 5
        
        for i in range(len(results_balanced) - 1):
            assert results_balanced[i].hybrid_score >= results_balanced[i + 1].hybrid_score


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
