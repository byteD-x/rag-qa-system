from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List

from .jieba_compat import load_jieba


class DocType(str, Enum):
    """文档类型"""

    TECHNICAL = "technical_docs"
    GENERAL = "general_text"
    CONVERSATIONAL = "conversational"
    CODE = "code"


CHUNK_SIZES: Dict[DocType, int] = {
    DocType.TECHNICAL: 512,
    DocType.GENERAL: 1024,
    DocType.CONVERSATIONAL: 256,
    DocType.CODE: 384,
}

OVERLAP_RATIO = 0.1


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    page_or_loc: str


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    text: str
    page_or_loc: str
    token_count: int


def get_chunk_size(doc_type: DocType = DocType.GENERAL) -> int:
    """获取文档类型对应的分块大小"""
    return CHUNK_SIZES.get(doc_type, CHUNK_SIZES[DocType.GENERAL])


def get_overlap_size(chunk_size: int) -> int:
    """根据分块大小计算重叠大小"""
    return int(chunk_size * OVERLAP_RATIO)


def chunk_segments(
    segments: Iterable[ParsedSegment],
    chunk_tokens: int = 800,
    overlap_tokens: int = 120,
    doc_type: DocType = DocType.GENERAL,
) -> List[Chunk]:
    if chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be > 0")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be in [0, chunk_tokens)")

    result: List[Chunk] = []
    next_index = 0
    jieba = load_jieba()

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        words = list(jieba.cut(text))
        if not words:
            continue

        start = 0
        step = chunk_tokens - overlap_tokens
        while start < len(words):
            end = min(start + chunk_tokens, len(words))
            piece = " ".join(words[start:end]).strip()
            if piece:
                result.append(
                    Chunk(
                        chunk_index=next_index,
                        text=piece,
                        page_or_loc=seg.page_or_loc,
                        token_count=end - start,
                    )
                )
                next_index += 1
            if end == len(words):
                break
            start += step

    return result


def chunk_by_structure(
    text: str,
    doc_type: DocType,
    page_or_loc: str = "loc:unknown",
) -> List[Chunk]:
    """
    基于文档结构分块（按段落、函数等）

    Args:
        text: 文档全文
        doc_type: 文档类型
        page_or_loc: 页码或位置

    Returns:
        分块列表
    """
    chunk_size = get_chunk_size(doc_type)
    overlap_size = get_overlap_size(chunk_size)

    if doc_type == DocType.CODE:
        segments = _split_code_by_structure(text)
    else:
        segments = _split_text_by_paragraphs(text)

    parsed_segments = [
        ParsedSegment(text=seg, page_or_loc=page_or_loc) for seg in segments if seg.strip()
    ]

    return chunk_segments(
        parsed_segments,
        chunk_tokens=chunk_size,
        overlap_tokens=overlap_size,
        doc_type=doc_type,
    )


def _split_code_by_structure(code: str) -> List[str]:
    """按代码结构分割（函数、类）"""
    import re

    parts = re.split(r"(?=(?:^|\n)(?:def |class |async def ))", code)
    return [part for part in parts if part.strip()]


def _split_text_by_paragraphs(text: str) -> List[str]:
    """按段落分割文本"""
    paragraphs = []
    current = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append("\n".join(current))
                current = []
        else:
            current.append(line)

    if current:
        paragraphs.append("\n".join(current))

    return paragraphs if paragraphs else [text]
