from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text_search import normalize_text, tokenize_text, unique_non_empty


QUESTION_WORD_RE = re.compile(r"(谁|什么|为何|为什么|怎么样|怎样|多少|是否|哪[里个些]|讲了什么|内容|概述|总结)")
ENTITY_HINT_RE = re.compile(r"([\u4e00-\u9fffA-Za-z0-9·]{2,20})(是谁|是什么|为什么|为何|关系|结局|结尾|讲了什么|内容|概述|总结)")
CHAPTER_HINT_RE = re.compile(r"(第\s*[0-9一二三四五六七八九十百千万零两〇]+\s*[章节卷回部篇])")


@dataclass(frozen=True)
class QueryRewritePlan:
    original_query: str
    retrieval_query: str
    focus_query: str
    expansion_terms: list[str] = field(default_factory=list)
    strategy_tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "original_query": self.original_query,
            "retrieval_query": self.retrieval_query,
            "focus_query": self.focus_query,
            "expansion_terms": list(self.expansion_terms),
            "strategy_tags": list(self.strategy_tags),
        }


def rewrite_query(question: str) -> QueryRewritePlan:
    original = " ".join(part.strip() for part in (question or "").splitlines() if part.strip()).strip()
    if not original:
        return QueryRewritePlan(original_query="", retrieval_query="", focus_query="")

    strategy_tags: list[str] = ["identity"]
    expansion_terms: list[str] = []

    entity_match = ENTITY_HINT_RE.search(original)
    if entity_match:
        expansion_terms.append(entity_match.group(1).strip())
        strategy_tags.append("entity_focus")

    chapter_match = CHAPTER_HINT_RE.search(original)
    if chapter_match:
        expansion_terms.append(chapter_match.group(1).replace(" ", ""))
        strategy_tags.append("chapter_focus")

    focus_query = QUESTION_WORD_RE.sub(" ", original)
    focus_query = normalize_text(focus_query).replace(" ", " ").strip()
    if focus_query and focus_query != normalize_text(original):
        expansion_terms.append(focus_query)
        strategy_tags.append("question_word_strip")

    lexical_terms = [token for token in tokenize_text(original) if len(token) >= 2][:8]
    if lexical_terms:
        expansion_terms.extend(lexical_terms)
        strategy_tags.append("lexical_expand")

    unique_terms = unique_non_empty(expansion_terms)
    retrieval_query = " ".join(unique_non_empty([original, *unique_terms]))
    return QueryRewritePlan(
        original_query=original,
        retrieval_query=retrieval_query,
        focus_query=focus_query or original,
        expansion_terms=unique_terms,
        strategy_tags=unique_non_empty(strategy_tags),
    )
