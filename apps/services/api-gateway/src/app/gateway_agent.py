from __future__ import annotations

import ast
import json
import time
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from shared.auth import CurrentUser
from shared.grounded_answering import compact_text
from shared.langchain_chat import build_chat_model, extract_message_text
from shared.model_routing import settings_with_model_route

from .ai_client import load_llm_settings
from .gateway_answering import contextualize_question
from .gateway_runtime import logger, runtime_settings
from .gateway_transport import downstream_headers, parse_corpus_id, request_service_json


AGENT_MAX_TOOL_CALLS = 3
AGENT_MAX_EVIDENCE = 8
AGENT_MAX_DOCUMENTS = 20


def _agent_runtime_contract(tools: list[StructuredTool]) -> dict[str, Any]:
    return {
        "tool_budget": {
            "max_tool_calls": AGENT_MAX_TOOL_CALLS,
            "max_evidence": AGENT_MAX_EVIDENCE,
            "max_documents": AGENT_MAX_DOCUMENTS,
        },
        "allowed_tools": [tool.name for tool in tools],
    }


async def run_agent_search(
    *,
    user: CurrentUser,
    scope_snapshot: dict[str, Any],
    question: str,
    history: list[dict[str, Any]],
    focus_hint: dict[str, Any] | None = None,
    agent_profile: dict[str, Any] | None = None,
    prompt_template: dict[str, Any] | None = None,
    retrieve_scope_evidence_fn: Any,
    fetch_corpus_documents_fn: Any,
    kb_service_url: str,
    request_service_json_fn: Any = request_service_json,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    contextualized_question = contextualize_question(question, history)
    settings = load_llm_settings()
    settings, _route = settings_with_model_route(
        settings,
        "agent",
        default_temperature=0.1,
        default_max_tokens=min(settings.default_max_tokens, 800),
    )
    if not settings.configured:
        return await retrieve_scope_evidence_fn(
            user=user,
            scope_snapshot=scope_snapshot,
            question=question,
            history=history,
            focus_hint=focus_hint,
        )

    tool_events: list[dict[str, Any]] = []
    agent_events: list[dict[str, Any]] = []
    evidence_by_unit: dict[str, dict[str, Any]] = {}
    services: list[dict[str, Any]] = []
    total_retrieval_ms = 0.0
    enabled_tools = set(list((agent_profile or {}).get("enabled_tools") or [])) or {"search_scope", "list_scope_documents", "search_corpus"}

    async def search_scope_tool(search_question: str, limit: int = AGENT_MAX_EVIDENCE) -> dict[str, Any]:
        nonlocal total_retrieval_ms
        tool_started = time.perf_counter()
        items, _, retrieval_meta = await retrieve_scope_evidence_fn(
            user=user,
            scope_snapshot=scope_snapshot,
            question=search_question,
            history=history,
            focus_hint=focus_hint,
        )
        total_retrieval_ms += round((time.perf_counter() - tool_started) * 1000.0, 3)
        _collect_evidence(evidence_by_unit, items, limit=limit)
        services.extend(list(retrieval_meta.get("services") or []))
        tool_events.append(
            {
                "tool": "search_scope",
                "question": search_question,
                "result_count": len(items),
                "retrieval": retrieval_meta,
            }
        )
        agent_events.append(
            {
                "type": "tool_result",
                "tool": "search_scope",
                "question": search_question,
                "result_count": len(items),
                "selected_candidates": int((retrieval_meta.get("aggregate") or {}).get("selected_candidates", len(items))),
            }
        )
        return {
            "result_count": len(items),
            "summary": _summarize_evidence(items),
            "selected_candidates": int((retrieval_meta.get("aggregate") or {}).get("selected_candidates", len(items))),
        }

    async def list_scope_documents_tool(corpus_id: str = "") -> dict[str, Any]:
        timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
        selected_corpora = [corpus_id] if corpus_id else list(scope_snapshot.get("corpus_ids") or [])
        documents: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=timeout) as client:
            for candidate in selected_corpora:
                if candidate and candidate not in scope_snapshot.get("corpus_ids", []):
                    continue
                docs = await fetch_corpus_documents_fn(client, user=user, corpus_id=candidate)
                documents.extend(docs[:AGENT_MAX_DOCUMENTS])
        tool_events.append(
            {
                "tool": "list_scope_documents",
                "corpus_id": corpus_id,
                "result_count": len(documents),
            }
        )
        agent_events.append(
            {
                "type": "tool_result",
                "tool": "list_scope_documents",
                "corpus_id": corpus_id,
                "result_count": len(documents),
            }
        )
        rendered = [
            {
                "corpus_id": str(item.get("corpus_id") or ""),
                "document_id": str(item.get("document_id") or ""),
                "title": str(item.get("title") or item.get("file_name") or ""),
                "query_ready": bool(item.get("query_ready")),
            }
            for item in documents[:AGENT_MAX_DOCUMENTS]
        ]
        return {"documents": rendered}

    async def search_corpus_tool(
        corpus_id: str,
        search_question: str,
        document_ids: list[str] | None = None,
        limit: int = AGENT_MAX_EVIDENCE,
    ) -> dict[str, Any]:
        nonlocal total_retrieval_ms
        if corpus_id not in scope_snapshot.get("corpus_ids", []):
            return {"result_count": 0, "summary": "corpus_id is outside the current scope"}
        _, raw_id = parse_corpus_id(corpus_id)
        timeout = httpx.Timeout(runtime_settings.request_timeout_seconds)
        headers = downstream_headers(user)
        tool_started = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await request_service_json_fn(
                client,
                "POST",
                f"{kb_service_url}/api/v1/kb/retrieve",
                headers=headers,
                json_body={
                    "base_id": raw_id,
                    "question": search_question,
                    "document_ids": list(document_ids or []),
                    "limit": max(1, min(limit, AGENT_MAX_EVIDENCE)),
                },
            )
        total_retrieval_ms += round((time.perf_counter() - tool_started) * 1000.0, 3)
        items = list(payload.get("items") or [])
        _collect_evidence(evidence_by_unit, items, limit=limit)
        services.append(
            {
                "corpus_id": corpus_id,
                "trace_id": str(payload.get("trace_id") or ""),
                "status": "ok",
                "retrieval": dict(payload.get("retrieval") or {}),
            }
        )
        tool_events.append(
            {
                "tool": "search_corpus",
                "corpus_id": corpus_id,
                "question": search_question,
                "result_count": len(items),
                "retrieval": dict(payload.get("retrieval") or {}),
            }
        )
        agent_events.append(
            {
                "type": "tool_result",
                "tool": "search_corpus",
                "corpus_id": corpus_id,
                "question": search_question,
                "result_count": len(items),
                "selected_candidates": int((payload.get("retrieval") or {}).get("selected_candidates", len(items))),
            }
        )
        return {
            "result_count": len(items),
            "summary": _summarize_evidence(items),
            "selected_candidates": int((payload.get("retrieval") or {}).get("selected_candidates", len(items))),
        }

    def calculator_tool(expression: str) -> dict[str, Any]:
        cleaned = str(expression or "").strip()
        if not cleaned:
            return {"expression": "", "result": "", "error": "expression is required"}

        def _eval(node: ast.AST) -> float:
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = _eval(node.operand)
                return value if isinstance(node.op, ast.UAdd) else -value
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
                left = _eval(node.left)
                right = _eval(node.right)
                return {
                    ast.Add: left + right,
                    ast.Sub: left - right,
                    ast.Mult: left * right,
                    ast.Div: left / right,
                    ast.Mod: left % right,
                    ast.Pow: left**right,
                }[type(node.op)]
            raise ValueError("unsupported expression")

        try:
            result = _eval(ast.parse(cleaned, mode="eval"))
            rendered = int(result) if float(result).is_integer() else round(float(result), 6)
            tool_events.append({"tool": "calculator", "expression": cleaned, "result": rendered})
            agent_events.append({"type": "tool_result", "tool": "calculator", "expression": cleaned, "result": rendered})
            return {"expression": cleaned, "result": rendered}
        except Exception as exc:
            tool_events.append({"tool": "calculator", "expression": cleaned, "error": exc.__class__.__name__})
            agent_events.append({"type": "tool_result", "tool": "calculator", "expression": cleaned, "error": str(exc)})
            return {"expression": cleaned, "error": "calculation_failed"}

    tools = []
    if "search_scope" in enabled_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=search_scope_tool,
                name="search_scope",
                description="Search across all corpora currently visible in the user's scope and return grounded evidence.",
            )
        )
    if "list_scope_documents" in enabled_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=list_scope_documents_tool,
                name="list_scope_documents",
                description="List queryable documents in the current scope, optionally filtered by one corpus_id.",
            )
        )
    if "search_corpus" in enabled_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=search_corpus_tool,
                name="search_corpus",
                description="Search one corpus in the current scope, optionally restricted to a list of document_ids.",
            )
        )
    if "calculator" in enabled_tools:
        tools.append(
            StructuredTool.from_function(
                func=calculator_tool,
                name="calculator",
                description="Evaluate a basic arithmetic expression when numerical computation is needed.",
            )
        )
    from .business_tools import extend_with_enabled_business_tools

    extend_with_enabled_business_tools(tools, enabled_tools)
    agent_contract = _agent_runtime_contract(tools)
    tools_by_name = {tool.name: tool for tool in tools}
    try:
        chat_model = build_chat_model(
            settings=settings,
            model=settings.model,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
            streaming=False,
        ).bind_tools(tools)
        messages: list[Any] = [
            SystemMessage(
                content=(
                    "You are a retrieval agent for a grounded RAG system. "
                    "Use tools to gather evidence before answering. "
                    "Stay strictly inside the user's current scope. "
                    "Prefer search_scope first, then narrow with list_scope_documents or search_corpus if needed. "
                    "Stop after enough evidence is found. Do not exceed 3 rounds of tool calls."
                    + (
                        f"\n\nCustom prompt template:\n{str((prompt_template or {}).get('content') or '').strip()}"
                        if str((prompt_template or {}).get("content") or "").strip()
                        else ""
                    )
                    + (
                        f"\n\nPersona:\n{str((agent_profile or {}).get('persona_prompt') or '').strip()}"
                        if str((agent_profile or {}).get("persona_prompt") or "").strip()
                        else ""
                    )
                )
            ),
            HumanMessage(content=f"User question:\n{contextualized_question}"),
        ]
        agent_events.append(
            {
                "type": "agent_started",
                "question": question.strip(),
                "contextualized_question": contextualized_question,
                "scope_corpus_count": len(list(scope_snapshot.get("corpus_ids") or [])),
            }
        )

        for round_index in range(AGENT_MAX_TOOL_CALLS):
            response = await chat_model.ainvoke(messages)
            messages.append(response)
            tool_calls = list(getattr(response, "tool_calls", []) or [])
            agent_events.append(
                {
                    "type": "assistant_turn",
                    "round": round_index + 1,
                    "tool_call_count": len(tool_calls),
                    "message_preview": compact_text(extract_message_text(response), 160),
                }
            )
            if not tool_calls:
                break
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("name") or "")
                tool = tools_by_name.get(tool_name)
                if tool is None:
                    continue
                tool_args = dict(tool_call.get("args") or {})
                agent_events.append(
                    {
                        "type": "tool_request",
                        "round": round_index + 1,
                        "tool": tool_name,
                        "args": tool_args,
                    }
                )
                result = await tool.ainvoke(tool_args)
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=str(tool_call.get("id") or ""),
                        name=tool_name,
                    )
                )

        final_ai_text = ""
        if messages and isinstance(messages[-1], AIMessage):
            final_ai_text = extract_message_text(messages[-1])
        if not evidence_by_unit:
            logger.info("agent mode completed without evidence final_message=%s", compact_text(final_ai_text, 120))

        evidence = _ordered_evidence(evidence_by_unit, limit=AGENT_MAX_EVIDENCE)
        retrieval_meta = {
            "services": services,
            "aggregate": {
                "empty_scope": False,
                "service_count": len(services),
                "successful_service_count": sum(1 for item in services if item.get("status") == "ok"),
                "failed_service_count": sum(1 for item in services if item.get("status") == "failed"),
                "partial_failure": any(item.get("status") == "failed" for item in services),
                "selected_candidates": len(evidence),
                "original_query": question.strip(),
                "contextualized_query": contextualized_question,
                "retrieval_ms": round(total_retrieval_ms, 3),
                "tool_call_count": len(tool_events),
                "tool_calls_used": len(tool_events),
                "tool_budget": AGENT_MAX_TOOL_CALLS,
                "execution_mode": "agent",
            },
            "agent": {
                **agent_contract,
                "events": agent_events,
                "tool_calls": tool_events,
                "tool_calls_used": len(tool_events),
                "final_message": final_ai_text,
            },
        }
        return evidence, contextualized_question, retrieval_meta
    except Exception as exc:
        logger.warning("agent mode degraded to grounded retrieval because tool-calling failed", exc_info=True)
        fallback_evidence, fallback_question, fallback_meta = await retrieve_scope_evidence_fn(
            user=user,
            scope_snapshot=scope_snapshot,
            question=question,
            history=history,
            focus_hint=focus_hint,
        )
        fallback_meta = dict(fallback_meta or {})
        aggregate = dict(fallback_meta.get("aggregate") or {})
        aggregate["execution_mode"] = "agent"
        aggregate["agent_fallback"] = True
        aggregate["agent_fallback_reason"] = exc.__class__.__name__
        aggregate["tool_budget"] = AGENT_MAX_TOOL_CALLS
        aggregate["tool_calls_used"] = len(tool_events)
        fallback_meta["aggregate"] = aggregate
        fallback_meta["agent"] = {
            **agent_contract,
            "events": agent_events,
            "tool_calls": tool_events,
            "tool_calls_used": len(tool_events),
            "final_message": "",
            "fallback": True,
            "fallback_reason": exc.__class__.__name__,
        }
        return fallback_evidence, fallback_question, fallback_meta


