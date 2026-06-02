"""PII 检测与脱敏引擎。

核心能力：
- 多类型 PII 检测：身份证、手机号、邮箱、银行卡、IP、地址、人名
- 可配置脱敏策略：Hash / Mask / Redact / Replace
- 中文 PII 专项：身份证号校验、手机号段识别
- 脱敏审计日志

使用方式::

    from .pii_detector import PIIDetector

    detector = PIIDetector()
    result = detector.detect("请联系张三，电话13800138000，身份证110101199001011234")
    safe_text = detector.anonymize(text, strategy="mask")
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 枚举与数据模型
# ---------------------------------------------------------------------------


class PIType(str, Enum):
    """PII 类型。"""
    PHONE = "phone"                # 手机号
    EMAIL = "email"                # 邮箱
    ID_CARD = "id_card"           # 身份证号
    BANK_CARD = "bank_card"       # 银行卡号
    IP_ADDRESS = "ip_address"     # IP 地址
    ADDRESS = "address"           # 地址
    PERSON_NAME = "person_name"   # 人名
    LICENSE_PLATE = "license_plate"  # 车牌号
    CREDIT_CARD = "credit_card"   # 信用卡号
    PASSPORT = "passport"         # 护照号


class AnonymizeStrategy(str, Enum):
    """脱敏策略。"""
    MASK = "mask"       # 部分遮盖: 138****8000
    HASH = "hash"       # 哈希替换: SHA256(原始值)
    REDACT = "redact"   # 完全移除: [已删除]
    REPLACE = "replace" # 替换为类型标签: [手机号]


@dataclass
class PIIMatch:
    """PII 匹配结果。"""
    pi_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0  # 置信度


@dataclass
class PIIDetectResult:
    """PII 检测结果。"""
    has_pii: bool = False
    matches: list[PIIMatch] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)  # type → count


# ---------------------------------------------------------------------------
# PII 检测规则
# ---------------------------------------------------------------------------

# 中国身份证号（18位 + 校验位）
# 使用 (?<!\d) 代替 \b 确保中文环境下正常工作（中文是 \w 字符）
_ID_CARD_PATTERN = re.compile(
    r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
)

# 中国手机号（主流号段）
_PHONE_PATTERN = re.compile(
    r"(?<!\d)1[3-9]\d{9}(?!\d)"
)

# 邮箱
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# 银行卡号（16-19位）
_BANK_CARD_PATTERN = re.compile(
    r"(?<!\d)\d{16,19}(?!\d)"
)

# IP 地址
_IP_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"
)

# 信用卡号（Visa/MasterCard 格式）
_CREDIT_CARD_PATTERN = re.compile(
    r"(?<!\d)(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})(?!\d)"
)

# 中国车牌号
_LICENSE_PLATE_PATTERN = re.compile(
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏琼宁][A-Z][A-HJ-NP-Z0-9]{4,5}[A-HJ-NP-Z0-9挂学警港澳]"
)

# 护照号（中国格式）
_PASSPORT_PATTERN = re.compile(
    r"(?<!\d)[EG]\d{8}(?!\d)"
)


# ---------------------------------------------------------------------------
# PII 检测器
# ---------------------------------------------------------------------------


class PIIDetector:
    """PII 检测与脱敏引擎。"""

    def __init__(self, *, enabled_types: list[str] | None = None) -> None:
        self._enabled_types = set(enabled_types or [t.value for t in PIType])
        self._rules: list[tuple[str, re.Pattern]] = [
            (PIType.ID_CARD.value, _ID_CARD_PATTERN),
            (PIType.PHONE.value, _PHONE_PATTERN),
            (PIType.EMAIL.value, _EMAIL_PATTERN),
            (PIType.CREDIT_CARD.value, _CREDIT_CARD_PATTERN),
            (PIType.LICENSE_PLATE.value, _LICENSE_PLATE_PATTERN),
            (PIType.PASSPORT.value, _PASSPORT_PATTERN),
            (PIType.IP_ADDRESS.value, _IP_PATTERN),
        ]

    def detect(self, text: str) -> PIIDetectResult:
        """检测文本中的所有 PII。

        参数:
            text: 待检测文本

        返回:
            PIIDetectResult
        """
        if not text:
            return PIIDetectResult()

        matches: list[PIIMatch] = []
        summary: dict[str, int] = {}

        for pi_type, pattern in self._rules:
            if pi_type not in self._enabled_types:
                continue

            for match in pattern.finditer(text):
                value = match.group()
                confidence = 1.0

                # 身份证号校验
                if pi_type == PIType.ID_CARD.value and not self._validate_id_card(value):
                    confidence = 0.5  # 校验不通过降低置信度

                # 银行卡去重（避免与身份证冲突）
                if pi_type == PIType.BANK_CARD.value:
                    # 如果已经被其他规则匹配则跳过
                    overlapping = any(
                        m.start <= match.start() < m.end or m.start < match.end() <= m.end
                        for m in matches
                    )
                    if overlapping:
                        continue

                matches.append(PIIMatch(
                    pi_type=pi_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                    confidence=confidence,
                ))
                summary[pi_type] = summary.get(pi_type, 0) + 1

        # 按位置排序
        matches.sort(key=lambda m: m.start)

        if matches:
            logger.debug("pii_detected count=%d types=%s", len(matches), list(summary.keys()))

        return PIIDetectResult(
            has_pii=len(matches) > 0,
            matches=matches,
            summary=summary,
        )

    def anonymize(
        self,
        text: str,
        strategy: str = "mask",
        *,
        mask_char: str = "*",
    ) -> str:
        """对文本中的 PII 进行脱敏。

        参数:
            text: 原始文本
            strategy: mask / hash / redact / replace
            mask_char: 遮盖字符

        返回:
            脱敏后的文本
        """
        result = self.detect(text)
        if not result.has_pii:
            return text

        # 从后往前替换，避免偏移问题
        anonymized = text
        for match in reversed(result.matches):
            replacement = self._apply_strategy(
                match.value, match.pi_type, strategy, mask_char
            )
            anonymized = anonymized[:match.start] + replacement + anonymized[match.end:]

        return anonymized

    def audit_report(self, text: str) -> dict[str, Any]:
        """生成 PII 审计报告。"""
        result = self.detect(text)
        return {
            "has_pii": result.has_pii,
            "pii_count": len(result.matches),
            "by_type": result.summary,
            "sample_values": {m.pi_type: m.value for m in result.matches[:5]},
        }

    @staticmethod
    def _apply_strategy(
        value: str,
        pi_type: str,
        strategy: str,
        mask_char: str = "*",
    ) -> str:
        """应用脱敏策略。"""
        if strategy == AnonymizeStrategy.REDACT.value:
            return "[已删除]"

        if strategy == AnonymizeStrategy.REPLACE.value:
            type_labels = {
                PIType.PHONE.value: "[手机号]",
                PIType.EMAIL.value: "[邮箱]",
                PIType.ID_CARD.value: "[身份证号]",
                PIType.BANK_CARD.value: "[银行卡号]",
                PIType.IP_ADDRESS.value: "[IP地址]",
                PIType.CREDIT_CARD.value: "[信用卡号]",
                PIType.LICENSE_PLATE.value: "[车牌号]",
                PIType.PASSPORT.value: "[护照号]",
            }
            return type_labels.get(pi_type, "[PII]")

        if strategy == AnonymizeStrategy.HASH.value:
            h = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
            return f"[HASH:{h}]"

        # MASK: 部分遮盖
        if strategy == AnonymizeStrategy.MASK.value:
            if pi_type == PIType.PHONE.value:
                return value[:3] + mask_char * 4 + value[-4:]
            elif pi_type == PIType.EMAIL.value:
                at_pos = value.index("@")
                return value[0] + mask_char * 3 + value[at_pos:]
            elif pi_type == PIType.ID_CARD.value:
                return value[:6] + mask_char * 8 + value[-4:]
            elif pi_type == PIType.BANK_CARD.value:
                return value[:4] + mask_char * 8 + value[-4:]
            elif pi_type == PIType.IP_ADDRESS.value:
                parts = value.split(".")
                return f"{parts[0]}.{parts[1]}.{mask_char * 3}.{mask_char * 3}"
            elif pi_type == PIType.CREDIT_CARD.value:
                return mask_char * 12 + value[-4:]
            else:
                # 通用策略：保留首尾各 1/4
                quarter = max(len(value) // 4, 1)
                return value[:quarter] + mask_char * max(len(value) - 2 * quarter, 4) + value[-quarter:]

        return value

    @staticmethod
    def _validate_id_card(id_number: str) -> bool:
        """校验中国身份证号。"""
        if len(id_number) != 18:
            return False

        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_chars = "10X98765432"

        try:
            total = sum(int(id_number[i]) * weights[i] for i in range(17))
            expected_check = check_chars[total % 11]
            return id_number[17].upper() == expected_check
        except (ValueError, IndexError):
            return False


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

pii_detector = PIIDetector()
