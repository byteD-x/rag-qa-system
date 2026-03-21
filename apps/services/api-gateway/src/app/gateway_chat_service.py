from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from shared.auth import CurrentUser
from shared.prompt_safety import analyze_prompt_safety, apply_safety_response_policy
from shared.tracing import current_trace_id, ensure_trace_id

from .gateway_agent import run_agent_search
from .gateway_answering import classify_evidence, compact_text, generate_grounded_answer
from .gateway_audit_support import write_gateway_audit_event
from .gateway_platform_store import resolve_platform_context
from .gateway_pricing import estimate_usage_cost, usage_with_meta
from .gateway_runtime import (
    GATEWAY_CHAT_LATENCY_MS,
    GATEWAY_CHAT_REQUESTS_TOTAL,
    GATEWAY_COST_BUDGET_REJECTIONS_TOTAL,
    GATEWAY_LLM_TOKENS_TOTAL,
    GATEWAY_RETRIEVAL_FANOUT_TOTAL,
    GATEWAY_RETRIEVAL_FANOUT_WALL_MS,
    GATEWAY_SAFETY_EVENTS_TOTAL,
    logger,
    runtime_settings,
)
from .gateway_schemas import ChatScopePayload
from .gateway_scope import normalize_execution_mode
from .gateway_transport import downstream_headers, request_service_json
from .gateway_workflows import workflow_kind_for_turn


RESUME_TARGET_GENERATION = "generate_answer"
RESUME_TARGET_PERSISTENCE = "persist_message"
TEMPORAL_HINT_PATTERN = re.compile(r"(19|20)\d{2}|q[1-4]|版本|版|生效|历史|当前|最新|现行|去年|今年|之前|之后|上线前|上线后", re.IGNORECASE)
VISUAL_HINT_PATTERN = re.compile(r"截图|图中|图片|界面|页面|终端|控制台|红框|标红|框选|框起来|标注", re.IGNORECASE)


def _platform_instruction_text(platform_context: dict[str, Any]) -> str:
    prompt_template = dict(platform_context.get("prompt_template") or {})
    agent_profile = dict(platform_context.get("agent_profile") or {})
    parts: list[str] = []
    if str(prompt_template.get("content") or "").strip():
        parts.append(f"Prompt template instructions:\n{str(prompt_template.get('content') or '').strip()}")
    if str(agent_profile.get("persona_prompt") or "").strip():
        parts.append(f"Agent persona:\n{str(agent_profile.get('persona_prompt') or '').strip()}")
    enabled_tools = list(agent_profile.get("enabled_tools") or [])
    if enabled_tools:
        parts.append("Enabled agent tools: " + ", ".join(enabled_tools))
    return "\n\n".join(parts).strip()


def _workflow_tool_calls(prepared: dict[str, Any]) -> list[dict[str, Any]]:
    return list((((prepared.get("retrieval_meta") or {}).get("agent") or {}).get("tool_calls") or []))


def _workflow_agent_events(prepared: dict[str, Any]) -> list[dict[str, Any]]:
    return list((((prepared.get("retrieval_meta") or {}).get("agent") or {}).get("events") or []))


def _has_temporal_intent(question: str) -> bool:
    return bool(TEMPORAL_HINT_PATTERN.search(str(question or "").strip()))


def _has_visual_intent(question: str) -> bool:
    return bool(VISUAL_HINT_PATTERN.search(str(question or "").strip()))


def _sort_version_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        return (
            1 if bool(item.get("is_current_version")) else 0,
            int(item.get("version_number") or 0),
            str(item.get("created_at") or ""),
        )

    return sorted(documents, key=_sort_key, reverse=True)


def _describe_version_document(document: dict[str, Any]) -> str:
    title = str(document.get("title") or document.get("file_name") or document.get("display_name") or "").strip()
    version_label = str(document.get("raw", {}).get("version_label") or document.get("version_label") or "").strip()
    status = str(document.get("raw", {}).get("version_status") or document.get("version_status") or "").strip()
    effective_from = str(document.get("raw", {}).get("effective_from") or document.get("effective_from") or "").strip()
    parts = [part for part in (title, version_label, status) if part]
    if effective_from:
        parts.append(f"生效自 {effective_from}")
    return " / ".join(parts)


def _build_interrupt_option(
    *,
    option_id: str,
    label: str,
    description: str,
    patch: dict[str, Any] | None = None,
    badges: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": option_id,
        "label": label,
        "description": description,
        "patch": dict(patch or {}),
        "badges": [str(item).strip() for item in list(badges or []) if str(item).strip()],
        "meta": dict(meta or {}),
    }


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _effective_now(item: dict[str, Any]) -> bool:
    now = datetime.now(timezone.utc)
    effective_from = _parse_timestamp(item.get("effective_from") or item.get("raw", {}).get("effective_from"))
    effective_to = _parse_timestamp(item.get("effective_to") or item.get("raw", {}).get("effective_to"))
    if effective_from and effective_from > now:
        return False
    if effective_to and effective_to < now:
        return False
    return True


def _normalized_version_candidate(item: dict[str, Any]) -> dict[str, Any]:
    raw = dict(item.get("raw") or {})
    return {
        "id": str(item.get("document_id") or item.get("id") or ""),
        "document_id": str(item.get("document_id") or item.get("id") or ""),
        "title": str(item.get("title") or item.get("document_title") or item.get("file_name") or item.get("display_name") or ""),
        "file_name": str(item.get("file_name") or item.get("document_title") or item.get("title") or ""),
        "version_family_key": str(item.get("version_family_key") or raw.get("version_family_key") or ""),
        "version_label": str(item.get("version_label") or raw.get("version_label") or ""),
        "version_number": int(item.get("version_number") or raw.get("version_number") or 0),
        "version_status": str(item.get("version_status") or raw.get("version_status") or ""),
        "is_current_version": bool(item.get("is_current_version") or raw.get("is_current_version")),
        "effective_from": str(item.get("effective_from") or raw.get("effective_from") or ""),
        "effective_to": str(item.get("effective_to") or raw.get("effective_to") or ""),
        "created_at": item.get("created_at") or raw.get("created_at"),
        "raw": raw,
        "evidence_hits": int(item.get("evidence_hits") or 0),
    }


def _version_candidate_score(item: dict[str, Any], *, question: str) -> float:
    score = 0.0
    if bool(item.get("is_current_version")):
        score += 3.0
    if _effective_now(item):
        score += 2.2
    score += min(float(int(item.get("version_number") or 0)) * 0.12, 1.2)
    score += min(float(int(item.get("evidence_hits") or 0)) * 0.55, 2.2)
    if _has_temporal_intent(question) and _effective_now(item):
        score += 0.9
    if str(item.get("version_status") or "").strip().lower() == "active":
        score += 0.5
    return round(score, 4)


def _version_badges(item: dict[str, Any]) -> list[str]:
    badges: list[str] = []
    version_label = str(item.get("version_label") or "").strip()
    if version_label:
        badges.append(version_label)
    if bool(item.get("is_current_version")):
        badges.append("current")
    if _effective_now(item):
        badges.append("effective")
    status = str(item.get("version_status") or "").strip()
    if status:
        badges.append(status)
    return badges


def _version_meta(item: dict[str, Any], *, score: float) -> dict[str, Any]:
    return {
        "document_id": str(item.get("document_id") or ""),
        "version_family_key": str(item.get("version_family_key") or ""),
        "version_label": str(item.get("version_label") or ""),
        "version_status": str(item.get("version_status") or ""),
        "version_number": int(item.get("version_number") or 0),
        "effective_from": str(item.get("effective_from") or ""),
        "effective_to": str(item.get("effective_to") or ""),
        "effective_now": _effective_now(item),
        "score": score,
        "evidence_hits": int(item.get("evidence_hits") or 0),
    }


