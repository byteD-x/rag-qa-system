from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .gateway_answering import contextualize_question
from .gateway_runtime import logger, runtime_settings
from .gateway_transport import downstream_headers, parse_corpus_id, request_service_json


async def retrieve_corpus_payload(
    client: httpx.AsyncClient,
    *,
    user: CurrentUser,
    headers: dict[str, str],
    corpus_id: str,
    base_id: str,
    question: str,
    document_ids: list[str],
    semaphore: asyncio.Semaphore,
    kb_service_url: str,
    request_service_json_fn: Any = request_service_json,
) -> dict[str, Any]:
    async with semaphore:
        try:
            payload = await request_service_json_fn(
                client,
                "POST",
                f"{kb_service_url}/api/v1/kb/retrieve",
                headers=headers,
                json_body={"base_id": base_id, "question": question, "document_ids": document_ids, "limit": 8},
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail or "request failed")}
            logger.warning(
                "gateway retrieval fanout failed corpus_id=%s status_code=%s detail=%s",
                corpus_id,
                exc.status_code,
                detail.get("detail"),
            )
            return {
                "corpus_id": corpus_id,
                "payload": None,
                "error": {
                    "status_code": exc.status_code,
                    "code": str(detail.get("code") or "upstream_request_failed"),
                    "detail": str(detail.get("detail") or "request failed"),
                },
            }
        except Exception:
            logger.exception("gateway retrieval fanout crashed corpus_id=%s", corpus_id)
            return {
                "corpus_id": corpus_id,
                "payload": None,
                "error": {
                    "status_code": 500,
                    "code": "fanout_request_failed",
                    "detail": "unexpected retrieval fanout failure",
                },
            }
        return {"corpus_id": corpus_id, "payload": payload, "error": {}}


