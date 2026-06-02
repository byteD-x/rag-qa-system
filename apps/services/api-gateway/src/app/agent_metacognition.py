"""Agent 元认知模块 —— 知道自己"不知道什么"，主动澄清。

核心能力：
- 知识边界识别：判断问题是否在自己的能力范围内
- 主动澄清：生成精准的澄清问题，减少猜测
- 置信度评估：对自己的回答给出置信度评分
- 不确定性来源分类：知识缺失 / 信息不足 / 歧义 / 超出领域

使用方式::

    from .agent_metacognition import MetacognitionEngine

    engine = MetacognitionEngine()
    check = await engine.check(question, evidence, history)
    if check.needs_clarification:
        return check.clarification_question
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .context_window import estimate_tokens
from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class UncertaintyType(str, Enum):
    """不确定性来源分类。"""
    KNOWLEDGE_GAP = "knowledge_gap"       # 知识库中无相关信息
    INFORMATION_INSUFFICIENT = "info_insufficient"  # 信息不完整
    AMBIGUITY = "ambiguity"               # 问题本身存在歧义
    OUT_OF_DOMAIN = "out_of_domain"       # 超出能力范围
    CONFIDENCE_LOW = "confidence_low"     # 低置信度


class ClarifyStrategy(str, Enum):
    """澄清策略。"""
    ASK_CONTEXT = "ask_context"           # 请求更多上下文
    ASK_SPECIFIC = "ask_specific"         # 请求具体信息（版本/时间/系统名）
    NARROW_SCOPE = "narrow_scope"         # 缩小范围
    CONFIRM_INTENT = "confirm_intent"     # 确认意图
    DECLINE = "decline"                   # 无法回答


@dataclass
class MetacognitionCheck:
    """元认知检查结果。"""
    needs_clarification: bool = False     # 是否需要澄清
    uncertainty_type: str = ""            # 不确定性类型
    uncertainty_level: float = 0.0        # 不确定性 0-1
    clarification_question: str = ""      # 生成的澄清问题
    strategy: str = ""                    # 澄清策略
    reason: str = ""                      # 原因说明
    confidence_bound: float = 0.0         # 当前置信度下界
    suggested_alternatives: list[str] = field(default_factory=list)  # 备选方向


# ---------------------------------------------------------------------------
# 知识边界检测 Prompt
# ---------------------------------------------------------------------------

_METACOGNITION_PROMPT = """你是一个 Agent 自我认知模块。分析以下情况，判断 AI Agent 是否应该请求用户澄清。

## 评估维度
1. **知识覆盖**: 证据是否足以回答用户问题？
2. **信息完整**: 用户问题是否包含足够具体的信息？
3. **歧义检测**: 问题是否可能有多重解读？
4. **领域边界**: 问题是否在 Agent 的能力范围内？

## 输出格式
```json
{
  "needs_clarification": true/false,
  "uncertainty_type": "info_insufficient",
  "uncertainty_level": 0.0-1.0,
  "clarification_question": "具体澄清问题",
  "strategy": "ask_specific",
  "reason": "简短原因说明"
}
```

