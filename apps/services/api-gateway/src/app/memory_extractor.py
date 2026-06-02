"""记忆提取器 —— 从对话中自动抽取长期记忆三元组。

三层记忆架构：
- 短期记忆：会话内的消息窗口（已由 gateway_chat_service 实现）
- 长期记忆：用户偏好、事实、知识 → 自动提取 + 向量检索
- 工作记忆：Agent 执行中间状态 → 由 gateway_graph 的 ChatGraphState 承载

记忆提取流程：
1. 对话完成后，异步调用 LLM 提取 (subject, predicate, object) 三元组
2. 三元组存入 PostgreSQL + embedding 存入 Qdrant
3. 新对话开始时，基于问题检索相关记忆注入上下文

集成方式::

    from .memory_extractor import extract_memories, MemoryStore

    store = MemoryStore(db_session, qdrant_client)
    await extract_memories(user_id, messages, store)
"""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from shared.grounded_answering import compact_text

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class MemoryTriple:
    """记忆五元组 —— subject-predicate-object-importance-decay_rate。

    相比旧版 SPO 三元组的增强：
    - importance: 重要性评分 0-1（由 LLM 评估 + 使用频率加权）
    - decay_rate: 遗忘速率因子（基于 Ebbinghaus 遗忘曲线）
    - access_count: 被检索调用的次数
    """

    subject: str  # 主体（用户/话题）
    predicate: str  # 谓词（偏好/知道/需要/...）
    object: str  # 客体（具体内容）
    memory_type: str = "fact"  # preference / fact / knowledge
    confidence: float = 1.0  # 置信度 0-1
    importance: float = 0.5  # 重要性 0-1（新增）
    decay_rate: float = 0.1  # 遗忘速率 0-1，越高遗忘越快（新增）
    access_count: int = 0  # 被检索次数（新增）
    source_session_id: str = ""


@dataclass
class MemoryEntry:
    """持久化的记忆条目（增强版）。"""

    id: str
    user_id: str
    memory_type: str
    subject: str
    predicate: str
    object: str
    embedding_id: str  # Qdrant point id
    confidence: float
    importance: float = 0.5  # 重要性（新增）
    decay_rate: float = 0.1  # 遗忘速率（新增）
    access_count: int = 0  # 检索次数（新增）
    last_accessed_at: float = 0.0  # 最后检索时间（新增，用于衰减计算）
    source_session_id: str = ""
    version: int = 1
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def effective_importance(self) -> float:
        """计算考虑遗忘衰减后的有效重要性。

        使用 Ebbinghaus 遗忘曲线: R = e^(-t/S)
        其中 S = 相对记忆强度（importance 越高，遗忘越慢）。

        如果从未被访问过，则使用创建时间作为基准。
        """
        now = time.time()
        reference_time = self.last_accessed_at if self.last_accessed_at > 0 else self.created_at
        elapsed_hours = (now - reference_time) / 3600.0

        # 记忆强度：importance 越高 → 遗忘越慢
        # stability: 0.1 (极不稳定) ~ 10.0 (非常稳定)
        stability = 0.1 + self.importance * 9.9

        # 指数衰减
        decay_factor = math.exp(-elapsed_hours / (stability * 24.0))  # 以天为单位的半衰期
        return round(self.importance * decay_factor, 4)

    @property
    def effective_confidence(self) -> float:
        """考虑重要性衰减后的有效置信度。"""
        return round(self.confidence * (0.5 + 0.5 * self.effective_importance), 4)


# ---------------------------------------------------------------------------
# 记忆提取 Prompt
# ---------------------------------------------------------------------------

_MEMORY_EXTRACTION_PROMPT = """你是一个用户记忆提取器。从对话中提取值得长期保存的用户信息和知识。

## 提取规则
1. 只提取有长期价值的信息：
   - **preference（偏好）**: 用户的角色、习惯、喜欢的回答风格、常用知识库
   - **fact（事实）**: 用户提到的事实信息（公司、项目、部门、版本号等）
   - **knowledge（知识）**: 用户分享的专业知识或领域见解
2. 不要提取临时性的、仅对该轮对话有意义的信息
3. 不要提取已经在知识库中可以查到的内容
4. 每个三元组的 subject 是话题/主体，predicate 描述关系，object 是具体内容
5. **importance（重要性）**: 0-1 分值，评估该记忆对长期使用的重要程度：
   - 0.8-1.0: 用户核心身份/角色/长期偏好（如职位、主管产品）
   - 0.5-0.7: 有一定长期价值的信息（如常用版本、项目名）
   - 0.2-0.4: 一般事实信息（如一次性提到的背景信息）
   - 0.0-0.1: 临时信息（不建议长期存储）
6. 如果对话中没有值得长期保存的信息，返回空数组

## 输出格式
```json
{
  "memories": [
    {
      "subject": "用户角色",
      "predicate": "是",
      "object": "后端开发工程师",
      "memory_type": "preference",
      "confidence": 0.95,
      "importance": 0.85
    }
  ]
}
```

## 示例
用户说："我是负责支付系统的后端工程师，我们用的是 v3.0 版本，我更喜欢简洁的回答"

```json
{
  "memories": [
    {"subject": "用户角色", "predicate": "是", "object": "后端开发工程师", "memory_type": "preference", "confidence": 0.95, "importance": 0.90},
    {"subject": "用户", "predicate": "负责", "object": "支付系统", "memory_type": "fact", "confidence": 0.90, "importance": 0.85},
    {"subject": "当前使用版本", "predicate": "是", "object": "v3.0", "memory_type": "fact", "confidence": 0.85, "importance": 0.55},
    {"subject": "用户", "predicate": "偏好回答风格", "object": "简洁", "memory_type": "preference", "confidence": 0.90, "importance": 0.70}
  ]
}
```
"""

