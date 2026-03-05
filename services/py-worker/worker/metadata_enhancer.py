from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from worker.chunking import DocType


@dataclass(frozen=True)
class EnhancedMetadata:
    """增强后的元数据"""

    keywords: List[str]
    doc_type: DocType
    language: str
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    section_hierarchy: List[Dict[str, str]] = field(default_factory=list)


class MetadataEnhancer:
    """元数据增强器"""

    CODE_PATTERNS = [
        r"\bdef\s+\w+",
        r"\bclass\s+\w+",
        r"\bfunction\s+\w+",
        r"\bvar\s+\w+",
        r"\bconst\s+\w+",
        r"\bimport\s+\w+",
        r"\bfrom\s+\w+\s+import",
        r"\bpublic\s+class",
        r"\bprivate\s+def",
    ]

    TECHNICAL_TERMS = [
        "api",
        "http",
        "json",
        "database",
        "server",
        "client",
        "authentication",
        "authorization",
        "encryption",
        "deployment",
        "configuration",
        "endpoint",
        "request",
        "response",
    ]

    CONVERSATIONAL_PATTERNS = [
        r"你好",
        r"谢谢",
        r"请问",
        r"\bhello\b",
        r"\bthank\b",
        r"\bplease\b",
        r"\bhow\b",
        r"\bwhat\b",
        r"你好吗",
        r"帮助您",
        r"有问题",
    ]

    SECTION_PATTERNS = [
        r"^(#{1,6})\s+(.+)$",
        r"^(\d+(?:\.\d+)*)\s+(.+)$",
        r"^(第.+[章节条项款])\s*(.+)$",
        r"^(Chapter\s+\d+)\s*[:：]?\s*(.+)$",
        r"^(Section\s+\d+(?:\.\d+)*)\s*[:：]?\s*(.+)$",
    ]

    def __init__(self, max_keywords: int = 5):
        """
        初始化元数据增强器

        Args:
            max_keywords: 提取的关键词最大数量
        """
        self._max_keywords = max_keywords
        self._compiled_code_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.CODE_PATTERNS
        ]
        self._compiled_conv_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.CONVERSATIONAL_PATTERNS
        ]
        self._compiled_section_patterns = [
            re.compile(p, re.MULTILINE) for p in self.SECTION_PATTERNS
        ]

    def enhance(self, text: str) -> EnhancedMetadata:
        """
        增强文档元数据

        Args:
            text: 文档文本

        Returns:
            增强后的元数据
        """
        keywords = self._extract_keywords(text)
        doc_type = self._classify_document(text)
        language = self._detect_language(text)
        word_count = len(text.split())
        sentences = self._split_sentences(text)
        sentence_count = len(sentences)
        avg_sentence_length = (
            sum(len(s.split()) for s in sentences) / sentence_count
            if sentence_count > 0
            else 0.0
        )

        section_hierarchy = self._extract_section_hierarchy(text)

        return EnhancedMetadata(
            keywords=keywords,
            doc_type=doc_type,
            language=language,
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=avg_sentence_length,
            section_hierarchy=section_hierarchy,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        words = re.findall(r"\b[a-zA-Z\u4e00-\u9fff]{2,}\b", text.lower())

        if not words:
            return []

        word_freq = Counter(words)

        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
        }

        filtered_words = [
            (word, freq) for word, freq in word_freq.items() if word not in stop_words
        ]

        filtered_words.sort(key=lambda x: x[1], reverse=True)

        return [word for word, _ in filtered_words[: self._max_keywords]]

    def _classify_document(self, text: str) -> DocType:
        """分类文档类型"""
        code_score = sum(
            1 for pattern in self._compiled_code_patterns if pattern.search(text)
        )

        conv_score = sum(
            1 for pattern in self._compiled_conv_patterns if pattern.search(text)
        )

        tech_score = sum(
            1 for term in self.TECHNICAL_TERMS if term.lower() in text.lower()
        )

        scores = {
            DocType.CODE: code_score * 3,
            DocType.CONVERSATIONAL: conv_score * 3,
            DocType.TECHNICAL: tech_score,
            DocType.GENERAL: 0,
        }

        max_score = max(scores.values())
        if max_score == 0:
            return DocType.GENERAL

        doc_type = max(scores, key=lambda x: scores[x])

        if scores[doc_type] < 3:
            return DocType.GENERAL

        return doc_type

    def _detect_language(self, text: str) -> str:
        """检测语言"""
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = len(text)

        if total_chars == 0:
            return "unknown"

        chinese_ratio = chinese_chars / total_chars

        if chinese_ratio > 0.3:
            return "zh"
        elif chinese_ratio > 0.1:
            return "zh-en"
        else:
            return "en"

    def _split_sentences(self, text: str) -> List[str]:
        """分割句子"""
        sentences = re.split(r"[。！？.!?]", text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_section_hierarchy(self, text: str) -> List[Dict[str, str]]:
        """提取章节标题层级"""
        sections: List[Dict[str, str]] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            for pattern in self._compiled_section_patterns:
                match = pattern.match(line)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        marker, title = groups
                        level = self._calculate_section_level(marker)
                        sections.append(
                            {"level": str(level), "title": title.strip(), "marker": marker}
                        )
                    break

        return sections

    def _calculate_section_level(self, marker: str) -> int:
        """计算章节层级"""
        if marker.startswith("#"):
            return len(marker)

        if re.match(r"\d+(?:\.\d+)*", marker):
            return len(marker.split("."))

        if re.search(r"第.+ [章节条项款]", marker):
            return 1

        if re.match(r"Chapter\s+\d+", marker, re.IGNORECASE):
            return 1

        if re.match(r"Section\s+\d+", marker, re.IGNORECASE):
            return 2

        return 1

    def to_dict(self, metadata: EnhancedMetadata) -> Dict:
        """将元数据转换为字典"""
        return {
            "keywords": metadata.keywords,
            "doc_type": metadata.doc_type.value,
            "language": metadata.language,
            "word_count": metadata.word_count,
            "sentence_count": metadata.sentence_count,
            "avg_sentence_length": round(metadata.avg_sentence_length, 2),
            "section_hierarchy": metadata.section_hierarchy,
        }
