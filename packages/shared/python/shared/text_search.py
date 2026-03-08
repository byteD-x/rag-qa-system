from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
HAN_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,32}")
WHITESPACE_RE = re.compile(r"\s+")
TSQUERY_ESCAPE_RE = re.compile(r"[&|!:()'\\]")


def normalize_text(text: str) -> str:
    """Return a normalized lowercase string for search matching.

    Input:
    - text: Raw text.

    Output:
    - Lowercased text with collapsed whitespace.

    Failure:
    - Never raises for normal string input.
    """
    return WHITESPACE_RE.sub(" ", (text or "").strip().lower())


def tokenize_text(text: str, *, dedupe: bool = True) -> list[str]:
    """Tokenize mixed Chinese and ASCII text for FTS and fallback ranking.

    Input:
    - text: Raw question or document text.
    - dedupe: When true, keep first occurrence order only.

    Output:
    - Token list that includes ASCII tokens and Chinese bigrams.

    Failure:
    - Never raises for normal string input.
    """
    normalized = normalize_text(text)
    tokens: list[str] = []

    for token in ASCII_TOKEN_RE.findall(normalized):
        tokens.append(token)

    for block in HAN_TOKEN_RE.findall(normalized):
        if len(block) <= 2:
            tokens.append(block)
            continue
        for index in range(len(block) - 1):
            tokens.append(block[index : index + 2])
        tokens.append(block[: min(len(block), 8)])

    if dedupe:
        return list(dict.fromkeys(tokens))
    return tokens


def build_fts_lexeme_text(*parts: str) -> str:
    """Build a whitespace-separated lexeme string for to_tsvector().

    Input:
    - parts: Text fragments that should contribute to full-text search.

    Output:
    - A whitespace-separated token string.

    Failure:
    - Never raises for normal string input.
    """
    tokens: list[str] = []
    for part in parts:
        tokens.extend(tokenize_text(part, dedupe=False))
    return " ".join(tokens)


def build_simple_tsquery(text: str) -> str:
    """Build a conservative OR tsquery expression from user text.

    Input:
    - text: User query text.

    Output:
    - A tsquery string such as "token1 | token2".

    Failure:
    - Never raises for normal string input.
    """
    escaped: list[str] = []
    for token in tokenize_text(text):
        cleaned = TSQUERY_ESCAPE_RE.sub(" ", token).strip()
        if cleaned:
            escaped.append(cleaned)
    return " | ".join(escaped)


def score_term_overlap(question: str, target_text: str) -> float:
    """Compute a lightweight lexical overlap score.

    Input:
    - question: User query.
    - target_text: Candidate text.

    Output:
    - A non-negative lexical score.

    Failure:
    - Never raises for normal string input.
    """
    target = normalize_text(target_text)
    if not target:
        return 0.0

    query_tokens = tokenize_text(question, dedupe=False)
    if not query_tokens:
        return 0.0

    score = 0.0
    token_counter = Counter(query_tokens)
    for token, weight in token_counter.items():
        if token and token in target:
            score += min(float(weight), 2.0)
    if normalize_text(question) and normalize_text(question) in target:
        score += 2.5
    return score


def unique_non_empty(values: Iterable[str]) -> list[str]:
    """Return unique non-empty strings in first-seen order.

    Input:
    - values: Arbitrary string iterable.

    Output:
    - Ordered unique non-empty strings.

    Failure:
    - Never raises for normal string input.
    """
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = (value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        results.append(item)
    return results
