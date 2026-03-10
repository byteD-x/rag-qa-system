from __future__ import annotations

from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from shared.langchain_chat import invoke_prompt_chain, stream_prompt_chain
from shared.llm_settings import LLMSettings


async def create_llm_completion(
    *,
    settings: LLMSettings,
    prompt: ChatPromptTemplate,
    inputs: dict[str, Any],
    prompt_key: str | None = None,
    prompt_version: str | None = None,
    route_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    return await invoke_prompt_chain(
        settings=settings,
        prompt=prompt,
        inputs=inputs,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        route_key=route_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def create_llm_completion_stream(
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
    return await stream_prompt_chain(
        settings=settings,
        prompt=prompt,
        inputs=inputs,
        on_text_delta=on_text_delta,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        route_key=route_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
