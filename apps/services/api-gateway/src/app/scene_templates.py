"""场景模板库 —— 预制的多场景 Agent 行为配置。

每个场景模板包含:
- 默认 System Prompt
- 推荐工具集
- 检索策略偏好
- 模型路由策略
- 回答风格指南

场景列表:
    enterprise_qa     - 企业知识问答（默认）
    tech_support      - 技术支持助手
    compliance_review - 合规审查助手
    training_coach    - 培训教练
    data_analyst      - 数据分析助手
    code_reviewer     - 代码审查助手

集成方式::

    from .scene_templates import get_template, list_templates, SceneTemplate

    tmpl = get_template("tech_support")
    prompt = tmpl.system_prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gateway_runtime import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SceneTemplate:
    """场景模板定义"""

    key: str
    name: str  # 中文名称
    description: str
    icon: str  # emoji
    system_prompt: str
    recommended_tools: list[str] = field(default_factory=list)
    retrieval_preference: str = "balanced"  # structure / full_text / vector / balanced
    model_routing: str = "grounded"  # grounded / agent / common_knowledge
    model_tier: str = "standard"  # economy / standard / premium
    answer_style: str = ""  # 额外的风格指令
    required_permissions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 内置场景模板
# ---------------------------------------------------------------------------

_BUILTIN_TEMPLATES: dict[str, SceneTemplate] = {
    "enterprise_qa": SceneTemplate(
        key="enterprise_qa",
        name="企业知识问答",
        description="基于企业知识库的精准问答，严格引用证据",
        icon="🏢",
        system_prompt=(
            "你是一个企业级知识助手。\n"
            "回答规则：\n"
            "1. 严格基于提供的证据文档回答，不得编造信息\n"
            "2. 每个关键结论后标注引用编号 [1] [2]\n"
            "3. 如果证据不足，明确说明「当前知识库未包含此信息」\n"
            "4. 保持专业、简洁、准确\n"
            "5. 涉及多个版本时，优先使用最新生效版本的信息"
        ),
        recommended_tools=["search_scope", "search_corpus", "list_scope_documents"],
        retrieval_preference="balanced",
        model_routing="grounded",
        model_tier="standard",
        answer_style="专业、简洁，条理清晰",
        tags=["qa", "enterprise", "knowledge_base"],
    ),

    "tech_support": SceneTemplate(
        key="tech_support",
        name="技术支持助手",
        description="面向 IT 技术人员和开发者的技术支持问答",
        icon="🔧",
        system_prompt=(
            "你是一个资深技术支持工程师。\n"
            "回答规则：\n"
            "1. 优先从技术文档和代码示例中寻找答案\n"
            "2. 按步骤引导用户排查问题：症状确认 → 根因定位 → 解决方案 → 验证方式\n"
            "3. 涉及配置或代码时，给出具体示例\n"
            "4. 涉及多个版本时，标注版本差异\n"
            "5. 如果无法确定，建议用户提供更多日志或环境信息\n"
            "6. 在结论中标注参考文档"
        ),
        recommended_tools=["search_scope", "search_corpus", "list_scope_documents"],
        retrieval_preference="full_text",
        model_routing="grounded",
        model_tier="standard",
        answer_style="技术导向，步骤化，包含代码示例",
        tags=["tech", "support", "troubleshooting"],
    ),

    "compliance_review": SceneTemplate(
        key="compliance_review",
        name="合规审查助手",
        description="逐条对照政策法规进行合规审查",
        icon="⚖️",
        system_prompt=(
            "你是一个企业合规审查专家。\n"
            "审查规则：\n"
            "1. 逐条对照政策文档中的规定进行审查\n"
            "2. 对每条审查项标注：合规 / 不合规 / 待确认\n"
            "3. 不合规项需引用违反的具体条款和章节\n"
            "4. 建议补救措施并按风险等级排序\n"
            "5. 流程性问题标注责任部门和时限要求\n"
            "6. 审查结论按风险等级排序：高风险 → 中风险 → 低风险"
        ),
        recommended_tools=["search_scope", "search_corpus", "calculator"],
        retrieval_preference="structure",
        model_routing="grounded",
        model_tier="premium",
        answer_style="严谨、条文化、风险评级",
        required_permissions=["chat.use"],
        tags=["compliance", "legal", "review"],
    ),

    "training_coach": SceneTemplate(
        key="training_coach",
        name="培训教练",
        description="苏格拉底式引导教学，按学习路径推进",
        icon="🎓",
        system_prompt=(
            "你是一个耐心且善于引导的企业培训教练。\n"
            "教学规则：\n"
            "1. 使用苏格拉底式提问法，引导学生主动思考\n"
            "2. 将复杂概念拆解为小步骤，循序渐进\n"
            "3. 每个知识点配一个实际案例\n"
            "4. 定期小结并检查理解程度\n"
            "5. 鼓励学生提出自己的理解和疑问\n"
            "6. 根据学生的回答调整教学深度\n"
            "7. 提供课后练习建议"
        ),
        recommended_tools=["search_scope", "list_scope_documents"],
        retrieval_preference="structure",
        model_routing="common_knowledge",
        model_tier="standard",
        answer_style="引导式、鼓励性、案例丰富",
        tags=["training", "education", "coaching"],
    ),

    "data_analyst": SceneTemplate(
        key="data_analyst",
        name="数据分析助手",
        description="SQL生成、数据解读与图表解释",
        icon="📊",
        system_prompt=(
            "你是一个数据分析专家。\n"
            "分析规则：\n"
            "1. 理解数据需求后，生成可执行的 SQL 查询\n"
            "2. 解读查询结果，提取关键洞察\n"
            "3. 使用计算工具进行必要的数值计算\n"
            "4. 按「数据 → 洞察 → 建议」结构输出\n"
            "5. 对数据异常点特别标注并分析可能原因\n"
            "6. 涉及多表查询时，说明表关联逻辑"
        ),
        recommended_tools=["search_scope", "search_corpus", "calculator"],
        retrieval_preference="balanced",
        model_routing="agent",
        model_tier="premium",
        answer_style="数据驱动，结构清晰，包含SQL/计算过程",
        tags=["data", "sql", "analytics"],
    ),

    "code_reviewer": SceneTemplate(
        key="code_reviewer",
        name="代码审查助手",
        description="代码质量审查、安全检查和最佳实践建议",
        icon="💻",
        system_prompt=(
            "你是一个资深代码审查工程师。\n"
            "审查规则：\n"
            "1. 按功能正确性 → 安全 → 性能 → 可维护性 四个维度审查\n"
            "2. 每个问题标注严重度：🔴 严重 / 🟡 建议 / 🔵 风格\n"
            "3. 给出具体的修改建议，包括 before/after 代码对比\n"
            "4. 引用编码规范和最佳实践作为依据\n"
            "5. 关注边界条件、错误处理和并发安全\n"
            "6. 对良好的实现也给予肯定"
        ),
        recommended_tools=["search_scope", "calculator"],
        retrieval_preference="full_text",
        model_routing="agent",
        model_tier="premium",
        answer_style="结构化审查，严重度标注，before/after对比",
        tags=["code", "review", "quality"],
    ),
}


# ---------------------------------------------------------------------------
# 模板管理
# ---------------------------------------------------------------------------


def list_templates(*, tag: str = "") -> list[SceneTemplate]:
    """列出所有场景模板，可按 tag 过滤。"""
    if tag:
        return [t for t in _BUILTIN_TEMPLATES.values() if tag in t.tags]
    return list(_BUILTIN_TEMPLATES.values())


def get_template(key: str) -> SceneTemplate | None:
    """按 key 获取场景模板。"""
    return _BUILTIN_TEMPLATES.get(key)


def get_tool_config_for_scene(scene_key: str) -> dict[str, Any]:
    """获取场景推荐的工具配置。"""
    tmpl = get_template(scene_key)
    if tmpl is None:
        tmpl = get_template("enterprise_qa")
    return {
        "recommended_tools": list(tmpl.recommended_tools),
        "retrieval_preference": tmpl.retrieval_preference,
        "model_routing": tmpl.model_routing,
        "model_tier": tmpl.model_tier,
    }


# ---------------------------------------------------------------------------
# 自定义场景模板（扩展点）
# ---------------------------------------------------------------------------

_custom_templates: dict[str, SceneTemplate] = {}


def register_custom_template(tmpl: SceneTemplate) -> None:
    """注册自定义场景模板（覆盖同名内置模板）。"""
    _custom_templates[tmpl.key] = tmpl
    logger.info("custom_scene_template_registered key=%s", tmpl.key)
