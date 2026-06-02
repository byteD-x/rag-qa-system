"""用户画像动态构建。

核心能力：
- 从记忆库中聚合构建用户画像
- 画像维度：角色/偏好/习惯/知识水平/关注领域/沟通风格
- 动态更新（每次新记忆入库时增量刷新）
- 画像摘要生成（注入到系统 prompt）

使用方式::

    from .user_profile import UserProfileBuilder

    builder = UserProfileBuilder(store)
    profile = await builder.build(user_id)
    summary = builder.summarize(profile)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class UserProfile:
    """用户画像。"""

    user_id: str = ""

    # 身份角色
    role: str = ""  # 职位/角色
    department: str = ""  # 部门
    responsibility: str = ""  # 职责领域

    # 偏好
    answer_style: str = ""  # 简洁/详细/结构化/口语化
    preferred_language: str = ""  # 偏好语言
    preferred_model: str = ""  # 偏好模型层级

    # 知识水平
    expertise_areas: list[str] = field(default_factory=list)  # 专业领域
    skill_level: str = ""  # 技术水平: beginner/intermediate/expert
    known_versions: list[str] = field(default_factory=list)  # 关注的版本号

    # 行为习惯
    common_questions: list[str] = field(default_factory=list)  # 常问问题类型
    active_hours: str = ""  # 活跃时间
    avg_session_turns: float = 0.0  # 平均会话轮数

    # 元数据
    total_memories: int = 0
    last_updated: float = 0.0
    confidence: float = 0.5


@dataclass
class ProfileRule:
    """画像构建规则 —— 如何从记忆中提取画像。"""
    memory_type: str = "preference"
    subject_pattern: str = ""  # subject 匹配模式
    target_field: str = ""  # 画像中的目标字段
    priority: int = 0  # 优先级（越高越重要）


# ---------------------------------------------------------------------------
# 画像构建规则
# ---------------------------------------------------------------------------

PROFILE_RULES: list[ProfileRule] = [
    ProfileRule("preference", "用户角色", "role", 10),
    ProfileRule("preference", "用户", "role", 9),  # 泛化匹配
    ProfileRule("fact", "用户", "department", 8),
    ProfileRule("fact", "用户部门", "department", 8),
    ProfileRule("preference", "回答风格", "answer_style", 7),
    ProfileRule("preference", "偏好回答风格", "answer_style", 7),
    ProfileRule("preference", "偏好语言", "preferred_language", 7),
    ProfileRule("fact", "当前使用版本", "known_versions", 6),
    ProfileRule("fact", "使用版本", "known_versions", 6),
    ProfileRule("knowledge", "专业领域", "expertise_areas", 5),
    ProfileRule("fact", "职责", "responsibility", 8),
    ProfileRule("fact", "负责", "responsibility", 8),
]


# ---------------------------------------------------------------------------
# 画像构建器
# ---------------------------------------------------------------------------


class UserProfileBuilder:
    """从记忆库中动态构建用户画像。"""

    def __init__(self, store: Any = None) -> None:
        self._store = store

    async def build(self, user_id: str) -> UserProfile:
        """从记忆库构建完整用户画像。

        参数:
            user_id: 用户标识

        返回:
            UserProfile
        """
        profile = UserProfile(user_id=user_id, last_updated=time.time())

        if self._store is None:
            return profile

        try:
            all_memories = await self._store.list_by_user(user_id, limit=500)
        except Exception as exc:
            logger.warning("user_profile_build_failed user=%s err=%s", user_id, exc)
            return profile

        if not all_memories:
            return profile

        profile.total_memories = len(all_memories)

        # 只使用活跃记忆（有效重要性 > 0.1）
        active = [m for m in all_memories if getattr(m, "is_active", True)]
        active = [m for m in active if getattr(m, "effective_importance", 0.5) > 0.1]

        # 按规则匹配
        for mem in active:
            self._apply_rule(profile, mem)

        # 汇总技能水平
        profile.skill_level = self._estimate_skill(profile)

        # 画像置信度
        profile.confidence = min(round(len(active) / 20.0, 2), 1.0)

        return profile

    def summarize(self, profile: UserProfile) -> str:
        """生成画像摘要文本（可注入到系统 prompt）。"""
        parts: list[str] = []

        if profile.role:
            role_line = f"用户角色：{profile.role}"
            if profile.department:
                role_line += f"，部门：{profile.department}"
            parts.append(role_line)

        if profile.responsibility:
            parts.append(f"职责领域：{profile.responsibility}")

        if profile.expertise_areas:
            parts.append(f"专业领域：{'、'.join(profile.expertise_areas[:5])}")

        if profile.answer_style:
            style_map = {
                "简洁": "偏好简洁扼要的回答",
                "详细": "偏好详尽全面的回答",
                "结构化": "偏好分点分步骤的结构化回答",
                "口语化": "偏好自然口语化的交流风格",
            }
            parts.append(style_map.get(profile.answer_style, f"交流风格：{profile.answer_style}"))

        if profile.known_versions:
            parts.append(f"关注版本：{'、'.join(profile.known_versions[:3])}")

        if profile.skill_level:
            level_map = {
                "expert": "技术水平：专家级，可以使用专业术语",
                "intermediate": "技术水平：中级，平衡专业性和易懂性",
                "beginner": "技术水平：初级，需要更多解释和引导",
            }
            parts.append(level_map.get(profile.skill_level, ""))

        return "；".join(part for part in parts if part)

    # ---- 内部 ----

    def _apply_rule(self, profile: UserProfile, memory: Any) -> None:
        """将记忆按规则映射到画像字段。"""
        subject = str(getattr(memory, "subject", "") or "").strip()
        obj = str(getattr(memory, "object", "") or "").strip()
        memory_type = str(getattr(memory, "memory_type", "") or "fact").strip()
        importance = getattr(memory, "importance", 0.5)

        for rule in sorted(PROFILE_RULES, key=lambda r: r.priority, reverse=True):
            if rule.memory_type != memory_type:
                continue
            if rule.subject_pattern not in subject:
                continue

            field = rule.target_field
            if field == "role" and not profile.role:
                profile.role = obj
            elif field == "department" and not profile.department:
                profile.department = obj
            elif field == "responsibility" and not profile.responsibility:
                profile.responsibility = obj
            elif field == "answer_style" and not profile.answer_style:
                profile.answer_style = obj
            elif field == "preferred_language":
                profile.preferred_language = obj
            elif field == "known_versions" and obj not in profile.known_versions:
                if importance >= 0.4:
                    profile.known_versions.append(obj)
            elif field == "expertise_areas" and obj not in profile.expertise_areas:
                if importance >= 0.3:
                    profile.expertise_areas.append(obj)

    def _estimate_skill(self, profile: UserProfile) -> str:
        """估算用户技术水平。"""
        score = 0.0
        if profile.expertise_areas:
            score += min(len(profile.expertise_areas) * 0.1, 0.3)
        if profile.known_versions:
            score += min(len(profile.known_versions) * 0.05, 0.15)
        tech_keywords = ["开发", "工程师", "架构", "运维", "算法", "数据", "代码"]
        if profile.role and any(kw in profile.role for kw in tech_keywords):
            score += 0.25
        if profile.responsibility and any(kw in profile.responsibility for kw in tech_keywords):
            score += 0.15

        if score >= 0.5:
            return "expert"
        elif score >= 0.25:
            return "intermediate"
        return "beginner"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


async def build_user_profile(user_id: str, *, store: Any = None) -> UserProfile:
    """便捷函数：构建用户画像。"""
    builder = UserProfileBuilder(store)
    return await builder.build(user_id)


def summarize_user_profile(profile: UserProfile) -> str:
    """便捷函数：生成画像摘要。"""
    builder = UserProfileBuilder()
    return builder.summarize(profile)
