# AGENTS.md

> 本文件定义本仓库的人机协作协议（Owner / AI Agent / Reviewer）。
> Last updated: 2026-06-06

## 1. 目标与范围

本规范适用于仓库根目录及所有子目录，目标是让 AI 参与开发时做到：
- 结果可验证：每项完成都能用命令或测试结果证明
- 过程可追踪：任务状态、阻塞原因、变更范围清晰
- 风险可控：默认小步变更、可回滚、避免破坏性操作

## 2. 角色定义

- `Owner`：定义业务目标、确认优先级、做最终取舍
- `AI Agent`：执行实现、补齐测试与文档、输出验证证据
- `Reviewer`：审查风险与回归，确认是否达到交付标准

## 3. 协作原则

1. 不暴露敏感信息：禁止输出或提交密钥、口令、token、连接串、`.env` 内容。
2. 不使用高风险命令：默认禁止破坏性操作；确需清理旧文件时必须限定范围且可解释。
3. 不做“猜测完成”：没有验证结果时不得标记 `done`。
4. 不做超大改动：超过当前任务边界的重构必须先拆分并获得确认。
5. 保持编码一致性：新增或修改文件统一使用 `UTF-8`（无 BOM）。
6. 接口或配置变更必须同步文档：至少更新 `README.md`、`AGENTS.md` 或相关 `docs/*`。

## 4. 状态机

任务状态统一使用以下枚举：
- `todo`
- `in_progress`
- `blocked`
- `review`
- `done`

允许的流转：
- `todo -> in_progress -> review -> done`
- 任意状态在遇到阻塞时可转 `blocked`
- `blocked` 解除后回到 `in_progress`

## 5. AI Agent 标准执行流程

1. 明确范围：复述目标，列出本次改动边界。
2. 读取上下文：先看相关代码与文档，再落地改动。
3. 最小实现：优先小改动，避免无关重构。
4. 自检验证：执行必要测试或检查，记录命令与结果。
5. 文档同步：使用方式、接口、配置变化必须更新文档。
6. 交付说明：输出 `What / Why / How to verify / Risk`。

## 6. Definition of Done

同时满足以下条件才可标记 `done`：
- 功能或文档改动与任务目标一致
- 关键路径验证通过
- 无新增敏感信息泄露风险
- 受影响文档已同步
- 交接信息完整

## 7. 基线验证命令

在仓库根目录执行：

- `python scripts/quality/check-encoding.py --root .`
- `cd apps/web && npm run test:unit`
- `cd apps/web && npm run build`
- `python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base`
- `docker compose config --quiet`

说明：
- 文档类改动至少执行编码检查与 `docker compose config --quiet`
- 涉及前端时补跑 `cd apps/web && npm run test:unit` 与 `cd apps/web && npm run build`
- 涉及 Python 后端时补跑 `python -m compileall ...` 或对应服务测试

## 8. 任务记录规范

### 8.1 里程碑表模板
| milestone | description | owner | status | updated_at |
|---|---|---|---|---|
| Mx | 一句话目标 | `@owner` | `todo` | YYYY-MM-DD |

### 8.2 任务表模板
| task_id | milestone | title | assignee | status | verify_cmd | expected_result | updated_at |
|---|---|---|---|---|---|---|---|
| T-XXX-001 | Mx | 任务名称 | `@agent` | `todo` | `cmd` | 一句话结果 | YYYY-MM-DD |

## 9. Blocked 上报格式

当任务进入 `blocked`，按以下结构同步：
- `问题`
- `影响`
- `已尝试`
- `需要决策`

## 10. 交付输出模板

- `What`：改了什么
- `Why`：为什么这样改
- `How to verify`：如何验证（命令 + 预期结果）
- `Risk`：已知风险与回滚方式

## 11. AI Agent 增强模块索引

本项目已实现 AI Agent 全栈能力，各模块职责如下：