## 策略选择指南
- ask_context: 用户问题太宽泛，需要了解使用场景
- ask_specific: 缺少具体参数（版本号、时间、系统名等）
- narrow_scope: 涉及范围太广，需要聚焦
- confirm_intent: 问题有歧义，需要确认用户真实意图
- decline: 完全超出知识范围且无法通过澄清改善
"""


# ---------------------------------------------------------------------------
# 元认知引擎
# ---------------------------------------------------------------------------


class MetacognitionEngine:
    """Agent 元认知引擎 —— 自我认知 + 主动澄清。"""

    # 规则检测阈值（不需要 LLM 即可判断）
    RULE_BASED_THRESHOLDS = {
        "empty_evidence": 0.9,        # 无证据 → 高不确定性
        "very_short_question": 0.3,   # 问题过短
        "ambiguous_keywords": 0.45,   # 歧义词
    }

    # 歧义关键词（可能导致多重解读）
    AMBIGUOUS_PATTERNS = [
        (re.compile(r"那个|这个|它|他|她"), "指代不明"),
        (re.compile(r"怎么办|怎么弄|怎么做"), "操作意图不明"),
        (re.compile(r"好不好|行不行|可以吗|对吗"), "确认性问题"),
        (re.compile(r"哪个版本|哪个系统|哪个部门"), "选择意图不明"),
        (re.compile(r"最新的|最近的|现在的|以前的"), "时间范围不明确"),
    ]

    def __init__(self, build_chat_model_fn: Any = None, settings: Any = None) -> None:
        self._build_fn = build_chat_model_fn
        self._settings = settings

    async def check(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        history: list[dict[str, Any]],
        *,
        use_llm: bool = True,
    ) -> MetacognitionCheck:
        """执行元认知检查。

        参数:
            question: 用户问题
            evidence: 检索到的证据
            history: 对话历史
            use_llm: 是否使用 LLM 深度分析

        返回:
            MetacognitionCheck
        """
        # 1. 快速规则检测（毫秒级）
        rule_result = self._rule_check(question, evidence, history)

        # 2. 如果规则检测已经很确定，直接返回
        if rule_result.uncertainty_level >= 0.8 or rule_result.uncertainty_level <= 0.1:
            return rule_result

        # 3. LLM 深度分析（可选）
        if use_llm and self._build_fn and self._settings:
            try:
                llm_result = await self._llm_check(question, evidence, history)
                # LLM 结果优先（但保留规则检测的关键判断）
                if llm_result.uncertainty_level > rule_result.uncertainty_level:
                    return llm_result
                return rule_result
            except Exception as exc:
                logger.warning("metacognition_llm_failed err=%s", exc)

        return rule_result

    def _rule_check(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        history: list[dict[str, Any]],
    ) -> MetacognitionCheck:
        """基于规则的快速元认知检测（< 1ms）。"""
        reasons: list[str] = []
        uncertainty = 0.0

        # 检查1：证据充足性
        if not evidence:
            uncertainty += self.RULE_BASED_THRESHOLDS["empty_evidence"]
            reasons.append("无检索证据")
        elif len(evidence) < 2:
            top_score = max(
                (float(e.get("evidence_path", {}).get("final_score", 0)) for e in evidence),
                default=0.0,
            )
            if top_score < 0.01:
                uncertainty += 0.5
                reasons.append("证据相关性低")

        # 检查2：问题长度
        cleaned = question.strip()
        if len(cleaned) < 8:
            uncertainty += self.RULE_BASED_THRESHOLDS["very_short_question"]
            reasons.append("问题过于简短")

        # 检查3：歧义词检测
        for pattern, label in self.AMBIGUOUS_PATTERNS:
            if pattern.search(cleaned):
                uncertainty += self.RULE_BASED_THRESHOLDS["ambiguous_keywords"]
                reasons.append(f"歧义: {label}")
                break

        # 检查4：超出知识范围的模式
        if any(kw in cleaned for kw in ["未来预测", "股票", "医疗诊断", "法律建议"]):
            uncertainty += 0.5
            reasons.append("超出知识领域范围")

        # 检查5：上下文连贯性
        if len(history) >= 3:
            last_user = history[-1].get("content", "") if history[-1].get("role") == "user" else ""
            if last_user and len(last_user) < 10:
                # 可能依赖上文的简短追问
                uncertainty += 0.15

        uncertainty = min(uncertainty, 1.0)

        # 确定不确定性类型
        un_type = self._classify_uncertainty(uncertainty, evidence, cleaned)

        # 生成澄清问题
        needs = uncertainty >= 0.35
        strategy = self._select_strategy(un_type, uncertainty)
        clarification = self._generate_clarification(
            question, un_type, strategy, reasons
        ) if needs else ""

        return MetacognitionCheck(
            needs_clarification=needs,
            uncertainty_type=un_type,
            uncertainty_level=round(uncertainty, 4),
            clarification_question=clarification,
            strategy=strategy,
            reason="; ".join(reasons) if reasons else "信息充分",
            confidence_bound=round(1.0 - uncertainty, 4),
            suggested_alternatives=self._suggest_alternatives(question, evidence),
        )

    async def _llm_check(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        history: list[dict[str, Any]],
    ) -> MetacognitionCheck:
        """LLM 深度元认知分析。"""
        evidence_text = "\n---\n".join(
            f"[{e.get('document_title', '')}] {e.get('content', '')[:400]}"
            for e in evidence[:5]
        ) or "无证据"

        context = f"""用户问题：{question}

