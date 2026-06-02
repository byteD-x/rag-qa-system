"""任务拆解引擎 —— 将复杂问题分解为可并行/串行执行的子任务 DAG。

核心流程：
1. 问题复杂度评估（简单/中等/复杂）
2. 复杂度 ≥ 3 时触发 LLM 拆解，输出子任务列表 + 依赖关系
3. 构建执行 DAG，拓扑排序识别并行组
4. 驱动并行执行引擎，子任务失败时动态重规划

与 gateway_agent.py 集成：
    from .task_decomposer import TaskDecomposer, DecompositionResult

    decomposer = TaskDecomposer(build_chat_model_fn=build_chat_model, settings=settings)
    result = await decomposer.decompose(question="...", context={...})
    if result.requires_decomposition:
        dag = result.dag  # TaskDAG 实例
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from shared.grounded_answering import compact_text

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SubTask:
    """拆解后的子任务"""

    id: str  # 唯一标识，如 "task-1"
    description: str  # 子任务的自然语言描述
    question: str  # 子任务对应的检索/推理问题
    depends_on: list[str] = field(default_factory=list)  # 依赖的其他子任务 ID
    category: str = "retrieval"  # retrieval / reasoning / compute / verification
    priority: int = 0  # 优先级，数字越大越优先
    expected_tool: str = ""  # 预期使用的工具名
    verification_hint: str = ""  # 验证提示（用于结果自检）


@dataclass
class DecompositionResult:
    """任务拆解结果"""

    original_question: str
    complexity_score: int  # 1-5，1=极简单，5=极复杂
    requires_decomposition: bool  # 是否需要拆解（≥3 触发）
    sub_tasks: list[SubTask] = field(default_factory=list)
    execution_order: list[list[str]] = field(default_factory=list)  # [[task-1,task-2],[task-3]] 表示并行组
    reasoning: str = ""  # LLM 拆解理由
    error: str = ""


# ---------------------------------------------------------------------------
# 复杂度分类器
# ---------------------------------------------------------------------------


_COMPLEXITY_INDICATORS = {
    # 低复杂度信号（简单问候、单事实查询）
    "low": [
        "你好", "谢谢", "再见", "什么是", "多少", "谁",
        "几点", "哪里", "什么时候", "怎么拼",
        "hello", "hi", "thanks", "bye",
    ],
    # 高复杂度信号（多步推理、比较、条件判断）
    "high": [
        "比较", "对比", "差异", "区别", "vs",
        "如果", "假如", "假设", "条件",
        "第一步", "第二步", "然后", "接着", "最后",
        "总结", "归纳", "分析", "评估", "判断",
        "为什么", "怎么计算", "如何得出",
        "同时", "以及", "还有", "包括",
        "先", "再", "之后",
        "列出所有", "找出所有",
    ],
}

# 问题长度阈值
_SHORT_THRESHOLD = 20  # 字符
_LONG_THRESHOLD = 120  # 字符


def assess_complexity(question: str, context: dict[str, Any] | None = None) -> int:
    """快速评估问题复杂度（1-5），不依赖 LLM 调用。

    评估维度：
    - 问题长度
    - 关键词信号（多步推理、比较、条件）
    - 上下文复杂度（多知识库、版本冲突）
    """
    q = str(question or "").strip()
    score = 1

    # 长度维度
    q_len = len(q)
    if q_len <= _SHORT_THRESHOLD:
        score += 0
    elif q_len <= _LONG_THRESHOLD:
        score += 1
    else:
        score += 2

    # 高复杂度关键词计数
    high_count = sum(1 for kw in _COMPLEXITY_INDICATORS["high"] if kw in q)
    if high_count >= 3:
        score += 2
    elif high_count >= 1:
        score += 1

    # 低复杂度信号降权（仅当问题很短时）
    if q_len <= _SHORT_THRESHOLD:
        low_count = sum(1 for kw in _COMPLEXITY_INDICATORS["low"] if kw in q)
        if low_count >= 1 and high_count == 0:
            score = max(1, score - 1)

    # 上下文信号
    ctx = context or {}
    corpus_count = len(list(ctx.get("corpus_ids") or []))
    if corpus_count > 3:
        score += 1
    if ctx.get("has_version_conflict"):
        score += 1

    return min(5, max(1, score))


# ---------------------------------------------------------------------------
# 任务拆解器
# ---------------------------------------------------------------------------


_DECOMPOSITION_SYSTEM_PROMPT = """你是一个任务拆解专家。你需要将用户的复杂问题拆解为可独立执行的子任务。

