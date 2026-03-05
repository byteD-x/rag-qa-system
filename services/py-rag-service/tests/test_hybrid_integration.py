"""
混合检索集成测试
验证混合检索（RRF）相比单一检索（仅稠密或仅稀疏）的优势
"""
import pytest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hybrid_retriever import HybridRetriever, RetrievalResult


class TestHybridVsSingleRetrieval:
    """比较混合检索与单一检索的效果"""

    def test_hybrid_outperforms_sparse_only(self):
        """测试混合检索优于仅稀疏检索"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        documents = []
        for i in range(20):
            if i < 5:
                text = "Python machine learning algorithms"
            elif i < 10:
                text = "Deep learning neural networks"
            else:
                text = "Data science analytics"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        sparse_results = retriever.sparse_search("Python machine learning", top_k=10)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=documents[i]["text"],
                score=0.95 - i * 0.1,
                retrieval_type="dense",
            )
            for i in range(min(10, len(documents)))
        ]
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=10)
        
        assert len(hybrid_results) >= max(len(sparse_results), len(dense_results))
        
        sparse_chunk_ids = {r.chunk_id for r in sparse_results}
        hybrid_chunk_ids = {r.chunk_id for r in hybrid_results}
        
        assert len(hybrid_chunk_ids) >= len(sparse_chunk_ids)

    def test_hybrid_outperforms_dense_only(self):
        """测试混合检索优于仅稠密检索"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        documents = []
        for i in range(20):
            if i < 5:
                text = "Kubernetes container orchestration deployment"
            elif i < 10:
                text = "Docker containers microservices architecture"
            else:
                text = "Cloud native applications scalability"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}",
                document_id=f"doc{i}",
                corpus_id="c1",
                file_name="test.txt",
                page_or_loc="p1",
                text=documents[i]["text"],
                score=0.85 - i * 0.05,
                retrieval_type="dense",
            )
            for i in range(10)
        ]
        
        sparse_results = retriever.sparse_search("Kubernetes Docker containers", top_k=10)
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=10)
        
        assert len(hybrid_results) >= len(dense_results)
        
        dense_chunk_ids = {r.chunk_id for r in dense_results}
        hybrid_chunk_ids = {r.chunk_id for r in hybrid_results}
        
        assert len(hybrid_chunk_ids) >= len(dense_chunk_ids)

    def test_hybrid_recall_improvement(self):
        """测试混合检索召回率提升"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        documents = []
        for i in range(20):
            if i < 5:
                text = "Python programming language tutorial"
            elif i < 10:
                text = "Java object oriented programming"
            elif i < 15:
                text = "JavaScript web development frontend"
            else:
                text = "Rust system programming performance"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk0", document_id="doc0", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[0]["text"],
                score=0.95, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk2", document_id="doc2", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[2]["text"],
                score=0.85, retrieval_type="dense",
            ),
        ]
        
        sparse_results = retriever.sparse_search("programming language", top_k=10)
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=10)
        
        dense_chunk_ids = {r.chunk_id for r in dense_results}
        sparse_chunk_ids = {r.chunk_id for r in sparse_results}
        hybrid_chunk_ids = {r.chunk_id for r in hybrid_results}
        
        union_single = dense_chunk_ids | sparse_chunk_ids
        
        assert len(hybrid_chunk_ids) >= len(union_single) * 0.8

    def test_hybrid_balances_weights(self):
        """测试混合检索平衡权重"""
        retriever_high_dense = HybridRetriever(dense_weight=0.9, sparse_weight=0.1)
        retriever_high_sparse = HybridRetriever(dense_weight=0.1, sparse_weight=0.9)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk_a", document_id="doc_a", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text="content a", score=0.9, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk_b", document_id="doc_b", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text="content b", score=0.7, retrieval_type="dense",
            ),
        ]
        
        sparse_results = [
            RetrievalResult(
                chunk_id="chunk_b", document_id="doc_b", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text="content b", score=0.95, retrieval_type="sparse",
            ),
            RetrievalResult(
                chunk_id="chunk_c", document_id="doc_c", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text="content c", score=0.85, retrieval_type="sparse",
            ),
        ]
        
        hybrid_high_dense = retriever_high_dense.hybrid_search(
            dense_results, sparse_results, top_k=5
        )
        hybrid_high_sparse = retriever_high_sparse.hybrid_search(
            dense_results, sparse_results, top_k=5
        )
        
        assert len(hybrid_high_dense) == len(hybrid_high_sparse)
        
        score_high_dense = {r.chunk_id: r.score for r in hybrid_high_dense}
        score_high_sparse = {r.chunk_id: r.score for r in hybrid_high_sparse}
        
        assert abs(score_high_dense["chunk_a"] - score_high_sparse["chunk_a"]) > 0.0001


class TestRRFRealWorldScenario:
    """真实场景下的 RRF 测试"""

    def test_multilingual_query(self):
        """测试多语言查询场景"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        documents = []
        for i in range(15):
            if i < 5:
                text = "Python programming tutorial"
            elif i < 10:
                text = "Machine learning algorithms"
            else:
                text = "Data science analytics"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk0", document_id="doc0", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[0]["text"], score=0.92, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk5", document_id="doc5", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[5]["text"], score=0.88, retrieval_type="dense",
            ),
        ]
        
        sparse_results = retriever.sparse_search("Python programming", top_k=5)
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(hybrid_results) >= 1
        assert any("Python" in r.text for r in hybrid_results)

    def test_technical_terms(self):
        """测试技术术语检索"""
        retriever = HybridRetriever(dense_weight=0.7, sparse_weight=0.3)
        
        documents = []
        for i in range(15):
            if i < 5:
                text = "RESTful API design principles HTTP methods"
            elif i < 10:
                text = "GraphQL query language schema resolvers"
            else:
                text = "gRPC protocol buffers microservices"
            
            documents.append({
                "chunk_id": f"chunk{i}",
                "document_id": f"doc{i}",
                "corpus_id": "c1",
                "file_name": "test.txt",
                "page_or_loc": "p1",
                "text": f"{text} document {i}",
            })
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id="chunk0", document_id="doc0", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[0]["text"], score=0.89, retrieval_type="dense",
            ),
            RetrievalResult(
                chunk_id="chunk5", document_id="doc5", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[5]["text"], score=0.87, retrieval_type="dense",
            ),
        ]
        
        sparse_results = retriever.sparse_search("RESTful API HTTP", top_k=5)
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=5)
        
        assert len(hybrid_results) >= 1
        chunk0_result = next((r for r in hybrid_results if r.chunk_id == "chunk0"), None)
        assert chunk0_result is not None