def _collect_evidence(
    evidence_by_unit: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    limit: int,
) -> None:
    for item in items[: max(limit, AGENT_MAX_EVIDENCE)]:
        unit_id = str(item.get("unit_id") or "")
        if not unit_id:
            continue
        existing = evidence_by_unit.get(unit_id)
        if existing is None:
            evidence_by_unit[unit_id] = item
            continue
        existing_score = float(((existing.get("evidence_path") or {}).get("final_score") or 0.0))
        next_score = float(((item.get("evidence_path") or {}).get("final_score") or 0.0))
        if next_score > existing_score:
            evidence_by_unit[unit_id] = item


def _ordered_evidence(evidence_by_unit: dict[str, dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    ordered = sorted(
        evidence_by_unit.values(),
        key=lambda item: float(((item.get("evidence_path") or {}).get("final_score") or 0.0)),
        reverse=True,
    )
    limited = ordered[: max(limit, 1)]
    for index, item in enumerate(limited, start=1):
        evidence_path = dict(item.get("evidence_path") or {})
        evidence_path["final_rank"] = index
        item["evidence_path"] = evidence_path
    return limited


def _summarize_evidence(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No evidence found."
    lines: list[str] = []
    for index, item in enumerate(items[:3], start=1):
        lines.append(
            f"[{index}] {item.get('document_title') or ''} / {item.get('section_title') or ''}: "
            f"{compact_text(str(item.get('quote') or item.get('raw_text') or ''), 120)}"
        )
    return "\n".join(lines)


# ============================================================================
# 增强 Agent：集成工具注册中心 + 任务拆解 + 反思闭环
# ============================================================================


async def run_enhanced_agent(
    *,
    user: CurrentUser,
    scope_snapshot: dict[str, Any],
    question: str,
    history: list[dict[str, Any]],
    focus_hint: dict[str, Any] | None = None,
    agent_profile: dict[str, Any] | None = None,
    prompt_template: dict[str, Any] | None = None,
    retrieve_scope_evidence_fn: Any,
    fetch_corpus_documents_fn: Any,
    kb_service_url: str,
    request_service_json_fn: Any = request_service_json,
    enable_decomposition: bool = True,
    enable_reflection: bool = True,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """增强版 Agent 执行 —— 在基础 Agent 之上叠加任务拆解和反思能力。

    与 run_agent_search 的差异：
    1. 工具通过 tool_registry 管理，支持动态注册/发现
    2. 复杂问题自动触发任务拆解 → 并行执行子任务
    3. 生成回答后执行自检（完整性/准确性/引用准确性）
    4. 工具调用失败时自动分析根因并尝试恢复
    5. 成功策略记录到策略记忆，下次优先复用

    参数:
        enable_decomposition: 是否启用任务拆解
        enable_reflection: 是否启用反思自检
    """
    from .agent_reflection import AgentReflector
    from .task_decomposer import TaskDecomposer
    from .tool_registry import tool_registry

    settings = load_llm_settings()
    settings, _route = settings_with_model_route(
        settings,
        "agent",
        default_temperature=0.1,
        default_max_tokens=min(settings.default_max_tokens, 800),
    )
    if not settings.configured:
        return await retrieve_scope_evidence_fn(
            user=user,
            scope_snapshot=scope_snapshot,
            question=question,
            history=history,
            focus_hint=focus_hint,
        )

    contextualized_question = contextualize_question(question, history)
    decomposer = TaskDecomposer(
        build_chat_model_fn=build_chat_model,
        settings=settings,
        complexity_threshold=3,
    )
    reflector = AgentReflector(
        build_chat_model_fn=build_chat_model,
        settings=settings,
        self_check_threshold=0.6,
    )

    all_evidence: list[dict[str, Any]] = []
    all_tool_events: list[dict[str, Any]] = []
    all_agent_events: list[dict[str, Any]] = []
    composite_meta: dict[str, Any] = {}

    # ---- Step 1: 任务拆解 ----
    decomposition_result = None
    if enable_decomposition:
        try:
            decomposition_result = await decomposer.decompose(
                question,
                context={
                    "corpus_ids": scope_snapshot.get("corpus_ids", []),
                    "execution_mode": "agent",
                },
                history=history,
            )
            logger.info(
                "enhanced_agent_decomposed complexity=%d requires=%s sub_tasks=%d",
                decomposition_result.complexity_score,
                decomposition_result.requires_decomposition,
                len(decomposition_result.sub_tasks),
            )
        except Exception as exc:
            logger.warning("enhanced_agent_decompose_failed err=%s", exc)

    # ---- Step 2: 执行 ----
    if decomposition_result and decomposition_result.requires_decomposition and decomposition_result.sub_tasks:
        # 并行执行拆解后的子任务组
        enabled_tools = set(list((agent_profile or {}).get("enabled_tools") or [])) or {
            "search_scope", "list_scope_documents", "search_corpus",
        }
        sub_results: dict[str, dict[str, Any]] = {}

        for group_idx, task_ids in enumerate(decomposition_result.execution_order):
            # 当前并行组中的子任务并发执行
            group_tasks = []
            for tid in task_ids:
                sub = next((t for t in decomposition_result.sub_tasks if t.id == tid), None)
                if sub is None:
                    continue
                group_tasks.append(sub)

            async def _execute_sub_task(sub) -> dict[str, Any]:
                try:
                    sub_evidence, _, sub_meta = await run_agent_search(
                        user=user,
                        scope_snapshot=scope_snapshot,
                        question=sub.question,
                        history=history,
                        focus_hint=focus_hint,
                        agent_profile=agent_profile,
                        prompt_template=prompt_template,
                        retrieve_scope_evidence_fn=retrieve_scope_evidence_fn,
                        fetch_corpus_documents_fn=fetch_corpus_documents_fn,
                        kb_service_url=kb_service_url,
                        request_service_json_fn=request_service_json_fn,
                    )
                    return {
                        "task_id": sub.id,
                        "status": "completed",
                        "evidence": sub_evidence,
                        "meta": sub_meta,
                    }
                except Exception as exc:
                    logger.warning("sub_task_failed task_id=%s err=%s", sub.id, exc)
                    return {"task_id": sub.id, "status": "failed", "error": str(exc), "evidence": [], "meta": {}}

            import asyncio

            batch = await asyncio.gather(*[_execute_sub_task(t) for t in group_tasks])
            for result in batch:
                if result:
                    sub_results[result["task_id"]] = result
                    all_evidence.extend(result.get("evidence") or [])
                    agent_events_from_sub = list((result.get("meta") or {}).get("agent", {}).get("events") or [])
                    all_agent_events.extend(agent_events_from_sub)
                    tool_events_from_sub = list((result.get("meta") or {}).get("agent", {}).get("tool_calls") or [])
                    all_tool_events.extend(tool_events_from_sub)

        composite_meta = {
            "execution_mode": "enhanced_agent",
            "decomposition": {
                "complexity_score": decomposition_result.complexity_score,
                "requires_decomposition": True,
                "sub_tasks": [
                    {
                        "id": t.id,
                        "description": t.description,
                        "category": t.category,
                        "depends_on": t.depends_on,
                        "status": sub_results.get(t.id, {}).get("status", "pending"),
                    }
                    for t in decomposition_result.sub_tasks
                ],
                "execution_order": decomposition_result.execution_order,
                "reasoning": decomposition_result.reasoning,
            },
        }
    else:
        # 标准 Agent 路径（保持向后兼容）
        evidence, _, retrieval_meta = await run_agent_search(
            user=user,
            scope_snapshot=scope_snapshot,
            question=question,
            history=history,
            focus_hint=focus_hint,
            agent_profile=agent_profile,
            prompt_template=prompt_template,
            retrieve_scope_evidence_fn=retrieve_scope_evidence_fn,
            fetch_corpus_documents_fn=fetch_corpus_documents_fn,
            kb_service_url=kb_service_url,
            request_service_json_fn=request_service_json_fn,
        )
        all_evidence = evidence
        all_agent_events = list((retrieval_meta.get("agent") or {}).get("events") or [])
        all_tool_events = list((retrieval_meta.get("agent") or {}).get("tool_calls") or [])
        composite_meta = dict(retrieval_meta or {})
        composite_meta["execution_mode"] = "enhanced_agent"
        composite_meta["decomposition"] = {
            "complexity_score": decomposition_result.complexity_score if decomposition_result else 1,
            "requires_decomposition": False,
        }

    # ---- Step 3: 去重证据 ----
    evidence_by_unit: dict[str, dict[str, Any]] = {}
    for item in all_evidence:
        unit_id = str(item.get("unit_id") or "")
        if not unit_id:
            continue
        existing = evidence_by_unit.get(unit_id)
        if existing is None:
            evidence_by_unit[unit_id] = item
        else:
            existing_score = float(((existing.get("evidence_path") or {}).get("final_score") or 0.0))
            next_score = float(((item.get("evidence_path") or {}).get("final_score") or 0.0))
            if next_score > existing_score:
                evidence_by_unit[unit_id] = item
    deduped_evidence = _ordered_evidence(evidence_by_unit, limit=AGENT_MAX_EVIDENCE)

    # ---- Step 4: 策略记忆 ----
    if decomposition_result and decomposition_result.requires_decomposition:
        scenario_key = f"decomposed_{decomposition_result.complexity_score}"
        reflector.record_strategy(
            scenario_key=scenario_key,
            approach=f"拆解为{len(decomposition_result.sub_tasks)}个子任务",
            tool_sequence=list({e.get("tool", "") for e in all_tool_events if e.get("tool")}),
            success=len(deduped_evidence) > 0,
        )

    composite_meta["agent"] = {
        "events": all_agent_events,
        "tool_calls": all_tool_events,
        "tool_calls_used": len(all_tool_events),
        "enhanced": True,
    }

    return deduped_evidence, contextualized_question, composite_meta


async def reflect_on_answer(
    answer: str,
    evidence: list[dict[str, Any]],
    question: str,
    *,
    settings: Any | None = None,
) -> dict[str, Any]:
    """对生成的回答进行反思自检（便捷函数）。

    返回:
        包含自检结果的 dict，可直接合并到 workflow_state 中。
    """
    from .agent_reflection import AgentReflector

    if settings is None:
        settings = load_llm_settings()
    reflector = AgentReflector(build_chat_model_fn=build_chat_model, settings=settings)
    check = await reflector.self_check(answer=answer, evidence=evidence, question=question)
    return {
        "reflection_passed": check.passed,
        "reflection_confidence": check.confidence,
        "reflection_completeness": check.completeness_score,
        "reflection_accuracy": check.accuracy_score,
        "reflection_citation": check.citation_score,
        "reflection_issues": check.issues,
        "reflection_suggestions": check.suggestions,
        "reflection_needs_retry": check.needs_retry,
    }
