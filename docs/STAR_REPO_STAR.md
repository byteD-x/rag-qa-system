# RAG-QA STAR 主材料

> Last updated: 2026-06-08  
> 口径：所有结果都绑定到当前仓库代码、测试或文档；没有真实业务报告的数据只写“待补指标”。

## STAR 1：把回答从“生成文本”收紧为“证据约束输出”

**Situation**：企业 RAG 问答不能只依赖模型生成，面试官更关心系统如何知道“凭什么答、引用哪里、答不了怎么办”。

**Task**：设计一条从检索证据到回答生成的可信链路，保留引用、回答模式、模型路由和 trace 元数据。

**Action**：
- 使用多信号检索和 EvidenceBlock 保存文档、章节、原文、分数和 evidence path。
- 回答链路根据证据强度选择 grounded、weak 或 refusal 路径。
- 将 `trace_id`、`llm_trace`、成本估算和反馈快照写入 Gateway 工作流与会话元数据。

**Result**：
- 本地测试覆盖 common knowledge、strict refusal、fallback route、引用和反馈快照等关键分支。
- 可在面试中展示“证据结构 + 回答边界 + trace”的工程闭环；真实业务准确率仍需目标数据集验证。

**证据**：`apps/services/api-gateway/src/app/gateway_answering.py`、`apps/services/api-gateway/src/app/gateway_chat_service.py`、`packages/python/shared/grounded_answering.py`、`tests/test_backend_infra.py`、`tests/test_chat_workflow_resume_and_budget.py`

## STAR 2：最终回答阶段接入受控 Tool Calling

**Situation**：模型在最终回答阶段如果可以任意调用工具，会带来不可控的执行面；如果完全不用工具，又无法补充知识库范围、工作流 trace、工具注册状态等摘要信息。

**Task**：在默认关闭的前提下，把最终回答模型的 `tool_calls` 映射到受控 ToolRegistry，并限制工具集合、轮次和 trace 输出。

**Action**：
- 使用 `GATEWAY_FINAL_ANSWER_TOOLS_ENABLED=false` 作为默认关闭开关。
- 仅向非流式 grounded 回答暴露 `kb_scope_summary`、`workflow_trace_summary`、`tool_registry_stats`。
- 最多执行一轮工具调用，拒绝非准入工具，阻断第二轮工具调用，并只记录脱敏工具 trace。

**Result**：
- 工具调用能力可用于回答前的摘要补充，但不会变成 shell、文件写入、任意 HTTP 或动态插件入口。
- 测试覆盖默认关闭、准入工具执行、非准入工具拒绝和第二轮阻断。

**证据**：`apps/services/api-gateway/src/app/gateway_answering.py`、`apps/services/api-gateway/src/app/business_tools.py`、`tests/test_backend_infra.py::test_generate_grounded_answer_final_tools_default_off_keeps_plain_llm_call`、`tests/test_backend_infra.py::test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools`、`tests/test_backend_infra.py::test_generate_grounded_answer_rejects_non_whitelisted_final_tool_call`、`tests/test_backend_infra.py::test_generate_grounded_answer_blocks_second_round_final_tool_calls`

## STAR 3：把工具执行收敛到 Tool Workflow 与只读 MCP adapter

**Situation**：Agent 平台需要给模型和外部客户端提供工具能力，但工具面一旦过宽，会引入维护操作、配置泄露和远程执行风险。

**Task**：复用 ToolRegistry，提供可审计、只读、边界明确的工具工作流和本机 MCP JSON-RPC adapter。

**Action**：
- `POST /api/v1/agents/tool-workflow` 默认 `direct`，显式 `plan_reflect_repair` 才返回规划、反思和一次受控修复。
- 受控修复仅覆盖 `data_controls_dry_run` 空 `scopes` 的 dry-run 场景。
- `POST /api/v1/mcp` 只支持 `initialize`、`tools/list`、`tools/call`，只暴露 3 个摘要工具。

**Result**：
- 工具能力能被 HTTP 与 MCP 客户端复用，但不暴露 `prompt_preview`、配置审计明细、shell、文件写入、任意 HTTP 或动态插件。
- 测试覆盖只读工具列表、blocked 工具拒绝、参数类型检查、权限校验和 audit 事件。

**证据**：`apps/services/api-gateway/src/app/tool_workflow.py`、`apps/services/api-gateway/src/app/gateway_mcp_adapter.py`、`apps/services/api-gateway/src/app/gateway_mcp_routes.py`、`tests/test_tool_workflow.py`、`tests/test_mcp_adapter.py`、`tests/test_backend_infra.py::test_gateway_mcp_route_lists_readonly_tools_and_writes_audit`

## STAR 4：Semantic Cache 的安全命中边界

**Situation**：回答缓存可以降低重复问题成本，但企业知识问答不能让相似问题跨知识库、跨范围误命中。

**Task**：实现回答级缓存，同时保留 scope/corpus 隔离、TTL、LRU 与可观测元数据。

**Action**：
- L1 使用问题、知识库范围和模型名组成精确缓存键。
- L2 语义命中默认关闭，开启后需要同 scope/corpus key 并满足相似度阈值。
- 命中响应只返回原问题 hash，不返回原问题明文。

**Result**：
- 同一范围内的重复问题可以跳过 LLM 生成；语义命中需要显式开关和阈值控制。
- 本地测试覆盖精确命中、语义命中、scope 隔离、缓存元数据和命中后跳过生成。

**证据**：`apps/services/api-gateway/src/app/semantic_cache.py`、`apps/services/api-gateway/src/app/gateway_chat_service.py`、`tests/test_inference_optimization.py::TestSemanticCache`、`tests/test_chat_workflow_resume_and_budget.py::test_handle_chat_message_uses_semantic_cache_hit_without_generation`

## STAR 5：容器构建边界从“大仓库上下文”收敛为服务级资产

**Situation**：AI 应用仓库常包含本地数据、日志、虚拟环境、报告和 Agent 状态，如果直接进入 Docker build context，容易放大构建体积和敏感信息风险。

**Task**：明确容器边界，只覆盖 Web API 运行时、readiness、worker 与 eval，不包含桌面客户端或本机自动化能力。

**Action**：
- 使用 `apps/services/api-gateway/Dockerfile` 与 `apps/services/knowledge-base/Dockerfile`。
- 根 `.dockerignore` 排除 `.env`、虚拟环境、日志、数据目录、报告产物、本地 Agent 状态和 secrets。
- 保留 `.env.example` 等已提交示例文件用于文档说明。

**Result**：
- 容器构建资产边界更清晰，文档与测试明确服务源码和环境示例仍可用。
- 本地 `docker compose config --quiet` 仍取决于机器是否安装 Docker，不作为代码正确性唯一依据。

**证据**：`.dockerignore`、`apps/services/api-gateway/Dockerfile`、`apps/services/knowledge-base/Dockerfile`、`docker-compose.yml`、`tests/test_container_assets.py`

## 待补指标

- 真实业务数据集上的准确率、召回率、幻觉率、延迟、吞吐和成本收益。
- 长时间线上运行的缓存命中率和模型路由收益。
- 生产环境 SLO、容量规划和事故复盘样本。
