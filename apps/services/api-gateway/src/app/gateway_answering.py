from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage, ToolMessage

from shared.grounded_answering import (
    COMMON_KNOWLEDGE_DISCLAIMER,
    classify_evidence,
    compact_history_messages,
    compact_text,
    dicts_to_langchain_messages,
    ensure_citation_markers,
    ensure_common_knowledge_disclaimer,
    evidence_prompt_lines,
    fallback_answer,
    is_low_signal_common_knowledge_question,
    langchain_messages_to_dicts,
    low_signal_common_knowledge_answer,
)
from shared.model_routing import execute_with_model_route_fallback, settings_with_model_route_plan
from shared.prompt_registry import get_prompt_definition
from shared.prompt_safety import augment_settings_prompt, blocked_prompt_answer

from .ai_client import load_llm_settings
from .context_prioritizer import ContextPrioritizer
from .context_window import ContextWindowManager, estimate_tokens
from .gateway_config import SHORT_QUESTION_RE
from .gateway_runtime import logger, runtime_settings
from .langchain_client import create_llm_completion, create_llm_completion_stream


FINAL_ANSWER_TOOL_NAMES = frozenset({"kb_scope_summary", "workflow_trace_summary", "tool_registry_stats"})
FINAL_ANSWER_MAX_TOOL_CALLS = 3


def _attach_route_trace(
    completion: dict[str, Any],
    route_key: str,
    *,
    route_attempts: list[str] | None = None,
) -> dict[str, Any]:
    llm_trace = dict(completion.get("llm_trace") or {})
    if route_key:
        llm_trace["route_key"] = route_key
    if route_attempts:
        llm_trace["route_attempts"] = list(route_attempts)
        llm_trace["fallback_used"] = len(route_attempts) > 1 and route_attempts[-1] != route_attempts[0]
    payload = dict(completion)
    payload["llm_trace"] = llm_trace
    return payload


def _final_answer_tools_enabled() -> bool:
    return bool(getattr(runtime_settings, "final_answer_tools_enabled", False))


def get_final_answer_llm_tools() -> list[dict[str, Any]]:
    """Return the read-only ToolRegistry schemas exposed to final-answer models."""
    from .business_tools import ensure_business_tools_registered
    from .tool_registry import tool_registry

    ensure_business_tools_registered()
    return tool_registry.get_llm_tools(enabled_tools=set(FINAL_ANSWER_TOOL_NAMES), categories=["system"])


async def _execute_final_answer_tool_calls(tool_calls: list[dict[str, Any]]) -> tuple[list[ToolMessage], dict[str, Any]]:
    from .tool_registry import tool_registry

    messages: list[ToolMessage] = []
    events: list[dict[str, Any]] = []
    allowed = set(FINAL_ANSWER_TOOL_NAMES)

    for index, tool_call in enumerate(tool_calls, start=1):
        tool_name = str(tool_call.get("name") or "").strip()
        trace_tool_name = _final_answer_trace_tool_name(tool_name)
        tool_call_id = str(tool_call.get("id") or f"call-{index}")
        raw_args = tool_call.get("args")
        args = raw_args if isinstance(raw_args, dict) else {}
        payload: dict[str, Any]
        event: dict[str, Any] = {"tool": trace_tool_name}

        if index > FINAL_ANSWER_MAX_TOOL_CALLS:
            event["status"] = "skipped"
            event["reason"] = "tool_call_budget_exceeded"
            payload = {"success": False, "error": "tool call budget exceeded"}
        elif tool_name not in allowed:
            event["status"] = "rejected"
            event["reason"] = "tool_not_allowed"
            payload = {"success": False, "error": "tool is not allowed for final answer"}
        else:
            result = await tool_registry.execute(tool_name, args)
            event.update(
                {
                    "status": "success" if result.success else "failed",
                    "duration_ms": result.duration_ms,
                    "from_cache": result.from_cache,
                }
            )
            if result.success:
                event["result_keys"] = sorted(str(key) for key in result.data.keys())[:12]
                payload = {"success": True, "data": result.data}
            else:
                safe_error = _safe_tool_error(result.error)
                event["error"] = safe_error
                payload = {"success": False, "error": safe_error}

        events.append(event)
        messages.append(
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=tool_call_id,
                name=trace_tool_name,
            )
        )

    executed = sum(1 for event in events if event.get("status") == "success")
    return messages, {
        "enabled": True,
        "rounds": 1 if tool_calls else 0,
        "requested": len(tool_calls),
        "executed": executed,
        "rejected": sum(1 for event in events if event.get("status") in {"rejected", "skipped"}),
        "failed": sum(1 for event in events if event.get("status") == "failed"),
        "events": events,
    }