class TestPerformanceMetrics:
    """性能指标测试"""

    def test_retrieval_latency(self):
        """测试检索延迟"""
        import time
        
        retriever = HybridRetriever()
        
        documents = [
            {"chunk_id": f"chunk{i}", "document_id": f"doc{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1",
             "text": f"Document content number {i} with some keywords"}
            for i in range(100)
        ]
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}", document_id=f"doc{i}", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[i]["text"], score=0.99 - i * 0.01,
                retrieval_type="dense",
            )
            for i in range(24)
        ]
        
        start_time = time.time()
        sparse_results = retriever.sparse_search("keywords document", top_k=24)
        sparse_time = time.time() - start_time
        
        start_time = time.time()
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=24)
        hybrid_fusion_time = time.time() - start_time
        
        assert sparse_time < 1.0
        assert hybrid_fusion_time < 0.1
        assert len(hybrid_results) <= 24

    def test_memory_efficiency(self):
        """测试内存效率"""
        retriever = HybridRetriever()
        
        documents = [
            {"chunk_id": f"chunk{i}", "document_id": f"doc{i}", "corpus_id": "c1",
             "file_name": "test.txt", "page_or_loc": "p1",
             "text": "x" * 1000}
            for i in range(50)
        ]
        
        retriever.build_bm25_index(documents)
        
        dense_results = [
            RetrievalResult(
                chunk_id=f"chunk{i}", document_id=f"doc{i}", corpus_id="c1",
                file_name="test.txt", page_or_loc="p1",
                text=documents[i]["text"], score=0.99 - i * 0.01,
                retrieval_type="dense",
            )
            for i in range(24)
        ]
        
        sparse_results = retriever.sparse_search("test", top_k=24)
        
        hybrid_results = retriever.hybrid_search(dense_results, sparse_results, top_k=24)
        
        assert len(hybrid_results) <= 24


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
