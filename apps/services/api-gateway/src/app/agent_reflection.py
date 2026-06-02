"""Agent 反思闭环 —— 输出自检、失败分析、策略记忆。

实现 ReAct → Reflexion 的升级：
1. 输出自检 —— 生成回答后 LLM 自评完整性/准确性/引用准确性
2. 失败分析 —— 工具调用失败/检索结果为空时 LLM 分析根因
3. 策略记忆 —— 同类问题的成功策略存入长期记忆，下次优先复用
4. 执行置信度 —— 每个子任务输出置信度，低于阈值触发人工确认

集成方式:
    from .agent_reflection import AgentReflector

    reflector = AgentReflector(build_chat_model_fn, settings)
    check = await reflector.self_check(answer, evidence)
    if check.needs_retry:
        # 修正后重新生成
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from shared.grounded_answering import compact_text

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SelfCheckResult:
    """输出自检结果"""

    passed: bool  # 是否通过自检
    completeness_score: float  # 完整性评分 0-1
    accuracy_score: float  # 准确性评分 0-1
    citation_score: float  # 引用准确性评分 0-1
    issues: list[str] = field(default_factory=list)  # 发现的问题
    suggestions: list[str] = field(default_factory=list)  # 改进建议
    needs_retry: bool = False  # 是否需要重试
    retry_hint: str = ""  # 重试提示
    confidence: float = 0.5  # 整体置信度 0-1


@dataclass
class FailureAnalysis:
    """失败分析结果"""

    root_cause: str  # 根因分类: tool_error / retrieval_empty / timeout / model_error / scope_mismatch
    detail: str  # 详细分析
    recoverable: bool  # 是否可恢复
    suggested_action: str  # 建议操作: retry / expand_scope / rephrase / give_up
    alternative_tools: list[str] = field(default_factory=list)  # 替代工具建议
    rephrased_question: str = ""  # 重述后的问题


@dataclass
class StrategyRecord:
    """策略记录 —— 存储到长期记忆中"""

    scenario_key: str  # 场景标识（如 "multi_version_comparison"）
    approach: str  # 成功的策略描述
    tool_sequence: list[str] = field(default_factory=list)  # 使用的工具序列
    success_rate: float = 0.0  # 历史成功率
    last_used_at: float = 0.0  # 最后使用时间


# ---------------------------------------------------------------------------
# 自检 Prompt
# ---------------------------------------------------------------------------

_SELF_CHECK_PROMPT = """你是一个严格的回答质量审查员。请评估以下 AI 回答的质量。

## 评估维度
1. **完整性** (0-1): 回答是否完整覆盖了用户问题的所有方面？
2. **准确性** (0-1): 回答内容是否与提供的证据一致？是否存在编造或幻觉？
3. **引用准确性** (0-1): 引用标记是否正确地指向了对应的证据？

## 输出格式
```json
{
  "completeness_score": 0.85,
  "accuracy_score": 0.92,
  "citation_score": 0.90,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1"],
  "needs_retry": false,
  "retry_hint": "",
  "confidence": 0.89
}
```

## 注意事项
- 严格以证据为准，不要假设回答正确
- 如果回答声称了证据中没有的事实，标记为幻觉
- 如果引用 [1] [2] 与证据序号不对应，降低 citation_score
- needs_retry: 当 accuracy_score < 0.6 或 citation_score < 0.5 时建议重试
"""


# ---------------------------------------------------------------------------
# 失败分析 Prompt
# ---------------------------------------------------------------------------

_FAILURE_ANALYSIS_PROMPT = """你是一个 AI Agent 故障诊断专家。请分析以下工具调用失败的原因并给出恢复建议。

## 输出格式
```json
{
  "root_cause": "tool_error",
  "detail": "具体原因分析",
  "recoverable": true,
  "suggested_action": "rephrase",
  "alternative_tools": ["search_corpus"],
  "rephrased_question": "优化后的问题"
}
```

## root_cause 可选值
- tool_error: 工具调用本身出错（参数错误、权限不足等）
- retrieval_empty: 检索返回空结果
- timeout: 工具调用超时
- model_error: LLM 模型调用失败
- scope_mismatch: 知识库范围不匹配

