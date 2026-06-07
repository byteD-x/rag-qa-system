from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .llm_settings import LLMSettings
from .tracing import current_trace_id, ensure_trace_id


def build_chat_model(
    *,
    settings: LLMSettings,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    streaming: bool,
) -> ChatOpenAI:
    return ChatOpenAI(
        model_name=(model or settings.model).strip(),
        openai_api_key=settings.api_key,
        openai_api_base=settings.base_url,
        request_timeout=settings.timeout_seconds,
        temperature=settings.default_temperature if temperature is None else temperature,
        max_tokens=settings.default_max_tokens if max_tokens is None else max_tokens,
        extra_body=settings.extra_body or None,
        streaming=streaming,
        stream_usage=True,
        max_retries=0,
    )


def _usage_payload(message: AIMessage | AIMessageChunk) -> dict[str, Any]:
    usage = dict(getattr(message, "usage_metadata", {}) or {})
    if usage:
        return {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    response_metadata = dict(getattr(message, "response_metadata", {}) or {})
    token_usage = dict(response_metadata.get("token_usage") or {})
    return {
        "prompt_tokens": int(token_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(token_usage.get("completion_tokens") or 0),
        "total_tokens": int(token_usage.get("total_tokens") or 0),
    }


def _normalize_tool_calls(message: AIMessage | AIMessageChunk) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for index, raw_call in enumerate(list(getattr(message, "tool_calls", []) or []), start=1):
        if not isinstance(raw_call, dict):
            continue
        name = str(raw_call.get("name") or "").strip()
        if not name:
            continue
        args = raw_call.get("args")
        calls.append(
            {
                "id": str(raw_call.get("id") or f"call-{index}"),
                "name": name,
                "args": args if isinstance(args, dict) else {},
            }
        )
    return calls


def extract_message_text(message: AIMessage | AIMessageChunk) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
        return "\n".join(parts).strip()
    return ""


def _ensure_llm_enabled(settings: LLMSettings) -> None:
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM answer generation is disabled",
        )
    if not settings.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM answer generation is not configured",
        )


def build_llm_trace(
    *,
    settings: LLMSettings,
    prompt_key: str | None,
    prompt_version: str | None,
    model_requested: str | None,
    model_resolved: str | None,
    route_key: str | None,
    streaming: bool,
    started_at: float,
) -> dict[str, Any]:
    request_trace_id = ensure_trace_id(current_trace_id(), prefix="gateway-")
    return {
        "llm_call_id": f"llm-{uuid4().hex}",
        "request_trace_id": request_trace_id,
        "provider": settings.provider,
        "model_requested": str(model_requested or settings.model),
        "model_resolved": str(model_resolved or model_requested or settings.model),
        "route_key": str(route_key or ""),
        "prompt_key": str(prompt_key or ""),
        "prompt_version": str(prompt_version or ""),
        "streaming": streaming,
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
    }


async def invoke_prompt_chain(
    *,
    settings: LLMSettings,
    prompt: ChatPromptTemplate,
    inputs: dict[str, Any],
    tools: list[Any] | None = None,
    extra_messages: list[BaseMessage] | None = None,
    include_raw_message: bool = False,
    prompt_key: str | None = None,
    prompt_version: str | None = None,
    route_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    _ensure_llm_enabled(settings)
    started_at = time.perf_counter()
    try:
        chat_model = build_chat_model(
            settings=settings,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,
        )
        if tools:
            chat_model = chat_model.bind_tools(tools)
        if tools or extra_messages:
            messages = list(prompt.format_messages(**inputs))
            messages.extend(list(extra_messages or []))
            result = await chat_model.ainvoke(messages)
        else:
            chain = prompt | chat_model
            result = await chain.ainvoke(inputs)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM service is unavailable",
        ) from exc

    answer = extract_message_text(result)
    tool_calls = _normalize_tool_calls(result)
    if not answer and not tool_calls:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM service returned an empty answer",
        )
    response_metadata = dict(getattr(result, "response_metadata", {}) or {})
    payload = {
        "answer": answer,
        "reasoning": "",
        "model": str(response_metadata.get("model_name") or model or settings.model),
        "provider": settings.provider,
        "finish_reason": str(response_metadata.get("finish_reason") or ""),
        "usage": _usage_payload(result),
        "tool_calls": tool_calls,
        "llm_trace": build_llm_trace(
            settings=settings,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            model_requested=model,
            model_resolved=str(response_metadata.get("model_name") or model or settings.model),
            route_key=route_key,
            streaming=False,
            started_at=started_at,
        ),
    }
    if include_raw_message:
        payload["_raw_message"] = result
    return payload


async def stream_prompt_chain(
    *,
    settings: LLMSettings,
    prompt: ChatPromptTemplate,
    inputs: dict[str, Any],
    on_text_delta: Any,
    prompt_key: str | None = None,
    prompt_version: str | None = None,
    route_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    _ensure_llm_enabled(settings)
    started_at = time.perf_counter()
    answer_parts: list[str] = []
    usage: dict[str, Any] = {}
    finish_reason = ""
    resolved_model = model or settings.model
    try:
        chat_model = build_chat_model(
            settings=settings,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
        chain = prompt | chat_model
        async for chunk in chain.astream(inputs):
            delta = extract_message_text(chunk)
            if delta:
                answer_parts.append(delta)
                callback_result = on_text_delta(delta, "".join(answer_parts))
                if hasattr(callback_result, "__await__"):
                    await callback_result
            usage = _usage_payload(chunk) or usage
            response_metadata = dict(getattr(chunk, "response_metadata", {}) or {})
            finish_reason = str(response_metadata.get("finish_reason") or finish_reason)
            resolved_model = str(response_metadata.get("model_name") or resolved_model)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM service is unavailable",
        ) from exc

    answer = "".join(answer_parts).strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM service returned an empty answer",
        )
    return {
        "answer": answer,
        "reasoning": "",
        "model": resolved_model,
        "provider": settings.provider,
        "finish_reason": finish_reason,
        "usage": usage,
        "llm_trace": build_llm_trace(
            settings=settings,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            model_requested=model,
            model_resolved=resolved_model,
            route_key=route_key,
            streaming=True,
            started_at=started_at,
        ),
    }
