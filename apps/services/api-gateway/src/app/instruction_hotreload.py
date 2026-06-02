"""指令热更新管理器。

核心能力：
- 不重启服务即可更新系统指令/场景模板/Agent Profile
- 版本追踪（每次更新记录版本号和时间）
- 变更通知（通知活跃会话指令已更新）
- 原子替换（update → reload 两步操作保证一致性）

使用方式::

    from .instruction_hotreload import InstructionHotReloader

    reloader = InstructionHotReloader()
    reloader.update("system_prompt", "L1", "新的系统提示词...")
    changed_sessions = reloader.reload()
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class InstructionLayer(str, Enum):
    """指令层级（与 instruction_merger 五层对应）。"""
    L1_SYSTEM = "system"         # 全局系统
    L2_SCENE = "scene"           # 场景模板
    L3_AGENT = "agent"           # Agent Profile
    L4_SESSION = "session"       # 会话级
    L5_CALL = "call"             # 调用级


@dataclass
class InstructionSnapshot:
    """指令快照。"""
    layer: str
    key: str                     # 场景 key / agent profile id / "global"
    content: str
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""
    change_log: str = ""


@dataclass
class ReloadEvent:
    """重载事件。"""
    event_id: str
    layer: str
    key: str
    old_version: int
    new_version: int
    affected_sessions: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# 热更新管理器
# ---------------------------------------------------------------------------


class InstructionHotReloader:
    """指令热更新管理器 —— 无需重启的指令更新。"""

    def __init__(self) -> None:
        self._instructions: dict[str, dict[str, InstructionSnapshot]] = {
            InstructionLayer.L1_SYSTEM.value: {},
            InstructionLayer.L2_SCENE.value: {},
            InstructionLayer.L3_AGENT.value: {},
        }
        self._history: list[ReloadEvent] = []
        self._active_sessions: dict[str, set[str]] = {}  # session_id → {指令快照 keys}
        self._global_version: int = 0

    # ---- 更新操作 ----

    def update(
        self,
        key: str,
        layer: str,
        content: str,
        *,
        updated_by: str = "",
        change_log: str = "",
    ) -> InstructionSnapshot:
        """更新一条指令。

        参数:
            key: 指令标识（场景key / agent_id / "global"）
            layer: 指令层级
            content: 新内容
            updated_by: 更新人
            change_log: 变更说明

        返回:
            更新后的快照
        """
        layer_key = self._normalize_layer(layer)
        old = self._instructions[layer_key].get(key)
        new_version = (old.version + 1) if old else 1

        snapshot = InstructionSnapshot(
            layer=layer_key,
            key=key,
            content=content,
            version=new_version,
            updated_by=updated_by,
            change_log=change_log,
        )

        self._instructions[layer_key][key] = snapshot
        self._global_version += 1

        logger.info(
            "instruction_updated layer=%s key=%s version=%d by=%s",
            layer_key, key, new_version, updated_by,
        )
        return snapshot

    def reload(self, *, force_all: bool = False) -> list[ReloadEvent]:
        """触发重载 —— 通知所有活跃会话指令已变更。

        返回受影响的会话列表。

        参数:
            force_all: 是否强制所有会话重载（否则仅通知有变更的会话）
        """
        events: list[ReloadEvent] = []

        for layer_key, instructions in self._instructions.items():
            for key, snapshot in instructions.items():
                affected = self._find_affected_sessions(layer_key, key, force_all)
                if affected or force_all:
                    event = ReloadEvent(
                        event_id=f"reload_{uuid.uuid4().hex[:8]}",
                        layer=layer_key,
                        key=key,
                        old_version=snapshot.version - 1,
                        new_version=snapshot.version,
                        affected_sessions=affected,
                    )
                    events.append(event)
                    self._history.append(event)

        if events:
            logger.info("instruction_reloaded events=%d sessions=%d",
                len(events),
                len({s for e in events for s in e.affected_sessions}),
            )

        return events

    # ---- 查询操作 ----

    def get(self, key: str, layer: str = "system") -> InstructionSnapshot | None:
        """获取指定指令的当前快照。"""
        return self._instructions.get(self._normalize_layer(layer), {}).get(key)

    def get_version(self, key: str, layer: str = "system") -> int:
        """获取指令版本号。"""
        snapshot = self.get(key, layer)
        return snapshot.version if snapshot else 0

    def list_all(self, layer: str = "") -> dict[str, InstructionSnapshot]:
        """列出所有指令。"""
        if layer:
            return dict(self._instructions.get(self._normalize_layer(layer), {}))
        result = {}
        for layer_instructions in self._instructions.values():
            result.update(layer_instructions)
        return result

    def is_stale(self, session_id: str, key: str, layer: str) -> bool:
        """检查会话使用的指令是否已过时。"""
        current = self.get(key, layer)
        if current is None:
            return False

        session_keys = self._active_sessions.get(session_id, set())
        session_version_key = f"{layer}:{key}:{current.version}"
        return session_version_key not in session_keys

    # ---- 会话管理 ----

    def register_session(self, session_id: str) -> None:
        """注册活跃会话（用于变更通知）。"""
        if session_id not in self._active_sessions:
            self._active_sessions[session_id] = set()

    def unregister_session(self, session_id: str) -> None:
        """注销会话。"""
        self._active_sessions.pop(session_id, None)

    def mark_session_synced(self, session_id: str, key: str, layer: str) -> None:
        """标记会话已同步最新指令。"""
        snapshot = self.get(key, layer)
        if snapshot is None:
            return

        if session_id not in self._active_sessions:
            self._active_sessions[session_id] = set()

        self._active_sessions[session_id].add(f"{layer}:{key}:{snapshot.version}")

    # ---- 历史 ----

    def history(self, limit: int = 20) -> list[ReloadEvent]:
        """获取重载历史。"""
        return self._history[-limit:]

    @property
    def global_version(self) -> int:
        return self._global_version

    # ---- 内部 ----

    def _find_affected_sessions(self, layer: str, key: str, force_all: bool) -> list[str]:
        """查找受影响的会话。"""
        if force_all:
            return list(self._active_sessions.keys())

        affected = []
        for session_id, keys in self._active_sessions.items():
            for session_key in keys:
                if session_key.startswith(f"{layer}:{key}:"):
                    affected.append(session_id)
                    break
        return affected

    @staticmethod
    def _normalize_layer(layer: str) -> str:
        mapping = {
            "L1": InstructionLayer.L1_SYSTEM.value,
            "L2": InstructionLayer.L2_SCENE.value,
            "L3": InstructionLayer.L3_AGENT.value,
            "system": InstructionLayer.L1_SYSTEM.value,
            "scene": InstructionLayer.L2_SCENE.value,
            "agent": InstructionLayer.L3_AGENT.value,
        }
        return mapping.get(layer, layer)
