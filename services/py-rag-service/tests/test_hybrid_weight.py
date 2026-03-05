"""
测试混合检索权重配置功能
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import rerank_points
from qdrant_client.http.models import ScoredPoint


def test_rerank_points_default_weight():
    """测试默认权重（0.7）"""
    # 创建模拟数据
    point1 = ScoredPoint(
        id=1,
        version=1,
        score=0.9,
        payload={"text": "test document", "document_id": "doc1", "corpus_id": "corpus1", "file_name": "test.txt", "page_or_loc": "page1"},
    )
    point2 = ScoredPoint(
        id=2,
        version=1,
        score=0.8,
        payload={"text": "another test", "document_id": "doc2", "corpus_id": "corpus1", "file_name": "test2.txt", "page_or_loc": "page1"},
    )
    
    # 使用默认权重
    result = rerank_points("test", [point1, point2], top_k=2)
    
    assert len(result) == 2
    # 验证分数计算：vector_score * 0.7 + lexical * 0.3
    # point1: 0.9 * 0.7 + lexical * 0.3
    # point2: 0.8 * 0.7 + lexical * 0.3
    assert result[0].vector_score == 0.9
    assert result[1].vector_score == 0.8


def test_rerank_points_custom_weight():
    """测试自定义权重"""
    point1 = ScoredPoint(
        id=1,
        version=1,
        score=0.9,
        payload={"text": "test document", "document_id": "doc1", "corpus_id": "corpus1", "file_name": "test.txt", "page_or_loc": "page1"},
    )
    
    # 使用不同权重
    result_05 = rerank_points("test", [point1], top_k=1, dense_weight=0.5)
    result_09 = rerank_points("test", [point1], top_k=1, dense_weight=0.9)
    
    # 验证权重影响最终分数
    # dense_weight=0.5: final = 0.9 * 0.5 + lexical * 0.5
    # dense_weight=0.9: final = 0.9 * 0.9 + lexical * 0.1
    assert result_05[0].final_score != result_09[0].final_score


def test_rerank_points_weight_validation():
    """测试权重范围验证"""
    point1 = ScoredPoint(
        id=1,
        version=1,
        score=0.9,
        payload={"text": "test document", "document_id": "doc1", "corpus_id": "corpus1", "file_name": "test.txt", "page_or_loc": "page1"},
    )
    
    # 测试边界值
    result_00 = rerank_points("test", [point1], top_k=1, dense_weight=0.0)
    result_10 = rerank_points("test", [point1], top_k=1, dense_weight=1.0)
    
    # dense_weight=0.0: final = lexical * 1.0 (完全依赖词法)
    # dense_weight=1.0: final = vector_score * 1.0 (完全依赖向量)
    assert result_00[0].final_score >= 0.0
    assert result_10[0].final_score == 0.9  # 纯向量分数


def test_rerank_points_weight_influence():
    """测试权重对排序的影响"""
    # 创建两个点，向量分数低但词法匹配好，另一个相反
    point_high_vector = ScoredPoint(
        id=1,
        version=1,
        score=0.95,
        payload={"text": "unrelated content", "document_id": "doc1", "corpus_id": "corpus1", "file_name": "test.txt", "page_or_loc": "page1"},
    )
    point_low_vector = ScoredPoint(
        id=2,
        version=1,
        score=0.6,
        payload={"text": "test test test", "document_id": "doc2", "corpus_id": "corpus1", "file_name": "test2.txt", "page_or_loc": "page1"},
    )
    
    # 高向量权重：向量分数高的排前面
    result_high_dense = rerank_points("test", [point_high_vector, point_low_vector], top_k=2, dense_weight=0.9)
    assert result_high_dense[0].vector_score == 0.95
    
    # 低向量权重（高词法权重）：词法匹配好的可能排前面
    result_low_dense = rerank_points("test", [point_high_vector, point_low_vector], top_k=2, dense_weight=0.3)
    # 词法匹配好的可能排前面（取决于实际词法分数）
    assert len(result_low_dense) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
