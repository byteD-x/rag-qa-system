"""RAG-QA SDK 数据类型定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChatRequest:
    """聊天请求"""

    question: str
    session_id: str = ""
    scope: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "grounded"  # grounded / agent
    focus_hint: dict[str, Any] = field(default_factory=dict)
    agent_profile_id: str = ""
    instruction_override: dict[str, Any] = field(default_factory=dict)


@dataclass
class Citation:
    """引用证据"""

    index: int
    document_title: str = ""
    section_title: str = ""
    quote: str = ""
    document_id: str = ""
    score: float = 0.0
    version_label: str = ""


@dataclass
class ChatResponse:
    """聊天响应"""

    answer: str
    answer_mode: str = ""
    execution_mode: str = ""
    citations: list[Citation] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    latency: dict[str, Any] = field(default_factory=dict)
    message_id: str = ""
    trace_id: str = ""
    retrieval: dict[str, Any] = field(default_factory=dict)
    agent_events: list[dict[str, Any]] = field(default_factory=list)
    reflection: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatStreamChunk:
    """流式聊天块"""

    event: str  # delta / done / error / tool_call
    content: str = ""
    citations: list[Citation] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class KnowledgeBase:
    """知识库"""

    id: str
    name: str
    description: str = ""
    category: str = ""
    document_count: int = 0
    created_at: str = ""


@dataclass
class Document:
    """文档"""

    id: str
    file_name: str
    title: str = ""
    status: str = ""
    version_label: str = ""
    version_number: int = 0
    is_current_version: bool = False
    corpus_id: str = ""
    base_id: str = ""
    created_at: str = ""


@dataclass
class AgentProfile:
    """Agent配置"""

    id: str
    name: str
    description: str = ""
    persona_prompt: str = ""
    enabled_tools: list[str] = field(default_factory=list)
    default_corpus_ids: list[str] = field(default_factory=list)
    scene_template_key: str = ""


@dataclass
class PromptTemplate:
    """Prompt模板"""

    id: str
    name: str
    content: str
    visibility: str = "personal"
    tags: list[str] = field(default_factory=list)
    favorite: bool = False


@dataclass
class SceneTemplate:
    """场景模板"""

    key: str
    name: str
    description: str
    icon: str
    recommended_tools: list[str] = field(default_factory=list)
    model_routing: str = "grounded"
    model_tier: str = "standard"
    tags: list[str] = field(default_factory=list)