def _rank_version_candidates(question: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_hits: dict[str, int] = {}
    for item in candidates:
        document_id = str(item.get("document_id") or item.get("id") or "")
        if document_id:
            evidence_hits[document_id] = evidence_hits.get(document_id, 0) + 1
    normalized = []
    for item in candidates:
        candidate = _normalized_version_candidate(item)
        candidate["evidence_hits"] = evidence_hits.get(candidate["document_id"], 0)
        candidate["score"] = _version_candidate_score(candidate, question=question)
        normalized.append(candidate)
    return sorted(
        normalized,
        key=lambda item: (
            float(item.get("score") or 0.0),
            1 if bool(item.get("is_current_version")) else 0,
            1 if _effective_now(item) else 0,
            int(item.get("version_number") or 0),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )


def _build_scope_ambiguity_prompt(question: str) -> dict[str, Any]:
    return {
        "kind": "scope_ambiguity",
        "title": "当前没有可用知识范围",
        "detail": "需要先确认检索范围，或者允许按常识给出保底回答。",
        "question": question,
        "options": [
            _build_interrupt_option(
                option_id="scope:all",
                label="改为全部知识库",
                description="使用当前账号可见的全部知识库重新检索。",
                patch={"scope_override": {"mode": "all", "document_ids": []}},
            ),
            _build_interrupt_option(
                option_id="common:allow",
                label="允许常识保底",
                description="允许在证据不足时补充通用知识回答。",
                patch={"allow_common_knowledge": True},
            ),
        ],
        "recommended_option_id": "scope:all",
        "allow_free_text": True,
        "fallback_prompt": "如果以上都不合适，请补充要查的部门、系统或文档。",
    }


def _build_insufficient_evidence_prompt(question: str) -> dict[str, Any]:
    return {
        "kind": "insufficient_evidence",
        "title": "证据不足，先确认回答策略",
        "detail": "当前知识范围没有找到足够证据。可以允许常识保底，或者补充更具体的信息后继续。",
        "question": question,
        "options": [
            _build_interrupt_option(
                option_id="common:allow",
                label="允许常识保底",
                description="先给一个保守答案，并标注不是完全基于知识库证据。",
                patch={"allow_common_knowledge": True},
            ),
            _build_interrupt_option(
                option_id="question:refine",
                label="我来补充信息",
                description="补充文档名、时间点、系统名或业务范围，再继续检索。",
            ),
        ],
        "recommended_option_id": "common:allow",
        "allow_free_text": True,
        "fallback_prompt": "建议补充文档名称、版本、生效时间或截图位置。",
    }


def _build_version_conflict_prompt(*, question: str, candidates: list[dict[str, Any]], kind: str, detail: str) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    recommended_option_id = ""
    for item in _sort_version_documents(candidates)[:4]:
        document_id = str(item.get("document_id") or item.get("id") or "")
        version_label = str(item.get("version_label") or item.get("raw", {}).get("version_label") or "").strip() or f"v{int(item.get('version_number') or item.get('raw', {}).get('version_number') or 0)}"
        option_id = f"document:{document_id}"
        if bool(item.get("is_current_version") or item.get("raw", {}).get("is_current_version")) and not recommended_option_id:
            recommended_option_id = option_id
        options.append(
            _build_interrupt_option(
                option_id=option_id,
                label=f"按 {version_label} 回答",
                description=_describe_version_document(item),
                patch={"document_ids": [document_id]},
            )
        )
    return {
        "kind": kind,
        "title": "检测到版本差异，请先确认依据版本",
        "detail": detail,
        "question": question,
        "options": options,
        "recommended_option_id": recommended_option_id or (options[0]["id"] if options else ""),
        "allow_free_text": True,
        "fallback_prompt": "如果这些版本都不对，请补充具体时间点或版本标识。",
    }


def _visual_region_label(item: dict[str, Any]) -> str:
    if str(item.get("source_kind") or "").strip() != "visual_region":
        return ""
    explicit_label = str(item.get("region_label") or "").strip()
    if explicit_label:
        return explicit_label
    title = str(item.get("section_title") or "").strip()
    match = re.match(r"Page\s+\d+\s+(.+)$", title, re.IGNORECASE)
    if match:
        return str(match.group(1) or "").strip()
    return title


def _build_visual_ambiguity_prompt(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    region_items: list[dict[str, Any]] = []
    seen_region_units: set[str] = set()
    for item in evidence:
        if str(item.get("source_kind") or "").strip() != "visual_region":
            continue
        unit_id = str(item.get("unit_id") or "").strip()
        if not unit_id or unit_id in seen_region_units:
            continue
        seen_region_units.add(unit_id)
        region_items.append(item)
        if len(region_items) >= 4:
            break
    visual_items = region_items
    if len(visual_items) < 2:
        fallback_items: list[dict[str, Any]] = []
        seen_assets: set[str] = set()
        for item in evidence:
            asset_id = str(item.get("asset_id") or "").strip()
            if not asset_id or asset_id in seen_assets or not str(item.get("source_kind") or "").startswith("visual"):
                continue
            seen_assets.add(asset_id)
            fallback_items.append(item)
            if len(fallback_items) >= 4:
                break
        visual_items = fallback_items
    if len(visual_items) < 2:
        return {}
    options = []
    for item in visual_items:
        region_label = _visual_region_label(item)
        page_number = int(item.get("page_number") or 0)
        label = (
            f"第 {page_number} 页 · {region_label}"
            if page_number and region_label
            else str(item.get("section_title") or "").strip()
            or (f"第 {page_number} 页截图" if page_number else "截图区域")
        )
        detail = str(item.get("document_title") or "").strip()
        if str(item.get("version_label") or "").strip():
            detail = f"{detail} / {str(item.get('version_label') or '').strip()}".strip(" /")
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)):
            detail = f"{detail} / 置信度 {float(confidence) * 100:.1f}%".strip(" /")
        if region_label:
            question_suffix = (
                f"请聚焦第 {page_number} 页截图中的「{region_label}」区域回答。"
                if page_number
                else f"请聚焦截图中的「{region_label}」区域回答。"
            )
        else:
            question_suffix = f"请聚焦第 {page_number} 页截图「{label}」相关内容。" if page_number else f"请聚焦截图区域「{label}」相关内容。"
        options.append(
            _build_interrupt_option(
                option_id=(
                    f"region:{str(item.get('unit_id') or '')}"
                    if region_label
                    else f"asset:{str(item.get('asset_id') or '')}"
                ),
                label=label,
                description=detail or "聚焦该截图区域继续回答。",
                patch={
                    "document_ids": [str(item.get("document_id") or "")] if str(item.get("document_id") or "") else [],
                    "question_suffix": question_suffix,
                },
            )
        )
    return {
        "kind": "visual_ambiguity",
        "title": "命中了多处截图证据，请先确认要聚焦的区域",
        "detail": "当前问题更像是在问某一张截图或某一块标注区域，但检索命中了多个视觉证据。",
        "question": question,
        "options": options,
        "recommended_option_id": options[0]["id"] if options else "",
        "allow_free_text": True,
        "fallback_prompt": "可以直接补充“第几页”“哪张截图”或“红框中的哪一块”。",
    }


async def _build_temporal_clarification_prompt(
    *,
    user: CurrentUser,
    question: str,
    scope_snapshot: dict[str, Any],
    fetch_corpus_documents_fn: Any,
) -> dict[str, Any]:
    if not _has_temporal_intent(question):
        return {}
    if list(scope_snapshot.get("document_ids") or []):
        return {}
    corpus_ids = list(scope_snapshot.get("corpus_ids") or [])
    if len(corpus_ids) != 1:
        return {}
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        documents = await fetch_corpus_documents_fn(client, user=user, corpus_id=corpus_ids[0])
    families: dict[str, list[dict[str, Any]]] = {}
    for item in documents:
        raw = dict(item.get("raw") or {})
        family_key = str(raw.get("version_family_key") or "").strip()
        if not family_key:
            continue
        normalized = {
            "id": str(item.get("document_id") or item.get("id") or ""),
            "document_id": str(item.get("document_id") or item.get("id") or ""),
            "title": str(item.get("title") or item.get("file_name") or item.get("display_name") or ""),
            "file_name": str(item.get("file_name") or item.get("title") or ""),
            "version_family_key": family_key,
            "version_label": str(raw.get("version_label") or ""),
            "version_number": int(raw.get("version_number") or 0),
            "version_status": str(raw.get("version_status") or ""),
            "is_current_version": bool(raw.get("is_current_version")),
            "effective_from": str(raw.get("effective_from") or ""),
            "effective_to": str(raw.get("effective_to") or ""),
            "created_at": item.get("created_at"),
            "raw": raw,
        }
        families.setdefault(family_key, []).append(normalized)
    candidate_families = [items for items in families.values() if len(items) > 1]
    if len(candidate_families) != 1:
        return {}
    return _build_version_conflict_prompt(
        question=question,
        candidates=candidate_families[0],
        kind="time_ambiguity",
        detail="你的问题带有时间或版本语义，而当前知识范围内存在多个版本。先确认依据版本，能显著降低误答风险。",
    )


def _build_evidence_version_conflict_prompt(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, list[dict[str, Any]]] = {}
    for item in evidence[:6]:
        family_key = str(item.get("version_family_key") or "").strip()
        version_label = str(item.get("version_label") or "").strip()
        if not family_key or not version_label:
            continue
        families.setdefault(family_key, []).append(item)
    for items in families.values():
        version_labels = {str(item.get("version_label") or "").strip() for item in items if str(item.get("version_label") or "").strip()}
        if len(version_labels) > 1:
            return _build_version_conflict_prompt(
                question=question,
                candidates=items,
                kind="version_conflict",
                detail="检索结果同时命中了同一业务文档的多个版本，而且这些版本可能给出不同结论。",
            )
    return {}


def _build_version_conflict_prompt(*, question: str, candidates: list[dict[str, Any]], kind: str, detail: str) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    ranked_candidates = _rank_version_candidates(question, candidates)
    recommended_option_id = ""
    current_candidate = next((item for item in ranked_candidates if bool(item.get("is_current_version"))), None)
    historical_candidate = next((item for item in ranked_candidates if not bool(item.get("is_current_version"))), None)
    for item in ranked_candidates[:4]:
        document_id = str(item.get("document_id") or item.get("id") or "")
        version_label = str(item.get("version_label") or "").strip() or f"v{int(item.get('version_number') or 0)}"
        option_id = f"document:{document_id}"
        if bool(item.get("is_current_version")) and not recommended_option_id:
            recommended_option_id = option_id
        options.append(
            _build_interrupt_option(
                option_id=option_id,
                label=f"按 {version_label} 回答",
                description=_describe_version_document(item),
                patch={
                    "document_ids": [document_id],
                    "focus_hint": {
                        "kind": "single_version",
                        "document_ids": [document_id],
                        "primary_document_id": document_id,
                        "version_label": version_label,
                        "version_family_key": str(item.get("version_family_key") or ""),
                        "display_text": version_label,
                    },
                },
                badges=_version_badges(item),
                meta=_version_meta(item, score=float(item.get("score") or 0.0)),
            )
        )
    if current_candidate and historical_candidate:
        current_id = str(current_candidate.get("document_id") or "")
        historical_id = str(historical_candidate.get("document_id") or "")
        current_label = str(current_candidate.get("version_label") or "").strip() or f"v{int(current_candidate.get('version_number') or 0)}"
        historical_label = str(historical_candidate.get("version_label") or "").strip() or f"v{int(historical_candidate.get('version_number') or 0)}"
        options.append(
            _build_interrupt_option(
                option_id=f"compare:{current_id}:{historical_id}",
                label=f"先比较 {current_label} 与 {historical_label}",
                description=f"先总结 {current_label} 和 {historical_label} 的正文差异，再结合问题给出结论。",
                patch={
                    "document_ids": [current_id, historical_id],
                    "question_suffix": f"请先总结 {current_label} 与 {historical_label} 的正文差异，再回答原问题。",
                    "focus_hint": {
                        "kind": "compare_versions",
                        "document_ids": [current_id, historical_id],
                        "primary_document_id": current_id,
                        "compare_document_ids": [current_id, historical_id],
                        "version_labels": [current_label, historical_label],
                        "version_family_key": str(current_candidate.get("version_family_key") or ""),
                        "display_text": f"{current_label} vs {historical_label}",
                    },
                },
                badges=[current_label, historical_label, "compare"],
                meta={
                    "version_family_key": str(current_candidate.get("version_family_key") or ""),
                    "document_ids": [current_id, historical_id],
                    "version_labels": [current_label, historical_label],
                },
            )
        )
    return {
        "kind": kind,
        "title": "检测到版本差异，请先确认依据版本",
        "detail": detail,
        "question": question,
        "options": options,
        "recommended_option_id": recommended_option_id or (options[0]["id"] if options else ""),
        "allow_free_text": True,
        "fallback_prompt": "如果这些版本都不对，请补充具体时间点、版本标签，或说明你要比较的两个版本。",
        "subject": {
            "type": "version_family",
            "id": str((ranked_candidates[0].get("version_family_key") if ranked_candidates else "") or ""),
            "summary": f"{len(ranked_candidates)} 个候选版本" if ranked_candidates else "",
        },
    }


def _build_visual_ambiguity_prompt(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    region_items: list[dict[str, Any]] = []
    seen_region_units: set[str] = set()
    for item in evidence:
        if str(item.get("source_kind") or "").strip() != "visual_region":
            continue
        unit_id = str(item.get("unit_id") or "").strip()
        if not unit_id or unit_id in seen_region_units:
            continue
        seen_region_units.add(unit_id)
        region_items.append(item)
        if len(region_items) >= 4:
            break
    visual_items = region_items
    if len(visual_items) < 2:
        fallback_items: list[dict[str, Any]] = []
        seen_assets: set[str] = set()
        for item in evidence:
            asset_id = str(item.get("asset_id") or "").strip()
            if not asset_id or asset_id in seen_assets or not str(item.get("source_kind") or "").startswith("visual"):
                continue
            seen_assets.add(asset_id)
            fallback_items.append(item)
            if len(fallback_items) >= 4:
                break
        visual_items = fallback_items
    if len(visual_items) < 2:
        return {}
    options = []
    for item in visual_items:
        region_label = _visual_region_label(item)
        page_number = int(item.get("page_number") or 0)
        label = (
            f"第 {page_number} 页 · {region_label}"
            if page_number and region_label
            else str(item.get("section_title") or "").strip()
            or (f"第 {page_number} 页截图" if page_number else "截图区域")
        )
        detail = str(item.get("document_title") or "").strip()
        if str(item.get("version_label") or "").strip():
            detail = f"{detail} / {str(item.get('version_label') or '').strip()}".strip(" /")
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)):
            detail = f"{detail} / 置信度 {float(confidence) * 100:.1f}%".strip(" /")
        if region_label:
            question_suffix = (
                f"请聚焦第 {page_number} 页截图中的“{region_label}”区域回答。"
                if page_number
                else f"请聚焦截图中的“{region_label}”区域回答。"
            )
        else:
            question_suffix = (
                f"请聚焦第 {page_number} 页截图“{label}”相关内容。"
                if page_number
                else f"请聚焦截图区域“{label}”相关内容。"
            )
        document_ids = [str(item.get("document_id") or "")] if str(item.get("document_id") or "") else []
        badges = [badge for badge in [
            str(item.get("version_label") or "").strip(),
            f"p.{page_number}" if page_number else "",
            f"{float(confidence) * 100:.1f}%" if isinstance(confidence, (int, float)) else "",
        ] if badge]
        options.append(
            _build_interrupt_option(
                option_id=(
                    f"region:{str(item.get('unit_id') or '')}"
                    if region_label
                    else f"asset:{str(item.get('asset_id') or '')}"
                ),
                label=label,
                description=detail or "聚焦这个截图区域继续回答。",
                patch={
                    "document_ids": document_ids,
                    "question_suffix": question_suffix,
                    "focus_hint": {
                        "kind": "visual_region",
                        "document_ids": document_ids,
                        "asset_id": str(item.get("asset_id") or ""),
                        "region_id": str(item.get("unit_id") or "") if region_label else "",
                        "region_label": region_label,
                        "page_number": page_number or None,
                        "version_label": str(item.get("version_label") or ""),
                        "display_text": label,
                    },
                },
                badges=badges,
                meta={
                    "document_id": str(item.get("document_id") or ""),
                    "asset_id": str(item.get("asset_id") or ""),
                    "region_id": str(item.get("unit_id") or "") if region_label else "",
                    "region_label": region_label,
                    "page_number": page_number or None,
                    "version_label": str(item.get("version_label") or ""),
                    "confidence": confidence,
                },
            )
        )
    return {
        "kind": "visual_ambiguity",
        "title": "命中了多处截图证据，请先确认要聚焦的区域",
        "detail": "当前问题更像是在问截图中的某一处区域，但检索同时命中了多个视觉证据。",
        "question": question,
        "options": options,
        "recommended_option_id": options[0]["id"] if options else "",
        "allow_free_text": True,
        "fallback_prompt": "可以直接补充第几页、哪张截图，或者红框中的哪一块。",
        "subject": {
            "type": "visual_region_group",
            "id": str((visual_items[0].get("asset_id") if visual_items else "") or ""),
            "summary": f"{len(visual_items)} 个候选截图区域" if visual_items else "",
        },
    }


