from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, Sequence
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchAny, ScoredPoint

from .hybrid_retriever import HybridRetriever, RetrievalResult
from .logger import setup_logger
from .query_cache import QueryCache
from .intent_classifier import IntentClassifier, get_classifier, IntentType
from .query_rewriter import QueryRewriter, MultiQueryRetriever
from .exceptions import RAGServiceError, LLMError, RetrievalError, ValidationError
from .metrics import metrics_collector, QueryMetrics
from .retrieval_tracker import get_tracker, track_retrieval, get_retrieval_quality_stats

logger = setup_logger(
    name=__name__,
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name="py-rag-service",
)


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


class StreamQueryRequest(BaseModel):
    """流式查询请求（与传统请求相同）"""
    question: str = Field(min_length=1, max_length=8000)
    scope: Scope


class StreamQueryParams(BaseModel):
    """流式查询 URL 参数"""
    question: str = Field(min_length=1, max_length=8000)
    scope_json: str = Field(..., description="JSON encoded Scope object")


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
    hybrid_dense_weight: float
    hybrid_sparse_weight: float
    reranker_model: str
    query_cache_enabled: bool
    query_cache_ttl_hours: int
    query_cache_max_size: int
    multi_query_enabled: bool
    multi_query_max_variants: int
    multi_query_timeout_ms: int


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
        self._hybrid_retriever = HybridRetriever(
            dense_weight=cfg.hybrid_dense_weight,
            sparse_weight=cfg.hybrid_sparse_weight,
        )
        self._intent_classifier = get_classifier()
        self._query_rewriter = QueryRewriter(llm_client=None)
        self._multi_query_retriever: Optional[MultiQueryRetriever] = None
        if cfg.multi_query_enabled:
            self._multi_query_retriever = MultiQueryRetriever(
                base_retriever=self._hybrid_retriever,
                query_rewriter=self._query_rewriter,
                max_variants=cfg.multi_query_max_variants,
                timeout_ms=cfg.multi_query_timeout_ms,
            )
        self._last_retrieval_count = 0
        self._last_rerank_scores: list[float] = []
        self._last_intent: Optional[Dict] = None
        self._query_cache: Optional[QueryCache] = None
        if cfg.query_cache_enabled:
            self._query_cache = QueryCache(
                max_size=cfg.query_cache_max_size,
                ttl_hours=cfg.query_cache_ttl_hours,
            )

    def query(self, question: str, scope: Scope) -> QueryResponse:
        start_time = time.time()
        query_id = None
        
        try:
            query_id = get_tracker().generate_query_id()
        except Exception:
            pass
        
        metrics_start = metrics_collector.start_request()
        cache_key = self._build_cache_key(question, scope)
        
        if self._query_cache is not None:
            cached_result = self._query_cache.get(cache_key)
            if cached_result is not None:
                metrics_collector.record_cache_hit()
                metrics_collector.end_request(metrics_start)
                
                intent_result = self._last_intent or {"intent": "unknown", "confidence": 0.0}
                metrics_collector.record_query(QueryMetrics(
                    latency_seconds=(time.time() - start_time),
                    cache_hit=True,
                    retrieval_count=0,
                    status="success",
                    intent=intent_result.get("intent", "unknown"),
                    intent_confidence=intent_result.get("confidence", 0.0),
                    query_id=query_id,
                ))
                
                return cached_result

        metrics_collector.record_cache_miss()
        
        intent_result = self._intent_classifier.classify_and_get_strategy(question)
        self._last_intent = intent_result
        
        logger.info(
            f"Intent classification result",
            extra={
                "query_id": query_id,
                "extra_fields": {
                    "intent": intent_result["intent"],
                    "confidence": intent_result["confidence"],
                    "reason": intent_result["reason"],
                },
                "intent_info": {
                    "intent": intent_result["intent"],
                    "confidence": intent_result["confidence"],
                    "reason": intent_result["reason"],
                },
            },
        )
        
        strategy = intent_result["strategy"]
        effective_top_n = strategy.get("top_k", self._cfg.retrieval_top_n)
        effective_rerank_top_k = strategy.get("rerank_top_k", self._cfg.rerank_top_k)
        effective_dense_weight = strategy.get("dense_weight", self._cfg.hybrid_dense_weight)
        effective_sparse_weight = strategy.get("sparse_weight", self._cfg.hybrid_sparse_weight)
        
        logger.info(
            f"Routing to retrieval strategy based on intent",
            extra={
                "query_id": query_id,
                "extra_fields": {
                    "intent": intent_result["intent"],
                    "top_k": effective_top_n,
                    "rerank_top_k": effective_rerank_top_k,
                    "dense_weight": effective_dense_weight,
                    "sparse_weight": effective_sparse_weight,
                },
                "retrieval_stats": {
                    "top_k": effective_top_n,
                    "rerank_top_k": effective_rerank_top_k,
                    "dense_weight": effective_dense_weight,
                },
            },
        )

        query_filter = build_scope_filter(scope)

        multi_query_used = False
        multi_query_variants = 0
        
        if self._multi_query_retriever is not None and self._cfg.multi_query_enabled:
            multi_query_used = True
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            ranked_points = loop.run_until_complete(
                self._multi_query_retriever.retrieve(
                    question=question,
                    top_k=effective_rerank_top_k,
                    query_filter=query_filter,
                )
            )
            
            multi_query_variants = getattr(self._multi_query_retriever, '_last_variant_count', 0)
            if multi_query_variants > 0:
                metrics_collector.record_multi_query_usage(multi_query_variants)
            
            ranked = self._convert_to_ranked_chunks(question, ranked_points, effective_dense_weight)
        else:
            query_vector = self._llm.embed(question)

            query_result = self._client.query_points(
                collection_name=self._cfg.qdrant_collection,
                query=query_vector,
                query_filter=query_filter,
                limit=effective_top_n,
                with_payload=True,
                with_vectors=False,
            )

            ranked = rerank_points(
                question,
                query_result.points,
                effective_rerank_top_k,
                dense_weight=effective_dense_weight,
            )
        self._last_retrieval_count = len(ranked)
        
        if not ranked:
            self._last_rerank_scores = []
            response = build_no_evidence_response()
        else:
            self._last_rerank_scores = [item.final_score for item in ranked]

            best = ranked[0]
            if best.final_score < self._cfg.evidence_min_score:
                response = build_weak_evidence_response(best)
            else:
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

                response = QueryResponse(answer_sentences=answer_sentences, citations=citations)

        if self._query_cache is not None:
            self._query_cache.set(cache_key, response)
        
        latency = time.time() - start_time
        metrics_collector.end_request(metrics_start)
        
        avg_rerank_score = sum(self._last_rerank_scores) / len(self._last_rerank_scores) if self._last_rerank_scores else 0.0
        
        metrics_collector.record_query(QueryMetrics(
            latency_seconds=latency,
            cache_hit=False,
            retrieval_count=len(ranked),
            rerank_score_avg=avg_rerank_score,
            status="success",
            intent=intent_result.get("intent", "unknown"),
            intent_confidence=intent_result.get("confidence", 0.0),
            multi_query_used=multi_query_used,
            multi_query_variants=multi_query_variants,
            query_id=query_id,
        ))
        
        logger.info(
            f"RAG query completed",
            extra={
                "query_id": query_id,
                "extra_fields": {
                    "answer_sentences": len(response.answer_sentences),
                    "citations": len(response.citations),
                    "retrieval_count": len(ranked),
                    "avg_rerank_score": round(avg_rerank_score, 4),
                    "latency_ms": round(latency * 1000, 2),
                },
                "retrieval_stats": {
                    "retrieved_docs": len(ranked),
                    "avg_score": round(avg_rerank_score, 4),
                    "top_score": round(self._last_rerank_scores[0], 4) if self._last_rerank_scores else 0.0,
                },
            },
        )
        
        try:
            track_retrieval(
                question=question,
                intent=intent_result.get("intent", "unknown"),
                intent_confidence=intent_result.get("confidence", 0.0),
                retrieval_count=len(ranked),
                rerank_scores=self._last_rerank_scores,
                cache_hit=False,
                multi_query_used=multi_query_used,
                latency_ms=latency * 1000,
                multi_query_variants=multi_query_variants,
            )
        except Exception as e:
            logger.warning(f"Failed to track retrieval: {e}")
        
        return response

    def _build_cache_key(self, question: str, scope: Scope) -> str:
        scope_str = f"{scope.mode}|{','.join(sorted(scope.corpus_ids))}|{','.join(sorted(scope.document_ids))}|{scope.allow_common_knowledge}"
        return f"{question.strip()}||{scope_str}"

    def _convert_to_ranked_chunks(self, question: str, points, dense_weight: float) -> list[RankedChunk]:
        lexical_weight = 1.0 - dense_weight
        question_tokens = tokenize(question)
        ranked: list[RankedChunk] = []

        for point in points:
            payload = getattr(point, 'payload', {}) or {}
            text = str(payload.get('text', '')).strip()
            if not text:
                continue

            lexical = lexical_overlap(question_tokens, text)
            vector_score = float(getattr(point, 'score', 0.0))
            final_score = (vector_score * dense_weight) + (lexical * lexical_weight)

            ranked.append(
                RankedChunk(
                    chunk_id=str(getattr(point, 'id', '')),
                    document_id=str(payload.get('document_id', '')),
                    corpus_id=str(payload.get('corpus_id', '')),
                    file_name=str(payload.get('file_name', 'unknown')),
                    page_or_loc=str(payload.get('page_or_loc', 'loc:unknown')),
                    text=text,
                    vector_score=vector_score,
                    lexical_score=lexical,
                    final_score=final_score,
                )
            )

        ranked.sort(key=lambda item: item.final_score, reverse=True)
        return ranked

    @property
    def cache_stats(self) -> Optional[Dict[str, Any]]:
        if self._query_cache is None:
            return None
        return self._query_cache.stats

    async def query_stream(self, question: str, scope: Scope) -> AsyncGenerator[str, None]:
        """流式查询：逐句发送 answer_sentences
        
        SSE 格式:
        - data: {"type": "sentence", "data": {...}}\n\n
        - data: {"type": "citation", "data": {...}}\n\n
        - data: {"type": "done"}\n\n
        - data: {"type": "error", "message": "..."}}\n\n
        """
        try:
            yield self._format_sse("sentence", {"text": "正在识别问题意图...", "evidence_type": "source", "citation_ids": [], "confidence": 0.5})
            
            # 意图识别步骤
            intent_result = self._intent_classifier.classify_and_get_strategy(question)
            self._last_intent = intent_result
            
            logger.info(
                f"Intent classification result (stream)",
                extra={
                    "extra_fields": {
                        "intent": intent_result["intent"],
                        "confidence": intent_result["confidence"],
                        "reason": intent_result["reason"],
                    }
                },
            )
            
            # 根据意图调整检索策略
            strategy = intent_result["strategy"]
            effective_top_n = strategy.get("top_k", self._cfg.retrieval_top_n)
            effective_rerank_top_k = strategy.get("rerank_top_k", self._cfg.rerank_top_k)
            effective_dense_weight = strategy.get("dense_weight", self._cfg.hybrid_dense_weight)
            
            yield self._format_sse("sentence", {"text": f"正在基于意图 [{intent_result['intent']}] 检索相关知识...", "evidence_type": "source", "citation_ids": [], "confidence": 0.5})
            
            query_vector = self._llm.embed(question)
            query_filter = build_scope_filter(scope)

            query_result = self._client.query_points(
                collection_name=self._cfg.qdrant_collection,
                query=query_vector,
                query_filter=query_filter,
                limit=effective_top_n,
                with_payload=True,
                with_vectors=False,
            )

            ranked = rerank_points(
                question,
                query_result.points,
                effective_rerank_top_k,
                dense_weight=effective_dense_weight,
            )
            if not ranked:
                response = build_no_evidence_response()
                for sentence in response.answer_sentences:
                    yield self._format_sse("sentence", sentence.model_dump())
                yield self._format_sse("done")
                return

            best = ranked[0]
            if best.final_score < self._cfg.evidence_min_score:
                response = build_weak_evidence_response(best)
                for sentence in response.answer_sentences:
                    yield self._format_sse("sentence", sentence.model_dump())
                for citation in response.citations:
                    yield self._format_sse("citation", citation.model_dump())
                yield self._format_sse("done")
                return

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

            for citation in citations:
                yield self._format_sse("citation", citation.model_dump())

            answer_sentences: list[AnswerSentence] = []
            summary = ""
            try:
                summary = self._llm.generate_summary(question, selected)
            except Exception:
                summary = ""
            summary = sanitize_summary(summary)
            if summary:
                sentence = AnswerSentence(
                    text=summary,
                    evidence_type="source",
                    citation_ids=[item.citation_id for item in citations],
                    confidence=clip_confidence(best.final_score),
                )
                answer_sentences.append(sentence)
                yield self._format_sse("sentence", sentence.model_dump())
            else:
                fallback_selected = selected[: min(2, len(selected))]
                for idx, chunk in enumerate(fallback_selected, start=1):
                    citation_id = f"c{idx}"
                    snippet = compact_snippet(chunk.text, limit=220)
                    sentence = AnswerSentence(
                        text=f"根据资料可知：{snippet}",
                        evidence_type="source",
                        citation_ids=[citation_id],
                        confidence=clip_confidence(chunk.final_score),
                    )
                    answer_sentences.append(sentence)
                    yield self._format_sse("sentence", sentence.model_dump())

            max_common = max_common_sentences(len(answer_sentences), self._cfg.common_knowledge_max_ratio)
            if scope.allow_common_knowledge and max_common > 0:
                sentence = AnswerSentence(
                    text=f"{COMMON_KNOWLEDGE_PREFIX}以下内容为模型补充推断，请结合原文证据核验。",
                    evidence_type="common_knowledge",
                    citation_ids=[],
                    confidence=0.3,
                )
                answer_sentences.append(sentence)
                yield self._format_sse("sentence", sentence.model_dump())

            yield self._format_sse("done")

        except Exception as exc:
            yield self._format_sse("error", None, str(exc))

    def _format_sse(self, event_type: str, data: Any = None, error_message: str = None) -> str:
        """格式化 SSE 消息"""
        payload: dict[str, Any] = {"type": event_type}
        if data is not None:
            payload["data"] = data
        if error_message is not None:
            payload["message"] = error_message
        return f"data: {json.dumps(payload)}\n\n"


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

    hybrid_dense_weight = getenv_float("HYBRID_SEARCH_DENSE_WEIGHT", 0.7)
    if not (0.0 <= hybrid_dense_weight <= 1.0):
        hybrid_dense_weight = 0.7

    hybrid_sparse_weight = 1.0 - hybrid_dense_weight

    reranker_model = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()
    if not reranker_model:
        reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    query_cache_enabled_raw = os.getenv("QUERY_CACHE_ENABLED", "true").strip().lower()
    query_cache_enabled = query_cache_enabled_raw in ("true", "1", "yes", "on")

    multi_query_enabled_raw = os.getenv("MULTI_QUERY_ENABLED", "false").strip().lower()
    multi_query_enabled = multi_query_enabled_raw in ("true", "1", "yes", "on")

    multi_query_max_variants = getenv_int("MULTI_QUERY_MAX_VARIANTS", 3)
    if multi_query_max_variants < 1:
        multi_query_max_variants = 3

    multi_query_timeout_ms = getenv_int("MULTI_QUERY_TIMEOUT_MS", 500)
    if multi_query_timeout_ms < 100:
        multi_query_timeout_ms = 500

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
        hybrid_dense_weight=hybrid_dense_weight,
        hybrid_sparse_weight=hybrid_sparse_weight,
        reranker_model=reranker_model,
        query_cache_enabled=query_cache_enabled,
        query_cache_ttl_hours=max(getenv_int("QUERY_CACHE_TTL_HOURS", 24), 1),
        query_cache_max_size=max(getenv_int("QUERY_CACHE_MAX_SIZE", 10000), 1),
        multi_query_enabled=multi_query_enabled,
        multi_query_max_variants=multi_query_max_variants,
        multi_query_timeout_ms=multi_query_timeout_ms,
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


