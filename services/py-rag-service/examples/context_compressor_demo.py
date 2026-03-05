#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
上下文压缩器演示脚本

展示如何使用上下文压缩器来压缩检索结果，
并展示压缩率和信息保留率的效果。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.context_compressor import get_compressor, CompressionMode
from app.main import RankedChunk


def demo_extractive_compression():
    """演示提取式压缩"""
    print("=" * 80)
    print("提取式上下文压缩演示")
    print("=" * 80)
    
    query = "如何使用 Python 读取文件？"
    
    chunks = [
        RankedChunk(
            chunk_id="1",
            document_id="doc1",
            corpus_id="corpus1",
            file_name="Python 编程指南.pdf",
            page_or_loc="第 5 页",
            text="""
            Python 提供了多种读取文件的方法。
            最常用的方法是使用 open() 函数。
            open() 函数可以以不同的模式打开文件，如读取模式'r'、写入模式'w'、追加模式'a'等。
            打开文件后，可以使用 read() 方法一次性读取全部内容。
            也可以使用 readline() 方法逐行读取文件内容。
            还可以使用 readlines() 方法读取所有行到列表中。
            文件操作完成后，应该使用 close() 方法关闭文件以释放资源。
            现代 Python 编程推荐使用 with 语句来自动管理文件资源。
            with 语句会在代码块执行完毕后自动关闭文件，避免资源泄漏。
            示例代码：with open('file.txt', 'r', encoding='utf-8') as f: content = f.read()
            """,
            vector_score=0.95,
            lexical_score=0.9,
            final_score=0.93,
        ),
        RankedChunk(
            chunk_id="2",
            document_id="doc2",
            corpus_id="corpus1",
            file_name="Python 最佳实践.pdf",
            page_or_loc="第 12 页",
            text="""
            文件处理是 Python 编程中的常见任务。
            除了基本的读取操作，还可以使用上下文管理器来处理文件。
            上下文管理器通过 with 语句实现，能够自动处理资源的分配和释放。
            这种方式不仅适用于文件，也适用于数据库连接、网络 socket 等资源。
            使用上下文管理器可以让代码更加简洁和安全。
            """,
            vector_score=0.85,
            lexical_score=0.8,
            final_score=0.83,
        ),
        RankedChunk(
            chunk_id="3",
            document_id="doc3",
            corpus_id="corpus1",
            file_name="Python 进阶教程.pdf",
            page_or_loc="第 28 页",
            text="""
            Python 的 pathlib 模块提供了面向对象的路径操作方式。
            使用 Path 类可以更优雅地处理文件路径。
            Path 类支持路径的拼接、解析、遍历等操作。
            例如：from pathlib import Path; p = Path('data') / 'file.txt'
            这种方式比字符串拼接更加安全和可读。
            """,
            vector_score=0.75,
            lexical_score=0.7,
            final_score=0.73,
        ),
    ]
    
    compressor = get_compressor(
        llm_gateway=None,
        mode="extractive",
        max_tokens=150,
        enabled=True,
    )
    
    print(f"\n查询：{query}\n")
    print("原始检索结果：")
    for i, chunk in enumerate(chunks, 1):
        print(f"  [{i}] {chunk.file_name} ({chunk.page_or_loc})")
        print(f"      内容：{chunk.text[:100]}...")
    
    result = compressor.compress(query, chunks, max_tokens=150)
    
    print("\n" + "=" * 80)
    print("压缩结果统计：")
    print("=" * 80)
    print(f"  压缩模式：{result.mode.value}")
    print(f"  原始 token 数：{result.original_tokens}")
    print(f"  压缩后 token 数：{result.compressed_tokens}")
    print(f"  压缩率：{result.compression_rate:.2%}")
    print(f"  信息保留率：{result.information_retention_rate:.2%}")
    
    print("\n压缩后的内容：")
    print("-" * 80)
    print(result.compressed_text)
    print("-" * 80)
    
    if result.compression_rate >= 0.3:
        print("✅ 压缩率达到要求（≥30%）")
    else:
        print(f"⚠️  压缩率未达到要求（{result.compression_rate:.2%} < 30%）")
    
    if result.information_retention_rate >= 0.9:
        print("✅ 信息保留率达到要求（≥90%）")
    else:
        print(f"⚠️  信息保留率未达到要求（{result.information_retention_rate:.2%} < 90%）")


def demo_compression_comparison():
    """演示不同压缩模式对比"""
    print("\n\n")
    print("=" * 80)
    print("不同压缩模式对比")
    print("=" * 80)
    
    query = "机器学习算法"
    
    chunks = [
        RankedChunk(
            chunk_id="1",
            document_id="doc1",
            corpus_id="corpus1",
            file_name="机器学习基础.pdf",
            page_or_loc="第 1 章",
            text="""
            机器学习是人工智能的核心技术之一。
            它通过从数据中学习模式和规律，使计算机能够做出预测和决策。
            机器学习算法主要分为三大类：监督学习、无监督学习和强化学习。
            监督学习使用标记数据进行训练，常见的算法包括线性回归、逻辑回归、决策树、随机森林等。
            无监督学习使用未标记数据，主要用于聚类和降维，如 K-means、PCA 等。
            强化学习通过与环境交互学习最优策略，广泛应用于游戏、机器人等领域。
            """,
            vector_score=0.92,
            lexical_score=0.88,
            final_score=0.90,
        ),
    ]
    
    modes = [
        ("extractive", "提取式压缩"),
    ]
    
    for mode, mode_name in modes:
        compressor = get_compressor(
            llm_gateway=None,
            mode=mode,
            max_tokens=100,
            enabled=True,
        )
        
        result = compressor.compress(query, chunks, max_tokens=100)
        
        print(f"\n{mode_name}:")
        print(f"  压缩率：{result.compression_rate:.2%}")
        print(f"  信息保留率：{result.information_retention_rate:.2%}")
        print(f"  压缩后内容：{result.compressed_text[:100]}...")


def demo_disabled_compression():
    """演示禁用压缩的情况"""
    print("\n\n")
    print("=" * 80)
    print("禁用压缩的情况")
    print("=" * 80)
    
    query = "测试查询"
    
    chunks = [
        RankedChunk(
            chunk_id="1",
            document_id="doc1",
            corpus_id="corpus1",
            file_name="test.txt",
            page_or_loc="p1",
            text="这是测试内容",
            vector_score=0.9,
            lexical_score=0.8,
            final_score=0.85,
        ),
    ]
    
    compressor = get_compressor(
        llm_gateway=None,
        mode="extractive",
        max_tokens=100,
        enabled=False,
    )
    
    result = compressor.compress(query, chunks)
    
    print(f"  压缩模式：{result.mode.value}")
    print(f"  压缩率：{result.compression_rate:.2%}")
    print(f"  信息保留率：{result.information_retention_rate:.2%}")
    print(f"  原始内容 == 压缩后内容：{result.original_text == result.compressed_text}")


if __name__ == "__main__":
    demo_extractive_compression()
    demo_compression_comparison()
    demo_disabled_compression()
    
    print("\n\n")
    print("=" * 80)
    print("演示完成")
    print("=" * 80)
