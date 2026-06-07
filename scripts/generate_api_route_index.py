from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOTS = (
    Path("apps/services/api-gateway/src/app"),
    Path("apps/services/knowledge-base/src/app"),
)
HTTP_DECORATORS = {
    "get": ("GET",),
    "post": ("POST",),
    "put": ("PUT",),
    "patch": ("PATCH",),
    "delete": ("DELETE",),
    "options": ("OPTIONS",),
    "head": ("HEAD",),
}
ROUTE_DECORATORS = {"api_route", "route"}


@dataclass(frozen=True)
class ApiRoute:
    service: str
    path: str
    methods: tuple[str, ...]
    handler: str
    source: str
    line: int

    @property
    def method_label(self) -> str:
        return ", ".join(self.methods)


def parse_routes_from_file(source_path: str | Path, *, repo_root: str | Path | None = None) -> list[ApiRoute]:
    path = Path(source_path)
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    routes: list[ApiRoute] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            route = _route_from_decorator(
                decorator,
                handler=node.name,
                source_path=path,
                repo_root=root,
            )
            if route is not None:
                routes.append(route)
    return sorted(routes, key=_route_sort_key)


def collect_routes(
    source_paths: Sequence[str | Path] | None = None,
    *,
    repo_root: str | Path | None = None,
) -> list[ApiRoute]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    paths = list(source_paths or _default_python_sources(root))
    routes: list[ApiRoute] = []
    for path in paths:
        routes.extend(parse_routes_from_file(path, repo_root=root))
    return sorted(routes, key=_route_sort_key)


def build_markdown(routes: Sequence[ApiRoute], source_paths: Sequence[str | Path] | str | Path | None = None) -> str:
    source_labels = _source_labels(source_paths)
    lines = [
        "# API 路由清单",
        "",
        "> 本文件由 `scripts/generate_api_route_index.py` 静态解析 FastAPI 路由装饰器生成。",
        "> 它只列出路由、方法、处理函数和源码位置，不包含请求/响应示例、密钥、Prompt 或运行时数据。",
        "",
        "## 生成方式",
        "",
        "```powershell",
        ".venv\\Scripts\\python.exe scripts/generate_api_route_index.py --output docs/API_ROUTE_INDEX.md",
        "```",
        "",
        "## 源码范围",
        "",
    ]
    for label in source_labels:
        lines.append(f"- `{label}`")
    lines.extend(
        [
            "",
            f"## 路由总览（{len(routes)} 条）",
            "",
            "| service | methods | path | handler | source |",
            "|---|---|---|---|---|",
        ]
    )
    for route in sorted(routes, key=_route_sort_key):
        lines.append(
            "| "
            f"{route.service} | "
            f"`{route.method_label}` | "
            f"`{route.path}` | "
            f"`{route.handler}` | "
            f"`{route.source}:{route.line}` |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_for_repo(*, repo_root: str | Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    sources = list(_default_python_sources(root))
    return build_markdown(collect_routes(sources, repo_root=root), _relative_sources(sources, root))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a static FastAPI route index.")
    parser.add_argument("sources", nargs="*", help="Python source files or directories to scan. Defaults to Gateway and KB service app directories.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root used for relative source labels.")
    parser.add_argument("--output", "-o", help="Write Markdown to this path instead of stdout.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    source_paths = _expand_sources([Path(item) for item in args.sources], repo_root=repo_root)
    if not source_paths:
        source_paths = list(_default_python_sources(repo_root))
    markdown = build_markdown(collect_routes(source_paths, repo_root=repo_root), _relative_sources(source_paths, repo_root))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown, end="")
    return 0


def _route_from_decorator(
    decorator: ast.expr,
    *,
    handler: str,
    source_path: Path,
    repo_root: Path,
) -> ApiRoute | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    decorator_name = decorator.func.attr
    if decorator_name not in HTTP_DECORATORS and decorator_name not in ROUTE_DECORATORS:
        return None
    if not decorator.args:
        return None
    path = _literal_string(decorator.args[0])
    if not path:
        return None
    methods = HTTP_DECORATORS.get(decorator_name) or _methods_from_keywords(decorator.keywords) or ("GET",)
    source = _relative_source(source_path, repo_root)
    return ApiRoute(
        service=_service_from_source(source),
        path=path,
        methods=tuple(sorted(dict.fromkeys(method.upper() for method in methods))),
        handler=handler,
        source=source,
        line=getattr(decorator, "lineno", getattr(decorator.func, "lineno", 0)),
    )


def _methods_from_keywords(keywords: Sequence[ast.keyword]) -> tuple[str, ...]:
    for keyword in keywords:
        if keyword.arg != "methods":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return (value.value.upper(),)
        if isinstance(value, ast.List | ast.Tuple | ast.Set):
            methods = [_literal_string(item).upper() for item in value.elts]
            return tuple(method for method in methods if method)
    return ()


def _literal_string(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    return ""


def _default_python_sources(repo_root: Path) -> list[Path]:
    sources: list[Path] = []
    for root in DEFAULT_SOURCE_ROOTS:
        base = repo_root / root
        if base.exists():
            sources.extend(sorted(base.glob("*routes.py")))
            main_path = base / "main.py"
            if main_path.exists():
                sources.append(main_path)
    return sources


def _expand_sources(paths: Sequence[Path], *, repo_root: Path) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        resolved = path if path.is_absolute() else repo_root / path
        if resolved.is_dir():
            expanded.extend(sorted(resolved.glob("*.py")))
        elif resolved.is_file():
            expanded.append(resolved)
    return expanded


def _relative_sources(paths: Sequence[Path], repo_root: Path) -> list[str]:
    return [_relative_source(path, repo_root) for path in paths]


def _relative_source(path: Path, repo_root: Path) -> str:
    try:
        return PurePosixPath(path.resolve().relative_to(repo_root.resolve())).as_posix()
    except ValueError:
        return PurePosixPath(path).as_posix()


def _source_labels(source_paths: Sequence[str | Path] | str | Path | None) -> list[str]:
    if source_paths is None:
        return [PurePosixPath(path).as_posix() for path in DEFAULT_SOURCE_ROOTS]
    if isinstance(source_paths, str | Path):
        return [PurePosixPath(source_paths).as_posix()]
    return [PurePosixPath(path).as_posix() for path in source_paths]


def _service_from_source(source: str) -> str:
    if source.startswith("apps/services/api-gateway/"):
        return "api-gateway"
    if source.startswith("apps/services/knowledge-base/"):
        return "knowledge-base"
    return "custom"


def _route_sort_key(route: ApiRoute) -> tuple[str, str, str, str, int]:
    return (route.path, route.method_label, route.service, route.source, route.line)


if __name__ == "__main__":
    raise SystemExit(main())
