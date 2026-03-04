from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


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


def chunk_segments(
    segments: Iterable[ParsedSegment],
    chunk_tokens: int = 800,
    overlap_tokens: int = 120,
) -> List[Chunk]:
    if chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be > 0")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be in [0, chunk_tokens)")

    result: List[Chunk] = []
    next_index = 0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        words = text.split()
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