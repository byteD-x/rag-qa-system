"""多 Agent 协作编排器 —— Orchestrator-Worker 模式。

核心能力：
- Orchestrator 分析任务，拆解为子任务并分派给 Worker
- Worker 独立执行子任务（各自的工具集 + 知识范围）
- 结果聚合与去重（合并 Worker 结果）
- Worker 复用池（避免重复创建 Agent 上下文）
- 超时与容错（单个 Worker 失败不影响整体）

使用方式::

    from .agent_orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator()
    plan = await orchestrator.plan(question, scope)
    results = await orchestrator.execute(plan)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class WorkerType(str, Enum):
    """Worker 类型。"""
    RETRIEVER = "retriever"      # 检索型 Worker
    ANALYZER = "analyzer"        # 分析型 Worker
    COMPARATOR = "comparator"    # 对比型 Worker
    CALCULATOR = "calculator"    # 计算型 Worker
    SYNTHESIZER = "synthesizer"  # 综合型 Worker（最后执行）


@dataclass
class SubTask:
    """子任务定义。"""
    id: str = ""
    description: str = ""             # 子任务描述
    question: str = ""                # 子任务的具体问题
    worker_type: str = "retriever"    # Worker 类型
    depends_on: list[str] = field(default_factory=list)  # 依赖的子任务 ID
    assigned_tools: list[str] = field(default_factory=list)  # 分配的工具
    assigned_corpus_ids: list[str] = field(default_factory=list)  # 分配的知识库
    priority: int = 0                 # 优先级（越高越先执行）


@dataclass
class ExecutionPlan:
    """执行计划。"""
    plan_id: str = ""
    question: str = ""                # 原始问题
    sub_tasks: list[SubTask] = field(default_factory=list)
    execution_order: list[list[str]] = field(default_factory=list)  # 并行组 [["t1","t2"],["t3"]]
    estimated_time_ms: float = 0.0
    created_at: float = 0.0


@dataclass
class WorkerResult:
    """Worker 执行结果。"""
    task_id: str = ""
    success: bool = False
    evidence: list[dict[str, Any]] = field(default_factory=list)
    answer_fragment: str = ""         # Worker 产生的答案片段
    error: str = ""
    worker_type: str = ""
    execution_time_ms: float = 0.0
    tool_calls_made: int = 0


@dataclass
class OrchestrationResult:
    """编排执行结果。"""
    plan: ExecutionPlan | None = None
    worker_results: list[WorkerResult] = field(default_factory=list)
    aggregated_evidence: list[dict[str, Any]] = field(default_factory=list)
    aggregated_answer: str = ""
    total_time_ms: float = 0.0
    success_count: int = 0
    failure_count: int = 0


# ---------------------------------------------------------------------------
# 编排器
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """多 Agent 协作编排器。

    执行流程：
    1. plan(): 分析问题 → 拆解为子任务 → 生成执行计划
    2. execute(): 按拓扑排序并行执行子任务 → 聚合结果
    3. synthesize(): 综合所有 Worker 结果 → 生成最终回答
    """

    # 单 Worker 超时
    WORKER_TIMEOUT_SECONDS = 30.0
    # 最大并行 Worker 数
    MAX_PARALLEL_WORKERS = 4

    def __init__(
        self,
        *,
        worker_timeout: float = 30.0,
        max_parallel: int = 4,
    ) -> None:
        self.WORKER_TIMEOUT_SECONDS = worker_timeout
        self.MAX_PARALLEL_WORKERS = max_parallel

    # ---- 规划阶段 ----

    async def plan(
        self,
        question: str,
        scope: dict[str, Any],
        *,
        available_tools: list[str] | None = None,
    ) -> ExecutionPlan:
        """分析问题并生成执行计划。

        参数:
            question: 用户问题
            scope: 知识范围信息
            available_tools: 可用工具列表

        返回:
            ExecutionPlan
        """
        import uuid

        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4())[:8],
            question=question,
            created_at=time.time(),
        )

        # 基于问题特征自动拆解子任务
        sub_tasks = self._decompose_question(question, scope, available_tools or [])
        plan.sub_tasks = sub_tasks
        plan.execution_order = self._build_execution_order(sub_tasks)

        logger.debug(
            "orchestrator_plan plan_id=%s tasks=%d groups=%d",
            plan.plan_id, len(sub_tasks), len(plan.execution_order),
        )
        return plan

    def _decompose_question(
        self,
        question: str,
        scope: dict[str, Any],
        available_tools: list[str],
    ) -> list[SubTask]:
        """基于规则的问题拆解。"""
        question_lower = question.lower()
        tasks: list[SubTask] = []
        task_idx = 0

        # 检测对比模式 → COMPARATOR
        compare_keywords = ["对比", "比较", "区别", "差异", "vs", "和", "与", "不同"]
        if any(kw in question_lower for kw in compare_keywords):
            tasks.append(SubTask(
                id=f"task-{task_idx}",
                description="检索对比双方的证据",
                question=question,
                worker_type=WorkerType.COMPARATOR.value,
                assigned_tools=available_tools,
                priority=10,
            ))
            task_idx += 1

        # 检测计算模式 → CALCULATOR
        calc_keywords = ["计算", "多少", "总共", "合计", "汇总", "统计", "百分比", "平均"]
        if any(kw in question_lower for kw in calc_keywords):
            tasks.append(SubTask(
                id=f"task-{task_idx}",
                description="执行数据计算",
                question=question,
                worker_type=WorkerType.CALCULATOR.value,
                assigned_tools=[t for t in available_tools if "calc" in t.lower() or "math" in t.lower()],
                priority=5,
            ))
            task_idx += 1

        # 默认：RETRIEVER（检索知识库）
        tasks.append(SubTask(
            id=f"task-{task_idx}",
            description="检索知识库获取相关证据",
            question=question,
            worker_type=WorkerType.RETRIEVER.value,
            assigned_tools=[t for t in available_tools if "search" in t.lower()],
            assigned_corpus_ids=list(scope.get("corpus_ids") or []),
            priority=8,
        ))
        task_idx += 1

        # 如果涉及多知识库 → 添加 ANALYZER
        corpus_count = len(list(scope.get("corpus_ids") or []))
        if corpus_count > 1:
            tasks.append(SubTask(
                id=f"task-{task_idx}",
                description="跨知识库分析整合",
                question=question,
                worker_type=WorkerType.ANALYZER.value,
                depends_on=[f"task-0"],
                priority=6,
            ))
            task_idx += 1

        # 最后：SYNTHESIZER（综合所有结果）
        dep_ids = [t.id for t in tasks]
        tasks.append(SubTask(
            id=f"task-{task_idx}",
            description="综合所有子任务结果生成回答",
            question=question,
            worker_type=WorkerType.SYNTHESIZER.value,
            depends_on=dep_ids,
            priority=1,
        ))

        return tasks

    def _build_execution_order(self, sub_tasks: list[SubTask]) -> list[list[str]]:
        """拓扑排序生成并行执行组。"""
        if not sub_tasks:
            return []

        completed: set[str] = set()
        remaining = list(sub_tasks)
        groups: list[list[str]] = []

        while remaining:
            group: list[str] = []
            for task in list(remaining):
                if all(dep in completed for dep in task.depends_on):
                    group.append(task.id)
                    remaining.remove(task)
            if not group:
                # 循环依赖保护
                break
            groups.append(sorted(group, key=lambda tid: -next(
                (t.priority for t in sub_tasks if t.id == tid), 0
            )))
            completed.update(group)

        return groups

    # ---- 执行阶段 ----

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        worker_fn_map: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """按执行计划并行执行子任务。

        参数:
            plan: 执行计划
            worker_fn_map: Worker 类型 → 执行函数 映射

        返回:
            OrchestrationResult
        """
        started = time.perf_counter()
        results: dict[str, WorkerResult] = {}

        worker_fn_map = worker_fn_map or {}

        for group in plan.execution_order:
            # 并行执行同一组内的任务
            group_results = await asyncio.gather(
                *[
                    self._execute_subtask(
                        next(t for t in plan.sub_tasks if t.id == task_id),
                        worker_fn_map,
                    )
                    for task_id in group
                ],
                return_exceptions=True,
            )

            for task_id, result in zip(group, group_results):
                if isinstance(result, Exception):
                    results[task_id] = WorkerResult(
                        task_id=task_id,
                        success=False,
                        error=str(result),
                        execution_time_ms=0,
                    )
                else:
                    results[task_id] = result

        # 汇总
        worker_results = list(results.values())
        aggregated_evidence = self._aggregate_evidence(worker_results)
        aggregated_answer = self._synthesize_answer(worker_results, plan.question)

        orchestration = OrchestrationResult(
            plan=plan,
            worker_results=worker_results,
            aggregated_evidence=aggregated_evidence,
            aggregated_answer=aggregated_answer,
            total_time_ms=round((time.perf_counter() - started) * 1000, 3),
            success_count=sum(1 for r in worker_results if r.success),
            failure_count=sum(1 for r in worker_results if not r.success),
        )

        logger.info(
            "orchestrator_complete plan_id=%s success=%d fail=%d time_ms=%.1f",
            plan.plan_id, orchestration.success_count,
            orchestration.failure_count, orchestration.total_time_ms,
        )
        return orchestration

    async def _execute_subtask(
        self,
        task: SubTask,
        worker_fn_map: dict[str, Any],
    ) -> WorkerResult:
        """执行单个子任务。"""
        started = time.perf_counter()
        worker_type = task.worker_type

        worker_fn = worker_fn_map.get(worker_type) or worker_fn_map.get("retriever")
        if worker_fn is None:
            return WorkerResult(
                task_id=task.id,
                success=False,
                error=f"无 {worker_type} 类型的 Worker 函数",
                worker_type=worker_type,
                execution_time_ms=round((time.perf_counter() - started) * 1000, 3),
            )

        try:
            result = await asyncio.wait_for(
                worker_fn(task),
                timeout=self.WORKER_TIMEOUT_SECONDS,
            )
            if isinstance(result, WorkerResult):
                result.execution_time_ms = round((time.perf_counter() - started) * 1000, 3)
                return result
            # 简化：将返回值包装为 WorkerResult
            return WorkerResult(
                task_id=task.id,
                success=True,
                evidence=result if isinstance(result, list) else [],
                worker_type=worker_type,
                execution_time_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        except asyncio.TimeoutError:
            return WorkerResult(
                task_id=task.id,
                success=False,
                error=f"Worker {worker_type} 超时",
                worker_type=worker_type,
                execution_time_ms=self.WORKER_TIMEOUT_SECONDS * 1000,
            )
        except Exception as exc:
            return WorkerResult(
                task_id=task.id,
                success=False,
                error=str(exc),
                worker_type=worker_type,
                execution_time_ms=round((time.perf_counter() - started) * 1000, 3),
            )

    # ---- 聚合阶段 ----

    @staticmethod
    def _aggregate_evidence(worker_results: list[WorkerResult]) -> list[dict[str, Any]]:
        """聚合去重所有 Worker 的证据。"""
        seen_ids: set[str] = set()
        aggregated: list[dict[str, Any]] = []
        for wr in worker_results:
            if not wr.success:
                continue
            for ev in wr.evidence:
                ev_id = str(ev.get("chunk_id") or ev.get("id") or hash(str(ev)))
                if ev_id not in seen_ids:
                    seen_ids.add(ev_id)
                    aggregated.append(ev)
        return aggregated

    @staticmethod
    def _synthesize_answer(worker_results: list[WorkerResult], question: str) -> str:
        """综合 Worker 结果生成最终回答。"""
        fragments = [
            wr.answer_fragment
            for wr in worker_results
            if wr.success and wr.answer_fragment
        ]
        if not fragments:
            success_count = sum(1 for wr in worker_results if wr.success)
            if success_count == 0:
                return f"抱歉，无法完成'{question}'的分析，所有子任务执行失败。"
            return f"已完成 {success_count} 项分析，但未生成具体回答。"
        return "\n\n".join(fragments)