async def _build_enterprise_clarification_prompt(
    *,
    user: CurrentUser,
    question: str,
    scope_snapshot: dict[str, Any],
    evidence: list[dict[str, Any]],
    retrieval_meta: dict[str, Any],
    answer_mode: str,
    fetch_corpus_documents_fn: Any,
) -> dict[str, Any]:
    aggregate = dict(retrieval_meta.get("aggregate") or {})
    if bool(aggregate.get("empty_scope")):
        return _build_scope_ambiguity_prompt(question)
    prompt = await _build_temporal_clarification_prompt(
        user=user,
        question=question,
        scope_snapshot=scope_snapshot,
        fetch_corpus_documents_fn=fetch_corpus_documents_fn,
    )
    if prompt:
        return prompt
    prompt = _build_evidence_version_conflict_prompt(question, evidence)
    if prompt:
        return prompt
    if _has_visual_intent(question):
        prompt = _build_visual_ambiguity_prompt(question, evidence)
        if prompt:
            return prompt
    if str(answer_mode or "") == "refusal" and not evidence and not bool(scope_snapshot.get("allow_common_knowledge")):
        return _build_insufficient_evidence_prompt(question)
    return {}


async def _fetch_version_diff_summary(
    *,
    user: CurrentUser,
    current_document_id: str,
    historical_document_id: str,
) -> str:
    current_id = str(current_document_id or "").strip()
    historical_id = str(historical_document_id or "").strip()
    if not current_id or not historical_id or current_id == historical_id:
        return ""
    timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        payload = await request_service_json(
            client,
            "GET",
            f"{runtime_settings.kb_service_url}/api/v1/kb/documents/{current_id}/versions/{historical_id}/diff?compare_to_document_id={current_id}",
            headers=downstream_headers(user),
        )
    diff = dict((payload or {}).get("diff") or {})
    summary = dict(diff.get("summary") or {})
    changed_sections = int(summary.get("changed_sections") or 0)
    modified_chunks = int(summary.get("modified_chunks") or 0)
    added_chunks = int(summary.get("added_chunks") or 0)
    removed_chunks = int(summary.get("removed_chunks") or 0)
    if not any((changed_sections, modified_chunks, added_chunks, removed_chunks)):
        return "两个版本的正文没有明显差异。"
    return (
        f"共变更 {changed_sections} 个章节，新增 {added_chunks} 个片段，"
        f"删除 {removed_chunks} 个片段，修改 {modified_chunks} 个片段。"
    )