## 输出格式
严格按以下 JSON 格式输出：
```json
{
  "requires_decomposition": true,
  "reasoning": "拆解理由（一句话）",
  "sub_tasks": [
    {
      "id": "task-1",
      "description": "子任务简述",
      "question": "子任务具体问题（可直接用于检索）",
      "depends_on": [],
      "category": "retrieval",
      "expected_tool": "search_scope"
    }
  ]
}
```

## 拆解规则
1. 每个子任务应能独立检索或推理，不依赖其他子任务的"中间推理结果"
2. 如果子任务 B 的检索需要子任务 A 的结果作为输入，在 depends_on 中声明
3. category 可选值：retrieval（检索类）、reasoning（推理类）、compute（计算类）、verification（验证类）
4. 子任务数量控制在 2-6 个
5. 如果问题足够简单不需要拆解，requires_decomposition 设为 false，sub_tasks 为空数组
6. 子任务 question 必须具体、可操作，包含必要的限定条件

## 示例
用户问题："请比较 v2.0 和 v3.0 版本中关于退款流程的规定差异，并计算两个版本各涉及多少章节"

```json
{
  "requires_decomposition": true,
  "reasoning": "需要分别检索两个版本的内容，再进行比较和计数",
  "sub_tasks": [
    {
      "id": "task-1",
      "description": "检索 v2.0 中退款流程规定",
      "question": "v2.0 版本中退款流程的完整规定",
      "depends_on": [],
      "category": "retrieval",
      "expected_tool": "search_scope"
    },
    {
      "id": "task-2",
      "description": "检索 v3.0 中退款流程规定",
      "question": "v3.0 版本中退款流程的完整规定",
      "depends_on": [],
      "category": "retrieval",
      "expected_tool": "search_scope"
    },
    {
      "id": "task-3",
      "description": "比较两个版本的退款流程差异",
      "question": "v2.0 和 v3.0 中退款流程规定的具体差异点",
      "depends_on": ["task-1", "task-2"],
      "category": "reasoning",
      "expected_tool": ""
    },
    {
      "id": "task-4",
      "description": "统计各版本涉及的章节数量",
      "question": "v2.0 和 v3.0 各涉及多少个章节",
      "depends_on": ["task-1", "task-2"],
      "category": "compute",
      "expected_tool": "calculator"
    }
  ]
}
```
"""


class TaskDecomposer:
    """任务拆解引擎 —— 评估问题复杂度并按需拆解为子任务 DAG。"""

    def __init__(
        self,
        *,
        build_chat_model_fn: Callable,
        settings: Any,
        complexity_threshold: int = 3,
        max_sub_tasks: int = 6,
    ) -> None:
        self._build_chat_model = build_chat_model_fn
        self._settings = settings
        self._threshold = complexity_threshold
        self._max_sub_tasks = max_sub_tasks

    async def decompose(
        self,
        question: str,
        *,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        force: bool = False,
    ) -> DecompositionResult:
        """评估问题复杂度并按需拆解。

        参数:
            question: 用户原始问题
            context: 当前上下文（知识库范围、版本信息等）
            history: 历史消息
            force: 强制拆解（忽略复杂度阈值）
        返回:
            DecompositionResult
        """
        ctx = context or {}
        q = str(question or "").strip()

        # Step 1: 快速复杂度评估（不调用 LLM）
        complexity = assess_complexity(q, ctx)

        if not force and complexity < self._threshold:
            logger.info(
                "task_decomposer_skip complexity=%d threshold=%d question=%s",
                complexity,
                self._threshold,
                compact_text(q, 80),
            )
            return DecompositionResult(
                original_question=q,
                complexity_score=complexity,
                requires_decomposition=False,
                reasoning="复杂度未达阈值，跳过拆解",
            )

        # Step 2: LLM 拆解
        try:
            result = await self._llm_decompose(q, ctx, history)
            result.complexity_score = complexity
            return result
        except Exception as exc:
            logger.warning("task_decomposer_llm_failed err=%s", exc)
            return DecompositionResult(
                original_question=q,
                complexity_score=complexity,
                requires_decomposition=False,
                error=f"LLM 拆解失败: {exc}",
            )

    async def _llm_decompose(
        self,
        question: str,
        context: dict[str, Any],
        history: list[dict[str, Any]] | None,
    ) -> DecompositionResult:
        """调用 LLM 进行任务拆解。"""
        ctx_desc = ""
        corpus_ids = list(context.get("corpus_ids") or [])
        if corpus_ids:
            ctx_desc += f"\n当前可检索的知识库数量: {len(corpus_ids)}"
        if context.get("has_version_conflict"):
            ctx_desc += "\n注意：存在版本冲突，需要区分版本检索。"
        if context.get("execution_mode"):
            ctx_desc += f"\n执行模式: {context['execution_mode']}"

        system_prompt = _DECOMPOSITION_SYSTEM_PROMPT
        user_prompt = f"""用户问题：
{question}
{ctx_desc}

