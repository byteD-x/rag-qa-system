from __future__ import annotations

from typing import Any

from fastapi import HTTPException

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
from shared.model_routing import settings_with_model_route
from shared.prompt_registry import get_prompt_definition
from shared.prompt_safety import augment_settings_prompt, blocked_prompt_answer

from .ai_client import load_llm_settings
from .gateway_config import SHORT_QUESTION_RE
from .gateway_runtime import logger
from .langchain_client import create_llm_completion, create_llm_completion_stream


def _attach_route_trace(completion: dict[str, Any], route_key: str) -> dict[str, Any]:
    llm_trace = dict(completion.get("llm_trace") or {})
    if route_key:
        llm_trace["route_key"] = route_key
    payload = dict(completion)
    payload["llm_trace"] = llm_trace
    return payload


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


async def generate_grounded_answer(
    *,
    question: str,
    history: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    answer_mode: str,
    safety: dict[str, Any] | None = None,
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
        routed_settings, route = settings_with_model_route(
            settings,
            prompt_definition.route_key,
            default_model=settings.common_knowledge_model or settings.model,
            default_temperature=0.4,
            default_max_tokens=settings.common_knowledge_max_tokens,
        )
        if not routed_settings.configured:
            return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        if is_low_signal_common_knowledge_question(question):
            return {"answer": low_signal_common_knowledge_answer(question), "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        prompt = prompt_definition.build_prompt()
        inputs = {
            "settings_prompt": augment_settings_prompt(routed_settings.system_prompt or ""),
            "history": dicts_to_langchain_messages(
                compact_history_messages(
                    history,
                    limit=routed_settings.common_knowledge_history_messages,
                    content_limit=routed_settings.common_knowledge_history_chars,
                )
            ),
            "question": question.strip(),
        }
        try:
            completion = await create_llm_completion(
                settings=routed_settings,
                prompt=prompt,
                inputs=inputs,
                prompt_key=prompt_definition.key,
                prompt_version=prompt_definition.version,
                model=route["model"],
                temperature=route["temperature"],
                max_tokens=route["max_tokens"],
            )
            completion = _attach_route_trace(completion, route.route_key)
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
    routed_settings, route = settings_with_model_route(
        settings,
        prompt_definition.route_key,
        default_temperature=0.2,
        default_max_tokens=min(settings.default_max_tokens, 1200),
    )
    if not routed_settings.configured:
        return {"answer": fallback_answer(question, evidence, answer_mode), "provider": "", "model": "", "usage": {}, "llm_trace": {}}
    prompt = prompt_definition.build_prompt()
    inputs = {
        "settings_prompt": augment_settings_prompt(routed_settings.system_prompt or ""),
        "history": dicts_to_langchain_messages(history[-8:]),
        "question": question.strip(),
        "answer_mode": answer_mode,
        "evidence_block": evidence_prompt_lines(evidence),
    }
    try:
        completion = await create_llm_completion(
            settings=routed_settings,
            prompt=prompt,
            inputs=inputs,
            prompt_key=prompt_definition.key,
            prompt_version=prompt_definition.version,
            model=route["model"],
            temperature=route["temperature"],
            max_tokens=route["max_tokens"],
        )
        completion = _attach_route_trace(completion, route.route_key)
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
        routed_settings, route = settings_with_model_route(
            settings,
            prompt_definition.route_key,
            default_model=settings.common_knowledge_model or settings.model,
            default_temperature=0.4,
            default_max_tokens=settings.common_knowledge_max_tokens,
        )
        if not routed_settings.configured:
            answer = fallback_answer(question, evidence, answer_mode)
            await emit_answer(answer)
            return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        if is_low_signal_common_knowledge_question(question):
            answer = low_signal_common_knowledge_answer(question)
            await emit_answer(answer)
            return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}
        prompt = prompt_definition.build_prompt()
        inputs = {
            "settings_prompt": augment_settings_prompt(routed_settings.system_prompt or ""),
            "history": dicts_to_langchain_messages(
                compact_history_messages(
                    history,
                    limit=routed_settings.common_knowledge_history_messages,
                    content_limit=routed_settings.common_knowledge_history_chars,
                )
            ),
            "question": question.strip(),
        }
        try:
            completion = await create_llm_completion_stream(
                settings=routed_settings,
                prompt=prompt,
                inputs=inputs,
                on_text_delta=lambda _delta, answer_text: emit_answer(answer_text),
                prompt_key=prompt_definition.key,
                prompt_version=prompt_definition.version,
                model=route["model"],
                temperature=route["temperature"],
                max_tokens=route["max_tokens"],
            )
            completion = _attach_route_trace(completion, route.route_key)
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
    routed_settings, route = settings_with_model_route(
        settings,
        prompt_definition.route_key,
        default_temperature=0.2,
        default_max_tokens=min(settings.default_max_tokens, 1200),
    )
    if not routed_settings.configured:
        answer = fallback_answer(question, evidence, answer_mode)
        await emit_answer(answer)
        return {"answer": answer, "provider": "", "model": "", "usage": {}, "llm_trace": {}}
    prompt = prompt_definition.build_prompt()
    inputs = {
        "settings_prompt": augment_settings_prompt(routed_settings.system_prompt or ""),
        "history": dicts_to_langchain_messages(history[-8:]),
        "question": question.strip(),
        "answer_mode": answer_mode,
        "evidence_block": evidence_prompt_lines(evidence),
    }
    try:
        completion = await create_llm_completion_stream(
            settings=routed_settings,
            prompt=prompt,
            inputs=inputs,
            on_text_delta=lambda _delta, answer_text: emit_answer(answer_text),
            prompt_key=prompt_definition.key,
            prompt_version=prompt_definition.version,
            model=route["model"],
            temperature=route["temperature"],
            max_tokens=route["max_tokens"],
        )
        completion = _attach_route_trace(completion, route.route_key)
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
    "stream_grounded_answer",
]
