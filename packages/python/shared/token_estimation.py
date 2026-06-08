from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_ENGLISH_WORD_RE = re.compile(r"[a-zA-Z]+")
_NUMBER_RE = re.compile(r"\d+")


def estimate_tokens(text: str) -> int:
    """Estimate LLM token count without a tokenizer dependency."""
    if not text:
        return 0
    cjk_chars = len(_CJK_RE.findall(text))
    english_matches = _ENGLISH_WORD_RE.findall(text)
    number_matches = _NUMBER_RE.findall(text)
    english_words = len(english_matches)
    number_tokens = len(number_matches)
    matched_chars = cjk_chars + sum(len(m) for m in english_matches) + sum(len(m) for m in number_matches)
    remaining = max(len(text) - matched_chars, 0)
    estimated = cjk_chars * 1.5 + english_words * 1.3 + number_tokens * 0.5 + remaining * 0.3
    return max(int(estimated), 1)
