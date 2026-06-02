"""RAG-QA Python SDK —— 面向 Python 开发者的轻量客户端。

安装: pip install rag-qa-client
要求: Python >= 3.10

快速开始::

    from rag_qa_client import RAGQAClient

    client = RAGQAClient(base_url="http://localhost:8080", api_key="your-key")

    # 同步问答
    answer = client.ask("退款流程是什么？", scope={"corpus_ids": ["kb:abc"]})

    # 流式问答
    async for chunk in client.ask_stream("退款流程是什么？"):
        print(chunk, end="", flush=True)

    # 知识库管理
    bases = client.list_knowledge_bases()
    docs = client.list_documents("kb:abc")

    # Agent 模式
    answer = client.ask("比较 v2 和 v3 的退款差异", execution_mode="agent")
"""

from .client import RAGQAClient, AsyncRAGQAClient
from .types import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    KnowledgeBase,
    Document,
    Citation,
    AgentProfile,
    PromptTemplate,
    SceneTemplate,
)

__version__ = "0.1.0"
__all__ = [
    "RAGQAClient",
    "AsyncRAGQAClient",
    "ChatRequest",
    "ChatResponse",
    "ChatStreamChunk",
    "KnowledgeBase",
    "Document",
    "Citation",
    "AgentProfile",
    "PromptTemplate",
    "SceneTemplate",
]
