# RAG-QA 面试口径 Playbook

> Last updated: 2026-06-08  
> 用途：面试时快速统一“已实现、已验证、可选增强、待补指标”的表达，避免把最小 fixture 或本地测试包装成线上收益。

## 一句话定位

这是一个面向中文企业知识场景的 RAG 问答系统，核心价值不是只把文档塞进向量库，而是把多信号检索、证据约束回答、LangGraph 可恢复运行时、受控工具调用、缓存、成本治理和可观测 trace 串成一个可验证的 AI 应用后端。

## 当前可讲能力

| 能力 | 面试说法 | 证据 |
|---|---|---|
| 多信号检索 | 结构信号、PostgreSQL FTS 与 Qdrant 向量召回通过 weighted RRF 融合，再进入 rerank 和证据选择。 | `apps/services/knowledge-base/src/app/retrieve.py`、`packages/python/shared/retrieval.py`、`tests/test_backend_infra.py::test_retrieve_debug_route_serializes_evidence_and_debug_meta` |
| Grounded Answer | 回答前先判断证据强弱和安全风险，输出引用、answer mode、`llm_trace` 与成本估算。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`packages/python/shared/grounded_answering.py`、`tests/test_backend_infra.py` |
| 最终回答 Tool Calling | 默认关闭；开启后只在非流式 grounded 回答中暴露只读 `system` 工具，最多一轮 ToolRegistry 调用，并阻断第二轮工具调用。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`tests/test_backend_infra.py::test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools`、`tests/test_backend_infra.py::test_generate_grounded_answer_blocks_second_round_final_tool_calls` |
| 受控 Tool Workflow | `direct` 默认执行只读业务工具；`plan_reflect_repair` 只对安全 dry-run 场景做一次受控修复。 | `apps/services/api-gateway/src/app/tool_workflow.py`、`apps/services/api-gateway/src/app/gateway_platform_routes.py`、`tests/test_tool_workflow.py` |
| 只读 MCP adapter | `POST /api/v1/mcp` 支持 `initialize`、`tools/list`、`tools/call`，只暴露 3 个摘要工具，不接入动态插件市场。 | `apps/services/api-gateway/src/app/gateway_mcp_adapter.py`、`apps/services/api-gateway/src/app/gateway_mcp_routes.py`、`tests/test_mcp_adapter.py` |
| Trace 可观测闭环 | 请求、回答、反馈、工作流和事故事件统一携带 `trace_id`/`llm_trace`，可用于排障和审计，不宣称完整 APM 或已有独立 `TraceLogger` 类。 | `packages/python/shared/tracing.py`、`apps/services/api-gateway/src/app/gateway_chat_service.py`、`tests/test_api_error_payloads.py` |
| 运行时治理指标 | Gateway 记录 Tool Workflow 与 Prompt rollback 的聚合计数、成功率、耗时和短失败原因；`/api/v1/system/metrics-summary` 与 `/metrics` 可用于本地排障。 | `apps/services/api-gateway/src/app/governance_metrics.py`、`apps/services/api-gateway/src/app/gateway_system_routes.py`、`tests/test_governance_metrics.py` |
| Semantic Cache | L1 精确命中默认可用；L2 相似问法命中默认关闭，开启后限定同 scope/corpus key 与阈值。 | `apps/services/api-gateway/src/app/semantic_cache.py`、`tests/test_inference_optimization.py::TestSemanticCache`、`tests/test_chat_workflow_resume_and_budget.py::test_handle_chat_message_uses_semantic_cache_hit_without_generation` |
| Docker Web API 边界 | 使用服务级 Dockerfile 和根 `.dockerignore`，容器边界覆盖 Gateway、KB Service、Worker、readiness 与 eval，不包含桌面自动化。 | `apps/services/api-gateway/Dockerfile`、`apps/services/knowledge-base/Dockerfile`、`.dockerignore`、`tests/test_container_assets.py` |

## 不再使用的旧口径

- 不把 Prompt 治理说成“还没有页面”。当前仓库已有 Prompt Template、Agent Profile、五层指令体系、热更新与评估相关接口/视图，面试时应说“平台化能力已具备，真实运营效果待数据验证”。
- 不把工具能力说成泛化执行器。当前工具调用边界是 ToolRegistry 内的受控只读工具、默认关闭的最终回答工具调用、以及只读 MCP adapter。
- 不把本地目录同步的安全边界和模型工具准入混为一谈。前者是知识库连接器的目录范围限制，后者是模型可见工具集合与执行预算。
- 不承诺固定延迟、QPS、命中率、成本节省或真实幻觉率下降；这些必须由目标业务数据集、压测和人工标注报告补充。

## 推荐回答结构

1. 先讲业务问题：企业知识问答需要能解释证据、控制回答边界、支持排障。
2. 再讲工程路线：多信号检索和 grounded answer 解决可信回答，LangGraph 和 trace 解决长链路可恢复与可观测。
3. 补充平台能力：ToolRegistry、最终回答 Tool Calling、Tool Workflow、只读 MCP adapter、Semantic Cache 和运行时治理指标。
4. 最后讲边界：功能已由本地测试和最小 fixture 验证，真实收益指标仍需业务数据补齐。

## 可直接复用的表述

“我没有把这个项目包装成一个 Prompt Demo，而是把 RAG 的检索、回答、工具调用和观测边界都做成了可测试的后端能力。比如最终回答阶段的工具调用默认关闭，开启后也只能调用 `kb_scope_summary`、`workflow_trace_summary`、`tool_registry_stats` 这类只读摘要工具；MCP 入口也只是本机只读 adapter，不开放 shell、文件写、任意 HTTP 或动态插件。运行时治理指标也只记录 Tool Workflow 和 Prompt rollback 的聚合状态，不记录 prompt、payload 或工具输出。”

“缓存这块我会谨慎讲：L1 精确回答缓存和 L2 可选语义命中已经有实现和测试，但我不会说它节省了多少成本。真正的命中率、延迟和成本收益要看目标业务问题分布和压测报告。”
