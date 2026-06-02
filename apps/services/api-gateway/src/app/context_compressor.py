"""LLM-based 智能上下文压缩器。

核心能力：
- 两级压缩：提取式（保留关键句）→ 生成式（LLM 摘要合并）
- 实体白名单保护（人名、日期、金额、版本号等关键词不被压缩丢失）
- 压缩比可配置（保留比例 0.1-0.9）
- 压缩统计（压缩前后 token 数、关键实体保留率）

压缩策略：
- 第一级（提取式）：按句子评分，保留高分句子
- 第二级（生成式）：调用 LLM 将提取的关键句压缩为摘要

使用方式::

    from .context_compressor import ContextCompressor, compress_history

    compressor = ContextCompressor(build_chat_model_fn, settings)
    compressed = await compressor.compress(history_messages, target_ratio=0.5)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .context_window import estimate_tokens
from .gateway_runtime import logger

# ---------------------------------------------------------------------------
# 实体白名单
# ---------------------------------------------------------------------------

# 需要保护的实体模式（避免在压缩中丢失）
_ENTITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("日期", re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?")),
    ("时间", re.compile(r"\d{1,2}:\d{2}(:\d{2})?")),
    ("金额", re.compile(r"¥\s*\d+[\d,.]*\s*[万元亿]?|RMB\s*\d+[\d,.]*|USD\s*\d+[\d,.]*")),
    ("版本号", re.compile(r"[vV]\d+\.\d+(\.\d+)?(?:-[a-zA-Z0-9]+)?")),
    ("百分比", re.compile(r"\d+\.?\d*\s*%")),
    ("手机号", re.compile(r"1[3-9]\d{9}")),
    ("邮箱", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("IP地址", re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")),
    ("文件名", re.compile(r"[a-zA-Z0-9_\-./]+\.(pdf|docx?|xlsx?|pptx?|md|json|yaml|yml|py|java|ts|vue|sql)")),
    ("URL", re.compile(r"https?://[^\s]+")),
]


@dataclass
class ExtractedEntity:
    """从文本中提取的受保护实体。"""
    entity_type: str
    value: str
    position: int  # 在原文本中的起始位置


@dataclass
class SentenceScore:
    """句子评分。"""
    index: int
    text: str
    score: float = 0.0
    has_entity: bool = False
    is_question: bool = False


@dataclass
class CompressionResult:
    """压缩结果。"""
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float  # 压缩后/压缩前
    entities_found: int
    entities_preserved: int
    method: str = "extractive"  # extractive | generative | none (无需压缩)


# ---------------------------------------------------------------------------
# 压缩 Prompt
# ---------------------------------------------------------------------------

_COMPRESSION_SYSTEM_PROMPT = """你是一个对话历史压缩器。将多轮对话压缩为简洁的摘要，保留关键信息。

## 压缩规则
1. 提取用户的核心问题、需求和关键约束
2. 提取 AI 回答中给出的关键结论和数据
3. 去掉寒暄、重复、冗余和不重要的细节
4. 保留所有关键实体：日期、版本号、金额、人名、项目名、文件名
5. 按时间顺序组织摘要
6. 每条摘要不超过一段

