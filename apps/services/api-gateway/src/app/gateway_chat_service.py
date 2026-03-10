from __future__ import annotations

import time
from typing import Any

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
from .gateway_workflows import workflow_kind_for_turn


RESUME_TARGET_GENERATION = "generate_answer"
RESUME_TARGET_PERSISTENCE = "persist_message"


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
        "settings_prompt_append": _platform_instruction_text(platform_context),
        "answer_mode": answer_mode,
        "evidence_status": evidence_status,
        "grounding_score": grounding_score,
        "refusal_reason": refusal_reason,
        "safety": safety.as_dict(),
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
    return {
        "session_id": prepared["session_id"],
        "execution_mode": prepared["execution_mode"],
        "answer": answer_payload["answer"],
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