| 模块 | 文件 | 职责 |
|------|------|------|
| 工具注册中心 | `apps/services/api-gateway/src/app/tool_registry.py` | 可扩展工具注册/发现/执行/MCP兼容 |
| 工具发现与沙箱 | `apps/services/api-gateway/src/app/tool_discovery.py`、`tool_pipeline.py`、`tool_sandbox.py` | 工具发现、流水线执行与安全边界 |
| Agent 编排 | `apps/services/api-gateway/src/app/agent_orchestrator.py` | 多步骤 Agent 规划、证据聚合与预算估算 |
| Agent 元认知 | `apps/services/api-gateway/src/app/agent_metacognition.py` | 不确定性识别、澄清建议与错误恢复动作 |
| 人工接管队列 | `apps/services/api-gateway/src/app/gateway_handoff.py` | 本地会话接管队列抽象、优先级排序与原子认领 |
| 任务拆解引擎 | `apps/services/api-gateway/src/app/task_decomposer.py` | 复杂度评估+LLM拆解+DAG并行 |
| 反思闭环 | `apps/services/api-gateway/src/app/agent_reflection.py` | 输出自检+失败分析+策略记忆 |
| 记忆系统 | `apps/services/api-gateway/src/app/memory_extractor.py` | 三层记忆提取+Qdrant检索 |
| 记忆增强 | `apps/services/api-gateway/src/app/memory_importance.py`、`memory_injection.py`、`memory_integrator.py` | 重要性评分、遗忘曲线、上下文注入 |
| 语义缓存 | `apps/services/api-gateway/src/app/semantic_cache.py` | L1-L3三层缓存+LRU淘汰 |
| 模型监控 | `apps/services/api-gateway/src/app/model_health.py` | 延迟追踪+自动熔断+健康评分 |
| 复杂度分类 | `apps/services/api-gateway/src/app/complexity_classifier.py` | 7维特征快速评估+模型层级推荐 |
| 请求合并 | `apps/services/api-gateway/src/app/request_coalescer.py` | 窗口合并+leader-follower模式 |
| 指令体系 | `apps/services/api-gateway/src/app/instruction_merger.py` | 五层指令合并+冲突检测+变量系统 |
| 指令热更新与评估 | `apps/services/api-gateway/src/app/instruction_hotreload.py`、`instruction_evaluator.py` | 指令版本追踪、热更新事件与 A/B 评估 |
| 场景模板 | `apps/services/api-gateway/src/app/scene_templates.py` | 6大场景模板+一键切换 |
| 幻觉检测 | `apps/services/api-gateway/src/app/hallucination_detector.py` | 规则+LLM双路径幻觉检测 |
| 成本治理 | `apps/services/api-gateway/src/app/cost_attribution.py`、`cost_budget.py`、`gateway_pricing.py` | 成本归因、预算控制与 LLM 定价估算 |
| 平台安全 | `apps/services/api-gateway/src/app/api_key_manager.py`、`pii_detector.py`、`agent_guardrails.py` | API Key 生命周期、PII 检测与 Agent 护栏 |
| 上下文优化 | `apps/services/api-gateway/src/app/context_window.py`、`context_compressor.py`、`context_prioritizer.py` | 上下文窗口管理、压缩与优先级选择 |
| TTFT 优化 | `apps/services/api-gateway/src/app/ttft_optimizer.py` | 首 token 延迟追踪与健康判断 |
| Agent增强 | `apps/services/api-gateway/src/app/gateway_agent.py` | run_enhanced_agent()统一入口 |

测试覆盖：

- `tests/test_agent_capabilities.py` — Agent 核心能力（工具注册/任务拆解/反思/记忆）
- `tests/test_inference_optimization.py` — 推理优化（缓存/健康监控/复杂度/合并）
- `tests/test_platform_ecosystem.py` — 平台生态（指令/场景/幻觉/SDK）
- `tests/test_agent_orchestration.py`、`tests/test_agent_metacognition.py` — Agent 编排、预算与元认知
- `tests/test_memory_enhancement.py`、`tests/test_context_optimization.py` — 记忆增强与上下文优化
- `tests/test_cost_management.py`、`tests/test_platform_ecosystem_phase2.py` — 成本治理、API Key、PII、指令热更新与 TTFT
- `tests/test_backend_infra.py` — Gateway/KB 基础设施、人工接管队列和治理聚合回归
