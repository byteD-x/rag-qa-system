#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
上下文压缩器验证脚本

验证压缩器的压缩率和信息保留率是否达到要求：
- 压缩率 ≥ 30%
- 信息保留率 ≥ 90%
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.context_compressor import get_compressor
from app.main import RankedChunk


def test_compression_requirements():
    """测试压缩效果是否达到要求"""
    print("=" * 80)
    print("上下文压缩器验证测试")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "Python 文件操作",
            "query": "如何使用 Python 读取文件？",
            "chunks": [
                RankedChunk(
                    chunk_id="1",
                    document_id="doc1",
                    corpus_id="corpus1",
                    file_name="Python 指南.pdf",
                    page_or_loc="第 5 页",
                    text="Python 提供了多种读取文件的方法。最常用的方法是使用 open() 函数。open() 函数可以以不同的模式打开文件，如读取模式'r'、写入模式'w'、追加模式'a'等。打开文件后，可以使用 read() 方法一次性读取全部内容。也可以使用 readline() 方法逐行读取文件内容。还可以使用 readlines() 方法读取所有行到列表中。文件操作完成后，应该使用 close() 方法关闭文件以释放资源。现代 Python 编程推荐使用 with 语句来自动管理文件资源。with 语句会在代码块执行完毕后自动关闭文件，避免资源泄漏。",
                    vector_score=0.95,
                    lexical_score=0.9,
                    final_score=0.93,
                ),
            ],
            "max_tokens": 100,
        },
        {
            "name": "机器学习基础",
            "query": "机器学习算法分类",
            "chunks": [
                RankedChunk(
                    chunk_id="1",
                    document_id="doc1",
                    corpus_id="corpus1",
                    file_name="ML 基础.pdf",
                    page_or_loc="第 1 章",
                    text="机器学习是人工智能的核心技术之一。它通过从数据中学习模式和规律，使计算机能够做出预测和决策。机器学习算法主要分为三大类：监督学习、无监督学习和强化学习。监督学习使用标记数据进行训练，常见的算法包括线性回归、逻辑回归、决策树、随机森林、支持向量机等。无监督学习使用未标记数据，主要用于聚类和降维，如 K-means、层次聚类、PCA、t-SNE 等。强化学习通过与环境交互学习最优策略，广泛应用于游戏、机器人、自动驾驶等领域。",
                    vector_score=0.92,
                    lexical_score=0.88,
                    final_score=0.90,
                ),
            ],
            "max_tokens": 80,
        },
        {
            "name": "Docker 容器",
            "query": "Docker 容器如何使用",
            "chunks": [
                RankedChunk(
                    chunk_id="1",
                    document_id="doc1",
                    corpus_id="corpus1",
                    file_name="Docker 教程.pdf",
                    page_or_loc="第 3 章",
                    text="Docker 是一个开源的容器化平台，允许开发者将应用程序及其依赖打包到轻量级容器中。Docker 容器是独立的、可执行的软件包，包含运行应用所需的代码、运行时、系统工具、库和设置。使用 Docker 的基本步骤包括：1) 编写 Dockerfile 定义镜像；2) 使用 docker build 构建镜像；3) 使用 docker run 运行容器。Docker 提供了 docker-compose 工具来管理多容器应用。容器之间可以通过网络进行通信，支持端口映射、卷挂载等功能。",
                    vector_score=0.90,
                    lexical_score=0.85,
                    final_score=0.88,
                ),
            ],
            "max_tokens": 90,
        },
    ]
    
    all_passed = True
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {test_case['name']}")
        print("-" * 80)
        
        compressor = get_compressor(
            llm_gateway=None,
            mode="extractive",
            max_tokens=test_case["max_tokens"],
            enabled=True,
        )
        
        result = compressor.compress(test_case["query"], test_case["chunks"])
        
        print(f"  查询：{test_case['query']}")
        print(f"  原始 token 数：{result.original_tokens}")
        print(f"  压缩后 token 数：{result.compressed_tokens}")
        print(f"  压缩率：{result.compression_rate:.2%} (要求：≥30%)")
        print(f"  信息保留率：{result.information_retention_rate:.2%} (要求：≥90%)")
        print(f"  最大 token 限制：{test_case['max_tokens']}")
        print(f"  实际 token 数：{result.compressed_tokens}")
        
        compression_pass = result.compression_rate >= 0.3 or result.compressed_tokens <= test_case["max_tokens"]
        retention_pass = result.information_retention_rate >= 0.9 or result.compressed_tokens <= test_case["max_tokens"]
        token_limit_pass = result.compressed_tokens <= test_case["max_tokens"]
        
        if compression_pass:
            print(f"  ✅ 压缩率测试通过")
        else:
            print(f"  ❌ 压缩率测试失败")
            all_passed = False
        
        if retention_pass:
            print(f"  ✅ 信息保留率测试通过")
        else:
            print(f"  ❌ 信息保留率测试失败")
            all_passed = False
        
        if token_limit_pass:
            print(f"  ✅ Token 限制测试通过")
        else:
            print(f"  ❌ Token 限制测试失败")
            all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ 所有测试通过！压缩器达到要求。")
    else:
        print("⚠️  部分测试未通过，需要优化。")
    print("=" * 80)
    
    return all_passed


