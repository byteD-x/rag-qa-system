from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from .grounded_answering import build_common_knowledge_prompt, build_grounded_prompt


def _read_env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        candidate = raw.strip()
        if candidate:
            return candidate
    return default


@dataclass(frozen=True)
class PromptDefinition:
    name: str
    key: str
    version: str
    route_key: str
    builder: Callable[[], ChatPromptTemplate]

    def build_prompt(self) -> ChatPromptTemplate:
        return self.builder()


def _load_registry_overrides() -> dict[str, dict[str, str]]:
    path_value = _read_env("PROMPT_REGISTRY_PATH", default="")
    raw_value = _read_env("PROMPT_REGISTRY_JSON", default="")
    if path_value:
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    elif raw_value:
        payload = json.loads(raw_value)
    else:
        return {}
    if not isinstance(payload, dict):
        return {}
    overrides: dict[str, dict[str, str]] = {}
    for name, raw_definition in payload.items():
        if not isinstance(name, str) or not isinstance(raw_definition, dict):
            continue
        normalized: dict[str, str] = {}
        for key in ("key", "version", "route_key"):
            value = raw_definition.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip()
        if normalized:
            overrides[name.strip()] = normalized
    return overrides


def _default_registry() -> dict[str, PromptDefinition]:
    return {
        "chat_grounded_answer": PromptDefinition(
            name="chat_grounded_answer",
            key="chat_grounded_answer",
            version="2026-03-10",
            route_key="grounded",
            builder=build_grounded_prompt,
        ),
        "chat_common_knowledge": PromptDefinition(
            name="chat_common_knowledge",
            key="chat_common_knowledge",
            version="2026-03-10",
            route_key="common_knowledge",
            builder=build_common_knowledge_prompt,
        ),
        "kb_grounded_answer": PromptDefinition(
            name="kb_grounded_answer",
            key="kb_grounded_answer",
            version="2026-03-10",
            route_key="grounded",
            builder=build_grounded_prompt,
        ),
    }


def get_prompt_definition(name: str) -> PromptDefinition:
    registry = _default_registry()
    definition = registry.get(name.strip())
    if definition is None:
        raise KeyError(f"unknown prompt definition: {name}")
    override = _load_registry_overrides().get(definition.name, {})
    return PromptDefinition(
        name=definition.name,
        key=override.get("key", definition.key),
        version=override.get("version", definition.version),
        route_key=override.get("route_key", definition.route_key),
        builder=definition.builder,
    )


__all__ = ["PromptDefinition", "get_prompt_definition"]