def _safe_tool_error(error: str) -> str:
    text = str(error or "").strip().replace("\n", " ")
    return text[:160] if text else "tool execution failed"


def _final_answer_trace_tool_name(value: Any) -> str:
    name = str(value or "").strip()
    if name in FINAL_ANSWER_TOOL_NAMES:
        return name
    if not name:
        return "unknown"
    return "not_allowed"


def _tool_trace_without_internal_fields(completion: dict[str, Any]) -> dict[str, Any]:
    payload = dict(completion)
    payload.pop("_raw_message", None)
    return payload


def _attach_final_answer_tool_trace(
    completion: dict[str, Any],
    tool_trace: dict[str, Any],
    first_completion: dict[str, Any],
) -> dict[str, Any]:
    payload = _tool_trace_without_internal_fields(completion)
    llm_trace = dict(payload.get("llm_trace") or {})
    first_trace = dict(first_completion.get("llm_trace") or {})
    if first_trace.get("llm_call_id"):
        tool_trace = {**tool_trace, "pre_tool_llm_call_id": str(first_trace["llm_call_id"])}
    llm_trace["final_answer_tools"] = tool_trace
    payload["llm_trace"] = llm_trace
    return payload


async def _create_completion_with_optional_final_tools(
    *,
    settings: Any,
    prompt: Any,
    inputs: dict[str, Any],
    prompt_key: str,
    prompt_version: str,
    model: str,
    temperature: float,
    max_tokens: int,
    fallback_answer_text: str = "",
) -> dict[str, Any]:
    if not _final_answer_tools_enabled():
        return await create_llm_completion(
            settings=settings,
            prompt=prompt,
            inputs=inputs,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    tools = get_final_answer_llm_tools()
    first_completion = await create_llm_completion(
        settings=settings,
        prompt=prompt,
        inputs=inputs,
        tools=tools,
        include_raw_message=True,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    tool_calls = list(first_completion.get("tool_calls") or [])
    if not tool_calls:
        return _attach_final_answer_tool_trace(
            first_completion,
            {"enabled": True, "rounds": 0, "requested": 0, "executed": 0, "rejected": 0, "failed": 0, "events": []},
            first_completion,
        )

    raw_message = first_completion.get("_raw_message")
    if raw_message is None:
        raw_message = AIMessage(content=str(first_completion.get("answer") or ""), tool_calls=tool_calls)
    tool_messages, tool_trace = await _execute_final_answer_tool_calls(tool_calls)
    final_completion = await create_llm_completion(
        settings=settings,
        prompt=prompt,
        inputs=inputs,
        extra_messages=[raw_message, *tool_messages],
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    final_tool_calls = list(final_completion.get("tool_calls") or [])
    if final_tool_calls:
        tool_trace = {**tool_trace, "final_tool_calls_blocked": len(final_tool_calls)}
        if not str(final_completion.get("answer") or "").strip() and fallback_answer_text:
            final_completion = {**final_completion, "answer": fallback_answer_text}
    return _attach_final_answer_tool_trace(final_completion, tool_trace, first_completion)


def contextualize_question(question: str, history: list[dict[str, Any]]) -> str:
    cleaned = question.strip()
    if len(cleaned) >= 20 and not SHORT_QUESTION_RE.search(cleaned):
        return cleaned
    previous_users = [item["content"] for item in history if item["role"] == "user" and item["content"].strip()]
    if not previous_users:
        return cleaned
    previous_question = previous_users[-1]
    if previous_question == cleaned:
        return cleaned
    return previous_question + "\n当前追问：" + cleaned


# ---------------------------------------------------------------------------
# Token 预算动态分配
# ---------------------------------------------------------------------------


def resolve_token_budget(
    *,
    question: str,
    evidence_count: int,
    answer_mode: str,
    default_max_tokens: int = 4096,
    complexity_score: float | None = None,
) -> dict[str, int]:
    """根据问题复杂度、证据量、回答模式动态分配 Token 预算。

    返回各区域的预算分配：
    - system_budget: 系统提示词 token 预算
    - history_budget: 对话历史 token 预算
    - evidence_budget: 证据文本 token 预算
    - answer_budget: 回答生成 (max_tokens) 预算

    策略：
    - 复杂度高 → 更多 token 分配给 evidence + answer
    - 证据多 → history 压缩更多，优先保留证据
    - 常识模式 → 主要分配给 history（无证据依赖）
    - 拒绝模式 → 最小预算，仅保留最近的上下文
    """
    # 基础预算：按 default_max_tokens 分配
    total = max(default_max_tokens, 1024)

    if answer_mode == "refusal":
        return {
            "system_budget": int(total * 0.30),
            "history_budget": int(total * 0.70),
            "evidence_budget": 0,
            "answer_budget": 256,
        }

    if answer_mode == "common_knowledge":
        return {
            "system_budget": int(total * 0.25),
            "history_budget": int(total * 0.75),
            "evidence_budget": 0,
            "answer_budget": min(default_max_tokens, 1200),
        }

    # grounded / agent 模式
    # 复杂度越高 → 证据和答案占比越大
    complexity = max(complexity_score or 1.0, 1.0)
    evidence_ratio = 0.25 + min(complexity * 0.05, 0.15)  # 0.25 - 0.40
    answer_ratio = 0.15 + min(complexity * 0.03, 0.10)     # 0.15 - 0.25
    history_ratio = 1.0 - 0.20 - evidence_ratio - answer_ratio
    system_ratio = 0.20  # 固定 20% 给系统提示词

    # 证据数量修正：证据多时 history 压缩更强
    if evidence_count > 10:
        evidence_ratio += 0.05
        history_ratio -= 0.05
    elif evidence_count < 3:
        evidence_ratio -= 0.05
        history_ratio += 0.05

    return {
        "system_budget": max(int(total * system_ratio), 200),
        "history_budget": max(int(total * history_ratio), 300),
        "evidence_budget": max(int(total * evidence_ratio), 200),
        "answer_budget": max(int(total * answer_ratio), 256),
    }


def manage_context_for_generation(
    *,
    question: str,
    history: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    answer_mode: str,
    system_prompt: str = "",
    default_max_tokens: int = 4096,
    complexity_score: float | None = None,
    min_history_turns: int = 2,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """应用上下文窗口管理，返回优化后的 history 和 evidence_block。

    参数:
        question: 当前问题
        history: 原始对话历史
        evidence: 证据列表
        answer_mode: 回答模式
        system_prompt: 系统提示词
        default_max_tokens: 总 token 预算
        complexity_score: 复杂度评分
        min_history_turns: 最少保留的对话轮数

    返回:
        (managed_history, evidence_block, stats_dict)
    """
    # 1. 解析预算
    budget = resolve_token_budget(
        question=question,
        evidence_count=len(evidence),
        answer_mode=answer_mode,
        default_max_tokens=default_max_tokens,
        complexity_score=complexity_score,
    )

    # 2. 构建 evidence block
    evidence_block = evidence_prompt_lines(evidence)
    evidence_tokens = estimate_tokens(evidence_block)
    if evidence_tokens > budget["evidence_budget"]:
        # 裁剪证据
        ratio = budget["evidence_budget"] / max(evidence_tokens, 1)
        max_chars = max(int(len(evidence_block) * ratio * 1.1), 200)
        evidence_block = evidence_block[:max_chars] + "\n...（证据已截断）"

    # 3. 优先级排序（基于 question 相关性）
    prioritizer = ContextPrioritizer()
    managed_history = prioritizer.rank_and_select(
        history,
        question,
        token_budget=budget["history_budget"],
        min_turns=min_history_turns,
    )

    stats = {
        "budget": budget,
        "history_original": len(history),
        "history_managed": len(managed_history),
        "evidence_tokens": estimate_tokens(evidence_block),
        "history_tokens": sum(estimate_tokens(str(msg.get("content") or "")) for msg in managed_history),
    }

    logger.debug(
        "context_managed question_len=%d original_history=%d managed_history=%d evidence_tokens=%d budget=%s",
        len(question), len(history), len(managed_history), stats["evidence_tokens"], budget,
    )

    return managed_history, evidence_block, stats


def common_knowledge_prompt_messages(
    *,
    settings_prompt: str,
    question: str,
    history: list[dict[str, Any]],
    history_limit: int = 4,
    history_chars: int = 400,
) -> list[dict[str, str]]:
    prompt = get_prompt_definition("chat_common_knowledge").build_prompt()
    formatted = prompt.format_messages(
        settings_prompt=augment_settings_prompt(settings_prompt or ""),
        history=dicts_to_langchain_messages(
            compact_history_messages(history, limit=history_limit, content_limit=history_chars)
        ),
        question=question.strip(),
    )
    return langchain_messages_to_dicts(formatted)


def chat_prompt_messages(
    *,
    settings_prompt: str,
    question: str,
    history: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    answer_mode: str,
) -> list[dict[str, str]]:
    prompt = get_prompt_definition("chat_grounded_answer").build_prompt()
    formatted = prompt.format_messages(
        settings_prompt=augment_settings_prompt(settings_prompt or ""),
        history=dicts_to_langchain_messages(history[-8:]),
        question=question.strip(),
        answer_mode=answer_mode,
        evidence_block=evidence_prompt_lines(evidence),
    )
    return langchain_messages_to_dicts(formatted)


def _log_route_fallback(prompt_key: str, route_attempts: list[str]) -> None:
    if len(route_attempts) <= 1:
        return
    logger.warning(
        "llm route fallback engaged prompt=%s attempted_routes=%s selected_route=%s",
        prompt_key,
        route_attempts,
        route_attempts[-1],
    )


async def generate_grounded_answer(
    *,
    question: str,
    history: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    answer_mode: str,
    safety: dict[str, Any] | None = None,
    settings_prompt_append: str = "",
) -> dict[str, Any]:
    if bool((safety or {}).get("blocked")):
        return {
            "answer": blocked_prompt_answer(
                question=question,
                evidence=evidence,
                action=str((safety or {}).get("action") or "refuse"),
                fallback_answer_fn=fallback_answer,
            ),
            "provider": "",
            "model": "",
            "usage": {},
            "llm_trace": {},
        }
    if answer_mode == "refusal":
        return {"answer": fallback_answer(question, evidence, "refusal"), "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    settings = load_llm_settings()
    if answer_mode == "common_knowledge":
        prompt_definition = get_prompt_definition("chat_common_knowledge")
        route_plan = settings_with_model_route_plan(
            settings,
            prompt_definition.route_key,
            default_model=settings.common_knowledge_model or settings.model,
            default_temperature=0.4,
            default_max_tokens=settings.common_knowledge_max_tokens,
        )
        if not any(candidate.configured for candidate, _decision in route_plan):
            return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        if is_low_signal_common_knowledge_question(question):
            return {"answer": low_signal_common_knowledge_answer(question), "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        prompt = prompt_definition.build_prompt()
        primary_settings = route_plan[0][0]
        inputs = {
            "settings_prompt": augment_settings_prompt(
                "\n\n".join(part for part in ((primary_settings.system_prompt or "").strip(), settings_prompt_append.strip()) if part)
            ),
            "history": dicts_to_langchain_messages(
                compact_history_messages(
                    history,
                    limit=primary_settings.common_knowledge_history_messages,
                    content_limit=primary_settings.common_knowledge_history_chars,
                )
            ),
            "question": question.strip(),
        }
        try:
            completion, route, route_attempts = await execute_with_model_route_fallback(
                route_plan,
                call=lambda candidate_settings, candidate_route: create_llm_completion(
                    settings=candidate_settings,
                    prompt=prompt,
                    inputs=inputs,
                    prompt_key=prompt_definition.key,
                    prompt_version=prompt_definition.version,
                    model=candidate_route["model"],
                    temperature=candidate_route["temperature"],
                    max_tokens=candidate_route["max_tokens"],
                ),
            )
            _log_route_fallback(prompt_definition.key, route_attempts)
            completion = _attach_route_trace(completion, route.route_key, route_attempts=route_attempts)
            return {
                "answer": ensure_common_knowledge_disclaimer(str(completion["answer"])),
                "provider": completion["provider"],
                "model": completion["model"],
                "usage": completion["usage"],
                "llm_trace": completion.get("llm_trace") or {},
            }
        except HTTPException:
            logger.warning("llm common knowledge fallback engaged")
            return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    prompt_definition = get_prompt_definition("chat_grounded_answer")
    route_plan = settings_with_model_route_plan(
        settings,
        prompt_definition.route_key,
        default_temperature=0.2,
        default_max_tokens=min(settings.default_max_tokens, 1200),
    )
    if not any(candidate.configured for candidate, _decision in route_plan):
        return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    # Token 预算感知的上下文管理
    managed_history, managed_evidence_block, _ctx_stats = manage_context_for_generation(
        question=question,
        history=history,
        evidence=evidence,
        answer_mode=answer_mode,
        system_prompt=str(route_plan[0][0].system_prompt or ""),
        default_max_tokens=settings.default_max_tokens,
        min_history_turns=2,
    )
    prompt = prompt_definition.build_prompt()
    inputs = {
        "settings_prompt": augment_settings_prompt(
            "\n\n".join(part for part in ((route_plan[0][0].system_prompt or "").strip(), settings_prompt_append.strip()) if part)
        ),
        "history": dicts_to_langchain_messages(managed_history),
        "question": question.strip(),
        "answer_mode": answer_mode,
        "evidence_block": managed_evidence_block,
    }
    try:
        completion, route, route_attempts = await execute_with_model_route_fallback(
            route_plan,
            call=lambda candidate_settings, candidate_route: _create_completion_with_optional_final_tools(
                settings=candidate_settings,
                prompt=prompt,
                inputs=inputs,
                prompt_key=prompt_definition.key,
                prompt_version=prompt_definition.version,
                model=candidate_route["model"],
                temperature=candidate_route["temperature"],
                max_tokens=candidate_route["max_tokens"],
                fallback_answer_text=fallback_answer(question, evidence, answer_mode),
            ),
        )
        _log_route_fallback(prompt_definition.key, route_attempts)
        completion = _attach_route_trace(completion, route.route_key, route_attempts=route_attempts)
        return {
            "answer": ensure_citation_markers(str(completion["answer"]), evidence),
            "provider": completion["provider"],
            "model": completion["model"],
            "usage": completion["usage"],
            "llm_trace": completion.get("llm_trace") or {},
        }
    except HTTPException:
        logger.warning("llm grounded answer fallback engaged")
        return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}


async def stream_grounded_answer(
    *,
    question: str,
    history: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    answer_mode: str,
    on_answer: Any,
    safety: dict[str, Any] | None = None,
    settings_prompt_append: str = "",
) -> dict[str, Any]:
    async def emit_answer(answer_text: str) -> None:
        callback_result = on_answer(answer_text)
        if hasattr(callback_result, "__await__"):
            await callback_result

    if bool((safety or {}).get("blocked")):
        answer = blocked_prompt_answer(
            question=question,
            evidence=evidence,
            action=str((safety or {}).get("action") or "refuse"),
            fallback_answer_fn=fallback_answer,
        )
        await emit_answer(answer)
        return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    if answer_mode == "refusal":
        answer = fallback_answer(question, evidence, "refusal")
        await emit_answer(answer)
        return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    settings = load_llm_settings()
    if answer_mode == "common_knowledge":
        prompt_definition = get_prompt_definition("chat_common_knowledge")
        route_plan = settings_with_model_route_plan(
            settings,
            prompt_definition.route_key,
            default_model=settings.common_knowledge_model or settings.model,
            default_temperature=0.4,
            default_max_tokens=settings.common_knowledge_max_tokens,
        )
        if not any(candidate.configured for candidate, _decision in route_plan):
            answer = fallback_answer(question, evidence, answer_mode)
            await emit_answer(answer)
            return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        if is_low_signal_common_knowledge_question(question):
            answer = low_signal_common_knowledge_answer(question)
            await emit_answer(answer)
            return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        prompt = prompt_definition.build_prompt()
        primary_settings = route_plan[0][0]
        inputs = {
            "settings_prompt": augment_settings_prompt(
                "\n\n".join(part for part in ((primary_settings.system_prompt or "").strip(), settings_prompt_append.strip()) if part)
            ),
            "history": dicts_to_langchain_messages(
                compact_history_messages(
                    history,
                    limit=primary_settings.common_knowledge_history_messages,
                    content_limit=primary_settings.common_knowledge_history_chars,
                )
            ),
            "question": question.strip(),
        }
        try:
            completion, route, route_attempts = await execute_with_model_route_fallback(
                route_plan,
                call=lambda candidate_settings, candidate_route: create_llm_completion_stream(
                    settings=candidate_settings,
                    prompt=prompt,
                    inputs=inputs,
                    on_text_delta=lambda _delta, answer_text: emit_answer(answer_text),
                    prompt_key=prompt_definition.key,
                    prompt_version=prompt_definition.version,
                    model=candidate_route["model"],
                    temperature=candidate_route["temperature"],
                    max_tokens=candidate_route["max_tokens"],
                ),
            )
            _log_route_fallback(prompt_definition.key, route_attempts)
            completion = _attach_route_trace(completion, route.route_key, route_attempts=route_attempts)
            finalized_answer = ensure_common_knowledge_disclaimer(str(completion["answer"]))
            if finalized_answer != str(completion["answer"]):
                await emit_answer(finalized_answer)
            return {
                "answer": finalized_answer,
                "provider": completion["provider"],
                "model": completion["model"],
                "usage": completion["usage"],
                "llm_trace": completion.get("llm_trace") or {},
            }
        except HTTPException:
            logger.warning("llm common knowledge fallback engaged")
            answer = fallback_answer(question, evidence, answer_mode)
            await emit_answer(answer)
            return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    prompt_definition = get_prompt_definition("chat_grounded_answer")
    route_plan = settings_with_model_route_plan(
        settings,
        prompt_definition.route_key,
        default_temperature=0.2,
        default_max_tokens=min(settings.default_max_tokens, 1200),
    )
    if not any(candidate.configured for candidate, _decision in route_plan):
        answer = fallback_answer(question, evidence, answer_mode)
        await emit_answer(answer)
        return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}

    # Token 预算感知的上下文管理
    managed_history, managed_evidence_block, _ctx_stats = manage_context_for_generation(
        question=question,
        history=history,
        evidence=evidence,
        answer_mode=answer_mode,
        system_prompt=str(route_plan[0][0].system_prompt or ""),
        default_max_tokens=settings.default_max_tokens,
        min_history_turns=2,
    )
    prompt = prompt_definition.build_prompt()
    inputs = {
        "settings_prompt": augment_settings_prompt(
            "\n\n".join(part for part in ((route_plan[0][0].system_prompt or "").strip(), settings_prompt_append.strip()) if part)
        ),
        "history": dicts_to_langchain_messages(managed_history),
        "question": question.strip(),
        "answer_mode": answer_mode,
        "evidence_block": managed_evidence_block,
    }
    try:
        completion, route, route_attempts = await execute_with_model_route_fallback(
            route_plan,
            call=lambda candidate_settings, candidate_route: create_llm_completion_stream(
                settings=candidate_settings,
                prompt=prompt,
                inputs=inputs,
                on_text_delta=lambda _delta, answer_text: emit_answer(answer_text),
                prompt_key=prompt_definition.key,
                prompt_version=prompt_definition.version,
                model=candidate_route["model"],
                temperature=candidate_route["temperature"],
                max_tokens=candidate_route["max_tokens"],
            ),
        )
        _log_route_fallback(prompt_definition.key, route_attempts)
        completion = _attach_route_trace(completion, route.route_key, route_attempts=route_attempts)
        finalized_answer = ensure_citation_markers(str(completion["answer"]), evidence)
        if finalized_answer != str(completion["answer"]):
            await emit_answer(finalized_answer)
        return {
            "answer": finalized_answer,
            "provider": completion["provider"],
            "model": completion["model"],
            "usage": completion["usage"],
            "llm_trace": completion.get("llm_trace") or {},
        }
    except HTTPException:
        logger.warning("llm grounded answer fallback engaged")
        answer = fallback_answer(question, evidence, answer_mode)
        await emit_answer(answer)
        return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}


__all__ = [
    "COMMON_KNOWLEDGE_DISCLAIMER",
    "chat_prompt_messages",
    "classify_evidence",
    "common_knowledge_prompt_messages",
    "compact_text",
    "contextualize_question",
    "generate_grounded_answer",
    "manage_context_for_generation",
    "resolve_token_budget",
    "stream_grounded_answer",
]