async def retrieve_scope_evidence(
    *,
    user: CurrentUser,
    scope_snapshot: dict[str, Any],
    question: str,
    history: list[dict[str, Any]],
    focus_hint: dict[str, Any] | None = None,
    fetch_corpus_documents_fn: Any,
    kb_service_url: str,
    request_service_json_fn: Any = request_service_json,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    if not scope_snapshot["corpus_ids"]:
        return [], question.strip(), {"services": [], "aggregate": {"empty_scope": True, "service_count": 0}}
    contextualized_question = contextualize_question(question, history)
    document_scope_map = {
        str(corpus_id): [str(document_id) for document_id in (document_ids or []) if str(document_id).strip()]
        for corpus_id, document_ids in dict(scope_snapshot.get("documents_by_corpus") or {}).items()
        if str(corpus_id).strip()
    }
    fanout_started = time.perf_counter()
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        headers = downstream_headers(user)
        if scope_snapshot["document_ids"] and not document_scope_map:
            doc_lists = await asyncio.gather(
                *[fetch_corpus_documents_fn(client, user=user, corpus_id=corpus_id) for corpus_id in scope_snapshot["corpus_ids"]]
            )
            valid_documents = {item["document_id"]: item["corpus_id"] for documents in doc_lists for item in documents}
            for document_id in scope_snapshot["document_ids"]:
                corpus_id = valid_documents.get(document_id)
                if corpus_id:
                    document_scope_map.setdefault(corpus_id, []).append(document_id)
        semaphore = asyncio.Semaphore(runtime_settings.retrieval_fanout_limit)
        tasks = []
        for corpus_id in scope_snapshot["corpus_ids"]:
            _, raw_id = parse_corpus_id(corpus_id)
            document_ids = list(dict.fromkeys(document_scope_map.get(corpus_id, [])))
            tasks.append(
                retrieve_corpus_payload(
                    client,
                    user=user,
                    headers=headers,
                    corpus_id=corpus_id,
                    base_id=raw_id,
                    question=contextualized_question,
                    document_ids=document_ids,
                    semaphore=semaphore,
                    kb_service_url=kb_service_url,
                    request_service_json_fn=request_service_json_fn,
                )
            )
        service_results = await asyncio.gather(*tasks)
    fanout_wall_ms = round((time.perf_counter() - fanout_started) * 1000.0, 3)
    evidence: list[dict[str, Any]] = []
    retrieval_services: list[dict[str, Any]] = []
    failed_services: list[dict[str, Any]] = []
    for service_result in service_results:
        payload = service_result.get("payload")
        if not payload:
            failed_services.append(service_result)
            retrieval_services.append(
                {
                    "corpus_id": str(service_result.get("corpus_id") or ""),
                    "trace_id": "",
                    "status": "failed",
                    "error": dict(service_result.get("error") or {}),
                    "retrieval": {},
                }
            )
            continue
        evidence.extend(payload.get("items", []) if isinstance(payload, dict) else [])
        retrieval_services.append(
            {
                "corpus_id": str(service_result.get("corpus_id") or ""),
                "trace_id": str(payload.get("trace_id") or ""),
                "status": "ok",
                "retrieval": dict(payload.get("retrieval") or {}),
            }
        )
    if failed_services and not evidence:
        raise_api_error(502, "all_retrieval_services_failed", "all retrieval services failed for the selected scope")
    normalized_focus_hint = dict(focus_hint or {})

    def _focus_bonus(item: dict[str, Any]) -> float:
        bonus = 0.0
        target_documents = [str(entry).strip() for entry in list(normalized_focus_hint.get("document_ids") or []) if str(entry).strip()]
        if target_documents and str(item.get("document_id") or "") in target_documents:
            bonus += 1.2
        if str(normalized_focus_hint.get("primary_document_id") or "").strip() and str(item.get("document_id") or "") == str(normalized_focus_hint.get("primary_document_id") or "").strip():
            bonus += 0.6
        if str(normalized_focus_hint.get("region_id") or "").strip() and str(item.get("unit_id") or "") == str(normalized_focus_hint.get("region_id") or "").strip():
            bonus += 2.4
        if str(normalized_focus_hint.get("asset_id") or "").strip() and str(item.get("asset_id") or "") == str(normalized_focus_hint.get("asset_id") or "").strip():
            bonus += 1.0
        if str(normalized_focus_hint.get("version_family_key") or "").strip() and str(item.get("version_family_key") or "") == str(normalized_focus_hint.get("version_family_key") or "").strip():
            bonus += 0.5
        if str(normalized_focus_hint.get("version_label") or "").strip() and str(item.get("version_label") or "") == str(normalized_focus_hint.get("version_label") or "").strip():
            bonus += 0.4
        return bonus

    evidence.sort(
        key=lambda item: (
            float(((item.get("evidence_path") or {}).get("final_score") or 0.0)) + _focus_bonus(item),
            float(((item.get("evidence_path") or {}).get("final_score") or 0.0)),
        ),
        reverse=True,
    )
    filtered: list[dict[str, Any]] = []
    by_corpus: dict[str, int] = {}
    by_document: dict[str, int] = {}
    for item in evidence:
        corpus_id = str(item.get("corpus_id") or "")
        document_id = str(item.get("document_id") or "")
        if by_corpus.get(corpus_id, 0) >= 3 or by_document.get(document_id, 0) >= 2:
            continue
        filtered.append(item)
        by_corpus[corpus_id] = by_corpus.get(corpus_id, 0) + 1
        by_document[document_id] = by_document.get(document_id, 0) + 1
        if len(filtered) >= 8:
            break
    aggregate = {
        "empty_scope": False,
        "service_count": len(retrieval_services),
        "successful_service_count": sum(1 for item in retrieval_services if item.get("status") == "ok"),
        "failed_service_count": sum(1 for item in retrieval_services if item.get("status") == "failed"),
        "partial_failure": any(item.get("status") == "failed" for item in retrieval_services),
        "document_scope_cache_hit": bool(document_scope_map),
        "original_query": str(next((item.get("retrieval", {}).get("original_query", "") for item in retrieval_services if item.get("retrieval", {}).get("original_query")), question.strip())),
        "contextualized_query": contextualized_question,
        "rewritten_query": str(next((item.get("retrieval", {}).get("rewritten_query", "") for item in retrieval_services if item.get("retrieval", {}).get("rewritten_query")), contextualized_question)),
        "focus_query": str(next((item.get("retrieval", {}).get("focus_query", "") for item in retrieval_services if item.get("retrieval", {}).get("focus_query")), contextualized_question)),
        "structure_candidates": sum(int(item.get("retrieval", {}).get("structure_candidates", 0) or 0) for item in retrieval_services),
        "fts_candidates": sum(int(item.get("retrieval", {}).get("fts_candidates", 0) or 0) for item in retrieval_services),
        "vector_candidates": sum(int(item.get("retrieval", {}).get("vector_candidates", 0) or 0) for item in retrieval_services),
        "fused_candidates": sum(int(item.get("retrieval", {}).get("fused_candidates", 0) or 0) for item in retrieval_services),
        "reranked_candidates": sum(int(item.get("retrieval", {}).get("reranked_candidates", 0) or 0) for item in retrieval_services),
        "selected_candidates": len(filtered),
        "retrieval_ms": fanout_wall_ms,
        "sum_service_retrieval_ms": round(sum(float(item.get("retrieval", {}).get("retrieval_ms", 0.0) or 0.0) for item in retrieval_services), 3),
        "max_service_retrieval_ms": round(max((float(item.get("retrieval", {}).get("retrieval_ms", 0.0) or 0.0) for item in retrieval_services), default=0.0), 3),
        "rewrite_tags": list(dict.fromkeys(tag for item in retrieval_services for tag in list(item.get("retrieval", {}).get("rewrite_tags", []) or []) if tag)),
        "expansion_terms": list(dict.fromkeys(term for item in retrieval_services for term in list(item.get("retrieval", {}).get("expansion_terms", []) or []) if term)),
        "focus_hint_applied": bool(normalized_focus_hint),
    }
    return filtered, contextualized_question, {"services": retrieval_services, "aggregate": aggregate}
