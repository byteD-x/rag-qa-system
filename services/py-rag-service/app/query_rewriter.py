#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查询重写模块

生成多个查询视角，提升检索召回率。
通过 LLM 生成原始问题的 3 个变体，然后并行执行检索。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RewrittenQuery:
    """重写后的查询"""
    original: str
    rewritten: str
    perspective: str  # 视角说明


class QueryRewriter:
    """查询重写器"""

    def __init__(self, llm_client=None):
        """
        初始化查询重写器

        Args:
            llm_client: LLM 客户端 (可选，如果不提供则使用规则重写)
        """
        self.llm_client = llm_client
        self.max_queries = 3
        self.max_latency_ms = 500  # 最大延迟

    async def rewrite_query(self, question: str) -> List[RewrittenQuery]:
        """
        重写查询，生成多个视角

        Args:
            question: 原始问题

        Returns:
            重写后的查询列表
        """
        if self.llm_client:
            return await self._rewrite_with_llm(question)
        else:
            return self._rewrite_with_rules(question)

    async def _rewrite_with_llm(self, question: str) -> List[RewrittenQuery]:
        """使用 LLM 生成查询变体"""
        prompt = f"""请为以下问题生成 3 个不同视角的变体问题，要求：
1. 保持原意但使用不同的表达方式
2. 每个变体侧重不同的关键词
3. 包含同义词和相关术语

原始问题：{question}

请按以下 JSON 格式返回：
{{
    "variants": [
        {{"query": "变体 1", "perspective": "视角说明 1"}},
        {{"query": "变体 2", "perspective": "视角说明 2"}},
        {{"query": "变体 3", "perspective": "视角说明 3"}}
    ]
}}
"""
        try:
            # 调用 LLM (异步)
            response = await asyncio.wait_for(
                self.llm_client.generate(prompt),
                timeout=self.max_latency_ms / 1000
            )
            # 解析 JSON 响应 (简化处理)
            variants = self._parse_llm_response(response, question)
            return variants
        except asyncio.TimeoutError:
            # LLM 超时，降级到规则重写
            return self._rewrite_with_rules(question)
        except Exception:
            # 其他错误，返回原始问题
            return [RewrittenQuery(original=question, rewritten=question, perspective="原始问题")]

    def _rewrite_with_rules(self, question: str) -> List[RewrittenQuery]:
        """使用规则生成查询变体"""
        variants = []

        # 变体 1: 提取关键词
        keywords = self._extract_keywords(question)
        if keywords:
            variants.append(RewrittenQuery(
                original=question,
                rewritten=" ".join(keywords),
                perspective="关键词提取"
            ))

        # 变体 2: 同义词替换 (简化版)
        synonym_query = self._replace_synonyms(question)
        if synonym_query != question:
            variants.append(RewrittenQuery(
                original=question,
                rewritten=synonym_query,
                perspective="同义词替换"
            ))

        # 变体 3: 简化问题
        simplified = self._simplify_question(question)
        if simplified != question:
            variants.append(RewrittenQuery(
                original=question,
                rewritten=simplified,
                perspective="问题简化"
            ))

        # 确保至少有一个变体
        if not variants:
            variants.append(RewrittenQuery(
                original=question,
                rewritten=question,
                perspective="原始问题"
            ))

        return variants[:self.max_queries]

    def _extract_keywords(self, question: str) -> List[str]:
        """提取关键词"""
        # 简单的中文关键词提取 (基于词频和位置)
        # 实际应用中应该使用 jieba 等分词工具
        stop_words = {
            "的", "了", "是", "在", "和", "与", "及", "等", "个", "什么",
            "如何", "怎么", "怎样", "为什么", "哪些", "哪个", "谁",
            "where", "what", "when", "who", "why", "how", "the", "is", "are",
        }

        # 简单的分词 (按标点和空格)
        import re
        words = re.split(r'[，。！？；：,\.\!?;:\s]+', question)
        words = [w.strip() for w in words if w.strip()]

        # 过滤停用词，保留较长的词
        keywords = [
            w for w in words
            if w not in stop_words and len(w) >= 2
        ]

        return keywords[:5]  # 最多 5 个关键词

    def _replace_synonyms(self, question: str) -> str:
        """同义词替换"""
        synonyms = {
            "如何": "怎么",
            "怎么": "如何",
            "使用": "利用",
            "利用": "使用",
            "方法": "方式",
            "方式": "方法",
            "问题": "疑问",
            "错误": "问题",
            "解决": "处理",
            "处理": "解决",
        }

        result = question
        for orig, syn in synonyms.items():
            result = result.replace(orig, syn, 1)

        return result

    def _simplify_question(self, question: str) -> str:
        """简化问题"""
        import re

        simplified = re.sub(r'^(请问一下 | 请问 | 我想问 | 问一下)', '', question)

        simplified = re.sub(r'[？?]+$', '', simplified)

        simplified = simplified.replace("一下", "")

        return simplified.strip()

    def _parse_llm_response(self, response: str, original: str) -> List[RewrittenQuery]:
        """解析 LLM 响应"""
        import json

        try:
            data = json.loads(response)
            variants = []
            for item in data.get("variants", []):
                variants.append(RewrittenQuery(
                    original=original,
                    rewritten=item.get("query", original),
                    perspective=item.get("perspective", "LLM 生成")
                ))
            return variants
        except Exception:
            # 解析失败，返回规则重写结果
            return self._rewrite_with_rules(original)