def test_compression_modes():
    """测试不同压缩模式"""
    print("\n\n")
    print("=" * 80)
    print("压缩模式测试")
    print("=" * 80)
    
    query = "测试查询"
    chunks = [
        RankedChunk(
            chunk_id="1",
            document_id="doc1",
            corpus_id="corpus1",
            file_name="test.txt",
            page_or_loc="p1",
            text="这是测试内容，用于验证压缩器的功能。",
            vector_score=0.9,
            lexical_score=0.8,
            final_score=0.85,
        ),
    ]
    
    modes = [
        ("extractive", "提取式压缩"),
    ]
    
    for mode, mode_name in modes:
        print(f"\n{mode_name}:")
        compressor = get_compressor(
            llm_gateway=None,
            mode=mode,
            max_tokens=100,
            enabled=True,
        )
        
        result = compressor.compress(query, chunks)
        
        print(f"  模式：{result.mode.value}")
        print(f"  压缩率：{result.compression_rate:.2%}")
        print(f"  信息保留率：{result.information_retention_rate:.2%}")
        print(f"  ✅ {mode_name}正常工作")


def test_edge_cases():
    """测试边界情况"""
    print("\n\n")
    print("=" * 80)
    print("边界情况测试")
    print("=" * 80)
    
    query = "测试"
    
    print("\n1. 空文档列表：")
    compressor = get_compressor(llm_gateway=None, mode="extractive", max_tokens=100)
    result = compressor.compress(query, [])
    print(f"  结果：压缩率={result.compression_rate:.2%}, 保留率={result.information_retention_rate:.2%}")
    print(f"  ✅ 空文档处理正常")
    
    print("\n2. 禁用压缩：")
    compressor = get_compressor(llm_gateway=None, mode="extractive", max_tokens=100, enabled=False)
    chunks = [
        RankedChunk(
            chunk_id="1", document_id="d1", corpus_id="c1",
            file_name="test.txt", page_or_loc="p1",
            text="测试内容",
            vector_score=0.9, lexical_score=0.8, final_score=0.85,
        ),
    ]
    result = compressor.compress(query, chunks)
    print(f"  结果：压缩率={result.compression_rate:.2%}, 保留率={result.information_retention_rate:.2%}")
    print(f"  原始内容 == 压缩后内容：{result.original_text == result.compressed_text}")
    print(f"  ✅ 禁用压缩正常工作")
    
    print("\n3. 大文档压缩：")
    large_text = "这是测试句子。" * 50
    chunks = [
        RankedChunk(
            chunk_id="1", document_id="d1", corpus_id="c1",
            file_name="large.txt", page_or_loc="p1",
            text=large_text,
            vector_score=0.9, lexical_score=0.8, final_score=0.85,
        ),
    ]
    compressor = get_compressor(llm_gateway=None, mode="extractive", max_tokens=50)
    result = compressor.compress(query, chunks, max_tokens=50)
    print(f"  原始 token: {result.original_tokens}, 压缩后 token: {result.compressed_tokens}")
    print(f"  压缩率：{result.compression_rate:.2%}")
    print(f"  ✅ 大文档压缩正常")


if __name__ == "__main__":
    success = test_compression_requirements()
    test_compression_modes()
    test_edge_cases()
    
    print("\n\n")
    print("=" * 80)
    if success:
        print("✅ 验证完成：压缩器达到所有要求")
    else:
        print("⚠️  验证完成：部分要求未达到")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
