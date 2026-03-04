from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import Any, List, Literal, Sequence
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchAny, ScoredPoint


COMMON_KNOWLEDGE_PREFIX = "【常识补充】"

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "ollama": "http://host.docker.internal:11434/v1",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
EVIDENCE_DUMP_RE = re.compile(r"\[\d+\]\s*file=", re.IGNORECASE)


class Scope(BaseModel):
    mode: Literal["single", "multi"]
    corpus_ids: List[str] = Field(min_length=1)
    document_ids: List[str] = Field(default_factory=list)
    allow_common_knowledge: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> "Scope":
        if self.mode == "single" and len(self.corpus_ids) != 1:
            raise ValueError("scope.mode=single requires exactly one corpus_id")
        if self.mode == "multi" and len(self.corpus_ids) < 2:
            raise ValueError("scope.mode=multi requires at least two corpus_ids")

        corpus_seen: set[str] = set()
        for corpus_id in self.corpus_ids:
            trimmed = corpus_id.strip()
            if not trimmed:
                raise ValueError("scope.corpus_ids must not contain empty values")
            _validate_uuid(trimmed, "scope.corpus_ids")
            if trimmed in corpus_seen:
                raise ValueError(f"scope.corpus_ids contains duplicate value: {trimmed}")
            corpus_seen.add(trimmed)

        document_seen: set[str] = set()
        for document_id in self.document_ids:
            trimmed = document_id.strip()
            if not trimmed:
                raise ValueError("scope.document_ids must not contain empty values")
            _validate_uuid(trimmed, "scope.document_ids")
            if trimmed in document_seen:
                raise ValueError(f"scope.document_ids contains duplicate value: {trimmed}")
            document_seen.add(trimmed)

        return self


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    scope: Scope


class AnswerSentence(BaseModel):
    text: str
    evidence_type: Literal["source", "common_knowledge"]
    citation_ids: List[str]
    confidence: float


class Citation(BaseModel):
    citation_id: str
    file_name: str
    page_or_loc: str
    chunk_id: str
    snippet: str


class QueryResponse(BaseModel):
    answer_sentences: List[AnswerSentence]
    citations: List[Citation]


@dataclass(frozen=True)
class ServiceConfig:
    qdrant_url: str
    qdrant_collection: str
    embedding_dim: int
    retrieval_top_n: int
    rerank_top_k: int
    source_sentence_limit: int
    evidence_min_score: float
    common_knowledge_max_ratio: float
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_embedding_model: str
    llm_chat_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_retry_delay_milliseconds: int


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: str
    document_id: str
    corpus_id: str
    file_name: str
    page_or_loc: str
    text: str
    vector_score: float
    lexical_score: float
    final_score: float


def _resolve_provider_base_url(provider: str, explicit_base_url: str) -> str:
    explicit = explicit_base_url.strip()
    if explicit:
        return explicit.rstrip("/")

    normalized = provider.strip().lower()
    if normalized == "custom":
        return ""

    return PROVIDER_BASE_URLS.get(normalized, PROVIDER_BASE_URLS["openai"])


