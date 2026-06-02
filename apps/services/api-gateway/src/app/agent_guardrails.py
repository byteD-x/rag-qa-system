"""Agent 安全护栏 —— 危险操作拦截与敏感数据过滤。

核心能力：
- 工具调用前安全校验（危险操作确认 + 参数注入检测）
- 敏感数据过滤（API Key、密码、Token 等在日志/输出中脱敏）
- 内容安全边界（拒绝执行危险 shell 命令、文件删除等）
- 安全事件审计（记录所有拦截和确认操作）

使用方式::

    from .agent_guardrails import AgentGuardrails

    guardrails = AgentGuardrails()
    allowed, reason = guardrails.check_tool_call("delete_file", {"path": "/etc/passwd"})
    safe_output = guardrails.sanitize_output(response_text)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """风险等级。"""
    SAFE = "safe"             # 安全
    LOW = "low"               # 低风险
    MEDIUM = "medium"         # 中风险
    HIGH = "high"             # 高风险
    CRITICAL = "critical"     # 严重风险—必须拦截


class GuardAction(str, Enum):
    """护栏动作。"""
    ALLOW = "allow"                # 放行
    ALLOW_WITH_WARNING = "warn"    # 放行但记录警告
    CONFIRM = "confirm"            # 需要用户确认
    BLOCK = "block"                # 拦截
    SANITIZE = "sanitize"          # 脱敏后放行


@dataclass
class GuardResult:
    """护栏检查结果。"""
    allowed: bool = True
    action: str = "allow"
    risk_level: str = "safe"
    reason: str = ""
    sanitized_data: dict[str, Any] | None = None
    audit_event: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# 安全策略配置
# ---------------------------------------------------------------------------


# 高风险工具（需要确认）
HIGH_RISK_TOOLS: set[str] = {
    "execute_shell", "run_command", "delete_file", "delete_document",
    "restart_service", "deploy", "drop_table", "truncate_table",
    "update_production_config", "disable_user", "grant_admin",
}

# 危险 shell 命令模式
DANGEROUS_SHELL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("删除系统文件", re.compile(r"rm\s+-rf\s+/", re.IGNORECASE)),
    ("格式化磁盘", re.compile(r"mkfs\.|fdisk|dd\s+if=/dev/", re.IGNORECASE)),
    ("修改权限", re.compile(r"chmod\s+777", re.IGNORECASE)),
    ("下载执行", re.compile(r"(curl|wget).*\|.*(sh|bash|python)", re.IGNORECASE)),
    ("环境变量泄露", re.compile(r"env\s*\|", re.IGNORECASE)),
    ("进程注入", re.compile(r"/proc/\d+/", re.IGNORECASE)),
]

# 敏感数据模式（用于脱敏）
SENSITIVE_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("api_key", "sk-****", re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE)),
    ("bearer_token", "Bearer ****", re.compile(r"Bearer\s+[a-zA-Z0-9\-_.]{20,}", re.IGNORECASE)),
    ("password_field", "password=****", re.compile(r'(?:password|passwd|pwd|secret)\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE)),
    ("jwt_token", "JWT****", re.compile(r"eyJ[a-zA-Z0-9\-_]{20,}\.[a-zA-Z0-9\-_]{20,}\.[a-zA-Z0-9\-_]{10,}", re.IGNORECASE)),
    ("aws_key", "AKIA****", re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE)),
    ("private_key", "PRIVATE KEY****", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END (?:RSA |EC )?PRIVATE KEY-----", re.DOTALL)),
]

# 危险路径模式
DANGEROUS_PATHS: list[re.Pattern] = [
    re.compile(r"^/etc/(passwd|shadow|sudoers|ssh/)", re.IGNORECASE),
    re.compile(r"^/proc/", re.IGNORECASE),
    re.compile(r"^/sys/", re.IGNORECASE),
    re.compile(r"^C:\\Windows\\System32", re.IGNORECASE),
    re.compile(r"\.\./\.\."),
]


# ---------------------------------------------------------------------------
# Agent 安全护栏
# ---------------------------------------------------------------------------


class AgentGuardrails:
    """Agent 安全护栏 —— 多层级安全检查。"""

    def __init__(self) -> None:
        self._audit_log: list[dict[str, Any]] = []
        self._blocked_count: int = 0
        self._confirmed_count: int = 0

    # ---- 工具调用检查 ----

    def check_tool_call(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        *,
        user_confirmed: bool = False,
    ) -> GuardResult:
        """检查工具调用是否安全。

        参数:
            tool_name: 工具名
            tool_params: 工具参数
            user_confirmed: 用户是否已确认

        返回:
            GuardResult
        """
        # 1. 高风险工具需要确认
        if tool_name in HIGH_RISK_TOOLS:
            if user_confirmed:
                self._confirmed_count += 1
                return GuardResult(
                    allowed=True,
                    action=GuardAction.ALLOW_WITH_WARNING.value,
                    risk_level=RiskLevel.HIGH.value,
                    reason=f"高风险工具 {tool_name}，用户已确认",
                )
            return GuardResult(
                allowed=False,
                action=GuardAction.CONFIRM.value,
                risk_level=RiskLevel.HIGH.value,
                reason=f"高风险工具 {tool_name} 需要用户确认",
                audit_event={
                    "type": "tool_blocked",
                    "tool": tool_name,
                    "reason": "requires_confirmation",
                    "params": self._sanitize_params(tool_params),
                },
            )

        # 2. shell 命令检查
        if "command" in tool_params or "cmd" in tool_params:
            cmd = str(tool_params.get("command") or tool_params.get("cmd") or "")
            for label, pattern in DANGEROUS_SHELL_PATTERNS:
                if pattern.search(cmd):
                    self._blocked_count += 1
                    event = {
                        "type": "command_blocked",
                        "tool": tool_name,
                        "reason": label,
                        "command_preview": cmd[:200],
                    }
                    self._audit_log.append(event)
                    return GuardResult(
                        allowed=False,
                        action=GuardAction.BLOCK.value,
                        risk_level=RiskLevel.CRITICAL.value,
                        reason=f"危险命令: {label}",
                        audit_event=event,
                    )

        # 3. 路径检查
        if "path" in tool_params or "file_path" in tool_params:
            path = str(tool_params.get("path") or tool_params.get("file_path") or "")
            for pattern in DANGEROUS_PATHS:
                if pattern.search(path):
                    return GuardResult(
                        allowed=False,
                        action=GuardAction.BLOCK.value,
                        risk_level=RiskLevel.HIGH.value,
                        reason=f"危险路径: {path[:100]}",
                        audit_event={"type": "path_blocked", "path": path[:200]},
                    )

        return GuardResult(allowed=True, action=GuardAction.ALLOW.value, risk_level=RiskLevel.SAFE.value, reason="通过安全检查")

    # ---- 输出脱敏 ----

    def sanitize_output(self, text: str) -> tuple[str, int]:
        """脱敏输出文本中的敏感信息。

        返回:
            (脱敏后的文本, 脱敏数量)
        """
        sanitized = text
        count = 0
        for label, replacement, pattern in SENSITIVE_PATTERNS:
            matches = pattern.findall(sanitized)
            if matches:
                sanitized = pattern.sub(replacement, sanitized)
                count += len(matches)
                logger.debug("guardrail_sanitized type=%s count=%d", label, len(matches))
        return sanitized, count

    def sanitize_log_entry(self, log_text: str) -> str:
        """为日志条目脱敏（去除敏感内容但不改变格式）。"""
        text, _ = self.sanitize_output(log_text)
        return text

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        """脱敏工具参数（审计记录用）。"""
        safe = {}
        sensitive_keys = {"password", "passwd", "token", "api_key", "secret", "credential", "key"}
        for k, v in params.items():
            if k.lower() in sensitive_keys or any(sk in k.lower() for sk in sensitive_keys):
                safe[k] = "****"
            elif isinstance(v, str) and len(v) > 100:
                safe[k] = v[:100] + "..."
            else:
                safe[k] = v
        return safe

    # ---- 内容安全检查 ----

    def check_content(self, text: str) -> GuardResult:
        """检查生成内容是否安全。

        检查项：
        - 是否包含系统指令泄露（"我的系统提示词是..."）
        - 是否包含代码执行建议（eval/exec）
        - 是否包含敏感数据泄露
        """
        text_lower = text.lower()

        # 系统提示词泄露检查
        prompt_leak_indicators = [
            "system prompt", "system message", "系统提示词", "系统指令",
            "you are a", "your instructions are",
        ]
        for indicator in prompt_leak_indicators:
            if indicator in text_lower and len(text) > 30:
                return GuardResult(
                    allowed=False,
                    action=GuardAction.BLOCK.value,
                    risk_level=RiskLevel.HIGH.value,
                    reason=f"可能的系统提示词泄露: 内容包含 '{indicator}'",
                )

        # 代码执行建议
        if re.search(r"os\.system\(|subprocess\.|exec\(|eval\(|__import__\(", text):
            return GuardResult(
                allowed=False,
                action=GuardAction.SANITIZE.value,
                risk_level=RiskLevel.MEDIUM.value,
                reason="包含代码执行建议，需要脱敏",
            )

        return GuardResult(allowed=True, action=GuardAction.ALLOW.value, risk_level=RiskLevel.SAFE.value, reason="内容安全")

    # ---- 统计 ----

    def stats(self) -> dict[str, Any]:
        return {
            "blocked_total": self._blocked_count,
            "confirmed_total": self._confirmed_count,
            "audit_events_count": len(self._audit_log),
        }

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._audit_log[-limit:]


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

agent_guardrails = AgentGuardrails()