class MultiQueryRetriever:
    """多查询检索器"""

    def __init__(self, base_retriever, query_rewriter: QueryRewriter, max_variants: int = 3, timeout_ms: int = 500):
        """
        初始化多查询检索器

        Args:
            base_retriever: 基础检索器
            query_rewriter: 查询重写器
            max_variants: 最大查询变体数（默认 3）
            timeout_ms: 超时时间（毫秒，默认 500）
        """
        self.base_retriever = base_retriever
        self.query_rewriter = query_rewriter
        self.max_variants = max_variants
        self.timeout_ms = timeout_ms

    async def retrieve(self, question: str, top_k: int = 8, query_filter=None) -> List:
        """
        使用多查询检索

        Args:
            question: 原始问题
            top_k: 返回结果数
            query_filter: 检索过滤器（可选）

        Returns:
            去重后的检索结果
        """
        rewritten_queries = await self.query_rewriter.rewrite_query(question)

        tasks = [
            self.base_retriever.search(q.rewritten, top_k=top_k // len(rewritten_queries) + 1, query_filter=query_filter)
            for q in rewritten_queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        seen_ids = set()
        for result_list in results:
            if isinstance(result_list, Exception):
                continue
            for item in result_list:
                item_id = getattr(item, 'id', str(item))
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_results.append(item)

        all_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)
        return all_results[:top_k]


# 全局重写器实例
_rewriter: Optional[QueryRewriter] = None


def get_rewriter(llm_client=None) -> QueryRewriter:
    """获取全局重写器实例"""
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter(llm_client)
    return _rewriter


async def rewrite_query(question: str) -> List[RewrittenQuery]:
    """重写查询"""
    return await get_rewriter().rewrite_query(question)


if __name__ == "__main__":
    # 测试示例
    import asyncio

    test_questions = [
        "如何使用 Python 读取文件？",
        "Docker 容器无法启动怎么办？",
        "机器学习和深度学习有什么区别？",
    ]

    async def test():
        rewriter = QueryRewriter()

        print("=" * 70)
        print("查询重写器测试")
        print("=" * 70)

        for question in test_questions:
            print(f"\n原始问题：{question}")
            variants = await rewriter.rewrite_query(question)
            for i, var in enumerate(variants, 1):
                print(f"  变体{i} [{var.perspective}]: {var.rewritten}")

    asyncio.run(test())