## suggested_action 可选值
- retry: 用相同参数重试
- expand_scope: 扩大知识库检索范围
- rephrase: 用不同措辞重新检索
- switch_tool: 切换到替代工具
- give_up: 放弃并降级处理
"""


# ---------------------------------------------------------------------------
# Agent 反思器
# ---------------------------------------------------------------------------


class AgentReflector:
    """Agent 反思引擎 —— 输出自检 + 失败分析 + 策略记忆。"""

    def __init__(
        self,
        *,
        build_chat_model_fn: Callable,
        settings: Any,
        self_check_threshold: float = 0.6,
    ) -> None:
        self._build_chat_model = build_chat_model_fn
        self._settings = settings
        self._self_check_threshold = self_check_threshold
        self._strategies: dict[str, StrategyRecord] = {}

    # ---- 输出自检 -----------------------------------------------------------

    async def self_check(
        self,
        answer: str,
        evidence: list[dict[str, Any]],
        *,
        question: str = "",
        history: list[dict[str, Any]] | None = None,
    ) -> SelfCheckResult:
        """对生成的回答进行质量自检。

        参数:
            answer: 生成的回答
            evidence: 引用证据列表
            question: 原始问题
        返回:
            SelfCheckResult
        """
        if not answer.strip():
            return SelfCheckResult(
                passed=False,
                completeness_score=0.0,
                accuracy_score=0.0,
                citation_score=0.0,
                issues=["回答为空"],
                needs_retry=True,
                retry_hint="重新生成回答",
                confidence=0.0,
            )

        evidence_text = _format_evidence_for_check(evidence)

        user_prompt = f"""用户问题：
{question or "(未提供)"}

引用的证据：
{compact_text(evidence_text, 2000)}

AI 回答：
{answer}

请按照评估维度评分并输出 JSON。"""

        try:
            chat_model = self._build_chat_model(
                settings=self._settings,
                model=self._settings.model,
                temperature=0.0,
                max_tokens=min(self._settings.default_max_tokens, 600),
                streaming=False,
            )
            messages = [
                SystemMessage(content=_SELF_CHECK_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            response = await chat_model.ainvoke(messages)
            parsed = _parse_check_response(str(response.content or ""))
            return SelfCheckResult(
                passed=(
                    parsed.get("accuracy_score", 0) >= self._self_check_threshold
                    and parsed.get("citation_score", 0) >= 0.5
                ),
                completeness_score=float(parsed.get("completeness_score", 0.8)),
                accuracy_score=float(parsed.get("accuracy_score", 0.8)),
                citation_score=float(parsed.get("citation_score", 0.8)),
                issues=list(parsed.get("issues") or []),
                suggestions=list(parsed.get("suggestions") or []),
                needs_retry=bool(parsed.get("needs_retry", False)),
                retry_hint=str(parsed.get("retry_hint") or ""),
                confidence=float(parsed.get("confidence", 0.5)),
            )
        except Exception as exc:
            logger.warning("self_check_failed err=%s", exc)
            return SelfCheckResult(
                passed=True,  # 自检失败时不过度阻塞
                completeness_score=0.7,
                accuracy_score=0.7,
                citation_score=0.7,
                issues=[f"自检异常: {exc}"],
                confidence=0.5,
            )

    # ---- 失败分析 -----------------------------------------------------------

    async def analyze_failure(
        self,
        tool_name: str,
        error_message: str,
        params: dict[str, Any],
        *,
        question: str = "",
    ) -> FailureAnalysis:
        """分析工具调用失败的原因并给出恢复建议。

        参数:
            tool_name: 失败的工具名称
            error_message: 错误信息
            params: 调用参数
            question: 原始问题
        返回:
            FailureAnalysis
        """
        # 快速规则匹配（不调用 LLM 的场景）
        quick = _quick_failure_analysis(tool_name, error_message, params)
        if quick is not None:
            return quick

        # LLM 深度分析
        user_prompt = f"""工具名称: {tool_name}
调用参数: {json.dumps(params, ensure_ascii=False)}
错误信息: {error_message}
原始问题: {question or "(未提供)"}