class LLMGateway:
    def __init__(self, cfg: ServiceConfig):
        self._cfg = cfg
        self._base_url = _resolve_provider_base_url(cfg.llm_provider, cfg.llm_base_url)
        self._client = httpx.Client(timeout=cfg.llm_timeout_seconds)

    @property
    def embedding_enabled(self) -> bool:
        return bool(self._cfg.llm_api_key and self._cfg.llm_embedding_model and self._base_url)

    @property
    def chat_enabled(self) -> bool:
        return bool(self._cfg.llm_api_key and self._cfg.llm_chat_model and self._base_url)

    def embed(self, text: str) -> List[float]:
        if not self.embedding_enabled:
            return hash_embedding(text, self._cfg.embedding_dim)

        payload = {
            "model": self._cfg.llm_embedding_model,
            "input": text,
        }
        data = self._request_json("/embeddings", payload)
        try:
            embedding = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("embedding response format invalid") from exc

        if not isinstance(embedding, list) or len(embedding) == 0:
            raise RuntimeError("embedding response contains empty vector")

        try:
            return [float(v) for v in embedding]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("embedding response contains non-numeric vector values") from exc

    def generate_summary(self, question: str, evidence: Sequence[RankedChunk]) -> str:
        if not self.chat_enabled or len(evidence) == 0:
            return ""

        evidence_lines = []
        for idx, chunk in enumerate(evidence, start=1):
            evidence_lines.append(
                f"[{idx}] file={chunk.file_name} loc={chunk.page_or_loc}\n{compact_snippet(chunk.text, limit=260)}"
            )

        payload = {
            "model": self._cfg.llm_chat_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是企业知识库问答助手。"
                        "必须严格基于给定证据回答，不可虚构。"
                        "输出中文，最多两句，不要输出引用编号。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"问题：{question}\n\n"
                        f"证据：\n{chr(10).join(evidence_lines)}\n\n"
                        "请给出简洁答案。"
                    ),
                },
            ],
        }
        data = self._request_json("/chat/completions", payload)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("chat response format invalid") from exc

        if isinstance(content, list):
            pieces: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    pieces.append(str(item["text"]))
            merged = "".join(pieces).strip()
        else:
            merged = str(content).strip()

        if not merged:
            raise RuntimeError("chat response content is empty")

        return merged

    def _request_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("LLM_BASE_URL is required when LLM_PROVIDER=custom")

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._cfg.llm_api_key}",
            "Content-Type": "application/json",
        }

        attempts = self._cfg.llm_max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    self._sleep_between_retries()
                    continue
                raise RuntimeError(f"llm request failed: {exc}") from exc

            if resp.status_code >= 500 and attempt < attempts:
                self._sleep_between_retries()
                continue

            if resp.status_code >= 400:
                body = (resp.text or "").strip().replace("\n", " ")
                if len(body) > 300:
                    body = body[:300] + "..."
                raise RuntimeError(f"llm request rejected: status={resp.status_code} body={body}")

            try:
                data = resp.json()
            except ValueError as exc:
                raise RuntimeError("llm response is not valid json") from exc

            if not isinstance(data, dict):
                raise RuntimeError("llm response json is not an object")
            return data

        raise RuntimeError("llm request exhausted retries")

    def _sleep_between_retries(self) -> None:
        delay_ms = self._cfg.llm_retry_delay_milliseconds
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)


class RAGEngine:
    def __init__(self, cfg: ServiceConfig):
        self._cfg = cfg
        self._client = QdrantClient(url=cfg.qdrant_url)
        self._llm = LLMGateway(cfg)

    def query(self, question: str, scope: Scope) -> QueryResponse:
        query_vector = self._llm.embed(question)
        query_filter = build_scope_filter(scope)

        query_result = self._client.query_points(
            collection_name=self._cfg.qdrant_collection,
            query=query_vector,
            query_filter=query_filter,
            limit=self._cfg.retrieval_top_n,
            with_payload=True,
            with_vectors=False,
        )

        ranked = rerank_points(question, query_result.points, self._cfg.rerank_top_k)
        if not ranked:
            return build_no_evidence_response()

        best = ranked[0]
        if best.final_score < self._cfg.evidence_min_score:
            return build_weak_evidence_response(best)

        source_limit = min(self._cfg.source_sentence_limit, len(ranked))
        selected = ranked[:source_limit]

        citations: list[Citation] = []
        for idx, chunk in enumerate(selected, start=1):
            citation_id = f"c{idx}"
            citations.append(
                Citation(
                    citation_id=citation_id,
                    file_name=chunk.file_name,
                    page_or_loc=chunk.page_or_loc,
                    chunk_id=chunk.chunk_id,
                    snippet=compact_snippet(chunk.text, limit=220),
                )
            )

        answer_sentences: list[AnswerSentence] = []
        summary = ""
        try:
            summary = self._llm.generate_summary(question, selected)
        except Exception:
            summary = ""
        summary = sanitize_summary(summary)
        if summary:
            answer_sentences.append(
                AnswerSentence(
                    text=summary,
                    evidence_type="source",
                    citation_ids=[item.citation_id for item in citations],
                    confidence=clip_confidence(best.final_score),
                )
            )
        else:
            fallback_selected = selected[: min(2, len(selected))]
            for idx, chunk in enumerate(fallback_selected, start=1):
                citation_id = f"c{idx}"
                snippet = compact_snippet(chunk.text, limit=220)
                answer_sentences.append(
                    AnswerSentence(
                        text=f"根据资料可知：{snippet}",
                        evidence_type="source",
                        citation_ids=[citation_id],
                        confidence=clip_confidence(chunk.final_score),
                    )
                )

        max_common = max_common_sentences(len(answer_sentences), self._cfg.common_knowledge_max_ratio)
        if scope.allow_common_knowledge and max_common > 0:
            answer_sentences.append(
                AnswerSentence(
                    text=f"{COMMON_KNOWLEDGE_PREFIX}以下内容为模型补充推断，请结合原文证据核验。",
                    evidence_type="common_knowledge",
                    citation_ids=[],
                    confidence=0.3,
                )
            )

        return QueryResponse(answer_sentences=answer_sentences, citations=citations)


