"""Advanced RAG primitives shared by ingest, retrieval, evaluation and agents.

The module deliberately keeps the default path deterministic and dependency free.
External LLMs, vector stores and tracing exporters can opt in through callables or
environment variables, while local development still has a complete fallback.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence


_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]{2,}|[\u4e00-\u9fff]{2,8}")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])|(?<=[.!?])\s+|\n{2,}")
_HEADING_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s+|第[一二三四五六七八九十百千万0-9]+[章节篇部卷])")
_INJECTION_RE = re.compile(
    r"(?:ignore|disregard|forget).{0,36}(?:previous|system|developer|instruction|prompt)"
    r"|(?:忽略|无视).{0,20}(?:上文|系统|开发者|提示词|指令|规则)"
    r"|(?:reveal|show|print).{0,24}(?:system prompt|developer message|hidden prompt)"
    r"|(?:不要|无需).{0,12}(?:引用|证据|来源)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryVariant:
    text: str
    kind: str = "rewrite"
    weight: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryRoute:
    route: str
    reason: str
    needs_visual: bool = False
    needs_table: bool = False
    needs_graph: bool = False
    exact_token: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticChunk:
    chunk_id: str
    parent_id: str
    text: str
    start: int
    end: int
    section_title: str = ""
    chunk_kind: str = "child"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TableEvidence:
    columns: list[str]
    rows: list[dict[str, str]]
    source_text: str
    row_count: int
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphFact:
    subject: str
    relation: str
    object: str
    source_unit_id: str = ""
    confidence: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FreshnessMetadata:
    source_updated_at: str = ""
    indexed_at: str = ""
    expires_at: str = ""
    freshness_score: float = 0.5
    stale: bool = False
    action: str = "keep"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompilationArtifact:
    title: str
    outline: list[dict[str, Any]]
    entities: list[str]
    keywords: list[str]
    page_index: dict[str, int]
    content_hash: str
    generated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelRoute:
    route_key: str
    model: str
    reason: str
    estimated_input_tokens: int
    estimated_cost: float
    fallback_route: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_query(query: str) -> QueryRoute:
    cleaned = " ".join(str(query or "").split()).strip()
    lowered = cleaned.lower()
    exact = bool(re.search(r"(?:\b[A-Z]{2,}\b|\b\d+(?:\.\d+)+\b|版本|错误码|函数|接口|型号)", cleaned))
    visual = bool(re.search(r"截图|图片|图中|页面|界面|视觉|ocr|image|screenshot", lowered))
    table = bool(re.search(r"表格|表中|每一行|每列|统计|合计|占比|csv|excel|xlsx", lowered))
    graph = bool(re.search(r"关系|关联|依赖|上下游|谁负责|属于|连接|影响|全局|整体|全链路|所有依赖", lowered))
    if visual:
        return QueryRoute("multimodal", "query contains visual intent", needs_visual=True, exact_token=exact)
    if table:
        return QueryRoute("table", "query asks for tabular or aggregate evidence", needs_table=True, exact_token=exact)
    if graph:
        graph_route = "graph_global" if re.search(r"全局|整体|全链路|所有依赖", lowered) else "graph_local"
        return QueryRoute(graph_route, "query asks for entity or relationship evidence", needs_graph=True, exact_token=exact)
    if exact:
        return QueryRoute("exact", "query contains a stable identifier", exact_token=True)
    return QueryRoute("semantic", "default semantic retrieval")


def build_query_variants(
    query: str,
    *,
    expansion_terms: Iterable[str] = (),
    include_hyde: bool = False,
    hyde_generator: Callable[[str], str] | None = None,
    max_variants: int = 5,
) -> list[QueryVariant]:
    """Build deterministic Multi-Query variants with optional HyDE output.

    The fallback never invents an answer. When no generator is configured, a
    clearly marked deterministic document-style query is used instead.
    """
    cleaned = " ".join(str(query or "").split()).strip()
    if not cleaned:
        return []
    variants: list[QueryVariant] = [QueryVariant(cleaned, "original", 1.0)]
    terms = [str(item).strip() for item in expansion_terms if str(item).strip()]
    focus = " ".join(dict.fromkeys(terms[:8]))
    if focus and focus.lower() != cleaned.lower():
        variants.append(QueryVariant(f"{focus} {cleaned}".strip(), "multi_query", 0.85))
    stripped = re.sub(r"(?:请问|请|能否|可以|帮我|告诉我|什么是|如何|为什么)", " ", cleaned, flags=re.IGNORECASE)
    stripped = " ".join(stripped.split())
    if stripped and stripped.lower() != cleaned.lower():
        variants.append(QueryVariant(stripped, "focus", 0.8))
    if include_hyde:
        try:
            hypothetical = " ".join((str(hyde_generator(cleaned) if hyde_generator else f"相关文档通常描述：{cleaned}") or "").split()).strip()
        except Exception:
            hypothetical = ""
        if hypothetical:
            variants.append(QueryVariant(hypothetical[:1200], "hyde", 0.65))
    output: list[QueryVariant] = []
    seen: set[str] = set()
    for variant in variants:
        key = variant.text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(variant)
        if len(output) >= max(1, max_variants):
            break
    return output


def semantic_chunk_text(
    text: str,
    *,
    parent_id: str = "parent",
    section_title: str = "",
    target_chars: int = 1000,
    overlap_chars: int = 120,
) -> list[SemanticChunk]:
    """Split on headings and sentence boundaries before applying a bounded window."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    target = max(int(target_chars), 120)
    overlap = max(0, min(int(overlap_chars), target // 2))
    sentences = [part.strip() for part in _SENTENCE_RE.split(cleaned) if part.strip()]
    units: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > target:
            units.append(current.strip())
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        units.append(current)
    if not units:
        units = [cleaned]
    chunks: list[SemanticChunk] = []
    cursor = 0
    for index, unit in enumerate(units, start=1):
        position = cleaned.find(unit, cursor)
        position = cursor if position < 0 else position
        end = min(position + len(unit), len(cleaned))
        chunks.append(SemanticChunk(f"{parent_id}:{index}", parent_id, unit, position, end, section_title))
        cursor = max(end - overlap, position + 1)
    return chunks


def parent_child_retrieve(
    children: Sequence[Mapping[str, Any]],
    *,
    selected_ids: Iterable[str],
    parents: Mapping[str, str] | None = None,
    max_parent_chars: int = 2400,
) -> list[dict[str, Any]]:
    """Expand selected child chunks with their parent section context."""
    parent_map = dict(parents or {})
    selected = {str(item) for item in selected_ids if str(item)}
    output: list[dict[str, Any]] = []
    for item in children:
        unit_id = str(item.get("unit_id") or item.get("id") or "")
        if unit_id not in selected:
            continue
        row = dict(item)
        parent_id = str(row.get("parent_id") or row.get("section_id") or "")
        context = str(row.get("parent_text") or parent_map.get(parent_id) or "").strip()
        if context:
            row["parent_context"] = context[:max_parent_chars]
        row["retrieval_level"] = "child+parent"
        output.append(row)
    return output


def mmr_select(
    items: Sequence[Any],
    *,
    score_fn: Callable[[Any], float],
    text_fn: Callable[[Any], str],
    limit: int,
    diversity: float = 0.25,
) -> list[Any]:
    """Maximal marginal relevance using token shingles as a dependency-free fallback."""
    remaining = list(items)
    selected: list[Any] = []
    target = max(0, int(limit))
    while remaining and len(selected) < target:
        best = max(
            remaining,
            key=lambda item: float(score_fn(item)) - float(diversity) * max(
                (_jaccard(_token_set(text_fn(item)), _token_set(text_fn(other))) for other in selected
            ),
            default=0.0,
            ),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def adaptive_top_k(query: str, *, requested: int = 8, candidate_count: int = 0) -> int:
    route = classify_query(query).route
    base = max(1, int(requested))
    if route == "exact":
        base = min(base, 5)
    elif route in {"graph_local", "table"}:
        base = max(base, 8)
    elif len(_token_set(query)) <= 3:
        base = max(base, 10)
    return min(max(base, 1), max(candidate_count, base) if candidate_count else base)


def normalize_table_evidence(text: str, *, delimiter: str = "|") -> TableEvidence | None:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    rows = [[cell.strip() for cell in line.strip("|").split(delimiter)] for line in lines if delimiter in line]
    if len(rows) < 2:
        return None
    columns = rows[0]
    if not columns or len(columns) < 2:
        return None
    normalized: list[dict[str, str]] = []
    for values in rows[1:]:
        if values and all(re.fullmatch(r":?-{2,}:?", value.replace(" ", "")) for value in values):
            continue
        padded = (values + [""] * len(columns))[: len(columns)]
        normalized.append({columns[index]: padded[index] for index in range(len(columns))})
    return TableEvidence(columns, normalized, "\n".join(lines), len(normalized), 0.9)


def extract_graph_facts(text: str, *, source_unit_id: str = "") -> list[GraphFact]:
    facts: list[GraphFact] = []
    patterns = (
        re.compile(r"([\u4e00-\u9fffA-Za-z0-9_-]{2,30})\s*(?:属于|隶属|负责|依赖|关联|连接)\s*([\u4e00-\u9fffA-Za-z0-9_-]{2,30})"),
        re.compile(r"([\u4e00-\u9fffA-Za-z0-9_-]{2,30})\s+(?:is|owns|depends on|relates to)\s+([A-Za-z0-9_-]{2,30})", re.IGNORECASE),
    )
    for pattern in patterns:
        for match in pattern.finditer(str(text or "")):
            relation = "关系"
            facts.append(GraphFact(match.group(1).strip(), relation, match.group(2).strip(), source_unit_id, 0.65))
    return facts[:32]


def graph_route_evidence(query: str, evidence: Sequence[Any], *, mode: str = "local") -> list[Any]:
    """Route graph-like questions without requiring a graph database."""
    query_terms = _token_set(query)
    scored: list[tuple[float, Any]] = []
    for item in evidence:
        text = _item_text(item)
        facts = extract_graph_facts(text)
        entity_hit = len(query_terms.intersection(_token_set(text)))
        graph_bonus = 0.25 if facts else 0.0
        if mode == "global":
            graph_bonus += min(len(facts), 4) * 0.05
        scored.append((entity_hit + graph_bonus, item))
    return [item for _score, item in sorted(scored, key=lambda pair: pair[0], reverse=True)]


def sanitize_evidence_text(text: str) -> tuple[str, list[str]]:
    """Neutralize instruction-like evidence while preserving factual text."""
    cleaned = str(text or "")
    matches = _INJECTION_RE.findall(cleaned)
    if not matches:
        return cleaned, []
    sanitized = _INJECTION_RE.sub("[untrusted instruction removed]", cleaned)
    return sanitized, ["evidence_prompt_injection"]


def build_freshness_metadata(
    *,
    source_updated_at: Any = None,
    indexed_at: Any = None,
    expires_at: Any = None,
    stale_after_days: int = 30,
    now: datetime | None = None,
) -> FreshnessMetadata:
    current = now or datetime.now(timezone.utc)
    updated = _parse_datetime(source_updated_at)
    indexed = _parse_datetime(indexed_at)
    expires = _parse_datetime(expires_at)
    age_days = max((current - updated).total_seconds() / 86400.0, 0.0) if updated else 0.0
    score = max(0.05, min(1.0, 1.0 - age_days / max(float(stale_after_days), 1.0))) if updated else 0.5
    stale = bool(expires and expires < current) or bool(updated and indexed and updated > indexed) or age_days > stale_after_days
    action = "reindex" if expires and expires < current else "refresh" if stale else "keep"
    return FreshnessMetadata(
        source_updated_at=updated.isoformat() if updated else str(source_updated_at or ""),
        indexed_at=indexed.isoformat() if indexed else str(indexed_at or ""),
        expires_at=expires.isoformat() if expires else str(expires_at or ""),
        freshness_score=round(score, 6),
        stale=stale,
        action=action,
    )


def compile_knowledge_document(text: str, *, title: str = "") -> CompilationArtifact:
    """Create a PageIndex-like deterministic outline and retrieval metadata."""
    cleaned = str(text or "").strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    outline: list[dict[str, Any]] = []
    page_index: dict[str, int] = {}
    current: dict[str, Any] | None = None
    for line in lines:
        if _HEADING_RE.match(line) or (len(line) <= 80 and line.endswith((":", "："))):
            current = {"title": line.lstrip("# ").strip(), "summary": "", "children": []}
            outline.append(current)
        elif current is not None:
            if not current["summary"]:
                current["summary"] = line[:240]
            elif len(current["children"]) < 8:
                current["children"].append(line[:180])
        if re.search(r"(?:第\s*\d+\s*页|page\s*\d+)", line, re.IGNORECASE):
            page_match = re.search(r"(?:第\s*(\d+)\s*页|page\s*(\d+))", line, re.IGNORECASE)
            if page_match:
                page_index[line[:80]] = int(page_match.group(1) or page_match.group(2))
    keywords = list(dict.fromkeys(_TOKEN_RE.findall(cleaned.lower())))[:40]
    entities = [item for item in keywords if len(item) >= 3][:20]
    return CompilationArtifact(
        title=str(title or "").strip(),
        outline=outline[:80],
        entities=entities,
        keywords=keywords,
        page_index=page_index,
        content_hash=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def choose_rag_model_route(
    query: str,
    *,
    candidate_count: int = 0,
    context_tokens: int = 0,
    budget: float = 0.0,
    routes: Mapping[str, Mapping[str, Any]] | None = None,
) -> ModelRoute:
    route_config = dict(routes or {})
    complexity = len(_token_set(query)) + min(candidate_count, 10) + min(context_tokens // 800, 10)
    if classify_query(query).route == "exact" and complexity < 8:
        key = "fast_exact"
    elif complexity >= 18:
        key = "deep_grounded"
    else:
        key = "balanced_grounded"
    config = dict(route_config.get(key) or {})
    model = str(config.get("model") or os.getenv("RAG_DEFAULT_MODEL", "deepseek-chat"))
    input_tokens = max(int(context_tokens), len(str(query)) // 2)
    unit_cost = float(config.get("input_cost_per_1k") or os.getenv("RAG_INPUT_COST_PER_1K", "0") or 0.0)
    estimated = round(input_tokens / 1000.0 * unit_cost, 8)
    if budget > 0 and estimated > budget:
        key = "fast_exact"
        config = dict(route_config.get(key) or {})
        model = str(config.get("model") or model)
        estimated = round(input_tokens / 1000.0 * float(config.get("input_cost_per_1k") or unit_cost), 8)
    return ModelRoute(key, model, f"complexity={complexity}; budget={budget:.6f}", input_tokens, estimated, str(config.get("fallback_route") or ""))


def build_evaluation_record(
    *,
    question: str,
    answer: str = "",
    evidence: Sequence[Mapping[str, Any]] = (),
    expected_ids: Iterable[str] = (),
    trace_id: str = "",
    latency_ms: float = 0.0,
    cost: float = 0.0,
    safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    retrieved = [str(item.get("unit_id") or item.get("id") or "") for item in evidence]
    expected = {str(item) for item in expected_ids if str(item)}
    hits = len(expected.intersection(retrieved))
    return {
        "question": str(question or ""),
        "answer": str(answer or ""),
        "retrieved_unit_ids": retrieved,
        "expected_unit_ids": sorted(expected),
        "recall": round(hits / len(expected), 4) if expected else 0.0,
        "citation_count": len([item for item in evidence if item.get("document_id")]),
        "latency_ms": round(float(latency_ms), 3),
        "cost": round(float(cost), 8),
        "trace_id": str(trace_id or ""),
        "safety": dict(safety or {}),
    }


def _item_text(item: Any) -> str:
    if isinstance(item, Mapping):
        return " ".join(str(item.get(key) or "") for key in ("section_title", "quote", "raw_text", "parent_context"))
    return str(getattr(item, "raw_text", "") or getattr(item, "quote", "") or item)


def _token_set(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(str(text or ""))}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


__all__ = [
    "CompilationArtifact",
    "FreshnessMetadata",
    "GraphFact",
    "ModelRoute",
    "QueryRoute",
    "QueryVariant",
    "SemanticChunk",
    "TableEvidence",
    "adaptive_top_k",
    "build_evaluation_record",
    "build_freshness_metadata",
    "build_query_variants",
    "choose_rag_model_route",
    "classify_query",
    "compile_knowledge_document",
    "extract_graph_facts",
    "graph_route_evidence",
    "mmr_select",
    "normalize_table_evidence",
    "parent_child_retrieve",
    "sanitize_evidence_text",
    "semantic_chunk_text",
]