请分析失败原因并输出 JSON。"""

        try:
            chat_model = self._build_chat_model(
                settings=self._settings,
                model=self._settings.model,
                temperature=0.0,
                max_tokens=min(self._settings.default_max_tokens, 500),
                streaming=False,
            )
            messages = [
                SystemMessage(content=_FAILURE_ANALYSIS_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            response = await chat_model.ainvoke(messages)
            parsed = _parse_check_response(str(response.content or ""))
            return FailureAnalysis(
                root_cause=str(parsed.get("root_cause") or "tool_error"),
                detail=str(parsed.get("detail") or error_message),
                recoverable=bool(parsed.get("recoverable", True)),
                suggested_action=str(parsed.get("suggested_action") or "rephrase"),
                alternative_tools=list(parsed.get("alternative_tools") or []),
                rephrased_question=str(parsed.get("rephrased_question") or ""),
            )
        except Exception as exc:
            logger.warning("failure_analysis_failed err=%s", exc)
            return FailureAnalysis(
                root_cause="tool_error",
                detail=str(error_message),
                recoverable=True,
                suggested_action="rephrase",
            )

    # ---- 策略记忆 -----------------------------------------------------------

    def record_strategy(
        self,
        scenario_key: str,
        approach: str,
        tool_sequence: list[str],
        success: bool = True,
    ) -> None:
        """记录一次策略执行结果。"""
        existing = self._strategies.get(scenario_key)
        if existing is None:
            self._strategies[scenario_key] = StrategyRecord(
                scenario_key=scenario_key,
                approach=approach,
                tool_sequence=list(tool_sequence),
                success_rate=1.0 if success else 0.0,
                last_used_at=time.time(),
            )
        else:
            # 指数移动平均更新成功率
            alpha = 0.3
            existing.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * existing.success_rate
            existing.last_used_at = time.time()
            existing.tool_sequence = list(tool_sequence) if success else existing.tool_sequence
            existing.approach = approach if success else existing.approach

    def get_strategy(self, scenario_key: str) -> StrategyRecord | None:
        """获取已记录的策略。"""
        return self._strategies.get(scenario_key)

    def list_strategies(self, min_success_rate: float = 0.5) -> list[StrategyRecord]:
        """列出成功率高于阈值的策略。"""
        return sorted(
            [s for s in self._strategies.values() if s.success_rate >= min_success_rate],
            key=lambda s: s.success_rate,
            reverse=True,
        )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _format_evidence_for_check(evidence: list[dict[str, Any]]) -> str:
    """格式化证据用于自检。"""
    lines: list[str] = []
    for i, item in enumerate(evidence, start=1):
        content = item.get("quote") or item.get("raw_text") or ""
        doc = item.get("document_title") or ""
        section = item.get("section_title") or ""
        source = f"{doc} / {section}".strip(" /")
        lines.append(f"[{i}] {source}\n{compact_text(str(content), 300)}")
    return "\n\n".join(lines)


def _parse_check_response(content: str) -> dict[str, Any]:
    """从 LLM 响应中提取 JSON 对象。"""
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


def _quick_failure_analysis(
    tool_name: str,
    error_message: str,
    params: dict[str, Any],
) -> FailureAnalysis | None:
    """快速规则匹配的失败分析（不调用 LLM）。"""
    err_lower = str(error_message or "").lower()

    if "timeout" in err_lower or "timed out" in err_lower:
        return FailureAnalysis(
            root_cause="timeout",
            detail=f"工具 {tool_name} 执行超时",
            recoverable=True,
            suggested_action="retry",
        )

    if "empty" in err_lower or "no result" in err_lower or "not found" in err_lower:
        return FailureAnalysis(
            root_cause="retrieval_empty",
            detail=f"工具 {tool_name} 未找到结果",
            recoverable=True,
            suggested_action="expand_scope",
            alternative_tools=["search_scope"] if tool_name == "search_corpus" else [],
        )

    if "permission" in err_lower or "forbidden" in err_lower or "unauthorized" in err_lower:
        return FailureAnalysis(
            root_cause="tool_error",
            detail=f"工具 {tool_name} 权限不足",
            recoverable=False,
            suggested_action="give_up",
        )

    # 无法快速判断，交给 LLM
    return None