# 冲突解决 Prompt —— 当新旧记忆存在矛盾时
_MEMORY_CONFLICT_PROMPT = """你是一个记忆冲突仲裁员。当AI助手发现两条关于同一主题的用户记忆存在矛盾时，你需要判断应该保留哪条。

## 规则
- 更新、更具体的记忆优先
- 用户明确纠正的优先于之前推断的
- 如果无法判断，保留两条但降低置信度

## 已有记忆
{existing_memory}

## 新提取记忆
{new_memory}

## 输出格式
```json
{
  "action": "replace",
  "reason": "新记忆更具体且是用户明确表达",
  "merged_memory": {
    "subject": "...",
    "predicate": "...",
    "object": "...",
    "memory_type": "preference",
    "confidence": 0.95
  }
}
```

action 可选值: replace（用新的替换旧的）, keep_both（两条都保留）, merge（合并为一条）
"""


# ---------------------------------------------------------------------------
# 记忆提取器
# ---------------------------------------------------------------------------


class MemoryStore:
    """记忆持久化存储 —— 使用 PostgreSQL + Qdrant 双层存储。

    结构化数据存 PostgreSQL，向量 embedding 存 Qdrant 用于语义检索。
    """

    def __init__(self, db_session_factory: Any, qdrant_client: Any = None) -> None:
        self._db_factory = db_session_factory
        self._qdrant = qdrant_client
        self._embed_fn: Any = None  # lazy load

    async def upsert(self, entry: MemoryEntry) -> bool:
        """写入或更新一条记忆（冲突解决：同 subject+predicate 覆盖）。"""
        try:
            # 1. 检查冲突
            existing = await self._find_conflict(entry)
            if existing is not None:
                entry = await self._resolve_conflict(existing, entry)

            # 2. 写入 PostgreSQL
            await self._db_upsert(entry)

            # 3. 写入 Qdrant（如果有 embedding 能力）
            if self._qdrant is not None:
                await self._qdrant_upsert(entry)

            logger.debug("memory_upsert id=%s type=%s subject=%s", entry.id, entry.memory_type, entry.subject)
            return True
        except Exception as exc:
            logger.warning("memory_upsert_failed id=%s err=%s", entry.id, exc)
            return False

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        memory_type: str = "",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """检索与查询相关的用户记忆。

        优先使用 Qdrant 语义检索，fallback 到 PostgreSQL 关键词匹配。
        """
        if self._qdrant is not None and self._embed_fn is not None:
            return await self._qdrant_search(user_id, query, memory_type, limit)
        return await self._db_text_search(user_id, query, memory_type, limit)

    async def list_by_user(
        self,
        user_id: str,
        *,
        memory_type: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """列出用户的所有记忆条目。"""
        return await self._db_list(user_id, memory_type, limit, offset)

    async def deactivate(self, memory_id: str) -> bool:
        """停用一条记忆（软删除）。"""
        return await self._db_deactivate(memory_id)

    async def count(self, user_id: str) -> int:
        """统计用户记忆总数。"""
        return await self._db_count(user_id)

    # ---- 内部 ----

    async def _find_conflict(self, entry: MemoryEntry) -> MemoryEntry | None:
        """查找同 subject+predicate 的已有记忆。"""
        # 简化为查 PostgreSQL，实际实现需要连接数据库
        return None  # 占位

    async def _resolve_conflict(self, existing: MemoryEntry, new: MemoryEntry) -> MemoryEntry:
        """解决记忆冲突：保留更新的那一条。"""
        if new.updated_at > existing.updated_at:
            new.version = existing.version + 1
            return new
        existing.confidence = max(existing.confidence, new.confidence)
        return existing

    async def _db_upsert(self, entry: MemoryEntry) -> None:
        """写入 PostgreSQL。"""
        pass  # 由实际 DB 层实现

    async def _qdrant_upsert(self, entry: MemoryEntry) -> None:
        """写入 Qdrant。"""
        pass  # 由实际 Qdrant 层实现

    async def _qdrant_search(
        self, user_id: str, query: str, memory_type: str, limit: int
    ) -> list[MemoryEntry]:
        """Qdrant 语义检索。"""
        # 生成 query embedding 并在 Qdrant 中搜索
        return []

    async def _db_text_search(
        self, user_id: str, query: str, memory_type: str, limit: int
    ) -> list[MemoryEntry]:
        """PostgreSQL 文本匹配检索。"""
        return []

    async def _db_list(self, user_id: str, memory_type: str, limit: int, offset: int) -> list[MemoryEntry]:
        """PostgreSQL 分页列表。"""
        return []

    async def _db_deactivate(self, memory_id: str) -> bool:
        """PostgreSQL 软删除。"""
        return True

    async def _db_count(self, user_id: str) -> int:
        """PostgreSQL 计数。"""
        return 0


async def extract_memories(
    user_id: str,
    messages: list[dict[str, Any]],
    store: MemoryStore,
    *,
    build_chat_model_fn: Any = None,
    settings: Any = None,
    session_id: str = "",
) -> list[MemoryTriple]:
    """从对话消息中异步提取长期记忆。

    参数:
        user_id: 用户标识
        messages: 对话消息列表（最新一轮）
        store: 记忆持久化存储
        build_chat_model_fn: LLM 模型构建函数
        settings: LLM 配置
        session_id: 会话标识

    返回:
        提取到的记忆三元组列表
    """
    if build_chat_model_fn is None or settings is None:
        logger.warning("memory_extract_skip no_llm_config")
        return []

    # 构建对话文本
    conversation = _format_messages(messages)
    if not conversation.strip():
        return []

    try:
        chat_model = build_chat_model_fn(
            settings=settings,
            model=settings.model,
            temperature=0.0,
            max_tokens=min(settings.default_max_tokens, 800),
            streaming=False,
        )
        msgs = [
            SystemMessage(content=_MEMORY_EXTRACTION_PROMPT),
            HumanMessage(content=f"对话内容：\n{conversation}"),
        ]
        response = await chat_model.ainvoke(msgs)
        content = str(response.content or "").strip()

        parsed = _parse_json_response(content)
        raw_memories = list(parsed.get("memories") or [])

        triples: list[MemoryTriple] = []
        for raw in raw_memories:
            importance = float(raw.get("importance") or 0.5)
            confidence = float(raw.get("confidence") or 0.8)
            # 遗忘速率与重要性负相关：越重要 → 遗忘越慢
            decay_rate = round(0.3 * (1.0 - importance) + 0.02, 4)

            triple = MemoryTriple(
                subject=str(raw.get("subject") or ""),
                predicate=str(raw.get("predicate") or ""),
                object=str(raw.get("object") or ""),
                memory_type=str(raw.get("memory_type") or "fact"),
                confidence=confidence,
                importance=importance,
                decay_rate=decay_rate,
                source_session_id=session_id,
            )
            if triple.subject and triple.object:
                triples.append(triple)
                # 持久化（增强版五元组）
                entry = MemoryEntry(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    memory_type=triple.memory_type,
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    embedding_id=str(uuid.uuid4()),
                    confidence=triple.confidence,
                    importance=triple.importance,
                    decay_rate=triple.decay_rate,
                    access_count=0,
                    source_session_id=session_id,
                )
                await store.upsert(entry)

        logger.info(
            "memory_extracted user=%s count=%d session=%s",
            user_id,
            len(triples),
            session_id,
        )
        return triples
    except Exception as exc:
        logger.warning("memory_extract_failed user=%s err=%s", user_id, exc)
        return []


def _format_messages(messages: list[dict[str, Any]]) -> str:
    """将消息列表格式化为对话文本。"""
    lines: list[str] = []
    for msg in messages[-12:]:  # 只取最近 12 条
        role = str(msg.get("role") or "unknown")
        content = str(msg.get("content") or "")
        lines.append(f"[{role}]: {compact_text(content, 200)}")
    return "\n".join(lines)


def _parse_json_response(content: str) -> dict[str, Any]:
    """从 LLM 响应中提取 JSON。"""
    if "```json" in content:
        start = content.index("```json") + len("```json")
        end = content.index("```", start) if "```" in content[start:] else len(content)
        content = content[start:end].strip()
    elif "```" in content:
        start = content.index("```") + 3
        end = content.index("```", start) if "```" in content[start:] else len(content)
        content = content[start:end].strip()
    if "{" in content:
        start = content.index("{")
        end = content.rindex("}") + 1
        content = content[start:end]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}