def _build_answer_basis(prepared: dict[str, Any]) -> dict[str, Any]:
    focus_hint = dict(getattr(prepared.get("payload"), "focus_hint", {}) or {})
    evidence = list(prepared.get("evidence") or [])
    if str(focus_hint.get("kind") or "") == "compare_versions":
        labels = [str(item).strip() for item in list(focus_hint.get("version_labels") or []) if str(item).strip()]
        return {
            "kind": "compare_versions",
            "label": str(focus_hint.get("display_text") or "版本比较").strip(),
            "version_labels": labels,
            "document_ids": list(focus_hint.get("compare_document_ids") or focus_hint.get("document_ids") or []),
            "compare_summary": str(prepared.get("comparison_summary") or "").strip(),
        }
    if str(focus_hint.get("kind") or "") == "visual_region":
        parts = [
            str(focus_hint.get("version_label") or "").strip(),
            f"第 {int(focus_hint.get('page_number') or 0)} 页" if int(focus_hint.get("page_number") or 0) else "",
            str(focus_hint.get("region_label") or focus_hint.get("display_text") or "").strip(),
        ]
        return {
            "kind": "visual_region",
            "label": " / ".join(part for part in parts if part) or str(focus_hint.get("display_text") or "截图区域").strip(),
            "asset_id": str(focus_hint.get("asset_id") or "").strip(),
            "region_id": str(focus_hint.get("region_id") or "").strip(),
        }
    if str(focus_hint.get("version_label") or "").strip():
        return {
            "kind": "single_version",
            "label": str(focus_hint.get("version_label") or "").strip(),
            "document_ids": list(focus_hint.get("document_ids") or []),
        }
    if evidence:
        first = dict(evidence[0] or {})
        parts = [
            str(first.get("version_label") or "").strip(),
            str(first.get("document_title") or "").strip(),
        ]
        label = " / ".join(part for part in parts if part)
        if label:
            return {"kind": "evidence", "label": label}
    return {}


def _apply_answer_basis(answer: str, basis: dict[str, Any]) -> str:
    cleaned_answer = str(answer or "").strip()
    label = str(basis.get("label") or "").strip()
    if not label:
        return cleaned_answer
    header_lines = [f"回答依据：{label}"]
    compare_summary = str(basis.get("compare_summary") or "").strip()
    if compare_summary:
        header_lines.append(f"版本差异：{compare_summary}")
    return "\n\n".join(header_lines + ([cleaned_answer] if cleaned_answer else [])).strip()