def rerank_points(
    question: str,
    points: Sequence[ScoredPoint],
    top_k: int,
    dense_weight: float = 0.7,
) -> list[RankedChunk]:
    """
    重排序检索结果
    
    Args:
        question: 用户问题
        points: Qdrant 返回的检索结果
        top_k: 返回前 k 个结果
        dense_weight: 向量检索权重（默认 0.7），词法检索权重为 1.0 - dense_weight
    """
    question_tokens = tokenize(question)
    ranked: list[RankedChunk] = []
    lexical_weight = 1.0 - dense_weight

    for point in points:
        payload = point.payload or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            continue

        lexical = lexical_overlap(question_tokens, text)
        vector_score = float(point.score or 0.0)
        final_score = (vector_score * dense_weight) + (lexical * lexical_weight)

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


@app.exception_handler(RAGServiceError)
async def rag_service_error_handler(request: Request, exc: RAGServiceError):
    """统一处理 RAG 服务自定义异常"""
    logger.error(
        f"RAG service error: {exc.code}",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "extra_fields": {
                "error_code": exc.code,
                "error_detail": exc.detail,
                "path": request.url.path,
                **exc.extra_info,
            },
        },
        exc_info=True if exc.status_code >= 500 else False,
    )
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """统一处理所有未捕获的异常"""
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {exc}",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "extra_fields": {
                "error_type": type(exc).__name__,
                "path": request.url.path,
                "method": request.method,
            },
        },
        exc_info=True,
    )
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有 HTTP 请求的日志"""
    import time
    from uuid import uuid4

    request_id = str(uuid4())
    start_time = time.time()

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        f"{request.method} {request.url.path} completed",
        extra={
            "request_id": request_id,
            "duration_ms": round(duration_ms, 2),
            "extra_fields": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "client": request.client.host if request.client else "unknown",
            },
        },
    )

    return response


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    """
    请求超时中间件
    默认超时 60 秒，可通过环境变量 RAG_REQUEST_TIMEOUT 调整
    """
    import asyncio
    from datetime import timedelta
    
    timeout_seconds = int(os.getenv("RAG_REQUEST_TIMEOUT", "60"))
    
    try:
        # 使用 asyncio.wait_for 实现超时控制
        response = await asyncio.wait_for(call_next(request), timeout=timeout_seconds)
        return response
    except asyncio.TimeoutError:
        logger.error(
            f"Request timeout after {timeout_seconds}s",
            extra={
                "extra_fields": {
                    "path": request.url.path,
                    "method": request.method,
                    "timeout_seconds": timeout_seconds,
                },
            },
        )
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=504,  # Gateway Timeout
            content={
                "error": "Request timeout",
                "code": "REQUEST_TIMEOUT",
                "detail": f"Request exceeded {timeout_seconds}s timeout",
            },
        )


@app.get("/healthz")
def healthz(depth: str = Query(default="full", description="健康检查深度：basic 或 full")) -> dict:
    """
    健康检查端点
    
    Args:
        depth: basic (仅返回状态) 或 full (检查所有依赖)
    """
    # 简单健康检查
    if depth == "basic":
        logger.debug("Basic health check requested")
        return {"status": "ok", "service": "py-rag-service"}
    
    # 深度健康检查
    logger.info("Full health check requested")
    checks = {}
    overall_status = "ok"
    
    # 检查 Qdrant 连接
    try:
        cfg = build_service_config()
        qdrant_client = QdrantClient(url=cfg.qdrant_url, timeout=3)
        qdrant_client.get_collections()
        checks["qdrant"] = "ok"
        qdrant_client.close()
    except Exception as e:
        checks["qdrant"] = "unhealthy"
        overall_status = "degraded"
        logger.error(f"Health check: Qdrant connection failed: {e}")
    
    # 检查 LLM API (如果配置了)
    try:
        llm_api_key = os.getenv("LLM_API_KEY")
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        if llm_api_key:
            # 简单检查 API 连通性
            import httpx
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{llm_base_url}/api/tags")
                if response.status_code == 200:
                    checks["llm_api"] = "ok"
                else:
                    checks["llm_api"] = "degraded"
                    overall_status = "degraded"
        else:
            checks["llm_api"] = "not_configured"
    except Exception as e:
        checks["llm_api"] = "unhealthy"
        overall_status = "degraded"
        logger.error(f"Health check: LLM API check failed: {e}")
    
    # 检查缓存 (Redis)
    try:
        cache_host = os.getenv("QUERY_CACHE_REDIS_HOST")
        if cache_host:
            import redis
            r = redis.Redis(host=cache_host, port=6379, db=0, socket_timeout=3)
            r.ping()
            checks["redis_cache"] = "ok"
        else:
            checks["redis_cache"] = "not_configured"
    except Exception as e:
        checks["redis_cache"] = "unhealthy"
        overall_status = "degraded"
        logger.error(f"Health check: Redis cache check failed: {e}")
    
    return {
        "status": overall_status,
        "service": "py-rag-service",
        "checks": checks,
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/metrics/cache")
def cache_metrics() -> dict:
    if not hasattr(app.state, "engine"):
        return {"enabled": False, "available": False}
    
    engine = app.state.engine
    if not hasattr(engine, "cache_stats") or engine.cache_stats is None:
        return {"enabled": False, "available": False}
    
    stats = engine.cache_stats
    return {
        "enabled": True,
        "available": True,
        "size": stats.get("size", 0),
        "max_size": stats.get("max_size", 0),
        "hits": stats.get("hits", 0),
        "misses": stats.get("misses", 0),
        "hit_rate": stats.get("hit_rate", 0.0),
    }


@app.get("/metrics/retrieval-quality")
def retrieval_quality_stats(days: int = Query(default=7, description="统计天数")):
    """获取检索质量统计"""
    try:
        stats = get_retrieval_quality_stats(days=days)
        return {
            "success": True,
            "days": days,
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Failed to get retrieval quality stats: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@app.get("/metrics/retrieval-quality/report")
def retrieval_quality_report():
    """导出检索质量报告"""
    try:
        from .retrieval_tracker import get_tracker
        tracker = get_tracker()
        report_path = tracker.export_report()
        return {
            "success": True,
            "report_path": report_path,
        }
    except Exception as e:
        logger.error(f"Failed to export retrieval quality report: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@app.post("/v1/rag/query", response_model=QueryResponse)
def rag_query(payload: QueryRequest) -> QueryResponse:
    question = payload.question.strip()
    if not question:
        logger.warning("RAG query with empty question")
        raise ValidationError("question must not be blank")

    if not hasattr(app.state, "engine"):
        logger.info("Initializing RAG engine")
        app.state.engine = build_engine()

    try:
        logger.info(
            f"Processing RAG query",
            extra={
                "extra_fields": {
                    "question_length": len(question),
                    "scope_mode": payload.scope.mode,
                    "corpus_count": len(payload.scope.corpus_ids),
                }
            },
        )
        result = app.state.engine.query(question, payload.scope)
        logger.info(
            "RAG query completed",
            extra={
                "extra_fields": {
                    "answer_sentences": len(result.answer_sentences),
                    "citations": len(result.citations),
                }
            },
        )
        return result
    except Exception as exc:
        logger.error(
            f"RAG query failed: {exc}",
            extra={
                "extra_fields": {
                    "error_type": type(exc).__name__,
                }
            },
            exc_info=True,
        )
        # 返回友好的错误信息，而不是抛出异常
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


@app.get("/v1/rag/query/stream")
async def rag_query_stream(
    question: str = Query(..., min_length=1, max_length=8000, description="查询问题"),
    scope_json: str = Query(..., description="JSON encoded Scope object"),
) -> StreamingResponse:
    """SSE 流式查询端点
    
    使用方法:
    curl -N "http://localhost:8000/v1/rag/query/stream?question=测试&scope_json={...}"
    
    SSE 事件格式:
    - data: {"type": "sentence", "data": {...}}  答案句子
    - data: {"type": "citation", "data": {...}}  引用文献
    - data: {"type": "done"}                     流式结束
    - data: {"type": "error", "message": "..."}  错误信息
    """
    import asyncio
    from anyio import BrokenResourceError
    
    try:
        scope_dict = json.loads(scope_json)
        scope = Scope(**scope_dict)
    except (json.JSONDecodeError, ValueError) as exc:
        async def error_stream() -> AsyncGenerator[str, None]:
            yield f'data: {{"type": "error", "message": "Invalid scope_json: {str(exc)}"}}\n\n'
            yield 'data: {"type": "done"}\n\n'
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if not hasattr(app.state, "engine"):
        app.state.engine = build_engine()
    
    engine = app.state.engine
    
    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        try:
            async for event in engine.query_stream(question.strip(), scope):
                yield event
                await asyncio.sleep(0)
        except BrokenResourceError:
            pass
        except Exception as exc:
            yield f'data: {{"type": "error", "message": "{str(exc)}"}}\n\n'
            yield 'data: {"type": "done"}\n\n'
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/v1/rag/query/stream")
async def rag_query_stream_post(payload: StreamQueryRequest) -> StreamingResponse:
    """SSE 流式查询端点（POST 方式）
    
    使用方法:
    curl -N -X POST "http://localhost:8000/v1/rag/query/stream" \\
      -H "Content-Type: application/json" \\
      -d '{"question": "测试", "scope": {...}}'
    
    SSE 事件格式:
    - data: {"type": "sentence", "data": {...}}  答案句子
    - data: {"type": "citation", "data": {...}}  引用文献
    - data: {"type": "done"}                     流式结束
    - data: {"type": "error", "message": "..."}  错误信息
    """
    import asyncio
    from anyio import BrokenResourceError
    
    question = payload.question.strip()
    if not question:
        async def error_stream() -> AsyncGenerator[str, None]:
            yield 'data: {"type": "error", "message": "question must not be blank"}\n\n'
            yield 'data: {"type": "done"}\n\n'
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    if not hasattr(app.state, "engine"):
        app.state.engine = build_engine()
    
    engine = app.state.engine
    
    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流"""
        try:
            async for event in engine.query_stream(question, payload.scope):
                yield event
                await asyncio.sleep(0)
        except BrokenResourceError:
            pass
        except Exception as exc:
            yield f'data: {{"type": "error", "message": "{str(exc)}"}}\n\n'
            yield 'data: {"type": "done"}\n\n'
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
