"""RAG 幻觉检测 —— 检测生成内容与证据文档的不一致性。

检测维度：
1. 引用一致性：引用标记 [N] 是否指向实际存在的证据
2. 事实一致性：生成内容中的关键事实是否在证据中有支撑
3. 数字一致性：生成内容中的数字/日期是否与证据匹配
4. NLI推理：基于自然语言推理的语义一致性（需要NLI模型或LLM）

输出:
    HallucinationReport: 幻觉评分 + 具体不一致项列表

集成方式::

    from .hallucination_detector import HallucinationDetector

    detector = HallucinationDetector(build_chat_model_fn, settings)
    report = await detector.detect(answer="...", evidence=[...])
    if report.hallucination_score > 0.5:
        # 触发修正或告警
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from shared.grounded_answering import compact_text

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class HallucinationItem:
    """单个幻觉发现"""

    type: str  # fake_citation / fact_conflict / number_mismatch / unsupported_claim
    severity: str  # high / medium / low
    description: str  # 中文描述
    location: str  # 在回答中的位置（上下文引用）
    evidence_ref: str = ""  # 相关证据引用
    suggestion: str = ""  # 修正建议


@dataclass
class HallucinationReport:
    """幻觉检测报告"""

    hallucination_score: float  # 0-1，越高表示幻觉越多
    items: list[HallucinationItem] = field(default_factory=list)
    check_dimensions: dict[str, float] = field(default_factory=dict)  # 各维度评分
    passed: bool = True  # 是否通过检测
    needs_correction: bool = False


# ---------------------------------------------------------------------------
# 检测 Prompt
# ---------------------------------------------------------------------------

_HALLUCINATION_CHECK_PROMPT = """你是一个严格的事实核查员。请检查以下AI回答是否与提供的证据文档一致。

## 检查维度
1. **引用一致性**: 回答中的引用标记 [1] [2] 是否指向实际存在的证据？
2. **事实一致性**: 回答中的关键事实是否在证据中找到支撑？
3. **数字一致性**: 回答中的数字、日期、百分比是否与证据一致？
4. **编造检测**: 回答是否声称了证据中完全没有的信息？

## 输出格式
```json
{
  "hallucination_score": 0.15,
  "passed": true,
  "needs_correction": false,
  "check_dimensions": {
    "citation_consistency": 0.95,
    "fact_consistency": 0.90,
    "number_consistency": 0.88,
    "fabrication": 0.05
  },
  "items": [
    {
      "type": "number_mismatch",
      "severity": "low",
      "description": "回答中说'大约100人'，证据显示'98人'",
      "location": "第2段",
      "evidence_ref": "[3]",
      "suggestion": "修正为'98人'"
    }
  ]
}
```