def _sanitize_answer_payload(answer_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(answer_payload or {})
    return {
        "answer": str(payload.get("answer") or ""),
        "provider": str(payload.get("provider") or ""),
        "model": str(payload.get("model") or ""),
        "usage": dict(payload.get("usage") or {}),
        "llm_trace": dict(payload.get("llm_trace") or {}),
    }


def _sanitize_generation_checkpoint(generation_checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(generation_checkpoint or {})
    answer_payload = _sanitize_answer_payload(payload.get("answer_payload") or {})
    if not answer_payload["answer"] and not answer_payload["provider"] and not answer_payload["model"] and not answer_payload["usage"] and not answer_payload["llm_trace"]:
        return {}
    return {
        "answer_payload": answer_payload,
        "generation_ms": max(float(payload.get("generation_ms") or 0.0), 0.0),
    }


def _build_generation_checkpoint(answer_payload: dict[str, Any], generation_ms: float) -> dict[str, Any]:
    return {
        "answer_payload": _sanitize_answer_payload(answer_payload),
        "generation_ms": max(float(generation_ms or 0.0), 0.0),
    }


def _resume_target_for_stage(stage: str, *, generation_checkpoint: dict[str, Any] | None = None) -> str:
    cleaned_stage = str(stage or "").strip().lower()
    if generation_checkpoint:
        return RESUME_TARGET_PERSISTENCE
    if cleaned_stage in {"retrieval_completed", "retrieval_resumed"}:
        return RESUME_TARGET_GENERATION
    if cleaned_stage in {"generation_completed", "persistence_resumed"}:
        return RESUME_TARGET_PERSISTENCE
    return ""


def _build_resume_checkpoint(
    prepared: dict[str, Any],
    *,
    generation_checkpoint: dict[str, Any] | None = None,
    resume_target: str = "",
) -> dict[str, Any]:
    checkpoint = {
        "scope_snapshot": dict(prepared.get("scope_snapshot") or {}),
        "execution_mode": str(prepared.get("execution_mode") or ""),
        "history": list(prepared.get("history") or []),
        "evidence": list(prepared.get("evidence") or []),
        "contextualized_question": str(prepared.get("contextualized_question") or ""),
        "retrieval_meta": dict(prepared.get("retrieval_meta") or {}),
        "settings_prompt_append": str(prepared.get("settings_prompt_append") or ""),
        "comparison_summary": str(prepared.get("comparison_summary") or ""),
        "answer_mode": str(prepared.get("answer_mode") or ""),
        "evidence_status": str(prepared.get("evidence_status") or ""),
        "grounding_score": float(prepared.get("grounding_score") or 0.0),
        "refusal_reason": str(prepared.get("refusal_reason") or ""),
        "safety": dict(prepared.get("safety") or {}),
    }
    sanitized_generation_checkpoint = _sanitize_generation_checkpoint(generation_checkpoint)
    if sanitized_generation_checkpoint:
        checkpoint["generation_checkpoint"] = sanitized_generation_checkpoint
    cleaned_resume_target = str(resume_target or "").strip()
    if cleaned_resume_target:
        checkpoint["resume_target"] = cleaned_resume_target
    return checkpoint


def _resume_checkpoint_for_run(workflow_run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workflow_run, dict):
        return {}
    state = dict(workflow_run.get("workflow_state") or {})
    checkpoint = state.get("resume_checkpoint")
    return dict(checkpoint) if isinstance(checkpoint, dict) else {}


def _restore_prepared_from_resume_checkpoint(
    *,
    session_id: str,
    payload: Any,
    trace_id: str,
    total_started: float,
    resume_workflow_run: dict[str, Any],
) -> dict[str, Any] | None:
    checkpoint = _resume_checkpoint_for_run(resume_workflow_run)
    if not checkpoint:
        return None
    resume_started = time.perf_counter()
    resume_state = dict(resume_workflow_run.get("workflow_state") or {})
    generation_checkpoint = _sanitize_generation_checkpoint(checkpoint.get("generation_checkpoint") or {})
    resume_target = str(checkpoint.get("resume_target") or _resume_target_for_stage("", generation_checkpoint=generation_checkpoint))
    execution_mode = normalize_execution_mode(
        getattr(payload, "execution_mode", None) or str(checkpoint.get("execution_mode") or ""),
        default="grounded",
    )
    scope_snapshot = dict(checkpoint.get("scope_snapshot") or {})
    scope_snapshot["execution_mode"] = execution_mode
    prepared = {
        "session_id": session_id,
        "payload": payload,
        "trace_id": trace_id,
        "scope_snapshot": scope_snapshot,
        "execution_mode": execution_mode,
        "history": list(checkpoint.get("history") or []),
        "evidence": list(checkpoint.get("evidence") or []),
        "contextualized_question": str(checkpoint.get("contextualized_question") or payload.question),
        "retrieval_meta": dict(checkpoint.get("retrieval_meta") or {}),
        "settings_prompt_append": str(checkpoint.get("settings_prompt_append") or ""),
        "comparison_summary": str(checkpoint.get("comparison_summary") or ""),
        "answer_mode": str(checkpoint.get("answer_mode") or "grounded"),
        "evidence_status": str(checkpoint.get("evidence_status") or ""),
        "grounding_score": float(checkpoint.get("grounding_score") or 0.0),
        "refusal_reason": str(checkpoint.get("refusal_reason") or ""),
        "safety": dict(checkpoint.get("safety") or {}),
        "timing": {
            "total_started": total_started,
            "scope_ms": 0.0,
            "retrieval_ms": 0.0,
            "resume_ms": 0.0,
        },
        "resume": {
            "resumed": True,
            "source_run_id": str(resume_workflow_run.get("id") or ""),
            "source_stage": str(resume_state.get("stage") or resume_workflow_run.get("stage") or ""),
            "resume_target": resume_target,
            "reused_retrieval": True,
            "reused_generation": bool(generation_checkpoint),
        },
    }
    if generation_checkpoint:
        prepared["generation_checkpoint"] = generation_checkpoint
    prepared["timing"]["resume_ms"] = round((time.perf_counter() - resume_started) * 1000.0, 3)
    return prepared


def _enforce_session_cost_budget(
    *,
    session_id: str,
    user: CurrentUser,
    request: Any,
    request_scope: str,
    session_cost_summary_fn: Any,
) -> None:
    budget = float(runtime_settings.chat_session_cost_budget or 0.0)
    if budget <= 0:
        return
    summary = dict(session_cost_summary_fn(session_id, user) or {})
    current_total = round(float(summary.get("estimated_cost_total") or 0.0), 6)
    if current_total < budget:
        return
    GATEWAY_COST_BUDGET_REJECTIONS_TOTAL.labels("session").inc()
    GATEWAY_CHAT_REQUESTS_TOTAL.labels("rejected", "budget").inc()
    write_gateway_audit_event(
        action=request_scope,
        outcome="budget_exceeded",
        request=request,
        user=user,
        resource_type="chat_session",
        resource_id=session_id,
        scope="owner",
        details={
            "budget_scope": "session",
            "budget_amount": round(budget, 6),
            "current_estimated_cost": current_total,
            "currency": runtime_settings.llm_price_currency,
            "assistant_turns": int(summary.get("assistant_turns") or 0),
        },
    )
    raise HTTPException(
        status_code=429,
        detail={
            "detail": "chat session cost budget exceeded",
            "code": "chat_session_cost_budget_exceeded",
            "budget_scope": "session",
            "budget_amount": round(budget, 6),
            "current_estimated_cost": current_total,
            "currency": runtime_settings.llm_price_currency,
        },
        headers={"Retry-After": "3600"},
    )


def build_workflow_event(
    *,
    prepared: dict[str, Any],
    stage: str,
    status: str,
    response_payload: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    event = {
        "stage": stage,
        "status": status,
        "trace_id": prepared["trace_id"],
        "execution_mode": prepared["execution_mode"],
        "answer_mode": prepared["answer_mode"],
        "evidence_count": len(prepared["evidence"]),
        "retrieval_ms": float(prepared["timing"].get("retrieval_ms") or 0.0),
    }
    if prepared.get("resume"):
        event["resume"] = dict(prepared.get("resume") or {})
    if response_payload is not None:
        event["llm_trace"] = dict(response_payload.get("llm_trace") or {})
        event["latency"] = dict(response_payload.get("latency") or {})
    if error is not None:
        detail = str(getattr(error, "detail", "") or str(error) or "")
        event["error"] = {
            "type": error.__class__.__name__,
            "detail": detail,
            "class": "http" if hasattr(error, "status_code") else "runtime",
        }
    return event


def build_chat_workflow_state(
    *,
    prepared: dict[str, Any],
    stage: str,
    response_payload: dict[str, Any] | None = None,
    error: Exception | None = None,
    message_id: str = "",
    generation_checkpoint: dict[str, Any] | None = None,
    resume_target: str = "",
) -> dict[str, Any]:
    aggregate = dict(((prepared.get("retrieval_meta") or {}).get("aggregate") or {}))
    sanitized_generation_checkpoint = _sanitize_generation_checkpoint(generation_checkpoint)
    computed_resume_target = str(resume_target or "").strip() or _resume_target_for_stage(
        stage,
        generation_checkpoint=sanitized_generation_checkpoint,
    )
    state = {
        "stage": stage,
        "execution_mode": prepared["execution_mode"],
        "answer_mode": prepared["answer_mode"],
        "question": prepared["payload"].question,
        "contextualized_question": prepared["contextualized_question"],
        "scope_snapshot": dict(prepared["scope_snapshot"]),
        "evidence_count": len(prepared["evidence"]),
        "selected_candidates": int(aggregate.get("selected_candidates") or len(prepared["evidence"])),
        "partial_failure": bool(aggregate.get("partial_failure")),
        "retrieval_aggregate": aggregate,
        "retrieval_meta": dict(prepared.get("retrieval_meta") or {}),
        "evidence": list(prepared.get("evidence") or []),
        "clarification": dict(prepared.get("clarification") or {}),
        "history": list(prepared.get("history") or []),
        "agent_events": _workflow_agent_events(prepared),
        "safety": dict(prepared["safety"]),
        "timing": dict(prepared["timing"]),
        "resume_target": computed_resume_target,
        "can_resume": bool(computed_resume_target),
        "resume_checkpoint": _build_resume_checkpoint(
            prepared,
            generation_checkpoint=sanitized_generation_checkpoint,
            resume_target=computed_resume_target,
        ),
    }
    if prepared.get("resume"):
        state["resume"] = dict(prepared.get("resume") or {})
    if response_payload is not None:
        state["response"] = {
            "strategy_used": str(response_payload.get("strategy_used") or ""),
            "provider": str(response_payload.get("provider") or ""),
            "model": str(response_payload.get("model") or ""),
            "citation_count": len(list(response_payload.get("citations") or [])),
            "answer_preview": compact_text(str(response_payload.get("answer") or ""), 320),
            "latency": dict(response_payload.get("latency") or {}),
            "usage": dict(response_payload.get("usage") or {}),
            "cost": dict(response_payload.get("cost") or {}),
            "llm_trace": dict(response_payload.get("llm_trace") or {}),
            "message_id": message_id.strip(),
        }
    if error is not None:
        state["error"] = {
            "type": error.__class__.__name__,
            "detail": str(getattr(error, "detail", "") or str(error) or ""),
        }
    return state


async def prepare_chat_message(
    *,
    session_id: str,
    payload: Any,
    request: Any | None = None,
    request_scope: str = "chat.message.send",
    user: CurrentUser,
    load_session_fn: Any,
    default_scope_fn: Any,
    resolve_scope_snapshot_fn: Any,
    recent_history_messages_fn: Any,
    retrieve_scope_evidence_fn: Any,
    fetch_corpus_documents_fn: Any,
    session_cost_summary_fn: Any | None = None,
    resume_workflow_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    trace_id = ensure_trace_id(current_trace_id(), prefix="gateway-")
    session = load_session_fn(session_id, user)
    summary_fn = session_cost_summary_fn
    if summary_fn is None:
        from .gateway_sessions import session_cost_summary as _session_cost_summary

        summary_fn = lambda sid, current_user: _session_cost_summary(
            sid,
            current_user,
            load_session_fn=lambda inner_session_id, inner_user: load_session_fn(
                inner_session_id,
                inner_user,
            ),
        )
    _enforce_session_cost_budget(
        session_id=session_id,
        user=user,
        request=request,
        request_scope=request_scope,
        session_cost_summary_fn=summary_fn,
    )
    resumed = _restore_prepared_from_resume_checkpoint(
        session_id=session_id,
        payload=payload,
        trace_id=trace_id,
        total_started=total_started,
        resume_workflow_run=resume_workflow_run or {},
    )
    if resumed is not None:
        return resumed
    scope_payload = payload.scope or ChatScopePayload(**(session.get("scope_json") or default_scope_fn()))
    execution_mode = normalize_execution_mode(
        getattr(payload, "execution_mode", None) or str((session.get("scope_json") or {}).get("execution_mode") or ""),
        default="grounded",
    )
    focus_hint = dict(getattr(payload, "focus_hint", {}) or {})
    scope_started = time.perf_counter()
    scope_snapshot = await resolve_scope_snapshot_fn(user, scope_payload)
    scope_snapshot["execution_mode"] = execution_mode
    platform_context = resolve_platform_context(scope_snapshot, user)
    agent_profile = dict(platform_context.get("agent_profile") or {})
    if execution_mode == "agent" and not list(scope_snapshot.get("corpus_ids") or []) and list(agent_profile.get("default_corpus_ids") or []):
        scope_snapshot["mode"] = "multi"
        scope_snapshot["corpus_ids"] = list(agent_profile.get("default_corpus_ids") or [])
    scope_ms = round((time.perf_counter() - scope_started) * 1000.0, 3)
    history = recent_history_messages_fn(session_id, user, limit=8)
    retrieval_started = time.perf_counter()
    if execution_mode == "agent":
        evidence, contextualized_question, retrieval_meta = await run_agent_search(
            user=user,
            scope_snapshot=scope_snapshot,
            question=payload.question,
            history=history,
            focus_hint=focus_hint,
            agent_profile=agent_profile,
            prompt_template=dict(platform_context.get("prompt_template") or {}),
            retrieve_scope_evidence_fn=retrieve_scope_evidence_fn,
            fetch_corpus_documents_fn=fetch_corpus_documents_fn,
            kb_service_url=runtime_settings.kb_service_url,
        )
    else:
        evidence, contextualized_question, retrieval_meta = await retrieve_scope_evidence_fn(
            user=user,
            scope_snapshot=scope_snapshot,
            question=payload.question,
            history=history,
            focus_hint=focus_hint,
        )
    retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000.0, 3)
    answer_mode, evidence_status, grounding_score, refusal_reason = classify_evidence(
        evidence,
        allow_common_knowledge=bool(scope_snapshot.get("allow_common_knowledge")),
    )
    safety = analyze_prompt_safety(
        question=payload.question,
        history=history,
        evidence=evidence,
        prefer_fallback=bool(evidence) and execution_mode in {"grounded", "agent"},
    )
    answer_mode, evidence_status, grounding_score, refusal_reason = apply_safety_response_policy(
        answer_mode=answer_mode,
        evidence_status=evidence_status,
        grounding_score=grounding_score,
        refusal_reason=refusal_reason,
        safety=safety,
        evidence_count=len(evidence),
    )
    if safety.risk_level in {"medium", "high"}:
        GATEWAY_SAFETY_EVENTS_TOTAL.labels(safety.risk_level, safety.action).inc()
    clarification = await _build_enterprise_clarification_prompt(
        user=user,
        question=str(payload.question or ""),
        scope_snapshot=scope_snapshot,
        evidence=evidence,
        retrieval_meta=dict(retrieval_meta or {}),
        answer_mode=answer_mode,
        fetch_corpus_documents_fn=fetch_corpus_documents_fn,
    )
    if clarification:
        retrieval_meta = dict(retrieval_meta or {})
        aggregate = dict(retrieval_meta.get("aggregate") or {})
        aggregate["clarification_kind"] = str(clarification.get("kind") or "")
        aggregate["clarification_required"] = True
        retrieval_meta["aggregate"] = aggregate
    comparison_summary = ""
    compare_document_ids = [str(item).strip() for item in list(focus_hint.get("compare_document_ids") or []) if str(item).strip()]
    if len(compare_document_ids) >= 2:
        try:
            comparison_summary = await _fetch_version_diff_summary(
                user=user,
                current_document_id=compare_document_ids[0],
                historical_document_id=compare_document_ids[1],
            )
        except Exception:
            logger.warning("failed to load version diff summary compare_document_ids=%s", compare_document_ids, exc_info=True)
    settings_prompt_append = _platform_instruction_text(platform_context)
    if comparison_summary:
        settings_prompt_append = "\n\n".join(
            part
            for part in (
                settings_prompt_append,
                f"Version comparison summary:\n{comparison_summary}",
            )
            if str(part).strip()
        )
    return {
        "session_id": session_id,
        "payload": payload,
        "trace_id": trace_id,
        "scope_snapshot": scope_snapshot,
        "execution_mode": execution_mode,
        "history": history,
        "evidence": evidence,
        "contextualized_question": contextualized_question,
        "retrieval_meta": retrieval_meta,
        "platform_context": platform_context,
        "settings_prompt_append": settings_prompt_append,
        "comparison_summary": comparison_summary,
        "answer_mode": answer_mode,
        "evidence_status": evidence_status,
        "grounding_score": grounding_score,
        "refusal_reason": refusal_reason,
        "safety": safety.as_dict(),
        "clarification": clarification,
        "timing": {
            "total_started": total_started,
            "scope_ms": scope_ms,
            "retrieval_ms": retrieval_ms,
        },
        "resume": {
            "resumed": False,
            "source_run_id": "",
            "source_stage": "",
            "reused_retrieval": False,
        },
    }


def build_chat_response_payload(
    *,
    prepared: dict[str, Any],
    answer_payload: dict[str, Any],
    generation_ms: float,
) -> dict[str, Any]:
    total_ms = round((time.perf_counter() - float(prepared["timing"]["total_started"])) * 1000.0, 3)
    strategy_used = (
        "agent_grounded_qa"
        if prepared["execution_mode"] == "agent"
        else "common_knowledge_chat"
        if prepared["answer_mode"] == "common_knowledge"
        else "hybrid_grounded_qa"
    )
    cost_meta = estimate_usage_cost(
        answer_payload["usage"],
        llm_price_tiers=runtime_settings.llm_price_tiers,
        llm_input_price_per_1k_tokens=runtime_settings.llm_input_price_per_1k_tokens,
        llm_output_price_per_1k_tokens=runtime_settings.llm_output_price_per_1k_tokens,
        llm_price_currency=runtime_settings.llm_price_currency,
    )
    answer_basis = _build_answer_basis(prepared)
    final_answer = _apply_answer_basis(answer_payload["answer"], answer_basis)
    return {
        "session_id": prepared["session_id"],
        "execution_mode": prepared["execution_mode"],
        "answer": final_answer,
        "answer_mode": prepared["answer_mode"],
        "strategy_used": strategy_used,
        "evidence_status": prepared["evidence_status"],
        "grounding_score": prepared["grounding_score"],
        "refusal_reason": prepared["refusal_reason"],
        "safety": prepared["safety"],
        "resume": dict(prepared.get("resume") or {}),
        "citations": prepared["evidence"],
        "evidence_path": [item.get("evidence_path") or {} for item in prepared["evidence"]],
        "provider": answer_payload["provider"],
        "model": answer_payload["model"],
        "usage": answer_payload["usage"],
        "llm_trace": dict(answer_payload.get("llm_trace") or {}),
        "answer_basis": answer_basis,
        "scope_snapshot": prepared["scope_snapshot"],
        "trace_id": prepared["trace_id"],
        "retrieval": prepared["retrieval_meta"],
        "latency": {
            "scope_ms": prepared["timing"]["scope_ms"],
            "retrieval_ms": prepared["timing"]["retrieval_ms"],
            "generation_ms": generation_ms,
            "total_ms": total_ms,
            "resume_ms": float(prepared["timing"].get("resume_ms") or 0.0),
        },
        "cost": cost_meta,
    }


def finalize_chat_message(
    *,
    prepared: dict[str, Any],
    request: Any,
    user: CurrentUser,
    response_payload: dict[str, Any],
    persist_chat_turn_fn: Any,
) -> dict[str, Any]:
    total_ms = float((response_payload.get("latency") or {}).get("total_ms") or 0.0)
    retrieval_ms = float((response_payload.get("latency") or {}).get("retrieval_ms") or 0.0)
    cost_meta = dict(response_payload.get("cost") or {})
    logger.info(
        "chat_turn trace_id=%s mode=%s evidence=%s total_ms=%.3f retrieval_ms=%.3f est_cost=%.6f",
        prepared["trace_id"],
        prepared["answer_mode"],
        len(prepared["evidence"]),
        total_ms,
        retrieval_ms,
        float(cost_meta.get("estimated_cost") or 0.0),
    )
    persisted_message = persist_chat_turn_fn(
        session_id=prepared["session_id"],
        user=user,
        question=prepared["payload"].question,
        session_scope=prepared["scope_snapshot"],
        response_payload=response_payload,
        compact_text_fn=compact_text,
        usage_with_meta_fn=usage_with_meta,
    )
    write_gateway_audit_event(
        action="chat.message.send",
        outcome="blocked" if bool((prepared.get("safety") or {}).get("blocked")) else "success",
        request=request,
        user=user,
        resource_type="chat_session",
        resource_id=prepared["session_id"],
        scope="owner",
        details={
            "answer_mode": prepared["answer_mode"],
            "execution_mode": prepared["execution_mode"],
            "evidence_status": prepared["evidence_status"],
            "safety_risk_level": str((prepared.get("safety") or {}).get("risk_level") or "low"),
            "safety_reason_codes": list((prepared.get("safety") or {}).get("reason_codes") or []),
            "partial_failure": bool((prepared["retrieval_meta"].get("aggregate") or {}).get("partial_failure")),
            "selected_candidates": int((prepared["retrieval_meta"].get("aggregate") or {}).get("selected_candidates", 0) or 0),
            "resumed_from_run_id": str((prepared.get("resume") or {}).get("source_run_id") or ""),
            "resumed_from_stage": str((prepared.get("resume") or {}).get("source_stage") or ""),
        },
    )
    aggregate = dict(prepared["retrieval_meta"].get("aggregate") or {})
    GATEWAY_RETRIEVAL_FANOUT_TOTAL.labels(
        "empty_scope" if aggregate.get("empty_scope") else "partial" if aggregate.get("partial_failure") else "success"
    ).inc()
    GATEWAY_CHAT_REQUESTS_TOTAL.labels("success", prepared["answer_mode"]).inc()
    GATEWAY_CHAT_LATENCY_MS.observe(total_ms)
    if aggregate.get("retrieval_ms") is not None:
        GATEWAY_RETRIEVAL_FANOUT_WALL_MS.observe(float(aggregate.get("retrieval_ms") or 0.0))
    model_name = str(response_payload.get("model") or "fallback")
    usage = dict(response_payload.get("usage") or {})
    GATEWAY_LLM_TOKENS_TOTAL.labels("input", model_name).inc(float(usage.get("prompt_tokens") or 0))
    GATEWAY_LLM_TOKENS_TOTAL.labels("output", model_name).inc(float(usage.get("completion_tokens") or 0))
    response_payload["message"] = persisted_message
    return response_payload


async def handle_chat_message(
    *,
    session_id: str,
    payload: Any,
    request: Any,
    request_scope: str = "chat.message.send",
    user: CurrentUser,
    load_session_fn: Any,
    default_scope_fn: Any,
    resolve_scope_snapshot_fn: Any,
    recent_history_messages_fn: Any,
    retrieve_scope_evidence_fn: Any,
    fetch_corpus_documents_fn: Any,
    session_cost_summary_fn: Any | None = None,
    persist_chat_turn_fn: Any,
    start_workflow_run_fn: Any,
    update_workflow_run_fn: Any,
    resume_workflow_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow_run: dict[str, Any] | None = None
    workflow_events: list[dict[str, Any]] = []
    prepared = await prepare_chat_message(
        session_id=session_id,
        payload=payload,
        request=request,
        request_scope=request_scope,
        user=user,
        load_session_fn=load_session_fn,
        default_scope_fn=default_scope_fn,
        resolve_scope_snapshot_fn=resolve_scope_snapshot_fn,
        recent_history_messages_fn=recent_history_messages_fn,
        retrieve_scope_evidence_fn=retrieve_scope_evidence_fn,
        fetch_corpus_documents_fn=fetch_corpus_documents_fn,
        session_cost_summary_fn=session_cost_summary_fn,
        resume_workflow_run=resume_workflow_run,
    )
    generation_checkpoint = _sanitize_generation_checkpoint(prepared.get("generation_checkpoint") or {})
    initial_stage = (
        "persistence_resumed"
        if generation_checkpoint
        else "retrieval_resumed"
        if bool((prepared.get("resume") or {}).get("reused_retrieval"))
        else "retrieval_completed"
    )
    resume_target = str((prepared.get("resume") or {}).get("resume_target") or _resume_target_for_stage(initial_stage, generation_checkpoint=generation_checkpoint))
    initial_response_payload: dict[str, Any] | None = None
    if generation_checkpoint:
        initial_response_payload = build_chat_response_payload(
            prepared=prepared,
            answer_payload=dict(generation_checkpoint["answer_payload"]),
            generation_ms=float(generation_checkpoint["generation_ms"]),
        )
    workflow_run = start_workflow_run_fn(
        session_id=session_id,
        user=user,
        execution_mode=prepared["execution_mode"],
        workflow_kind=workflow_kind_for_turn(
            execution_mode=prepared["execution_mode"],
            answer_mode=prepared["answer_mode"],
        ),
        question=prepared["payload"].question,
        trace_id=prepared["trace_id"],
        scope_snapshot=prepared["scope_snapshot"],
        workflow_state=build_chat_workflow_state(
            prepared=prepared,
            stage=initial_stage,
            response_payload=initial_response_payload,
            generation_checkpoint=generation_checkpoint,
            resume_target=resume_target,
        ),
        workflow_events=[
            build_workflow_event(
                prepared=prepared,
                stage=initial_stage,
                status="running",
                response_payload=initial_response_payload,
            )
        ],
        tool_calls=_workflow_tool_calls(prepared),
    )
    workflow_events = list(
        workflow_run.get("workflow_events")
        or [
            build_workflow_event(
                prepared=prepared,
                stage=initial_stage,
                status="running",
                response_payload=initial_response_payload,
            )
        ]
    )
    generation_started = time.perf_counter()
    try:
        if generation_checkpoint:
            response_payload = dict(initial_response_payload or {})
        else:
            answer_payload = await generate_grounded_answer(
                question=prepared["contextualized_question"],
                history=prepared["history"],
                evidence=prepared["evidence"],
                answer_mode=prepared["answer_mode"],
                safety=prepared["safety"],
                settings_prompt_append=str(prepared.get("settings_prompt_append") or ""),
            )
            generation_ms = round((time.perf_counter() - generation_started) * 1000.0, 3)
            generation_checkpoint = _build_generation_checkpoint(answer_payload, generation_ms)
            response_payload = build_chat_response_payload(
                prepared=prepared,
                answer_payload=answer_payload,
                generation_ms=generation_ms,
            )
            update_workflow_run_fn(
                run_id=str(workflow_run.get("id") or ""),
                user=user,
                status="running",
                workflow_state=build_chat_workflow_state(
                    prepared=prepared,
                    stage="generation_completed",
                    response_payload=response_payload,
                    generation_checkpoint=generation_checkpoint,
                    resume_target=RESUME_TARGET_PERSISTENCE,
                ),
                workflow_events=workflow_events + [
                    build_workflow_event(
                        prepared=prepared,
                        stage="generation_completed",
                        status="running",
                        response_payload=response_payload,
                    )
                ],
                tool_calls=_workflow_tool_calls(prepared),
            )
            workflow_events = workflow_events + [
                build_workflow_event(
                    prepared=prepared,
                    stage="generation_completed",
                    status="running",
                    response_payload=response_payload,
                )
            ]
        result = finalize_chat_message(
            prepared=prepared,
            request=request,
            user=user,
            response_payload=response_payload,
            persist_chat_turn_fn=persist_chat_turn_fn,
        )
        persisted_message = dict(result.get("message") or {})
        workflow_run = update_workflow_run_fn(
            run_id=str(workflow_run.get("id") or ""),
            user=user,
            status="completed",
            workflow_state=build_chat_workflow_state(
                prepared=prepared,
                stage="persisted",
                response_payload=result,
                message_id=str(persisted_message.get("id") or ""),
                generation_checkpoint=generation_checkpoint,
                resume_target="",
            ),
            workflow_events=workflow_events + [
                build_workflow_event(
                    prepared=prepared,
                    stage="persisted",
                    status="completed",
                    response_payload=result,
                )
            ],
            tool_calls=_workflow_tool_calls(prepared),
            message_id=str(persisted_message.get("id") or ""),
        )
        result["workflow_run"] = workflow_run
        return result
    except Exception as exc:
        if workflow_run is not None:
            update_workflow_run_fn(
                run_id=str(workflow_run.get("id") or ""),
                user=user,
                status="failed",
                workflow_state=build_chat_workflow_state(
                    prepared=prepared,
                    stage="failed",
                    error=exc,
                    generation_checkpoint=generation_checkpoint,
                    resume_target=RESUME_TARGET_PERSISTENCE if generation_checkpoint else RESUME_TARGET_GENERATION,
                ),
                workflow_events=workflow_events + [
                    build_workflow_event(
                        prepared=prepared,
                        stage="failed",
                        status="failed",
                        error=exc,
                    )
                ],
                tool_calls=_workflow_tool_calls(prepared),
            )
        raise
