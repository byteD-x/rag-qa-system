# RAG-QA 项目亮点摘要

> Last updated: 2026-09-27
> 用途：作品集、简历和项目复盘的一页式摘要。完整 STAR 展开见 `docs/STAR_REPO_STAR.md` 与 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`。
> 按 P95、QPS/并发、召回/命中/拒答、规模和成本口径的可直接复用版本见 `AI_HIGHLIGHTS.md` 的“按统计口径整理的简历亮点”。

## 项目定位

RAG-QA 是一个企业知识问答后端与管理台项目，覆盖知识库入库、混合检索、grounded answer、LangGraph 可恢复运行时、Agent 工具调用、平台治理、缓存、成本估算和可观测 trace。

## STAR 成效摘要

| 背景/困难 | 解决办法 | 已验证成效与边界 |
|---|---|---|
| 检索接口每请求建连、建线程池，并发升高后 QPS 饱和、P95 劣化 | PostgreSQL 连接池、有界三路召回线程池、ACL 感知 TTL/LRU 缓存、single-flight；用 ABBA 交替压测消除预热偏差 | 纯检索接口并发 4–32：QPS **+48.8%–59.1%**、P95 **-29.0%–36.3%**，成功率/非空检索率均 **100%**；不外推到含 LLM 的端到端 SLA |
| RRF 相对排名分被误当绝对相关性，导致无证据题“有结果就作答” | dense 单路绝对 relevance、章节去重、按 Gateway 证据裁剪口径重标阈值 | 140 题评测：拒答率 **0→2.86%**，无证据题 grounded 误判 **12/12→0/12**，precision **0.75**、recall **0.25**；仍有 9/12 进入 weak_grounded |
| 部门权限、缓存复用和工作流恢复容易出现上下文不一致 | 文档仅存 `allowed_departments`，JWT 注入当前部门，召回前统一过滤，权限纳入缓存键和 checkpoint 校验 | 已交付 ACL 闭环并通过定向测试；暂无生产租户规模或安全审计数据 |
| 长链路失败难定位，Agent 工具扩展与预算边界不清 | LangGraph 可恢复节点、DAG 并行拆解、反思闭环、ToolRegistry、只读 MCP、trace 与治理指标 | 已交付可恢复与受控治理能力；暂无线上多实例稳定性和 Agent 成本收益数据 |

## 已落地亮点

| 方向 | 亮点 | 证据 |
|---|---|---|
| 检索工程 | 结构、FTS、向量多路召回，weighted RRF 融合，debug API 输出 `signal_scores` 与 `evidence_path`。 | `apps/services/knowledge-base/src/app/retrieve.py`、`tests/test_backend_infra.py::test_retrieve_debug_route_serializes_evidence_and_debug_meta` |
| 可信回答 | 回答链路区分 grounded、weak、refusal/common knowledge，保留引用、`llm_trace` 与反馈快照。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`tests/test_backend_infra.py` |
| 模型接入治理 | 支持 OpenAI-compatible 中转站模型发现、脱敏配置摘要、路由 fallback 与配置片段生成。 | `apps/services/api-gateway/src/app/gateway_llm_models.py`、`apps/web/src/views/platform/ModelProviderView.vue`、`tests/test_ai_platform_capabilities.py`、`apps/web/src/views/platform/ModelProviderView.test.ts` |
| Tool Calling | 最终回答工具调用默认关闭；开启后只允许 3 个只读摘要工具，最多一轮执行。 | `apps/services/api-gateway/src/app/gateway_answering.py`、`tests/test_backend_infra.py::test_generate_grounded_answer_executes_one_round_of_whitelisted_final_tools` |
| Tool Workflow | `direct` 和 `plan_reflect_repair` 两种模式复用 ToolRegistry；受控修复只覆盖安全 dry-run。 | `apps/services/api-gateway/src/app/tool_workflow.py`、`tests/test_tool_workflow.py` |
| MCP | 本机只读 JSON-RPC adapter 支持 `initialize`、`tools/list`、`tools/call`，只暴露摘要工具。 | `apps/services/api-gateway/src/app/gateway_mcp_adapter.py`、`tests/test_mcp_adapter.py` |
| 可观测 | Gateway、KB、反馈、审计事件携带 `trace_id`/`llm_trace`；工作流持久化记录工具调用和状态投影。 | `packages/python/shared/tracing.py`、`apps/services/api-gateway/src/app/gateway_workflows.py`、`tests/test_api_error_payloads.py` |
| 运行时治理指标 | Tool Workflow 与 Prompt rollback 聚合计数、成功率、耗时和短失败原因，JSON 摘要与 Prometheus 指标均可读取。 | `apps/services/api-gateway/src/app/governance_metrics.py`、`apps/services/api-gateway/src/app/gateway_system_routes.py`、`tests/test_governance_metrics.py` |
| 知识库治理 UI | 治理页支持单文档受控 rebuild 与批量 JSON 面板；批量写入必须先 dry-run，写入后仅对生成的 document_id 逐个受控 rebuild。 | `apps/web/src/views/kb/KBGovernanceView.vue`、`apps/web/src/views/kb/KBGovernanceView.test.ts` |
| 知识库批量预览 | `POST /api/knowledge_base/batch-dry-run` 对请求体内联多文档内容做 dry-run 分块摘要，不读取路径、不入库、不写向量。 | `apps/services/knowledge-base/src/app/kb_batch_dry_run.py`、`tests/test_backend_infra.py::test_knowledge_batch_dry_run_builds_sanitized_summary` |
| 知识库批量写入 | `POST /api/knowledge_base/batch-ingest` 只写入请求体内联文档并索引 section/chunk，不读取本机路径、不上传文件、不批量 delete。 | `apps/services/knowledge-base/src/app/kb_batch_ingest.py`、`tests/test_backend_infra.py::test_knowledge_batch_ingest_route_writes_inline_documents_without_raw_content` |
| 知识库受控重建 | `POST /api/knowledge_base/rebuild` 只基于已有 section/chunk 重建单文档向量，正式执行要求签名匹配。 | `apps/services/knowledge-base/src/app/kb_rebuild.py`、`tests/test_backend_infra.py::test_knowledge_rebuild_route_reindexes_existing_units_without_path_access` |
| 知识库后台队列 | `POST /api/knowledge_base/jobs` 将内联 ingest/rebuild 放入进程内串行队列，状态接口只返回脱敏摘要；不持久化、不扫描目录、不读取 source_file/source_path。 | `apps/services/knowledge-base/src/app/kb_job_queue.py`、`tests/test_backend_infra.py::test_knowledge_jobs_api_enqueues_and_reports_queue_without_raw_content` |
| 知识库固定 inbox 预览 | `GET /api/knowledge_base/auto-index/preview` 只读预览固定 inbox 一层文本/Markdown 文件，返回分块摘要和跳过原因；不接收任意路径、不递归扫描、不自动入库。 | `apps/services/knowledge-base/src/app/kb_auto_index.py`、`tests/test_backend_infra.py::test_knowledge_auto_index_preview_summarizes_fixed_inbox_without_raw_content` |
| 知识库只读索引 | `GET /api/knowledge_base/index` 返回已入库文档 metadata 摘要，不扫描文件系统，不回显正文、embedding 或完整路径。 | `apps/services/knowledge-base/src/app/kb_index.py`、`tests/test_backend_infra.py::test_knowledge_index_route_returns_metadata_summary_without_path_or_content` |
| Semantic Cache | L1 精确命中与可选 L2 语义命中；L2 受 scope/corpus key 与阈值控制。 | `apps/services/api-gateway/src/app/semantic_cache.py`、`tests/test_inference_optimization.py::TestSemanticCache` |
| 检索并发优化 | 连接池、有界召回线程池、ACL 感知检索缓存、single-flight；压测脚本统计 QPS/P95/错误率/非空召回率。 | `apps/services/knowledge-base/src/app/retrieval_cache.py`、`scripts/evaluation/benchmark-retrieval-concurrency.py`、`.codex/verification-report-perf-2026-09-27.md` |
| 拒答质量治理 | dense absolute relevance 贯通检索与回答判定，章节去重，端到端阈值标定。 | `packages/python/shared/grounded_answering.py`、`tests/test_shared_stack.py`、`.codex/verification-report-perf-2026-09-27.md` |
| Docker 边界 | 服务级 Dockerfile 加根 `.dockerignore`，排除本地状态和敏感文件，保留环境示例。 | `apps/services/api-gateway/Dockerfile`、`apps/services/knowledge-base/Dockerfile`、`tests/test_container_assets.py` |

## 简历可写版本

独立设计并实现企业级 RAG 问答系统，覆盖多信号检索融合、证据约束回答、LangGraph 可恢复工作流、受控 ToolRegistry/MCP 工具体系、模型中转站接入与路由 fallback、知识库治理 UI、回答级缓存、成本估算、trace 审计、运行时治理指标和 Docker Web API 部署边界；在固定脱敏语料的纯检索 ABBA 压测中实现并发 4–32 QPS 提升 48.8%–59.1%、P95 降低 29.0%–36.3%，并将无证据题 grounded 误判由 12/12 降至 0/12；端到端 LLM P95、缓存命中率和成本收益待真实业务数据补充。

## 边界说明

- 不宣称固定线上准确率、端到端（含 LLM）延迟或 QPS、缓存命中率或成本节省；当前数字仅适用于报告中注明的纯检索压测和 140 题评测。
- 本项目无订单、设备或线上用户规模数据，不填写订单数、用户数、设备数或金额收益。
- 不把只读 MCP adapter 说成动态插件市场。
- 不把最终回答 Tool Calling 说成任意工具执行能力。
- 不把模型发现说成自动保存密钥、自动账单拉取、任意供应商全托管或真实中转站端到端压测。
- 不把治理页受控 rebuild、batch dry-run 预览、batch-ingest、后台队列、固定 inbox 预览或只读 index API 说成文件上传、任意路径扫描、任意路径重建、批量 delete、文件系统索引、自动入库或持久任务调度能力。
- 不把 `usage_reconciliation` 说成自动账单拉取或财务级结算。
