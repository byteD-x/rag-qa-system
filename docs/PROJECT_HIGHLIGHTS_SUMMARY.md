# RAG-QA 项目亮点摘要

> Last updated: 2026-06-08  
> 用途：作品集、简历和项目复盘的一页式摘要。完整 STAR 展开见 `docs/STAR_REPO_STAR.md` 与 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`。

## 项目定位

RAG-QA 是一个企业知识问答后端与管理台项目，覆盖知识库入库、混合检索、grounded answer、LangGraph 可恢复运行时、Agent 工具调用、平台治理、缓存、成本估算和可观测 trace。

## 已落地亮点

| 方向 | 亮点 | 证据 |
|---|---|---|
| 检索工程 | 结构、FTS、向量多路召回，weighted RRF 融合，debug API 输出 `signal_scores` 与 `evidence_path`。 | `apps/services/knowledge-base/src/app/retrieve.py`、`tests/test_backend_infra.py::test_retrieve_debug_route_serializes_evidence_and_debug_meta` |
| 可信回答 | 回答链路区分 grounded、weak、refusal/common knowledge，保留引用、`llm_trace` 与反馈快照。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`tests/test_backend_infra.py` |
| Tool Calling | 最终回答工具调用默认关闭；开启后只允许 3 个只读摘要工具，最多一轮执行。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`tests/test_backend_infra.py::test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools` |
| Tool Workflow | `direct` 和 `plan_reflect_repair` 两种模式复用 ToolRegistry；受控修复只覆盖安全 dry-run。 | `apps/services/api-gateway/src/app/tool_workflow.py`、`tests/test_tool_workflow.py` |
| MCP | 本机只读 JSON-RPC adapter 支持 `initialize`、`tools/list`、`tools/call`，只暴露摘要工具。 | `apps/services/api-gateway/src/app/gateway_mcp_adapter.py`、`tests/test_mcp_adapter.py` |
| 可观测 | Gateway、KB、反馈、审计事件携带 `trace_id`/`llm_trace`；工作流持久化记录工具调用和状态投影。 | `packages/python/shared/tracing.py`、`apps/services/api-gateway/src/app/gateway_workflows.py`、`tests/test_api_error_payloads.py` |
| 运行时治理指标 | Tool Workflow 与 Prompt rollback 聚合计数、成功率、耗时和短失败原因，JSON 摘要与 Prometheus 指标均可读取。 | `apps/services/api-gateway/src/app/governance_metrics.py`、`apps/services/api-gateway/src/app/gateway_system_routes.py`、`tests/test_governance_metrics.py` |
| 知识库治理 UI | 治理页支持单文档受控 rebuild，必须先 dry-run 且 payload 签名匹配后才执行固定端点调用。 | `apps/web/src/views/kb/KBGovernanceView.vue`、`apps/web/src/views/kb/KBGovernanceView.test.ts` |
| Semantic Cache | L1 精确命中与可选 L2 语义命中；L2 受 scope/corpus key 与阈值控制。 | `apps/services/api-gateway/src/app/semantic_cache.py`、`tests/test_inference_optimization.py::TestSemanticCache` |
| Docker 边界 | 服务级 Dockerfile 加根 `.dockerignore`，排除本地状态和敏感文件，保留环境示例。 | `apps/services/api-gateway/Dockerfile`、`apps/services/knowledge-base/Dockerfile`、`tests/test_container_assets.py` |

## 简历可写版本

独立设计并实现企业级 RAG 问答系统，覆盖多信号检索融合、证据约束回答、LangGraph 可恢复工作流、受控 ToolRegistry/MCP 工具体系、知识库治理 UI、回答级缓存、成本估算、trace 审计、运行时治理指标和 Docker Web API 部署边界；通过后端 pytest、前端单测和最小离线评测 fixture 验证核心链路。

## 边界说明

- 不宣称固定线上准确率、延迟、QPS、缓存命中率或成本节省。
- 不把只读 MCP adapter 说成动态插件市场。
- 不把最终回答 Tool Calling 说成任意工具执行能力。
- 不把治理页受控 rebuild 说成文件上传、目录扫描、任意路径重建或后台队列能力。
- 不把 `usage_reconciliation` 说成自动账单拉取或财务级结算。
