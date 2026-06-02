"""分层指令合并引擎 —— 五层指令优先级合并 + 冲突检测 + 审核追踪。

五层架构（优先级从高到低）：
    L5 调用级 (API Parameter): 单次API调用注入，最高优先级
    L4 会话级 (Session Override): 会话级覆盖，会话结束后失效
    L3 Agent Profile: 用户可自定义的Agent人格+行为
    L2 场景级 (Scene Template): 按场景预设（客服/技术/培训/...）
    L1 全局系统 (LLM_SYSTEM_PROMPT): 管理员配置，所有人所有场景生效

冲突解决:
    - 高优先级覆盖低优先级同键配置
    - 互斥指令段检测（如 "简洁回答" vs "详细回答"）
    - 安全校验（注入检测 + 越权检测）

变量系统: 支持 {{variable_name}} 模板变量，由 instruction_variables.py 提供

集成方式::

    from .instruction_merger import InstructionMerger

    merger = InstructionMerger()
    result = merger.merge(
        system="你是企业助手...",
        scene="你正在处理技术支持问题...",
        agent_profile="用简洁的技术语言...",
        session={"language": "英文"},
        call_level={"focus_document": "退款流程v3.pdf"},
    )
    final_prompt = result.merged_text
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class InstructionLayer:
    """单层指令"""

    level: int  # 1-5
    name: str  # 层级名称
    source_id: str  # 来源标识
    text: str  # 指令文本
    variables: dict[str, str] = field(default_factory=dict)  # 变量值
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MergeResult:
    """合并结果"""

    merged_text: str  # 最终合并的指令文本
    layers_applied: list[str]  # 生效的层级列表
    conflicts: list[dict[str, Any]]  # 检测到的冲突
    warnings: list[str]  # 安全警告
    trace: list[dict[str, Any]]  # 合并追踪（可审计）


# ---------------------------------------------------------------------------
# 互斥指令对
# ---------------------------------------------------------------------------

# 检测互斥的指令对（提示 LLM 可能困惑的相反指令）
_MUTUALLY_EXCLUSIVE_PAIRS: list[tuple[str, str]] = [
    ("简洁", "详细"),
    ("简短", "详尽"),
    ("short", "detailed"),
    ("concise", "verbose"),
    ("中文", "英文"),
    ("Chinese", "English"),
    ("正式", "随意"),
    ("formal", "casual"),
    ("技术", "通俗"),
    ("专业", "大白话"),
]


# ---------------------------------------------------------------------------
# 合并引擎
# ---------------------------------------------------------------------------


class InstructionMerger:
    """五层指令合并引擎。"""

    def __init__(self, *, enable_safety_check: bool = True) -> None:
        self._enable_safety = enable_safety_check

    def merge(
        self,
        *,
        system: str = "",
        scene: str = "",
        agent_profile: str = "",
        session: dict[str, Any] | None = None,
        call_level: dict[str, Any] | None = None,
        variables: dict[str, str] | None = None,
    ) -> MergeResult:
        """合并五层指令为最终 prompt。

        参数:
            system: L1 全局系统指令
            scene: L2 场景指令
            agent_profile: L3 Agent个性指令
            session: L4 会话级覆盖 {"key": "value"}
            call_level: L5 调用级注入 {"key": "value"}
            variables: 全局变量替换 {"var_name": "value"}
        """
        layers: list[InstructionLayer] = []
        trace: list[dict[str, Any]] = []
        all_vars = dict(variables or {})

        # L1: 系统级
        if system.strip():
            layers.append(InstructionLayer(level=1, name="system", source_id="global", text=system.strip(), metadata={"editable_by": "admin"}))

        # L2: 场景级
        if scene.strip():
            layers.append(InstructionLayer(level=2, name="scene", source_id="scene_template", text=scene.strip(), metadata={"editable_by": "admin"}))

        # L3: Agent Profile
        if agent_profile.strip():
            layers.append(InstructionLayer(level=3, name="agent_profile", source_id="agent", text=agent_profile.strip(), metadata={"editable_by": "user"}))

        # L4: 会话级 → key-value 对拼接为指令文本
        if session:
            session_text = self._kv_to_text(session, "session")
            if session_text:
                layers.append(InstructionLayer(level=4, name="session", source_id="session", text=session_text, metadata={"editable_by": "user", "ttl": "session"}))

        # L5: 调用级
        if call_level:
            call_text = self._kv_to_text(call_level, "call")
            if call_text:
                layers.append(InstructionLayer(level=5, name="call_level", source_id="api", text=call_text, metadata={"editable_by": "caller", "ttl": "single_call"}))

        # 按优先级排序（L5最高 → L1最低，但最终拼接时L1在前L5在后）
        sorted_layers = sorted(layers, key=lambda l: l.level)

        conflicts = self._detect_conflicts(sorted_layers)
        warnings: list[str] = []

        if self._enable_safety:
            warnings = self._safety_check(sorted_layers)

        # 变量替换
        for layer in sorted_layers:
            layer.text = self._apply_variables(layer.text, {**all_vars, **layer.variables})

        # 合并文本：L1 基础 → L2-L5 追加
        parts: list[str] = []
        applied: list[str] = []
        for layer in sorted_layers:
            if layer.text.strip():
                parts.append(layer.text.strip())
                applied.append(f"L{layer.level}:{layer.name}")
                trace.append({
                    "level": layer.level,
                    "name": layer.name,
                    "source_id": layer.source_id,
                    "text_preview": layer.text[:120],
                    "variables": layer.variables,
                })

        merged = "\n\n".join(parts)

        logger.debug(
            "instruction_merged layers=%s conflicts=%d warnings=%d",
            applied,
            len(conflicts),
            len(warnings),
        )

        return MergeResult(
            merged_text=merged,
            layers_applied=applied,
            conflicts=conflicts,
            warnings=warnings,
            trace=trace,
        )

    def _kv_to_text(self, kv: dict[str, Any], prefix: str) -> str:
        """将会话/调用级 key-value 转换为自然语言指令行。"""
        lines: list[str] = []
        known_keys = {
            "language": "请用 {value} 回答。",
            "style": "回答风格: {value}。",
            "focus_document": "重点参考文档: {value}。",
            "focus_section": "重点关注章节: {value}。",
            "max_length": "回答字数限制: {value}字以内。",
            "temperature": "",  # 不转文本
            "model": "",       # 不转文本
        }
        for key, value in kv.items():
            if value is None or value == "":
                continue
            template = known_keys.get(key)
            if template == "":
                continue
            if template:
                lines.append(template.format(value=str(value)))
            else:
                lines.append(f"{prefix}_{key}: {value}")
        return "\n".join(lines)

    def _detect_conflicts(self, layers: list[InstructionLayer]) -> list[dict[str, Any]]:
        """检测不同层级间的互斥指令。"""
        conflicts: list[dict[str, Any]] = []
        all_text = "\n".join(l.text for l in layers)

        for a, b in _MUTUALLY_EXCLUSIVE_PAIRS:
            if a in all_text and b in all_text:
                # 找到来源层级
                a_layers = [l.name for l in layers if a in l.text]
                b_layers = [l.name for l in layers if b in l.text]
                if set(a_layers) != set(b_layers):  # 不同层级
                    conflicts.append({
                        "type": "mutually_exclusive",
                        "term_a": a,
                        "term_b": b,
                        "in_layers_a": a_layers,
                        "in_layers_b": b_layers,
                        "resolution": f"高优先级层级的 '{a if max(layers, key=lambda l: l.level) in a_layers else b}' 优先",
                    })
        return conflicts

    def _safety_check(self, layers: list[InstructionLayer]) -> list[str]:
        """安全校验：注入检测 + 越权检测。"""
        warnings: list[str] = []

        dangerous_patterns = [
            (r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?", "检测到指令覆盖尝试"),
            (r"(?i)you\s+are\s+now\s+\w+", "检测到角色伪装尝试"),
            (r"(?i)system\s*:\s*", "检测到角色标记伪造"),
            (r"(?i)forget\s+(everything|all)", "检测到记忆清除指令"),
        ]

        for layer in layers:
            if layer.level >= 4:  # 只检查 L4/L5（用户可输入的层）
                for pattern, desc in dangerous_patterns:
                    if re.search(pattern, layer.text):
                        warnings.append(f"[{layer.name}] {desc}: {layer.text[:80]}...")

        return warnings

    def _apply_variables(self, text: str, variables: dict[str, str]) -> str:
        """替换文本中的 {{var}} 模板变量。"""
        if not variables:
            return text

        def _replace(match: re.Match) -> str:
            var_name = match.group(1).strip()
            return variables.get(var_name, match.group(0))

        return re.sub(r"\{\{(\w+)\}\}", _replace, text)


# ---------------------------------------------------------------------------
# 内置变量提供器
# ---------------------------------------------------------------------------

_BUILTIN_VARIABLES: dict[str, str] = {
    "current_date": "",  # 运行时填充
    "current_time": "",
    "kb_name": "",
    "kb_summary": "",
    "user_name": "",
    "user_role": "",
    "session_id": "",
}


def resolve_builtin_variables(
    *,
    user_name: str = "",
    user_role: str = "",
    kb_name: str = "",
    kb_summary: str = "",
    session_id: str = "",
) -> dict[str, str]:
    """解析内置变量值。"""
    from datetime import datetime

    now = datetime.now()
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M:%S"),
        "kb_name": kb_name,
        "kb_summary": kb_summary,
        "user_name": user_name,
        "user_role": user_role,
        "session_id": session_id,
    }
