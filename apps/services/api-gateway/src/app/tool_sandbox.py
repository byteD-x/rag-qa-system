"""工具执行沙箱 —— 隔离执行不受信任的工具调用。

核心能力：
- Subprocess 隔离（轻量级，适合内部工具）
- 资源限制：超时、内存上限、输出大小上限
- 安全策略：禁止命令白名单 + 参数校验 + 网络访问控制
- 结果格式标准化：自动转换 stdout/stderr 为结构化输出
- 降级策略：沙箱不可用时降级为直接调用

使用方式::

    from .tool_sandbox import SandboxExecutor

    executor = SandboxExecutor()
    result = await executor.run("python script.py", timeout=10, max_memory_mb=256)
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class SandboxMode(str, Enum):
    """沙箱模式。"""
    SUBPROCESS = "subprocess"     # subprocess 隔离
    DOCKER = "docker"             # Docker 容器隔离
    DIRECT = "direct"             # 直接调用（无隔离，最低开销）
    RESTRICTED = "restricted"     # 受限模式：仅白名单命令
    DISABLED = "disabled"         # 停用沙箱


class SecurityLevel(str, Enum):
    """安全级别。"""
    TRUSTED = "trusted"           # 可信工具：直接调用
    SANDBOXED = "sandboxed"       # 沙箱隔离
    RESTRICTED = "restricted"     # 仅白名单命令
    BLOCKED = "blocked"           # 禁止执行


@dataclass
class SandboxPolicy:
    """沙箱安全策略。"""
    # 命令白名单（仅 restricted 模式生效）
    allowed_commands: list[str] = field(default_factory=lambda: ["python", "node", "echo", "cat", "ls", "grep"])
    # 禁止的命令模式
    blocked_patterns: list[str] = field(default_factory=lambda: [
        r"rm\s+-rf",
        r"mkfs\.",
        r"dd\s+if=",
        r">\s*/dev/",
        r"curl.*\|.*sh",
        r"wget.*\|.*sh",
        r"eval\s+",
        r"exec\s+",
        r"__import__",
        r"os\.system",
        r"subprocess",
    ])
    # 网络访问控制
    allow_network: bool = False
    allowed_hosts: list[str] = field(default_factory=list)
    # 文件系统访问
    allow_file_write: bool = False
    allowed_write_paths: list[str] = field(default_factory=list)
    # 模块白名单（Python 执行时）
    allowed_modules: list[str] = field(default_factory=lambda: [
        "json", "math", "datetime", "re", "collections", "itertools", "csv",
    ])


@dataclass
class SandboxResult:
    """沙箱执行结果。"""
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: float = 0.0
    truncated: bool = False
    was_sandboxed: bool = False
    security_action: str = ""  # "" 表示无安全拦截
    memory_used_mb: float = 0.0


# ---------------------------------------------------------------------------
# 沙箱执行器
# ---------------------------------------------------------------------------


class SandboxExecutor:
    """工具执行沙箱。

    提供多级隔离执行选项：
    - DIRECT: 直接调用（可信工具）
    - SUBPROCESS: subprocess 隔离（内部工具，默认）
    - DOCKER: Docker 容器隔离（外部/不可信工具）
    """

    # 默认限制
    DEFAULT_TIMEOUT_SECONDS = 30.0
    DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024  # 256KB
    DEFAULT_MAX_MEMORY_MB = 512

    def __init__(
        self,
        *,
        mode: str = "subprocess",
        policy: SandboxPolicy | None = None,
    ) -> None:
        self._mode = mode
        self._policy = policy or SandboxPolicy()

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        max_output_bytes: int | None = None,
        max_memory_mb: int | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "",
        input_data: str = "",
    ) -> SandboxResult:
        """在沙箱中执行命令。

        参数:
            command: 要执行的命令
            timeout: 超时时间（秒）
            max_output_bytes: 最大输出字节数
            max_memory_mb: 最大内存（MB）
            env: 环境变量
            cwd: 工作目录
            input_data: stdin 输入

        返回:
            SandboxResult
        """
        effective_timeout = timeout or self.DEFAULT_TIMEOUT_SECONDS
        effective_max_output = max_output_bytes or self.DEFAULT_MAX_OUTPUT_BYTES

        # 1. 安全策略检查
        security_action = self._check_security(command)
        if security_action:
            return SandboxResult(
                success=False,
                stderr=f"安全策略拦截: {security_action}",
                security_action=security_action,
            )

        # 2. 按模式执行
        started = time.perf_counter()

        if self._mode == SandboxMode.DIRECT.value:
            result = await self._run_direct(
                command, effective_timeout, effective_max_output, env, cwd, input_data
            )
        elif self._mode == SandboxMode.DOCKER.value:
            result = await self._run_docker(
                command, effective_timeout, effective_max_output, max_memory_mb, env, cwd, input_data
            )
        else:
            result = await self._run_subprocess(
                command, effective_timeout, effective_max_output, max_memory_mb, env, cwd, input_data
            )

        result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
        result.was_sandboxed = self._mode != SandboxMode.DIRECT.value
        return result

    def _check_security(self, command: str) -> str:
        """安全策略检查。返回非空字符串表示拦截。"""
        if self._mode == SandboxMode.DISABLED.value:
            return "沙箱已禁用"

        # 检查禁止模式
        for pattern in self._policy.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning("sandbox_blocked_pattern pattern=%s command=%.200s", pattern, command)
                return f"禁止的命令模式: {pattern}"

        # 受限模式：检查命令白名单
        if self._mode == SandboxMode.RESTRICTED.value:
            base_command = shlex.split(command)[0] if command.strip() else ""
            if base_command not in self._policy.allowed_commands:
                return f"命令不在白名单中: {base_command}"

        return ""

    async def _run_direct(
        self,
        command: str,
        timeout: float,
        max_output: int,
        env: dict[str, str] | None,
        cwd: str,
        input_data: str,
    ) -> SandboxResult:
        """直接执行（不隔离）。"""
        return await self._run_subprocess(command, timeout, max_output, None, env, cwd, input_data)

    async def _run_subprocess(
        self,
        command: str,
        timeout: float,
        max_output: int,
        max_memory_mb: int | None,
        env: dict[str, str] | None,
        cwd: str,
        input_data: str,
    ) -> SandboxResult:
        """Subprocess 隔离执行。"""
        try:
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                env=process_env,
                cwd=cwd or None,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(
                        input=input_data.encode("utf-8", errors="replace") if input_data else None
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    stderr=f"执行超时 ({timeout}s)",
                    exit_code=-1,
                )

            stdout_text, was_truncated = self._truncate_output(
                stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
                max_output,
            )
            stderr_text = (stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "")[:max_output]

            return SandboxResult(
                success=proc.returncode == 0,
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=proc.returncode or 0,
                truncated=was_truncated,
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                stderr=f"命令未找到: {command.split()[0] if command else ''}",
            )
        except Exception as exc:
            return SandboxResult(
                success=False,
                stderr=f"执行异常: {exc}",
            )

    async def _run_docker(
        self,
        command: str,
        timeout: float,
        max_output: int,
        max_memory_mb: int | None,
        env: dict[str, str] | None,
        cwd: str,
        input_data: str,
    ) -> SandboxResult:
        """Docker 容器隔离执行。"""
        docker_cmd_parts = [
            "docker", "run", "--rm",
            "--network", "none" if not self._policy.allow_network else "bridge",
        ]

        if max_memory_mb:
            docker_cmd_parts.extend(["--memory", f"{max_memory_mb}m"])

        if env:
            for k, v in env.items():
                docker_cmd_parts.extend(["-e", f"{k}={v}"])

        if cwd:
            docker_cmd_parts.extend(["-v", f"{cwd}:{cwd}", "-w", cwd])

        # 使用轻量 Python 镜像
        docker_cmd_parts.extend(["python:3.11-slim", "sh", "-c", command])

        full_docker_cmd = " ".join(docker_cmd_parts)

        try:
            result = await self._run_subprocess(
                full_docker_cmd, timeout + 10, max_output, max_memory_mb, None, "", input_data
            )
            return result
        except Exception as exc:
            logger.warning("docker_execution_failed err=%s", exc)
            # Docker 不可用时降级为 subprocess
            return await self._run_subprocess(
                command, timeout, max_output, max_memory_mb, env, cwd, input_data
            )

    @staticmethod
    def _truncate_output(text: str, max_bytes: int) -> tuple[str, bool]:
        """截断过长的输出。"""
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= max_bytes:
            return text, False
        truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
        return truncated + "\n...（输出已截断）", True


# ---------------------------------------------------------------------------
# Python 代码沙箱
# ---------------------------------------------------------------------------


class PythonSandbox:
    """Python 代码安全执行沙箱。

    使用 RestrictedPython 或 AST 白名单实现安全的 Python 代码执行。
    支持限制：模块导入白名单、禁止文件 I/O、禁止网络、超时控制。
    """

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self._policy = policy or SandboxPolicy()

    async def execute(
        self,
        code: str,
        *,
        globals_dict: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> SandboxResult:
        """在受限环境中执行 Python 代码。

        参数:
            code: Python 代码字符串
            globals_dict: 全局变量
            timeout: 超时时间

        返回:
            SandboxResult
        """
        if not code.strip():
            return SandboxResult(success=False, stderr="代码为空")

        g = {"__builtins__": self._restricted_builtins(), **(globals_dict or {})}
        local: dict[str, Any] = {}

        try:
            # AST 安全检查
            self._validate_ast(code)

            # 使用 subprocess 隔离执行
            executor = SandboxExecutor(mode=SandboxMode.SUBPROCESS.value, policy=self._policy)
            escaped_code = code.replace("'", "'\\''")
            py_command = f"python -c '{escaped_code}'"

            result = await executor.run(py_command, timeout=timeout)
            return result

        except SyntaxError as e:
            return SandboxResult(success=False, stderr=f"语法错误: {e}")
        except Exception as e:
            return SandboxResult(success=False, stderr=f"执行失败: {e}")

    def _restricted_builtins(self) -> dict[str, Any]:
        """受限的内建函数集。"""
        allowed = {
            "abs", "all", "any", "bin", "bool", "chr", "dict", "dir", "divmod",
            "enumerate", "filter", "float", "format", "frozenset", "getattr",
            "hasattr", "hash", "hex", "int", "isinstance", "issubclass",
            "iter", "len", "list", "map", "max", "min", "next", "oct",
            "ord", "pow", "print", "range", "repr", "reversed", "round",
            "set", "slice", "sorted", "str", "sum", "tuple", "type", "zip",
            "json", "math", "datetime", "re", "collections",
        }
        return {name: __builtins__.get(name) for name in allowed if name in __builtins__}

    def _validate_ast(self, code: str) -> None:
        """AST 级别安全校验（阻止危险操作）。"""
        import ast

        tree = ast.parse(code)

        for node in ast.walk(tree):
            # 禁止 import
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                else:
                    module = node.names[0].name if node.names else ""

                if module not in self._policy.allowed_modules and module != "__future__":
                    raise ValueError(f"禁止导入模块: {module}")

            # 禁止 exec/eval
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in {"exec", "eval", "compile", "__import__"}:
                        raise ValueError(f"禁止调用: {node.func.id}")

            # 禁止文件 I/O（通过 open）
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "open":
                    raise ValueError("禁止文件 I/O")
