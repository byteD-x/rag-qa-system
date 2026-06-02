"""OpenAPI/Swagger 工具自动发现。

核心能力：
- 从 OpenAPI 3.x / Swagger 2.x spec 自动注册工具
- 从 JSON Schema 生成 ToolDefinition 的 parameters 定义
- 支持本地文件、HTTP URL、或直接传入 dict
- 命名空间隔离（API 来源的工具加前缀避免冲突）
- 自动推断工具分类（基于 path 和 tag）

使用方式::

    from .tool_discovery import discover_tools_from_openapi

    tools = await discover_tools_from_openapi("https://api.example.com/openapi.json")
    for tool in tools:
        tool_registry.register_direct(tool)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

# HTTP 方法到工具动作的映射
_METHOD_ACTION_MAP = {
    "get": "查询",
    "post": "创建",
    "put": "更新",
    "patch": "修改",
    "delete": "删除",
}

# 路径段到分类的启发式映射
_PATH_CATEGORY_MAP: dict[str, str] = {
    "search": "search",
    "query": "search",
    "find": "search",
    "calculate": "compute",
    "compute": "compute",
    "stats": "compute",
    "export": "external",
    "webhook": "external",
    "admin": "system",
    "health": "system",
    "status": "system",
}


@dataclass
class DiscoveredTool:
    """从 OpenAPI spec 发现的工具。"""

    name: str              # 工具名（加前缀命名空间）
    description: str        # LLM 可见描述
    parameters: dict[str, Any]  # JSON Schema
    category: str = "external"
    original_path: str = ""
    http_method: str = "get"
    base_url: str = ""
    endpoint_path: str = ""
    tags: list[str] = field(default_factory=list)
    requires_confirmation: bool = False


# ---------------------------------------------------------------------------
# OpenAPI 解析器
# ---------------------------------------------------------------------------


class OpenAPIToolDiscoverer:
    """OpenAPI / Swagger spec → 工具定义解析器。

    支持的 spec 格式：
    - OpenAPI 3.x
    - Swagger 2.x（自动转换为 3.x 语义）
    """

    def __init__(self, *, namespace: str = "api", base_url: str = "") -> None:
        self._namespace = namespace
        self._base_url = base_url.rstrip("/") if base_url else ""

    def discover(self, spec: dict[str, Any]) -> list[DiscoveredTool]:
        """从 OpenAPI spec 中发现所有可注册的工具。

        参数:
            spec: OpenAPI 3.x 或 Swagger 2.x 的 JSON dict

        返回:
            DiscoveredTool 列表
        """
        tools: list[DiscoveredTool] = []

        # 获取 base URL
        servers = spec.get("servers") or []
        base_url = self._base_url
        if not base_url and servers:
            base_url = str(servers[0].get("url", "")).rstrip("/")

        # OpenAPI 3.x: paths 在顶层
        paths = spec.get("paths") or {}
        if not paths:
            # Swagger 2.x 兼容
            base_path = str(spec.get("basePath", "")).rstrip("/")
            if base_path and not base_url:
                host = spec.get("host", "")
                schemes = spec.get("schemes", ["https"])
                base_url = f"{schemes[0]}://{host}{base_path}"
            paths = spec.get("paths") or {}

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method in ["get", "post", "put", "patch", "delete"]:
                operation = path_item.get(method)
                if not isinstance(operation, dict):
                    continue

                tool = self._operation_to_tool(
                    path=str(path),
                    method=method,
                    operation=operation,
                    base_url=base_url,
                )
                if tool is not None:
                    tools.append(tool)

        logger.info("openapi_discovered namespace=%s count=%d", self._namespace, len(tools))
        return tools

    def _operation_to_tool(
        self,
        *,
        path: str,
        method: str,
        operation: dict[str, Any],
        base_url: str = "",
    ) -> DiscoveredTool | None:
        """将单个 OpenAPI operation 转换为工具。"""
        operation_id = str(operation.get("operationId") or "").strip()
        if not operation_id:
            # 从 path + method 生成
            operation_id = self._generate_operation_id(path, method)

        # 命名空间前缀
        tool_name = f"{self._namespace}_{operation_id}"

        # 描述
        summary = str(operation.get("summary") or "").strip()
        description = str(operation.get("description") or "").strip()
        if not summary and not description:
            summary = f"{_METHOD_ACTION_MAP.get(method, '调用')} {path}"

        full_description = summary
        if description and description != summary:
            full_description = f"{summary}\n{description}"

        # 参数 JSON Schema
        parameters = self._extract_parameters(operation)

        # 分类
        tags = [str(t).strip().lower() for t in operation.get("tags") or []]
        category = self._infer_category(path, method, tags)

        # 是否需要确认
        requires_confirmation = (
            method in {"post", "put", "patch", "delete"}
            and any(kw in path.lower() for kw in {"delete", "remove", "admin", "config"})
        )

        return DiscoveredTool(
            name=tool_name,
            description=full_description,
            parameters=parameters,
            category=category,
            original_path=path,
            http_method=method,
            base_url=base_url,
            endpoint_path=path,
            tags=tags,
            requires_confirmation=requires_confirmation,
        )

    def _extract_parameters(self, operation: dict[str, Any]) -> dict[str, Any]:
        """从 operation 中提取 JSON Schema 参数定义。"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # 路径参数
        for param in operation.get("parameters") or []:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name") or "").strip()
            if not name:
                continue
            schema = param.get("schema") or {}
            properties[name] = {
                "type": str(schema.get("type") or param.get("type") or "string"),
                "description": str(param.get("description") or "").strip(),
            }
            if bool(param.get("required")):
                required.append(name)

        # Request body (POST/PUT/PATCH)
        request_body = operation.get("requestBody") or {}
        if isinstance(request_body, dict):
            content = request_body.get("content") or {}
            json_content = content.get("application/json") or {}
            body_schema = json_content.get("schema") or {}
            if isinstance(body_schema, dict):
                body_props = body_schema.get("properties") or {}
                body_required = body_schema.get("required") or []
                for name, prop_schema in body_props.items():
                    if not isinstance(prop_schema, dict):
                        continue
                    properties[name] = {
                        "type": str(prop_schema.get("type") or "string"),
                        "description": str(prop_schema.get("description") or "").strip(),
                    }
                    if name in (list(body_required) if isinstance(body_required, list) else []):
                        required.append(name)

        result: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            result["required"] = required
        return result

    def _infer_category(self, path: str, method: str, tags: list[str]) -> str:
        """推断工具分类。"""
        path_lower = path.lower()
        for segment in path_lower.strip("/").split("/"):
            if segment in _PATH_CATEGORY_MAP:
                return _PATH_CATEGORY_MAP[segment]

        if method == "delete":
            return "system"
        if method in {"post", "put", "patch"}:
            return "external"

        return "general"

    @staticmethod
    def _generate_operation_id(path: str, method: str) -> str:
        """从 path + method 自动生成 operationId。"""
        # 将 path 转为 snake_case: /api/v1/user-profile → user_profile
        segments = [
            re.sub(r"[^a-zA-Z0-9]+", "_", seg).strip("_").lower()
            for seg in path.strip("/").split("/")
        ]
        meaningful = [s for s in segments if s and s not in {"api", "v1", "v2", "v3"}]
        return f"{method}_{'_'.join(meaningful)}" if meaningful else f"{method}_{path.strip('/').replace('/', '_')}"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def discover_tools_from_spec(
    spec: dict[str, Any],
    *,
    namespace: str = "api",
    base_url: str = "",
) -> list[DiscoveredTool]:
    """从 OpenAPI spec dict 中发现工具。"""
    discoverer = OpenAPIToolDiscoverer(namespace=namespace, base_url=base_url)
    return discoverer.discover(spec)


async def discover_tools_from_url(
    url: str,
    *,
    namespace: str = "api",
    timeout: float = 30.0,
) -> list[DiscoveredTool]:
    """从 HTTP URL 获取 OpenAPI spec 并发现工具。"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            spec = response.json()
    except Exception as exc:
        logger.warning("openapi_fetch_failed url=%s err=%s", url, exc)
        return []

    discoverer = OpenAPIToolDiscoverer(namespace=namespace, base_url=url.rsplit("/", 1)[0])
    return discoverer.discover(spec)


def generate_tool_definition(discovered: DiscoveredTool) -> dict[str, Any]:
    """将 DiscoveredTool 转为 ToolDefinition 兼容的字典格式。

    用于与 tool_registry.register_direct() 配合使用。
    """
    return {
        "name": discovered.name,
        "description": discovered.description,
        "parameters": discovered.parameters,
        "category": discovered.category,
        "requires_confirmation": discovered.requires_confirmation,
        "metadata": {
            "source": "openapi",
            "original_path": discovered.original_path,
            "http_method": discovered.http_method,
            "base_url": discovered.base_url,
            "endpoint_path": discovered.endpoint_path,
            "tags": discovered.tags,
        },
    }