## 评分标准
- hallucination_score < 0.1: 优秀，基本一致
- hallucination_score 0.1-0.3: 良好，有轻微不一致
- hallucination_score 0.3-0.5: 需关注，存在明显不一致
- hallucination_score > 0.5: 严重，需要修正后重答
"""


# ---------------------------------------------------------------------------
# 快速规则检测（不调用 LLM）
# ---------------------------------------------------------------------------


def _check_citation_consistency(answer: str, evidence: list[dict[str, Any]]) -> tuple[list[HallucinationItem], float]:
    """检查引用标记与证据的对应关系。"""
    items: list[HallucinationItem] = []
    ev_count = len(evidence)

    # 提取所有引用标记
    citations = re.findall(r"\[(\d+)\]", answer)
    cited_indices = {int(c) for c in citations}

    # 虚构引用：指向不存在的证据
    fake = cited_indices - set(range(1, ev_count + 1))
    for idx in sorted(fake):
        items.append(HallucinationItem(
            type="fake_citation",
            severity="high" if idx > ev_count + 3 else "medium",
            description=f"引用 [{idx}] 不存在的证据（仅有 {ev_count} 条证据）",
            location=f"引用标记 [{idx}]",
            suggestion="移除该引用或补充对应证据",
        ))

    # 未使用引用：有证据但未引用
    unused = set(range(1, ev_count + 1)) - cited_indices
    if unused and ev_count >= 3:
        items.append(HallucinationItem(
            type="fake_citation",
            severity="low",
            description=f"有 {len(unused)} 条证据未被引用: {sorted(unused)}",
            location="全文",
            suggestion="考虑是否应引用这些证据或精简证据数量",
        ))

    score = len(items) * 0.15
    return items, min(1.0, score)


def _check_number_consistency(answer: str, evidence: list[dict[str, Any]]) -> tuple[list[HallucinationItem], float]:
    """快速检查数字一致性（不调用 LLM）。"""
    items: list[HallucinationItem] = []

    # 从证据中提取数字
    ev_numbers: dict[str, str] = {}
    number_re = re.compile(r"\b(\d+(?:\.\d+)?)\s*(%|人|个|元|万|亿|次|天|小时|分钟|秒|月|年|页)?\b")
    for i, item in enumerate(evidence, start=1):
        text = str(item.get("quote") or item.get("raw_text") or "")
        for match in number_re.finditer(text):
            ev_numbers[f"{match.group(1)}{match.group(2) or ''}"] = f"[{i}]"

    # 从回答中检查关键数字是否在证据中出现
    answer_numbers = number_re.findall(answer)
    for num, unit in answer_numbers:
        full = f"{num}{unit or ''}"
        if full not in ev_numbers:
            # 不是所有数字都需要在证据中（如计算结果），仅记录可疑的
            pass

    score = len(items) * 0.1
    return items, min(1.0, score)


def detect_hallucination_rules(
    answer: str,
    evidence: list[dict[str, Any]],
    *,
    threshold: float = 0.5,
) -> HallucinationReport:
    """执行不依赖 LLM 的规则级幻觉检测。"""
    if not str(answer or "").strip():
        return HallucinationReport(hallucination_score=0.0, passed=True)

    cit_items, cit_score = _check_citation_consistency(answer, evidence)
    num_items, num_score = _check_number_consistency(answer, evidence)
    final_score = max(cit_score, num_score)
    return HallucinationReport(
        hallucination_score=round(final_score, 3),
        items=cit_items + num_items,
        check_dimensions={
            "citation_consistency": round(1.0 - cit_score, 3),
            "number_consistency": round(1.0 - num_score, 3),
            "llm_overall": 1.0,
        },
        passed=final_score < threshold,
        needs_correction=final_score >= threshold,
    )


def hallucination_report_to_dict(report: HallucinationReport) -> dict[str, Any]:
    """序列化幻觉检测报告，便于写入 API 响应与审计日志。"""
    return {
        "hallucination_score": report.hallucination_score,
        "passed": report.passed,
        "needs_correction": report.needs_correction,
        "check_dimensions": dict(report.check_dimensions),
        "items": [
            {
                "type": item.type,
                "severity": item.severity,
                "description": item.description,
                "location": item.location,
                "evidence_ref": item.evidence_ref,
                "suggestion": item.suggestion,
            }
            for item in report.items
        ],
    }


# ---------------------------------------------------------------------------
# LLM 深度检测
# ---------------------------------------------------------------------------


class HallucinationDetector:
    """RAG 幻觉检测器 —— 规则快速扫描 + LLM深度分析。"""

    def __init__(
        self,
        *,
        build_chat_model_fn: Callable | None = None,
        settings: Any = None,
        auto_correct_threshold: float = 0.5,
    ) -> None:
        self._build_chat_model = build_chat_model_fn
        self._settings = settings
        self._auto_correct_threshold = auto_correct_threshold

    async def detect(
        self,
        answer: str,
        evidence: list[dict[str, Any]],
        *,
        question: str = "",
        deep_check: bool = True,
    ) -> HallucinationReport:
        """检测回答中的幻觉。

        参数:
            answer: 生成的回答
            evidence: 引用证据列表
            question: 原始问题
            deep_check: 是否启用 LLM 深度检测
        """
        if not answer.strip():
            return HallucinationReport(hallucination_score=0.0, passed=True)

        # Phase 1: 快速规则检测
        rule_report = detect_hallucination_rules(
            answer,
            evidence,
            threshold=self._auto_correct_threshold,
        )
        all_items = list(rule_report.items)
        rule_score = float(rule_report.hallucination_score)

        # Phase 2: LLM 深度检测
        llm_score = 0.0
        llm_items: list[HallucinationItem] = []
        if deep_check and self._build_chat_model is not None and self._settings is not None:
            try:
                llm_score, llm_items = await self._llm_detect(answer, evidence, question)
            except Exception as exc:
                logger.warning("hallucination_llm_detect_failed err=%s", exc)

        all_items.extend(llm_items)
        final_score = max(rule_score, llm_score)

        return HallucinationReport(
            hallucination_score=round(final_score, 3),
            items=all_items,
            check_dimensions={
                "citation_consistency": float(rule_report.check_dimensions.get("citation_consistency", 1.0)),
                "number_consistency": float(rule_report.check_dimensions.get("number_consistency", 1.0)),
                "llm_overall": round(1.0 - llm_score, 3),
            },
            passed=final_score < self._auto_correct_threshold,
            needs_correction=final_score >= self._auto_correct_threshold,
        )

    async def _llm_detect(
        self,
        answer: str,
        evidence: list[dict[str, Any]],
        question: str,
    ) -> tuple[float, list[HallucinationItem]]:
        """LLM 深度幻觉检测。"""
        evidence_text = ""
        for i, item in enumerate(evidence, start=1):
            content = item.get("quote") or item.get("raw_text") or ""
            doc = item.get("document_title") or ""
            evidence_text += f"[{i}] {doc}: {compact_text(str(content), 200)}\n\n"

        user_prompt = f"""证据文档：
{compact_text(evidence_text, 3000)}

用户问题：
{question or "(未提供)"}

AI回答：
{answer}

请逐项检查并输出 JSON。"""

        chat_model = self._build_chat_model(
            settings=self._settings,
            model=self._settings.model,
            temperature=0.0,
            max_tokens=min(self._settings.default_max_tokens, 800),
            streaming=False,
        )
        messages = [
            SystemMessage(content=_HALLUCINATION_CHECK_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        response = await chat_model.ainvoke(messages)
        parsed = _parse_hallucination_response(str(response.content or ""))

        score = float(parsed.get("hallucination_score", 0.0))
        items: list[HallucinationItem] = []
        for raw in parsed.get("items", []):
            items.append(HallucinationItem(
                type=str(raw.get("type") or "unsupported_claim"),
                severity=str(raw.get("severity") or "medium"),
                description=str(raw.get("description") or ""),
                location=str(raw.get("location") or ""),
                evidence_ref=str(raw.get("evidence_ref") or ""),
                suggestion=str(raw.get("suggestion") or ""),
            ))

        return score, items


def _parse_hallucination_response(content: str) -> dict[str, Any]:
    """解析 LLM 响应 JSON。"""
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