def getenv_int(name: str, fallback: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def getenv_float(name: str, fallback: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def build_service_config() -> ServiceConfig:
    llm_timeout_seconds = getenv_float("LLM_TIMEOUT_SECONDS", 30)
    if llm_timeout_seconds <= 0:
        llm_timeout_seconds = 30

    llm_max_retries = getenv_int("LLM_MAX_RETRIES", 2)
    if llm_max_retries < 0:
        llm_max_retries = 0

    llm_retry_delay_milliseconds = getenv_int("LLM_RETRY_DELAY_MILLISECONDS", 600)
    if llm_retry_delay_milliseconds < 0:
        llm_retry_delay_milliseconds = 0

    return ServiceConfig(
        qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "rag_chunks"),
        embedding_dim=max(getenv_int("EMBEDDING_DIM", 256), 32),
        retrieval_top_n=max(getenv_int("RAG_RETRIEVAL_TOP_N", 24), 1),
        rerank_top_k=max(getenv_int("RAG_RERANK_TOP_K", 8), 1),
        source_sentence_limit=max(getenv_int("RAG_SOURCE_SENTENCE_LIMIT", 6), 1),
        evidence_min_score=getenv_float("RAG_EVIDENCE_MIN_SCORE", 0.05),
        common_knowledge_max_ratio=getenv_float("RAG_COMMON_KNOWLEDGE_MAX_RATIO", 0.15),
        llm_provider=(os.getenv("LLM_PROVIDER", "openai").strip().lower() or "openai"),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_embedding_model=os.getenv("LLM_EMBEDDING_MODEL", "").strip(),
        llm_chat_model=os.getenv("LLM_CHAT_MODEL", "").strip(),
        llm_timeout_seconds=llm_timeout_seconds,
        llm_max_retries=llm_max_retries,
        llm_retry_delay_milliseconds=llm_retry_delay_milliseconds,
    )


def _validate_uuid(raw: str, field_name: str) -> None:
    try:
        UUID(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} contains invalid uuid: {raw}") from exc


def hash_embedding(text: str, dim: int) -> List[float]:
    seed = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    values: List[float] = []
    counter = 0
    while len(values) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for item in block:
            values.append((item / 127.5) - 1.0)
            if len(values) >= dim:
                break
        counter += 1

    norm = sum(value * value for value in values) ** 0.5
    if norm == 0:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def build_scope_filter(scope: Scope) -> Filter:
    must: list[FieldCondition] = [
        FieldCondition(key="corpus_id", match=MatchAny(any=scope.corpus_ids)),
    ]
    if scope.document_ids:
        must.append(FieldCondition(key="document_id", match=MatchAny(any=scope.document_ids)))
    return Filter(must=must)


def rerank_points(question: str, points: Sequence[ScoredPoint], top_k: int) -> list[RankedChunk]:
    question_tokens = tokenize(question)
    ranked: list[RankedChunk] = []

    for point in points:
        payload = point.payload or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            continue

        lexical = lexical_overlap(question_tokens, text)
        vector_score = float(point.score or 0.0)
        final_score = (vector_score * 0.75) + (lexical * 0.25)

        ranked.append(
            RankedChunk(
                chunk_id=str(point.id),
                document_id=str(payload.get("document_id", "")),
                corpus_id=str(payload.get("corpus_id", "")),
                file_name=str(payload.get("file_name", "unknown")),
                page_or_loc=str(payload.get("page_or_loc", "loc:unknown")),
                text=text,
                vector_score=vector_score,
                lexical_score=lexical,
                final_score=final_score,
            )
        )

    ranked.sort(key=lambda item: item.final_score, reverse=True)
    return ranked[:top_k]


def tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


def lexical_overlap(question_tokens: set[str], source_text: str) -> float:
    if not question_tokens:
        return 0.0

    source_tokens = tokenize(source_text)
    if not source_tokens:
        return 0.0

    matched = sum(1 for token in question_tokens if token in source_tokens)
    return matched / float(len(question_tokens))


def compact_snippet(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def sanitize_summary(summary: str) -> str:
    cleaned = " ".join(summary.split()).strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    if EVIDENCE_DUMP_RE.search(cleaned):
        return ""
    if "file=" in lowered and "loc=" in lowered:
        return ""
    if "text:" in lowered and cleaned.count("[") >= 1:
        return ""
    return cleaned


def clip_confidence(score: float) -> float:
    if score < 0.05:
        return 0.05
    if score > 0.99:
        return 0.99
    return round(score, 4)


def max_common_sentences(source_count: int, ratio: float) -> int:
    if source_count <= 0 or ratio <= 0 or ratio >= 1:
        return 0
    return int((ratio * source_count) / (1 - ratio))


def build_no_evidence_response() -> QueryResponse:
    return QueryResponse(
        answer_sentences=[
            AnswerSentence(
                text=f"{COMMON_KNOWLEDGE_PREFIX}未检索到可用文档证据，请调整提问范围或补充资料。",
                evidence_type="common_knowledge",
                citation_ids=[],
                confidence=0.0,
            )
        ],
        citations=[],
    )


def build_weak_evidence_response(best: RankedChunk) -> QueryResponse:
    citation = Citation(
        citation_id="c1",
        file_name=best.file_name,
        page_or_loc=best.page_or_loc,
        chunk_id=best.chunk_id,
        snippet=compact_snippet(best.text, limit=220),
    )

    sentence = AnswerSentence(
        text=f"证据相关性偏低，建议优先查看《{best.file_name}》{best.page_or_loc}原文后再确认结论。",
        evidence_type="source",
        citation_ids=[citation.citation_id],
        confidence=0.2,
    )
    return QueryResponse(answer_sentences=[sentence], citations=[citation])


def build_engine() -> RAGEngine:
    return RAGEngine(build_service_config())


app = FastAPI(title="py-rag-service", version="0.3.0")


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok", "service": "py-rag-service"}


@app.post("/v1/rag/query", response_model=QueryResponse)
def rag_query(payload: QueryRequest) -> QueryResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be blank")

    if not hasattr(app.state, "engine"):
        app.state.engine = build_engine()

    try:
        return app.state.engine.query(question, payload.scope)
    except Exception:
        return QueryResponse(
            answer_sentences=[
                AnswerSentence(
                    text=f"{COMMON_KNOWLEDGE_PREFIX}当前检索服务暂不可用，请稍后重试。",
                    evidence_type="common_knowledge",
                    citation_ids=[],
                    confidence=0.1,
                )
            ],
            citations=[],
        )
