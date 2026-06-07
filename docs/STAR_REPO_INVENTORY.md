# RAG-QA 仓库盘点

> Generated/updated: 2026-06-08  
> 范围：仅基于当前 Git tracked source、测试、脚本和文档做保守盘点；不引用未跟踪构建产物或临时导出目录作为源码事实。

## 源码规模

| 类别 | 当前 tracked 文件数 |
|---|---:|
| API Gateway Python 模块 | 68 |
| Knowledge Base Python 模块 | 37 |
| Shared Python 模块 | 25 |
| 后端 pytest 文件 | 26 |
| Web Vue 组件/视图 | 39 |
| Web TypeScript 文件 | 32 |
| Python 脚本 | 19 |
| Markdown 文档 | 15 |

统计命令示例：

```powershell
git ls-files apps/services/api-gateway/src/app/*.py
git ls-files apps/services/knowledge-base/src/app/*.py
git ls-files tests/test_*.py
```

## 主要入口点

| 入口 | 文件 | 说明 |
|---|---|---|
| Gateway FastAPI | `apps/services/api-gateway/src/app/main.py` | 认证、聊天、平台、分析、MCP 等路由挂载 |
| Knowledge Base FastAPI | `apps/services/knowledge-base/src/app/main.py` | 知识库、检索、治理、视觉资产、同步路由 |
| Chat 服务 | `apps/services/api-gateway/src/app/gateway_chat_service.py` | 会话准备、检索、生成、持久化、cache 与 trace |
| Grounded Answer | `apps/services/api-gateway/src/app/gateway_answering.py` | 回答模式、模型路由、最终回答工具调用 |
| ToolRegistry | `apps/services/api-gateway/src/app/tool_registry.py` | 工具注册、LangChain schema、执行统计 |
| Tool Workflow | `apps/services/api-gateway/src/app/tool_workflow.py` | `direct` 与 `plan_reflect_repair` 工具工作流 |
| MCP adapter | `apps/services/api-gateway/src/app/gateway_mcp_adapter.py` | 本机只读 JSON-RPC adapter |
| Semantic Cache | `apps/services/api-gateway/src/app/semantic_cache.py` | L1 精确和可选 L2 语义回答缓存 |
| KB Retrieval | `apps/services/knowledge-base/src/app/retrieve.py` | 多信号检索、融合、rerank 和 debug meta |
| Shared tracing | `packages/python/shared/tracing.py` | 跨服务 trace id 生成与传播 |

## 主要文档

| 文档 | 用途 |
|---|---|
| `README.md` | 项目能力、启动、环境变量、运行边界和验证命令 |
| `AI_HIGHLIGHTS.md` | 作品集和简历亮点入口 |
| `docs/README.md` | 文档导航 |
| `docs/reference/api-specification.md` | Gateway 与 KB API 契约 |
| `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md` | STAR 技术难点与追问 |
| `docs/reference/RAG_INTERVIEW_MATERIAL.md` | 深度面试材料 |
| `docs/STAR_REPO_STAR.md` | 当前仓库 STAR 主材料 |
| `docs/interview-playbook.md` | 面试口径速查 |
| `docs/PROJECT_HIGHLIGHTS_SUMMARY.md` | 项目亮点一页摘要 |
| `docs/STAR_REPO_INVENTORY.md` | tracked source、入口点、质量门禁与新近能力盘点 |

## 质量门禁

| 场景 | 命令 |
|---|---|
| 编码检查 | `python scripts/quality/check-encoding.py --root .` |
| 后端编译 | `python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base` |
| 聚焦测试选择 | `python scripts/quality/select_fast_tests.py --staged --fallback tests` |
| 分组 pytest | `python scripts/quality/run_pytest_groups.py --timeout-seconds 900 --heartbeat-seconds 30 tests` |
| Docker 配置 | `docker compose config --quiet` |

说明：本机如果没有 `docker` 命令，`docker compose config --quiet` 会因环境缺失失败，不能直接判定为代码问题。

## 新近补齐能力索引

| 能力 | 代码 | 测试 |
|---|---|---|
| 最终回答受控 Tool Calling | `apps/services/api-gateway/src/app/gateway_answering.py` | `tests/test_backend_infra.py::test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools` |
| Tool Workflow 修复闭环 | `apps/services/api-gateway/src/app/tool_workflow.py` | `tests/test_tool_workflow.py` |
| 只读 MCP JSON-RPC adapter | `apps/services/api-gateway/src/app/gateway_mcp_adapter.py`、`gateway_mcp_routes.py` | `tests/test_mcp_adapter.py` |
| 运行时治理指标 | `apps/services/api-gateway/src/app/governance_metrics.py`、`gateway_system_routes.py` | `tests/test_governance_metrics.py`、`tests/test_backend_infra.py::test_gateway_tool_workflow_route_records_failure_metrics` |
| Semantic Cache 命中边界 | `apps/services/api-gateway/src/app/semantic_cache.py` | `tests/test_inference_optimization.py::TestSemanticCache` |
| Trace 与反馈快照 | `packages/python/shared/tracing.py`、`apps/services/api-gateway/src/app/gateway_sessions.py` | `tests/test_api_error_payloads.py`、`tests/test_backend_infra.py::test_upsert_chat_message_feedback_snapshots_llm_metadata` |
| 知识库治理与运维聚合 | `apps/services/knowledge-base/src/app/kb_analytics_routes.py`、`apps/web/src/views/kb/KBGovernanceView.vue`、`docs/reference/kb-governance-workbench.md` | `tests/test_backend_infra.py::test_kb_governance_payload_aggregates_enterprise_queues`、`apps/web/src/views/kb/KBGovernanceView.test.ts` |
| Docker 构建上下文 | `.dockerignore`、服务级 Dockerfile | `tests/test_container_assets.py` |
