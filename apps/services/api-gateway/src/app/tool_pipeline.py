"""工具链编排引擎。

核心能力：
- DSL 定义工具链：顺序执行 / 并行执行 / 条件分支 / 循环
- 数据流传递：上游工具输出 → 下游工具输入
- 错误处理：单个节点失败可配置为 skip / retry / abort
- 可观测：每个节点的执行状态、耗时、输入输出记录

使用方式::

    from .tool_pipeline import ToolPipeline, Step, PipelineResult

    pipeline = ToolPipeline()
    pipeline.add(Step("search", tool="search_scope", inputs={"query": "$question"}))
    pipeline.add(Step("analyze", tool="analyze_data", inputs={"data": "$search.results"}))
    result = await pipeline.run(context={"question": "..."})
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class StepType(str, Enum):
    """步骤类型。"""
    TOOL = "tool"          # 调用已注册工具
    CONDITION = "condition"  # 条件分支
    PARALLEL = "parallel"   # 并行执行子步骤
    TRANSFORM = "transform"  # 数据转换（纯函数）


class ErrorPolicy(str, Enum):
    """步骤失败策略。"""
    ABORT = "abort"       # 终止整个管道
    SKIP = "skip"         # 跳过该步骤继续
    RETRY = "retry"       # 重试后继续
    DEFAULT_VALUE = "default_value"  # 使用默认值继续


@dataclass
class Step:
    """管道步骤定义。"""

    name: str                           # 步骤名（唯一标识）
    step_type: str = "tool"             # StepType
    tool: str = ""                      # 工具名（step_type=tool 时）
    inputs: dict[str, str] = field(default_factory=dict)  # 输入映射 {param: "$ref"}
    condition: str = ""                 # 条件表达式（step_type=condition 时）
    then_steps: list[Step] = field(default_factory=list)    # 条件为真时的子步骤
    else_steps: list[Step] = field(default_factory=list)    # 条件为假时的子步骤
    transform_fn: Callable | None = None  # 转换函数（step_type=transform 时）
    parallel_steps: list[Step] = field(default_factory=list)  # 并行子步骤
    on_error: str = "abort"             # ErrorPolicy
    max_retries: int = 1
    timeout_seconds: float = 30.0
    depends_on: list[str] = field(default_factory=list)
    output_key: str = ""                # 输出保存的 key（默认用 step name）


@dataclass
class StepResult:
    """步骤执行结果。"""

    step_name: str = ""
    success: bool = False
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    step_type: str = ""
    skipped: bool = False


@dataclass
class PipelineResult:
    """管道执行结果。"""

    pipeline_id: str = ""
    success: bool = False
    step_results: list[StepResult] = field(default_factory=list)
    final_output: Any = None
    total_time_ms: float = 0.0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# 工具链管道
# ---------------------------------------------------------------------------


class ToolPipeline:
    """工具链编排管道 —— 定义并执行多步骤工具调用。"""

    def __init__(self, *, name: str = "", tool_executor: Any = None) -> None:
        self._name = name or f"pipeline_{uuid.uuid4().hex[:6]}"
        self._steps: list[Step] = []
        self._tool_executor = tool_executor  # 实际执行工具的函数

    def add(self, step: Step) -> None:
        """添加步骤到管道。"""
        self._steps.append(step)

    def add_step(
        self,
        name: str,
        tool: str = "",
        inputs: dict[str, str] | None = None,
        *,
        depends_on: list[str] | None = None,
        on_error: str = "abort",
        output_key: str = "",
    ) -> Step:
        """便捷方法：添加工具调用步骤。"""
        step = Step(
            name=name,
            step_type=StepType.TOOL.value if tool else StepType.TRANSFORM.value,
            tool=tool,
            inputs=inputs or {},
            depends_on=depends_on or [],
            on_error=on_error,
            output_key=output_key or name,
        )
        self._steps.append(step)
        return step

    def add_condition(
        self,
        name: str,
        condition: str,
        then_steps: list[Step],
        else_steps: list[Step] | None = None,
        *,
        depends_on: list[str] | None = None,
    ) -> Step:
        """便捷方法：添加条件分支步骤。"""
        step = Step(
            name=name,
            step_type=StepType.CONDITION.value,
            condition=condition,
            then_steps=then_steps,
            else_steps=else_steps or [],
            depends_on=depends_on or [],
        )
        self._steps.append(step)
        return step

    def add_parallel(
        self,
        name: str,
        parallel_steps: list[Step],
        *,
        depends_on: list[str] | None = None,
    ) -> Step:
        """便捷方法：添加并行执行步骤组。"""
        step = Step(
            name=name,
            step_type=StepType.PARALLEL.value,
            parallel_steps=parallel_steps,
            depends_on=depends_on or [],
        )
        self._steps.append(step)
        return step

    async def run(self, context: dict[str, Any]) -> PipelineResult:
        """执行管道。

        参数:
            context: 初始上下文（包含变量和工具执行器）

        返回:
            PipelineResult
        """
        started = time.perf_counter()
        pipeline_id = uuid.uuid4().hex[:8]
        results: dict[str, StepResult] = {}

        try:
            for step in self._steps:
                result = await self._execute_step(step, context, results)
                results[step.name] = result

                if not result.success and not result.skipped:
                    if step.on_error == ErrorPolicy.ABORT.value:
                        raise RuntimeError(f"步骤 {step.name} 失败: {result.error}")
                    elif step.on_error == ErrorPolicy.RETRY.value:
                        for retry in range(step.max_retries):
                            result = await self._execute_step(step, context, results)
                            if result.success:
                                break
                            result.retry_count = retry + 1
                        results[step.name] = result
                        if not result.success:
                            raise RuntimeError(f"步骤 {step.name} 重试 {step.max_retries} 次后仍失败")

                # 保存输出到上下文
                if result.success and not result.skipped:
                    output_key = step.output_key or step.name
                    context[output_key] = result.output

        except Exception as exc:
            total_ms = round((time.perf_counter() - started) * 1000, 3)
            return PipelineResult(
                pipeline_id=pipeline_id,
                success=False,
                step_results=list(results.values()),
                total_time_ms=total_ms,
                steps_completed=sum(1 for r in results.values() if r.success),
                steps_failed=sum(1 for r in results.values() if not r.success and not r.skipped),
                steps_skipped=sum(1 for r in results.values() if r.skipped),
                error=str(exc),
            )

        total_ms = round((time.perf_counter() - started) * 1000, 3)
        return PipelineResult(
            pipeline_id=pipeline_id,
            success=True,
            step_results=list(results.values()),
            final_output=context,
            total_time_ms=total_ms,
            steps_completed=sum(1 for r in results.values() if r.success),
            steps_failed=sum(1 for r in results.values() if not r.success and not r.skipped),
            steps_skipped=sum(1 for r in results.values() if r.skipped),
        )

    async def _execute_step(
        self,
        step: Step,
        context: dict[str, Any],
        previous_results: dict[str, StepResult],
    ) -> StepResult:
        """执行单个步骤。"""
        started = time.perf_counter()

        try:
            if step.step_type == StepType.TOOL.value:
                output = await self._execute_tool_step(step, context)
            elif step.step_type == StepType.CONDITION.value:
                output = await self._execute_condition_step(step, context, previous_results)
            elif step.step_type == StepType.PARALLEL.value:
                output = await self._execute_parallel_step(step, context, previous_results)
            elif step.step_type == StepType.TRANSFORM.value:
                output = self._execute_transform_step(step, context)
            else:
                return StepResult(
                    step_name=step.name,
                    success=False,
                    error=f"未知步骤类型: {step.step_type}",
                    step_type=step.step_type,
                )

            return StepResult(
                step_name=step.name,
                success=True,
                output=output,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                step_type=step.step_type,
            )
        except Exception as exc:
            return StepResult(
                step_name=step.name,
                success=False,
                error=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                step_type=step.step_type,
            )

    async def _execute_tool_step(self, step: Step, context: dict[str, Any]) -> Any:
        """执行工具调用步骤。"""
        # 解析输入引用: "$search.results" → context["search"]["results"]
        resolved_inputs = {}
        for param, ref in step.inputs.items():
            resolved_inputs[param] = self._resolve_ref(ref, context)

        if self._tool_executor is not None:
            return await self._tool_executor(step.tool, resolved_inputs)

        # 无执行器时返回解析后的输入（调试用）
        return {"tool": step.tool, "inputs": resolved_inputs}

    async def _execute_condition_step(
        self,
        step: Step,
        context: dict[str, Any],
        previous_results: dict[str, StepResult],
    ) -> Any:
        """执行条件分支步骤。"""
        # 简单的条件评估（支持: $key == value, $key != value, $key contains value）
        condition_result = self._evaluate_condition(step.condition, context)

        if condition_result:
            branch_steps = step.then_steps
        else:
            branch_steps = step.else_steps

        branch_outputs = {}
        for branch_step in branch_steps:
            result = await self._execute_step(branch_step, context, previous_results)
            branch_outputs[branch_step.name] = result.output
            if not result.success and branch_step.on_error == ErrorPolicy.ABORT.value:
                raise RuntimeError(f"条件分支步骤 {branch_step.name} 失败: {result.error}")

        return branch_outputs

    async def _execute_parallel_step(
        self,
        step: Step,
        context: dict[str, Any],
        previous_results: dict[str, StepResult],
    ) -> Any:
        """执行并行步骤组。"""
        tasks = [
            self._execute_step(sub_step, context, previous_results)
            for sub_step in step.parallel_steps
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs = {}
        for sub_step, result in zip(step.parallel_steps, results):
            if isinstance(result, Exception):
                outputs[sub_step.name] = {"error": str(result)}
            else:
                outputs[sub_step.name] = result.output if isinstance(result, StepResult) else result
        return outputs

    def _execute_transform_step(self, step: Step, context: dict[str, Any]) -> Any:
        """执行数据转换步骤（同步）。"""
        if step.transform_fn is not None:
            return step.transform_fn(context)
        return context

    # ---- 辅助 ----

    @staticmethod
    def _resolve_ref(ref: str, context: dict[str, Any]) -> Any:
        """解析引用表达式。

        支持:
        - "$question" → context["question"]
        - "$search.results" → context["search"]["results"]
        - "$search.results[0]" → context["search"]["results"][0]
        - "literal_value" → "literal_value" (不以 $ 开头即字面量)
        """
        ref = str(ref).strip()
        if not ref.startswith("$"):
            return ref

        path = ref[1:]  # 去掉 $
        parts = path.replace("[", ".").replace("]", "").split(".")

        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                try:
                    index = int(part)
                    value = value[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return value

    @staticmethod
    def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
        """简单的条件表达式评估。"""
        condition = condition.strip()

        # $key exists
        if " exists" in condition and condition.startswith("$"):
            key = condition.split(" ")[0][1:]
            return key in context and context[key] is not None

        # $key is empty
        if " is empty" in condition and condition.startswith("$"):
            key = condition.split(" ")[0][1:]
            value = ToolPipeline._resolve_ref(f"${key}", context)
            return not value

        # $key == value
        if " == " in condition:
            left, right = condition.split(" == ", 1)
            lv = ToolPipeline._resolve_ref(left.strip(), context)
            rv = right.strip().strip("'\"")
            return str(lv) == rv

        # $key != value
        if " != " in condition:
            left, right = condition.split(" != ", 1)
            lv = ToolPipeline._resolve_ref(left.strip(), context)
            rv = right.strip().strip("'\"")
            return str(lv) != rv

        # $key contains value
        if " contains " in condition:
            left, right = condition.split(" contains ", 1)
            lv = ToolPipeline._resolve_ref(left.strip(), context)
            rv = right.strip().strip("'\"")
            return rv in str(lv)

        return True  # 默认通过