请评估是否需要拆解，并输出 JSON。"""

        chat_model = self._build_chat_model(
            settings=self._settings,
            model=self._settings.model,
            temperature=0.1,
            max_tokens=min(self._settings.default_max_tokens, 1500),
            streaming=False,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = await chat_model.ainvoke(messages)
        content = str(response.content or "").strip()

        # 解析 JSON（容错处理）
        parsed = _parse_json_response(content)
        return _build_result(question, parsed, self._max_sub_tasks)


def _parse_json_response(content: str) -> dict[str, Any]:
    """从 LLM 响应中提取 JSON，容错处理。"""
    # 尝试提取 ```json ``` 块
    if "```json" in content:
        start = content.index("```json") + len("```json")
        end = content.index("```", start) if "```" in content[start:] else len(content)
        content = content[start:end].strip()
    elif "```" in content:
        start = content.index("```") + 3
        end = content.index("```", start) if "```" in content[start:] else len(content)
        content = content[start:end].strip()

    # 尝试找 JSON 对象边界
    if "{" in content:
        start = content.index("{")
        end = content.rindex("}") + 1
        content = content[start:end]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"requires_decomposition": False, "sub_tasks": [], "reasoning": "JSON解析失败"}


def _build_result(
    question: str,
    parsed: dict[str, Any],
    max_sub_tasks: int,
) -> DecompositionResult:
    """从解析后的 JSON 构建 DecompositionResult。"""
    requires = bool(parsed.get("requires_decomposition", False))
    raw_tasks = list(parsed.get("sub_tasks") or [])[:max_sub_tasks]

    sub_tasks: list[SubTask] = []
    for raw in raw_tasks:
        st = SubTask(
            id=str(raw.get("id") or f"task-{len(sub_tasks)+1}"),
            description=str(raw.get("description") or ""),
            question=str(raw.get("question") or ""),
            depends_on=[str(d).strip() for d in list(raw.get("depends_on") or []) if str(d).strip()],
            category=str(raw.get("category") or "retrieval"),
            priority=int(raw.get("priority") or 0),
            expected_tool=str(raw.get("expected_tool") or ""),
            verification_hint=str(raw.get("verification_hint") or ""),
        )
        sub_tasks.append(st)

    # 构建并行执行组（拓扑排序）
    execution_order = _build_execution_order(sub_tasks)

    return DecompositionResult(
        original_question=question,
        complexity_score=0,  # 外部设置
        requires_decomposition=requires and len(sub_tasks) > 0,
        sub_tasks=sub_tasks,
        execution_order=execution_order,
        reasoning=str(parsed.get("reasoning") or ""),
    )


def _build_execution_order(sub_tasks: list[SubTask]) -> list[list[str]]:
    """基于依赖关系，拓扑排序生成并行执行组。

    同组内的子任务无相互依赖，可以并行执行。
    """
    if not sub_tasks:
        return []

    task_ids = {t.id for t in sub_tasks}
    deps: dict[str, set[str]] = {}
    for t in sub_tasks:
        deps[t.id] = {d for d in t.depends_on if d in task_ids}

    order: list[list[str]] = []
    completed: set[str] = set()
    remaining = set(task_ids)

    max_iterations = len(sub_tasks) + 1
    for _ in range(max_iterations):
        ready = [tid for tid in remaining if deps.get(tid, set()).issubset(completed)]
        if not ready:
            # 剩余任务有循环依赖或外部依赖，全放入下一组
            if remaining:
                order.append(sorted(remaining))
            break
        order.append(sorted(ready))
        completed.update(ready)
        remaining -= set(ready)
        if not remaining:
            break

    return order
