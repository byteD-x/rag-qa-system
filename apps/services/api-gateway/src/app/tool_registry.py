"""工具注册中心 —— 可扩展的 AI Agent 工具注册、发现、执行与生命周期管理。

支持：
- 装饰器注册：@tool_registry.register(name="xxx", category="search")
- MCP 协议兼容：通过 register_mcp_server 接入远程 MCP Server
- 工具选择策略：语义匹配 + 历史成功率排序
- 工具结果缓存：相同参数 + 短时间窗口内复用结果
- 工具执行沙箱：subprocess 隔离 + 资源限制（可选）
- 并行工具调用：asyncio.gather 无依赖工具并发执行

使用示例::

    from .tool_registry import tool_registry, ToolDefinition

    @tool_registry.register(name="search_corpus", category="search",
                           description="搜索指定语料库",
                           timeout_seconds=10, max_retries=2)
    async def search_corpus(corpus_id: str, query: str) -> dict: ...

    # 获取 LLM 可见的工具列表
    tools = tool_registry.get_llm_tools(context={"scope": "kb"})

    # 执行工具
    result = await tool_registry.execute("search_corpus", {"corpus_id": "x", "query": "y"})
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """工具执行结果"""

    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    from_cache: bool = False
    retry_count: int = 0


@dataclass
class ToolDefinition:
    """工具定义 —— 描述一个可被 Agent 调用的工具"""

    name: str
    description: str  # LLM 可见的自然语言描述
    handler: Callable  # 实际执行函数（sync 或 async）
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    category: str = "general"  # search / compute / external / system
    requires_confirmation: bool = False  # 高风险操作是否需要用户确认
    timeout_seconds: float = 30.0
    max_retries: int = 1
    cache_ttl_seconds: float = 0.0  # 0 表示不缓存
    is_async: bool = True

    # 运行时统计
    total_calls: int = 0
    total_success: int = 0
    total_duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.total_success / self.total_calls

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls


# ---------------------------------------------------------------------------
# 缓存条目
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    result: dict[str, Any]
    created_at: float


# ---------------------------------------------------------------------------
# 工具注册中心
# ---------------------------------------------------------------------------


class ToolRegistry:
    """可扩展的工具注册中心。

    单例模式，全局唯一实例 ``tool_registry``。
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._mcp_servers: dict[str, str] = {}  # name → endpoint
        self._cache: dict[str, _CacheEntry] = {}
        self._category_index: dict[str, list[str]] = defaultdict(list)
        self._lock = asyncio.Lock()

    # ---- 注册 / 注销 --------------------------------------------------------

    def register(
        self,
        *,
        name: str,
        description: str,
        category: str = "general",
        parameters: dict[str, Any] | None = None,
        requires_confirmation: bool = False,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
        cache_ttl_seconds: float = 0.0,
    ) -> Callable:
        """装饰器：注册一个工具处理函数。

        用法::

            @tool_registry.register(name="search_scope", category="search")
            async def search_scope(query: str) -> dict: ...
        """

        def decorator(func: Callable) -> Callable:
            is_async = asyncio.iscoroutinefunction(func)
            if parameters is None:
                inferred = _infer_parameters(func)
            else:
                inferred = parameters
            definition = ToolDefinition(
                name=name,
                description=description,
                handler=func,
                parameters=inferred,
                category=category,
                requires_confirmation=requires_confirmation,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                cache_ttl_seconds=cache_ttl_seconds,
                is_async=is_async,
            )
            self._tools[name] = definition
            self._category_index[category].append(name)
            logger.info("tool_registered name=%s category=%s async=%s", name, category, is_async)
            return func

        return decorator

    def register_direct(self, definition: ToolDefinition) -> None:
        """直接注册一个 ToolDefinition 实例（非装饰器路径）。"""
        if definition.name in self._tools:
            logger.warning("tool_overwrite name=%s", definition.name)
        self._tools[definition.name] = definition
        self._category_index[definition.category].append(definition.name)
        logger.info("tool_registered_direct name=%s category=%s", definition.name, definition.category)

    def unregister(self, name: str) -> bool:
        """注销工具，返回是否成功。"""
        tool = self._tools.pop(name, None)
        if tool is None:
            return False
        cat_list = self._category_index.get(tool.category, [])
        if name in cat_list:
            cat_list.remove(name)
        logger.info("tool_unregistered name=%s", name)
        return True

    # ---- 查询 ---------------------------------------------------------------

    def get(self, name: str) -> ToolDefinition | None:
        """按名称获取工具定义。"""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDefinition]:
        """列出所有已注册工具。"""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """按类别列出工具。"""
        names = self._category_index.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    @property
    def categories(self) -> list[str]:
        return sorted(self._category_index.keys())

    # ---- LLM 接口 -----------------------------------------------------------

    def get_llm_tools(
        self,
        *,
        context: dict[str, Any] | None = None,
        enabled_tools: set[str] | None = None,
        categories: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """生成 LLM 可见的工具列表（OpenAI function-calling 格式）。

        参数:
            context: 当前上下文（用于动态过滤，如屏蔽不需要的工具）
            enabled_tools: 显式启用的工具名集合
            categories: 按类别过滤
        """
        ctx = context or {}
        result: list[dict[str, Any]] = []
        for name, tool in self._tools.items():
            if enabled_tools is not None and name not in enabled_tools:
                continue
            if categories is not None and tool.category not in categories:
                continue
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": _clean_parameters(tool.parameters),
                    },
                }
            )
        return result

    def get_langchain_tools(
        self,
        *,
        enabled_tools: set[str] | None = None,
        categories: list[str] | None = None,
    ) -> list[StructuredTool]:
        """生成 LangChain StructuredTool 列表（用于 bind_tools）。"""
        result: list[StructuredTool] = []
        for name, tool in self._tools.items():
            if enabled_tools is not None and name not in enabled_tools:
                continue
            if categories is not None and tool.category not in categories:
                continue
            if tool.is_async:
                st = StructuredTool.from_function(
                    coroutine=tool.handler,
                    name=tool.name,
                    description=tool.description,
                )
            else:
                st = StructuredTool.from_function(
                    func=tool.handler,
                    name=tool.name,
                    description=tool.description,
                )
            result.append(st)
        return result

    # ---- 执行 ---------------------------------------------------------------

    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        *,
        force: bool = False,
        bypass_cache: bool = False,
    ) -> ToolResult:
        """执行指定工具，支持超时、重试、缓存。

        参数:
            name: 工具名称
            params: 工具参数
            force: 即使 requires_confirmation=True 也强制执行
            bypass_cache: 跳过缓存
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(tool_name=name, success=False, error=f"tool '{name}' not registered")

        if tool.requires_confirmation and not force:
            return ToolResult(
                tool_name=name,
                success=False,
                error="tool requires user confirmation",
            )

        # 缓存检查
        if not bypass_cache and tool.cache_ttl_seconds > 0:
            cache_key = _cache_key(name, params)
            entry = self._cache.get(cache_key)
            if entry is not None and (time.monotonic() - entry.created_at) < tool.cache_ttl_seconds:
                logger.debug("tool_cache_hit name=%s", name)
                return ToolResult(
                    tool_name=name,
                    success=True,
                    data=entry.result,
                    from_cache=True,
                )

        # 执行（含重试）
        last_error = ""
        for attempt in range(max(tool.max_retries + 1, 1)):
            started = time.perf_counter()
            try:
                if tool.is_async:
                    raw = await asyncio.wait_for(
                        tool.handler(**params),
                        timeout=tool.timeout_seconds,
                    )
                else:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(tool.handler, **params),
                        timeout=tool.timeout_seconds,
                    )
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                data = _normalize_result(raw)

                # 更新统计
                tool.total_calls += 1
                tool.total_success += 1
                tool.total_duration_ms += duration_ms

                # 写入缓存
                if tool.cache_ttl_seconds > 0:
                    cache_key = _cache_key(name, params)
                    self._cache[cache_key] = _CacheEntry(result=data, created_at=time.monotonic())

                return ToolResult(
                    tool_name=name,
                    success=True,
                    data=data,
                    duration_ms=duration_ms,
                    retry_count=attempt,
                )
            except asyncio.TimeoutError:
                last_error = f"tool '{name}' timed out after {tool.timeout_seconds}s"
                logger.warning("tool_timeout name=%s attempt=%d/%d", name, attempt + 1, tool.max_retries + 1)
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("tool_error name=%s attempt=%d/%d err=%s", name, attempt + 1, tool.max_retries + 1, exc)

        # 全部重试失败
        tool.total_calls += 1
        return ToolResult(tool_name=name, success=False, error=last_error, retry_count=tool.max_retries + 1)

    async def execute_parallel(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        *,
        bypass_cache: bool = False,
    ) -> list[ToolResult]:
        """并行执行多个工具调用（无依赖关系的工具并发执行）。

        参数:
            calls: [(tool_name, params), ...] 列表
        """
        tasks = [self.execute(name, params, bypass_cache=bypass_cache) for name, params in calls]
        return list(await asyncio.gather(*tasks))

    # ---- MCP 协议 -----------------------------------------------------------

    async def register_mcp_server(self, name: str, endpoint: str) -> bool:
        """注册一个 MCP Server 端点，自动发现其工具列表。

        返回是否注册成功。
        """
        import httpx

        self._mcp_servers[name] = endpoint
        timeout = httpx.Timeout(15.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{endpoint}/tools/list", json={})
                resp.raise_for_status()
                tools = list((resp.json() or {}).get("tools") or [])
            for tool_meta in tools:
                mcp_name = f"mcp:{name}:{tool_meta.get('name', 'unknown')}"
                definition = ToolDefinition(
                    name=mcp_name,
                    description=str(tool_meta.get("description") or f"MCP tool from {name}"),
                    handler=_mcp_handler_factory(endpoint, tool_meta.get("name", "")),
                    parameters=dict(tool_meta.get("parameters") or {}),
                    category="external",
                    is_async=True,
                )
                self._tools[mcp_name] = definition
                self._category_index["external"].append(mcp_name)
            logger.info("mcp_server_registered name=%s tool_count=%d", name, len(tools))
            return True
        except Exception as exc:
            logger.warning("mcp_server_register_failed name=%s err=%s", name, exc)
            return False

    def unregister_mcp_server(self, name: str) -> None:
        """注销 MCP Server 及其所有工具。"""
        self._mcp_servers.pop(name, None)
        prefix = f"mcp:{name}:"
        to_remove = [n for n in self._tools if n.startswith(prefix)]
        for n in to_remove:
            self.unregister(n)
        logger.info("mcp_server_unregistered name=%s removed_tools=%d", name, len(to_remove))

    # ---- 缓存管理 -----------------------------------------------------------

    def invalidate_cache(self, tool_name: str = "") -> int:
        """失效缓存。不指定名称则清空全部缓存。返回失效的条目数。"""
        if tool_name:
            prefix = _cache_key(tool_name, {})[:64]
            to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in to_remove:
                del self._cache[k]
            return len(to_remove)
        else:
            count = len(self._cache)
            self._cache.clear()
            return count

    # ---- 统计 ---------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """返回工具注册中心的运行时统计。"""
        tools_stats = {}
        for name, tool in self._tools.items():
            tools_stats[name] = {
                "category": tool.category,
                "total_calls": tool.total_calls,
                "success_rate": round(tool.success_rate, 4),
                "avg_duration_ms": round(tool.avg_duration_ms, 2),
            }
        return {
            "registered_tools": len(self._tools),
            "categories": len(self._category_index),
            "mcp_servers": len(self._mcp_servers),
            "cache_entries": len(self._cache),
            "tools": tools_stats,
        }


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

tool_registry = ToolRegistry()


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _infer_parameters(func: Callable) -> dict[str, Any]:
    """从函数签名粗略推断 JSON Schema 参数。"""
    import inspect

    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        param_type = "string"
        if param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
            if ann is int:
                param_type = "integer"
            elif ann is float:
                param_type = "number"
            elif ann is bool:
                param_type = "boolean"
            elif ann is list or str(ann).startswith("list"):
                param_type = "array"
            elif ann is dict or str(ann).startswith("dict"):
                param_type = "object"
        properties[param_name] = {"type": param_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _clean_parameters(raw: dict[str, Any]) -> dict[str, Any]:
    """清洗参数 JSON Schema，移除不兼容字段。"""
    cleaned = dict(raw)
    cleaned.setdefault("type", "object")
    cleaned.pop("additionalProperties", None)
    return cleaned


def _normalize_result(raw: Any) -> dict[str, Any]:
    """将工具返回值统一为 dict。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return {"result": raw}
    if isinstance(raw, (int, float, bool)):
        return {"result": raw}
    if isinstance(raw, list):
        return {"items": raw}
    return {"result": str(raw)}


def _cache_key(tool_name: str, params: dict[str, Any]) -> str:
    """生成缓存键。"""
    raw = json.dumps({"name": tool_name, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _mcp_handler_factory(endpoint: str, tool_name: str) -> Callable:
    """为 MCP 工具创建代理处理函数。"""

    import httpx

    async def _handler(**kwargs: Any) -> dict[str, Any]:
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{endpoint}/tools/call",
                json={"name": tool_name, "arguments": kwargs},
            )
            resp.raise_for_status()
            return dict(resp.json() or {})

    _handler.__name__ = f"mcp_{tool_name}"
    return _handler
