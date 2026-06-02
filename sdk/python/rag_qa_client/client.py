"""RAG-QA Python SDK 客户端实现。

提供同步和异步两种客户端，支持:
- 标准问答（grounded）
- Agent 模式问答
- SSE 流式输出
- 知识库管理
- Agent Profile / Prompt Template 管理
- 场景模板切换
- 缓存管理
- 成本查询
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
from urllib.parse import urljoin

import httpx

from .types import (
    AgentProfile,
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    Citation,
    Document,
    KnowledgeBase,
    PromptTemplate,
    SceneTemplate,
)


class RAGQAClient:
    """同步 RAG-QA 客户端。

    用法::

        client = RAGQAClient(base_url="http://localhost:8080", api_key="xxx")
        resp = client.ask("退款流程是什么？")
        print(resp.answer)
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8080",
        api_key: str = "",
        timeout: float = 60.0,
        default_session_id: str = "",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._session_id = default_session_id or f"sdk-{id(self):x}"

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _url(self, path: str) -> str:
        return urljoin(f"{self._base}/api/v1/", path.lstrip("/"))

    # ---- 核心问答 -----------------------------------------------------------

    def ask(
        self,
        question: str,
        *,
        scope: dict[str, Any] | None = None,
        execution_mode: str = "grounded",
        focus_hint: dict[str, Any] | None = None,
        agent_profile_id: str = "",
        session_id: str = "",
        instruction_override: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """发送问答请求，返回完整响应。

        参数:
            question: 问题文本
            scope: 知识库范围 {"corpus_ids": ["kb:xxx"], "allow_common_knowledge": true}
            execution_mode: "grounded" / "agent"
            agent_profile_id: Agent Profile ID（Agent 模式时使用）
            session_id: 会话ID（不传则使用默认会话）
            instruction_override: 调用级指令覆盖 {"language": "英文"}

        返回:
            ChatResponse
        """
        sid = session_id or self._session_id
        body: dict[str, Any] = {
            "question": question,
            "scope": scope or {"mode": "all"},
            "execution_mode": execution_mode,
        }
        if focus_hint:
            body["focus_hint"] = focus_hint
        if instruction_override:
            body["instruction_override"] = instruction_override

        with httpx.Client(timeout=self._timeout) as http:
            resp = http.post(
                self._url(f"/chat/sessions/{sid}/messages"),
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)

    def ask_stream(
        self,
        question: str,
        *,
        scope: dict[str, Any] | None = None,
        execution_mode: str = "grounded",
        session_id: str = "",
    ) -> Iterator[ChatStreamChunk]:
        """流式问答（SSE），返回迭代器。"""
        sid = session_id or self._session_id
        body: dict[str, Any] = {
            "question": question,
            "scope": scope or {"mode": "all"},
            "execution_mode": execution_mode,
        }

        with httpx.Client(timeout=self._timeout) as http:
            with http.stream(
                "POST",
                self._url(f"/chat/sessions/{sid}/messages/stream"),
                headers={**self._headers, "Accept": "text/event-stream"},
                json=body,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            yield ChatStreamChunk(event="done")
                            return
                        try:
                            data = json.loads(data_str)
                            yield ChatStreamChunk(
                                event=data.get("event", "delta"),
                                content=str(data.get("content") or ""),
                            )
                        except json.JSONDecodeError:
                            yield ChatStreamChunk(event="delta", content=data_str)

    # ---- 知识库管理 -----------------------------------------------------------

    def list_knowledge_bases(self) -> list[KnowledgeBase]:
        """列出当前用户可见的知识库。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(self._url("/kb/bases"), headers=self._headers)
            resp.raise_for_status()
            items = (resp.json() or {}).get("items", [])
            return [
                KnowledgeBase(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    category=str(item.get("category") or ""),
                    document_count=int(item.get("document_count") or 0),
                    created_at=str(item.get("created_at") or ""),
                )
                for item in items
            ]

    def list_documents(self, base_id: str) -> list[Document]:
        """列出知识库下的文档。"""
        raw_id = base_id.replace("kb:", "")
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(
                self._url(f"/kb/bases/{raw_id}/documents"),
                headers=self._headers,
            )
            resp.raise_for_status()
            items = (resp.json() or {}).get("items", [])
            return [
                Document(
                    id=str(item.get("document_id") or item.get("id") or ""),
                    file_name=str(item.get("file_name") or ""),
                    title=str(item.get("title") or item.get("file_name") or ""),
                    status=str(item.get("status") or ""),
                    version_label=str(item.get("version_label") or ""),
                    version_number=int(item.get("version_number") or 0),
                    is_current_version=bool(item.get("is_current_version")),
                    corpus_id=base_id,
                    base_id=raw_id,
                    created_at=str(item.get("created_at") or ""),
                )
                for item in items
            ]

    # ---- Agent & Prompt 管理 -----------------------------------------------

    def list_agent_profiles(self) -> list[AgentProfile]:
        """列出 Agent Profile。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(self._url("/platform/agent-profiles"), headers=self._headers)
            resp.raise_for_status()
            items = (resp.json() or {}).get("items", [])
            return [
                AgentProfile(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    persona_prompt=str(item.get("persona_prompt") or ""),
                    enabled_tools=list(item.get("enabled_tools") or []),
                    default_corpus_ids=list(item.get("default_corpus_ids") or []),
                    scene_template_key=str(item.get("scene_template_key") or ""),
                )
                for item in items
            ]

    def list_prompt_templates(self) -> list[PromptTemplate]:
        """列出 Prompt 模板。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(self._url("/platform/prompt-templates"), headers=self._headers)
            resp.raise_for_status()
            items = (resp.json() or {}).get("items", [])
            return [PromptTemplate(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                content=str(item.get("content") or ""),
                visibility=str(item.get("visibility") or "personal"),
                tags=list(item.get("tags") or []),
                favorite=bool(item.get("favorite")),
            ) for item in items]

    # ---- 场景模板 -----------------------------------------------------------

    def list_scene_templates(self, *, tag: str = "") -> list[SceneTemplate]:
        """列出可用的场景模板。"""
        with httpx.Client(timeout=self._timeout) as http:
            params = {"tag": tag} if tag else {}
            resp = http.get(self._url("/platform/scene-templates"), headers=self._headers, params=params)
            resp.raise_for_status()
            items = (resp.json() or {}).get("items", [])
            return [SceneTemplate(
                key=str(item.get("key") or ""),
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                icon=str(item.get("icon") or "📋"),
                recommended_tools=list(item.get("recommended_tools") or []),
                model_routing=str(item.get("model_routing") or "grounded"),
                model_tier=str(item.get("model_tier") or "standard"),
                tags=list(item.get("tags") or []),
            ) for item in items]

    # ---- 成本 ---------------------------------------------------------------

    def get_cost_breakdown(self, *, period_days: int = 30) -> dict[str, Any]:
        """获取成本分析。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(
                self._url("/platform/cost/breakdown"),
                headers=self._headers,
                params={"period_days": period_days},
            )
            resp.raise_for_status()
            return dict(resp.json() or {})

    def get_model_health(self) -> dict[str, Any]:
        """获取模型健康状态。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(self._url("/platform/cost/model-health"), headers=self._headers)
            resp.raise_for_status()
            return dict(resp.json() or {})

    # ---- 缓存 ---------------------------------------------------------------

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计。"""
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.get(self._url("/platform/cache/stats"), headers=self._headers)
            resp.raise_for_status()
            return dict(resp.json() or {})

    def invalidate_cache(self, *, corpus_id: str = "", question: str = "") -> dict[str, Any]:
        """失效缓存。"""
        with httpx.Client(timeout=self._timeout) as http:
            body: dict[str, Any] = {}
            if corpus_id:
                body["corpus_id"] = corpus_id
            if question:
                body["question"] = question
            resp = http.post(
                self._url("/platform/cache/invalidate"),
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            return dict(resp.json() or {})

    # ---- 辅助 ---------------------------------------------------------------

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        citations = []
        for i, item in enumerate(data.get("citations") or [], start=1):
            citations.append(Citation(
                index=i,
                document_title=str(item.get("document_title") or ""),
                section_title=str(item.get("section_title") or ""),
                quote=str(item.get("quote") or ""),
                document_id=str(item.get("document_id") or ""),
                score=float((item.get("evidence_path") or {}).get("final_score", 0)),
                version_label=str(item.get("version_label") or ""),
            ))
        return ChatResponse(
            answer=str(data.get("answer") or ""),
            answer_mode=str(data.get("answer_mode") or ""),
            execution_mode=str(data.get("execution_mode") or ""),
            citations=citations,
            usage=dict(data.get("usage") or {}),
            cost=dict(data.get("cost") or {}),
            latency=dict(data.get("latency") or {}),
            message_id=str(data.get("message", {}).get("id") or ""),
            trace_id=str(data.get("trace_id") or ""),
            retrieval=dict(data.get("retrieval") or {}),
            agent_events=list((data.get("retrieval") or {}).get("agent", {}).get("events", [])),
            reflection=dict(data.get("reflection") or {}),
        )


class AsyncRAGQAClient:
    """异步 RAG-QA 客户端（适用于 asyncio 应用）。

    用法::

        client = AsyncRAGQAClient(base_url="http://localhost:8080")
        async with client:
            resp = await client.ask("退款流程是什么？")
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8080",
        api_key: str = "",
        timeout: float = 60.0,
        default_session_id: str = "",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._session_id = default_session_id or f"sdk-async-{id(self):x}"
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AsyncRAGQAClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _url(self, path: str) -> str:
        return urljoin(f"{self._base}/api/v1/", path.lstrip("/"))

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def ask(
        self,
        question: str,
        *,
        scope: dict[str, Any] | None = None,
        execution_mode: str = "grounded",
        session_id: str = "",
    ) -> ChatResponse:
        """异步发送问答请求。"""
        client = self._ensure_client()
        sid = session_id or self._session_id
        body: dict[str, Any] = {
            "question": question,
            "scope": scope or {"mode": "all"},
            "execution_mode": execution_mode,
        }
        resp = await client.post(
            self._url(f"/chat/sessions/{sid}/messages"),
            headers=self._headers,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        sync_client = RAGQAClient(base_url=self._base, api_key=self._api_key)
        return sync_client._parse_response(data)

    async def ask_stream(
        self,
        question: str,
        *,
        scope: dict[str, Any] | None = None,
        execution_mode: str = "grounded",
        session_id: str = "",
    ) -> AsyncIterator[ChatStreamChunk]:
        """异步流式问答。"""
        client = self._ensure_client()
        sid = session_id or self._session_id
        body: dict[str, Any] = {
            "question": question,
            "scope": scope or {"mode": "all"},
            "execution_mode": execution_mode,
        }
        async with client.stream(
            "POST",
            self._url(f"/chat/sessions/{sid}/messages/stream"),
            headers={**self._headers, "Accept": "text/event-stream"},
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        yield ChatStreamChunk(event="done")
                        return
                    try:
                        data = json.loads(data_str)
                        yield ChatStreamChunk(
                            event=data.get("event", "delta"),
                            content=str(data.get("content") or ""),
                        )
                    except json.JSONDecodeError:
                        yield ChatStreamChunk(event="delta", content=data_str)