## 输出格式
```
[轮次1] 用户询问：xxx | AI回复核心：xxx
[轮次2] 用户追问：xxx | AI回复核心：xxx
```
如果只有一轮对话，直接输出压缩后的问答对。
"""


# ---------------------------------------------------------------------------
# 提取式压缩器（无 LLM，毫秒级）
# ---------------------------------------------------------------------------


class ExtractiveCompressor:
    """提取式压缩器 —— 快速从文本中提取高分句子，不调用 LLM。"""

    # 高分关键词（出现这些词的句子更值得保留）
    HIGH_VALUE_KEYWORDS = {
        "版本", "更新", "修改", "变更", "配置", "参数", "接口",
        "部署", "上线", "发布", "回滚", "故障", "修复", "问题",
        "版本号", "日期", "金额", "负责人", "审批", "合规",
        "query", "version", "config", "deploy", "fix", "bug",
    }

    # 低价值模式（这些模式的句子可以丢弃）
    LOW_VALUE_PATTERNS = [
        re.compile(p) for p in [
            r"^(好的|明白了|知道了|嗯|哦|谢谢|不客气|有问题再|欢迎|再见)",
            r"^(好的|我知道了|没问题|可以)",
        ]
    ]

    def compress(self, text: str, target_ratio: float = 0.5) -> tuple[str, CompressionResult]:
        """提取式压缩文本。

        参数:
            text: 待压缩文本
            target_ratio: 目标保留比例（0.1-0.9）

        返回:
            (压缩后文本, 压缩统计)
        """
        original_tokens = estimate_tokens(text)
        if not text.strip():
            return text, CompressionResult(
                compressed_text=text,
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                entities_found=0,
                entities_preserved=0,
            )

        # 提取受保护实体
        entities = self._extract_entities(text)

        # 分句
        sentences = self._split_sentences(text)

        # 评分
        scored: list[SentenceScore] = []
        entity_positions = {e.position for e in entities}
        for i, sent in enumerate(sentences):
            score = self._score_sentence(sent)
            has_entity = any(
                entity_pos_start <= pos < entity_pos_start + len(sent)
                for entity_pos_start in entity_positions
                for pos in [i * 10]  # 简化：仅检查句子是否包含实体
            )
            # 更准确地检查实体
            has_entity = self._sentence_has_entity(sent, entities)
            is_q = sent.strip().endswith("?") or sent.strip().endswith("？")
            scored.append(SentenceScore(index=i, text=sent, score=score, has_entity=has_entity, is_question=is_q))

        # 强制保留：含实体的句子 + 问句
        keep_indices: set[int] = set()
        for ss in scored:
            if ss.has_entity or ss.is_question:
                keep_indices.add(ss.index)

        # 按分数排序，保留 top-k%
        target_count = max(int(len(sentences) * target_ratio), 1)
        sorted_by_score = sorted(
            [ss for ss in scored if ss.index not in keep_indices],
            key=lambda x: x.score,
            reverse=True,
        )
        remaining = target_count - len(keep_indices)
        if remaining > 0:
            for ss in sorted_by_score[:remaining]:
                keep_indices.add(ss.index)

        # 按原始顺序输出
        kept_sentences = [sentences[i] for i in sorted(keep_indices) if i < len(sentences)]
        compressed = " ".join(kept_sentences)
        compressed_tokens = estimate_tokens(compressed)

        return compressed, CompressionResult(
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
            entities_found=len(entities),
            entities_preserved=sum(1 for e in entities if e.value in compressed),
            method="extractive",
        )

    def _extract_entities(self, text: str) -> list[ExtractedEntity]:
        """从文本中提取受保护实体。"""
        entities: list[ExtractedEntity] = []
        for entity_type, pattern in _ENTITY_PATTERNS:
            for match in pattern.finditer(text):
                entities.append(ExtractedEntity(
                    entity_type=entity_type,
                    value=match.group(),
                    position=match.start(),
                ))
        return entities

    def _split_sentences(self, text: str) -> list[str]:
        """简单分句（避免在版本号/数字中的 . 处分句）。"""
        # 处理版本号和小数中的点：用占位符替换
        protected = text
        version_placeholders: dict[str, str] = {}
        version_pattern = re.compile(r"(?:[vV]\d+)?\d+\.\d+(?:\.\d+)*(?:-[a-zA-Z0-9]+)?")
        for i, match in enumerate(version_pattern.finditer(text)):
            placeholder = f"__VER_{i}__"
            version_placeholders[placeholder] = match.group()
            protected = protected.replace(match.group(), placeholder, 1)

        sentences = re.split(r"(?<=[。！？!?\n])\s*", protected)
        result = [s.strip() for s in sentences if s.strip()]

        # 还原版本号
        for placeholder, original in version_placeholders.items():
            result = [s.replace(placeholder, original) for s in result]

        return result

    def _score_sentence(self, sentence: str) -> float:
        """评分句子重要性（0-1）。"""
        score = 0.0
        lower = sentence.lower()

        # 高分关键词
        for kw in self.HIGH_VALUE_KEYWORDS:
            if kw in lower:
                score += 0.15

        # 长度适中加分
        length = len(sentence)
        if 10 <= length <= 150:
            score += 0.2
        elif length > 150:
            score += 0.1

        # 数字包含加分
        if re.search(r"\d+", sentence):
            score += 0.1

        # 低价值模式减分
        for pattern in self.LOW_VALUE_PATTERNS:
            if pattern.match(sentence.strip()):
                score -= 0.4
                break

        return min(max(score, 0.0), 1.0)

    def _sentence_has_entity(self, sentence: str, entities: list[ExtractedEntity]) -> bool:
        """检查句子是否包含受保护实体。"""
        return any(e.value in sentence for e in entities)


# ---------------------------------------------------------------------------
# 生成式压缩器（LLM-based）
# ---------------------------------------------------------------------------


class GenerativeCompressor:
    """生成式压缩器 —— 调用 LLM 生成摘要。"""

    def __init__(self, build_chat_model_fn: Any, settings: Any) -> None:
        self._build_fn = build_chat_model_fn
        self._settings = settings

    async def compress(
        self,
        history: list[dict[str, Any]],
        target_ratio: float = 0.4,
    ) -> CompressionResult:
        """调用 LLM 将对话历史压缩为摘要。

        参数:
            history: 对话历史消息列表
            target_ratio: 目标压缩比（越小压缩越激进）

        返回:
            压缩结果
        """
        original_text = self._format_history(history)
        original_tokens = estimate_tokens(original_text)

        if original_tokens < 200 or not self._build_fn:
            return CompressionResult(
                compressed_text=original_text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                entities_found=0,
                entities_preserved=0,
                method="none",
            )

        try:
            chat_model = self._build_fn(
                settings=self._settings,
                model=self._settings.model,
                temperature=0.0,
                max_tokens=min(self._settings.default_max_tokens, 600),
                streaming=False,
            )
            msgs = [
                SystemMessage(content=_COMPRESSION_SYSTEM_PROMPT),
                HumanMessage(content=f"请压缩以下对话历史（保留关键信息）：\n\n{original_text[:3000]}"),
            ]
            response = await chat_model.ainvoke(msgs)
            compressed = str(response.content or "").strip()
            compressed_tokens = estimate_tokens(compressed)

            logger.debug(
                "context_compressed_generative original=%d compressed=%d ratio=%.2f",
                original_tokens, compressed_tokens, compressed_tokens / max(original_tokens, 1),
            )

            return CompressionResult(
                compressed_text=compressed,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compressed_tokens / max(original_tokens, 1),
                entities_found=0,
                entities_preserved=0,
                method="generative",
            )
        except Exception as exc:
            logger.warning("generative_compression_failed err=%s", exc)
            return CompressionResult(
                compressed_text=original_text[:800],
                original_tokens=original_tokens,
                compressed_tokens=estimate_tokens(original_text[:800]),
                compression_ratio=0.5,
                entities_found=0,
                entities_preserved=0,
                method="extractive_fallback",
            )

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for msg in history[-20:]:
            role = str(msg.get("role") or "unknown")
            content = str(msg.get("content") or "")
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 混合压缩器（提取式 + 生成式）
# ---------------------------------------------------------------------------


class ContextCompressor:
    """混合上下文压缩器 —— 提取式快速压缩 + 生成式深压缩。

    策略：
    1. Token < 阈值：不做压缩
    2. Token 中等：仅提取式压缩（毫秒级）
    3. Token 很大：提取式 → 生成式（LLM 深度摘要）
    """

    EXTRACTIVE_THRESHOLD = 800    # 超过此值开始提取式压缩
    GENERATIVE_THRESHOLD = 2500   # 超过此值升级为生成式压缩

    def __init__(
        self,
        build_chat_model_fn: Any = None,
        settings: Any = None,
    ) -> None:
        self._extractive = ExtractiveCompressor()
        self._generative = GenerativeCompressor(build_chat_model_fn, settings)

    async def compress(
        self,
        history: list[dict[str, Any]],
        target_ratio: float = 0.5,
    ) -> CompressionResult:
        """智能压缩对话历史。

        参数:
            history: 对话历史消息列表
            target_ratio: 目标压缩比

        返回:
            压缩结果
        """
        text = "\n".join(
            f"[{msg.get('role', '')}]: {msg.get('content', '')}"
            for msg in history[-30:]
        )
        total_tokens = estimate_tokens(text)

        # 不需要压缩
        if total_tokens < self.EXTRACTIVE_THRESHOLD:
            return CompressionResult(
                compressed_text=text,
                original_tokens=total_tokens,
                compressed_tokens=total_tokens,
                compression_ratio=1.0,
                entities_found=0,
                entities_preserved=0,
                method="none",
            )

        # 仅提取式
        if total_tokens < self.GENERATIVE_THRESHOLD:
            _, result = self._extractive.compress(text, target_ratio)
            return result

        # 提取式 + 生成式
        extracted, ext_result = self._extractive.compress(text, target_ratio)
        gen_result = await self._generative.compress(
            [{"role": "system", "content": extracted}],
            target_ratio=target_ratio,
        )
        gen_result.entities_found = ext_result.entities_found
        gen_result.entities_preserved = ext_result.entities_preserved
        return gen_result


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def compress_history(
    history: list[dict[str, Any]],
    *,
    build_chat_model_fn: Any = None,
    settings: Any = None,
    target_ratio: float = 0.5,
) -> CompressionResult:
    """便捷函数：压缩对话历史。"""
    compressor = ContextCompressor(build_chat_model_fn, settings)
    return await compressor.compress(history, target_ratio)


def extractive_compress_text(text: str, target_ratio: float = 0.5) -> tuple[str, CompressionResult]:
    """便捷函数：仅提取式压缩（毫秒级）。"""
    compressor = ExtractiveCompressor()
    return compressor.compress(text, target_ratio)