检索到的证据（{len(evidence)}条）：
{evidence_text}

对话历史最近5轮：
{self._format_history(history[-5:])}
"""
        chat_model = self._build_fn(
            settings=self._settings,
            model=self._settings.model,
            temperature=0.0,
            max_tokens=400,
            streaming=False,
        )
        msgs = [
            SystemMessage(content=_METACOGNITION_PROMPT),
            HumanMessage(content=context),
        ]
        response = await chat_model.ainvoke(msgs)
        content = str(response.content or "").strip()

        parsed = self._parse_json(content)
        return MetacognitionCheck(
            needs_clarification=bool(parsed.get("needs_clarification", False)),
            uncertainty_type=str(parsed.get("uncertainty_type", "")),
            uncertainty_level=float(parsed.get("uncertainty_level", 0.0)),
            clarification_question=str(parsed.get("clarification_question", "")),
            strategy=str(parsed.get("strategy", "")),
            reason=str(parsed.get("reason", "")),
            confidence_bound=round(1.0 - float(parsed.get("uncertainty_level", 0.0)), 4),
        )

    # ---- 辅助 ----

    @staticmethod
    def _classify_uncertainty(level: float, evidence: list, question: str) -> str:
        if not evidence:
            return UncertaintyType.KNOWLEDGE_GAP.value
        if level >= 0.7:
            return UncertaintyType.INFORMATION_INSUFFICIENT.value
        if level >= 0.4:
            return UncertaintyType.AMBIGUITY.value
        return UncertaintyType.CONFIDENCE_LOW.value

    @staticmethod
    def _select_strategy(uncertainty_type: str, level: float) -> str:
        if uncertainty_type == UncertaintyType.KNOWLEDGE_GAP.value:
            return ClarifyStrategy.DECLINE.value if level >= 0.8 else ClarifyStrategy.ASK_CONTEXT.value
        if uncertainty_type == UncertaintyType.INFORMATION_INSUFFICIENT.value:
            return ClarifyStrategy.ASK_SPECIFIC.value
        if uncertainty_type == UncertaintyType.AMBIGUITY.value:
            return ClarifyStrategy.CONFIRM_INTENT.value
        return ClarifyStrategy.ASK_CONTEXT.value

    def _generate_clarification(
        self,
        question: str,
        uncertainty_type: str,
        strategy: str,
        reasons: list[str],
    ) -> str:
        """生成澄清问题。"""
        templates = {
            ClarifyStrategy.ASK_CONTEXT.value: "我需要更多背景信息来更好地回答您的问题。请问您是在什么场景下遇到的这个问题？",
            ClarifyStrategy.ASK_SPECIFIC.value: f"关于'{question[:30]}...'，请问您能补充以下信息吗：涉及的版本号、时间范围、或具体的系统/模块名称？",
            ClarifyStrategy.CONFIRM_INTENT.value: f"关于'{question[:30]}...'，我想确认一下您的具体需求——您是想要[方案A]还是[方案B]？或者有其他考虑？",
            ClarifyStrategy.NARROW_SCOPE.value: f"这个问题涉及的范围比较广，能否先聚焦到您最关心的一个方面？",
            ClarifyStrategy.DECLINE.value: "抱歉，这个问题超出了我的知识范围。建议您咨询相关领域的专家或查阅专门的资料。",
        }
        return templates.get(strategy, templates[ClarifyStrategy.ASK_CONTEXT.value])

    def _suggest_alternatives(
        self,
        question: str,
        evidence: list[dict[str, Any]],
    ) -> list[str]:
        """基于已有证据给出替代方向建议。"""
        suggestions = []
        if evidence:
            titles = [e.get("document_title", "") for e in evidence[:3] if e.get("document_title")]
            if titles:
                suggestions.append(f"已有相关文档：{'、'.join(titles)}")
        if not evidence and question:
            suggestions.append("尝试去除版本号或时间限定词后重新搜索")
            suggestions.append("尝试更通用的关键词")
        return suggestions

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        import json
        try:
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end]
            elif "{" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                content = content[start:end]
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {}

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))[:200]
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)
