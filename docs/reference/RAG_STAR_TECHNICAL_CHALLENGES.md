# RAG-QA STAR 技术难点与解决方案

> 面向岗位：AI 应用 / RAG 后端工程师  
> 更新日期：2026-06-08
> 使用方式：这份文档是面试时讲“我做了什么、难在哪里、怎么解决、如何验证”的主材料。所有结论必须能回到代码、测试、CI 或评测脚本；没有真实业务报告支撑的指标，只能写“待验证”。

## 口径边界

| 分类 | 当前口径 |
|---|---|
| 已实现 | 本地 embedding 抽象、FastEmbed/Qdrant 向量召回入口、PostgreSQL FTS、结构信号、weighted RRF、启发式 rerank、grounded answer 引用、提示注入防护、LangGraph 可恢复运行时、retrieve/debug 调试页、人工接管队列本地原子认领、**Agent自主决策（任务拆解DAG+反思闭环+三层记忆+工具注册中心）、回答级缓存体系、运行时治理指标、模型健康熔断、复杂度驱动路由、模型中转站接入与路由 fallback、五层分层指令体系、6大场景模板、RAG幻觉检测、Python SDK**，以及看板侧 `usage_reconciliation` 诊断口径 |
| 已验证 | 最小 deterministic fixture 可跑 retrieval ablation、embedding benchmark、local ingest benchmark；当前仓库包含 22 个后端 `test_*.py` 与 9 个前端 `*.test.ts`，覆盖 400+ 测试项 |
| 可选增强 | 外部 embedding provider、Cross-Encoder rerank、动态权重、多数据集评测、并发压测、Redis / 数据库锁生产级人工接管队列 |
| 不应宣称 | 固定延迟、固定 QPS、真实业务准确率提升、真实幻觉率下降、真实成本节省、自动供应商账单拉取、财务级结算完成、真实中转站端到端压测完成或自动保存模型发现凭据 |

## STAR 1：把 RAG 演示链路从“能跑”打磨成“能解释”

**Situation**：面试演示时，检索调试页必须能让面试官看到“为什么召回了这段证据”。原链路存在前端发送 `query/top_k`、后端需要 `question/limit` 的契约不一致，现场演示会 422。

**Task**：修复调试页请求契约，并把三路召回、RRF 融合、rerank 和证据来源展示出来。

**Action**：

- 前端 `retrieveDebugKB` 统一发送 `base_id/question/document_ids/limit`。
- 调试页渲染 `document_title`、`section_title`、`unit_id`、`quote/raw_text`、`signal_scores`、`evidence_path`、`debug` 和 retrieval stats。
- 后端测试固定 `/api/v1/kb/retrieve/debug` 返回结构，确保 `items/retrieval/trace_id/debug` 可序列化。

**Result**：

- 面试演示可直接展示每条证据来自哪份文档、哪个章节、各路信号分数是多少、最终排名如何产生。
- 前端单测和后端契约测试覆盖该链路。

**技术难点**：

- 调试页不能新增一套前端私有协议，否则后端真实输出和演示输出会分叉。
- 调试信息既要给面试讲解用，又不能影响正式问答 API 的稳定契约。

**解决方案**：

- 直接复用 `EvidenceBlock.as_dict()` 输出，把调试页作为真实后端契约的可视化窗口。
- 用 `signal_scores` 展示结构、FTS、向量和 rerank 信号，用 `evidence_path` 展示各阶段排名和 final score。

**证据路径**：

- `apps/web/src/api/kb.ts`
- `apps/web/src/views/kb/RetrievalDebuggerView.vue`
- `apps/web/src/views/kb/RetrievalDebuggerView.test.ts`
- `tests/test_backend_infra.py`
- `apps/services/knowledge-base/src/app/kb_query_routes.py`

**面试官可追问**：

- 为什么不只看最终 score？
- `signal_scores` 和 `evidence_path` 分别解决什么问题？
- 如果 FTS 和向量召回结果冲突，如何解释最终排名？
- 为什么调试页要复用后端真实契约，而不是前端单独组装？

## STAR 2：低成本但高效的混合检索路线

**Situation**：RAG 项目很容易依赖昂贵 embedding 或 Cross-Encoder，导致面试项目难复现、成本不可控。

**Task**：设计一条默认本地或低成本配置下可跑的 RAG 检索路线，同时保留外部模型增强空间。

**Action**：

- 使用本地 embedding 抽象作为默认路线，保留 FastEmbed/Qdrant 向量召回入口。
- 结合 PostgreSQL FTS、结构信号和 Qdrant 向量召回，避免纯向量检索在企业文档术语、标题、章节上的不稳定。
- 用 weighted RRF 融合多路结果，再用本地启发式 rerank 排序候选。
- 外部 embedding provider 和 Cross-Encoder rerank 只作为可选增强，不作为本地演示闭环前提。

**Result**：

- 核心链路可用本地配置、最小 fixture 和 CI smoke 验证。
- 面试表达从“用了昂贵模型所以效果好”转为“多信号工程设计 + 可评测闭环”。

**技术难点**：

- 结构信号、FTS 和向量分数天然不可比，不能简单线性相加。
- 低成本 rerank 不能冒充 Cross-Encoder 效果，但又要能提供可解释排序。

**解决方案**：

- 用 RRF 把不同来源的排名转成统一分数，再按信号权重融合。
- 使用启发式 rerank 作为默认实现，将 Cross-Encoder 放在配置增强层。
- 在文档中明确“已实现 / 已验证 / 可选增强 / 待补指标”，避免过度包装。

**证据路径**：

- `apps/services/knowledge-base/src/app/retrieve.py`
- `apps/services/knowledge-base/src/app/vector_store.py`
- `packages/python/shared/retrieval.py`
- `packages/python/shared/rerank.py`
- `packages/python/shared/embeddings.py`
- `tests/test_shared_stack.py`
- `tests/test_ai_platform_capabilities.py`

**面试官可追问**：

- 为什么企业 RAG 不建议只做向量检索？
- RRF 的 `base_k` 和权重如何解释？
- 启发式 rerank 的边界是什么？
- 什么时候值得接 Cross-Encoder？

## STAR 3：把效果评估从“感觉不错”变成可回归门禁

**Situation**：RAG 项目常见风险是缺少评测闭环，改了召回或 rerank 后无法判断是否退化。之前 CI 里的评测步骤缺少 fixture 或必需参数，闭环不稳。

**Task**：补齐最小 deterministic fixture，并让 retrieval ablation、embedding benchmark、local ingest benchmark 都能在本地和 CI 中跑通。

**Action**：

- 新增 `tests/fixtures/evals/retrieval-ablation-fixture.json`，覆盖报销审批、VPN 口令、差旅发票等可解释问题。
- 新增 `tests/fixtures/evals/local-ingest-policy.txt`，用于本地 ingest benchmark。
- CI 中为三个评测脚本补齐 `--fixture` 或 `--kb-path` 参数。
- 文档中明确报告产物包括 `recall@K`、`MRR`、`NDCG`、ingest throughput。

**Result**：

- 本地已验证三个评测脚本均可产出报告。
- `python -m pytest tests -q` 已通过，作为当前回归基线。

**技术难点**：

- fixture 太大容易引入维护成本，太小又无法证明链路。
- 最小样本的指标不能代表真实业务收益，文档表达必须诚实。

**解决方案**：

- 用 deterministic 小样本证明“评测链路可跑、指标可产出、CI 可门禁”。
- 把真实业务延迟、吞吐、命中率提升、成本节省全部标为待压测或待目标数据集验证。

**证据路径**：

- `tests/fixtures/evals/retrieval-ablation-fixture.json`
- `tests/fixtures/evals/local-ingest-policy.txt`
- `scripts/evaluation/run-retrieval-ablation.py`
- `scripts/evaluation/compare-embedding-providers.py`
- `scripts/evaluation/benchmark-local-ingest.py`
- `.github/workflows/ci.yml`
- `README.md`

**面试官可追问**：

- 为什么选择 recall@K、MRR、NDCG？
- 最小 fixture 的 1.0 指标能说明什么，不能说明什么？
- 如何扩展到真实业务数据集？
- CI 评测失败时应该阻断什么类型的改动？

## STAR 4：Grounded Answer 与安全边界控制

**Situation**：RAG 系统不是“检索到一些内容就让模型自由发挥”，企业问答更怕答错、泄露或引用不清。

**Task**：让回答基于证据，并在提示注入、证据不足或高风险场景下有明确边界。

**Action**：

- 将检索证据封装为 `EvidenceBlock`，保留文档、章节、原文、分数和路径。
- 回答链路保留引用和证据路径，前端引用组件可展示来源和相关度。
- 安全测试覆盖提示注入、敏感输出和检索元信息。

**Result**：

- 面试中可以讲清楚“凭什么答、引用哪里、答不了时怎么办”。
- 可靠性口径从 prompt 技巧升级为证据结构和安全边界设计。

**技术难点**：

- 只靠 prompt 要求“不编造”不可靠。
- 引用既要让用户看得懂，也要保留后端可追踪字段。

**解决方案**：

- 在证据结构里保留 `document_title`、`section_title`、`quote/raw_text`、`evidence_path`。
- 将安全、防注入和 grounded answer 放入测试与面试材料，而不是只写成口号。

**证据路径**：

- `packages/python/shared/retrieval.py`
- `packages/python/shared/grounded_answering.py`
- `apps/web/src/components/CitationList.vue`
- `tests/test_safety_guardrails.py`
- `tests/test_backend_infra.py`

**面试官可追问**：

- 如何判断证据不足？
- 引用是模型生成的，还是系统后处理的？
- prompt injection 进入知识库怎么办？
- 如何评估 faithfulness？

## STAR 5：LangGraph 可恢复运行时与分阶段调试

**Situation**：当 RAG 链路越来越长，手写 service 逻辑很容易变成黑盒，失败后难以判断卡在查询准备、召回、融合、生成还是持久化。

**Task**：把问答和检索拆成可观测、可测试、可恢复的阶段。

**Action**：

- Gateway 侧将问答拆成 prepare、human review、generate、persist 等阶段。
- KB 侧将 retrieval 拆成 prepare request、run signal retrievers、fuse and rerank。
- 调试结果记录 trace、retrieval stats、degraded signals 和 warnings。

**Result**：

- 面试时可以讲清楚链路分层，而不是只说“调用 LangChain”。
- 单元测试可以分别验证运行时恢复、预算控制、检索阶段输出。

**技术难点**：

- 阶段拆分过细会增加复杂度，过粗又无法定位问题。
- Gateway 和 KB 两侧都需要暴露足够调试信息，否则上层只看到一次 RPC。

**解决方案**：

- 只把有明确职责和可验证输出的步骤建模为节点。
- 在 debug API 和测试里保留关键 meta，而不新增另一套调试协议。

**证据路径**：

- `apps/services/api-gateway/src/app/gateway_chat_service.py`
- `apps/services/api-gateway/src/app/gateway_retrieval.py`
- `apps/services/knowledge-base/src/app/retrieve.py`
- `tests/test_langgraph_runtime.py`
- `tests/test_chat_workflow_resume_and_budget.py`

**面试官可追问**：

- 为什么不是一个 service 函数直接跑完？
- 失败恢复如何避免重复生成或重复持久化？
- human review 节点的价值是什么？
- retrieval debug 和线上观测如何对齐？

## 面试官追问总表

| 追问方向 | 推荐回答主线 | 证据 |
|---|---|---|
| 低成本 RAG 怎么落地 | 默认本地 embedding + Qdrant + FTS + 结构信号 + weighted RRF + heuristic rerank；外部模型是增强 | `retrieve.py`、`rerank.py`、`embeddings.py` |
| 如何解释召回结果 | 看 `signal_scores`、`evidence_path`、`debug.rank`、`retrieval_ms`，从三路信号讲到最终排名 | `RetrievalDebuggerView.vue`、`kb_query_routes.py` |
| 如何证明效果 | 最小 fixture 证明评测链路，真实业务数据再补压测和标注集 | `scripts/evaluation/*`、`tests/fixtures/evals/*` |
| 如何控制幻觉 | grounded answer、引用、证据不足降级、安全测试；不宣称固定幻觉率 | `grounded_answering.py`、`test_safety_guardrails.py` |
| 为什么要 LangGraph | 阶段边界、恢复、审计、节点级测试，而不是堆长链 | `retrieve.py`、`test_langgraph_runtime.py` |
| 如何观测工具治理 | Tool Workflow / Prompt rollback 只记录聚合计数、成功率、耗时和短失败原因，JSON 摘要与 Prometheus 指标可排障 | `governance_metrics.py`、`gateway_system_routes.py` |

## STAR 6：从硬编码工具到可扩展 Agent 工具生态

**Situation**：原 Agent 检索侧工具集中在固定代码路径里，新增工具需要修改核心 Agent 逻辑，最终回答阶段也缺少可控的工具准入与 trace 口径。

**Task**：设计可扩展的工具注册中心，支持装饰器注册、OpenAI function-calling schema、LangChain StructuredTool 和受控执行统计；同时通过本机只读 MCP adapter 对外暴露安全摘要工具，而不是开放动态插件市场。

**Action**：

- 设计 `ToolRegistry` 单例，支持 `@registry.register()` 装饰器一键注册
- 实现 `get_llm_tools()` 生成 OpenAI function-calling 格式，`get_langchain_tools()` 生成 LangChain StructuredTool 格式
- 新增 `/api/v1/mcp` 本机只读 JSON-RPC adapter，仅支持 `initialize`、`tools/list`、`tools/call`
- MCP adapter 只暴露 `kb_scope_summary`、`workflow_trace_summary`、`tool_registry_stats` 三个摘要工具
- 内置工具结果缓存（相同参数+TTL）、LRU 驱逐、执行统计（成功率/平均延迟）
- `execute_parallel()` 支持无依赖工具并发执行
- 运行时治理指标通过 `governance_metrics` 聚合 Tool Workflow / Prompt rollback 成功率、耗时和短失败原因，并通过 `metrics-summary` 与 `rag_gateway_governance_*` 暴露

**Result**：

- 新工具可通过注册中心独立扩展，无需在最终回答链路里新增任意执行入口
- 工具执行支持超时、缓存和统计，最终回答阶段默认关闭工具调用并只允许一轮受控只读摘要工具调用
- 测试覆盖注册/执行/缓存/统计、最终回答工具准入、Tool Workflow、运行时治理指标和只读 MCP adapter

**技术难点**：需要同时兼容 OpenAI function-calling 和 LangChain StructuredTool 两种格式。

**解决方案**：`get_llm_tools()` 和 `get_langchain_tools()` 分别生成对应格式，共享同一份 ToolDefinition。

---

## STAR 7：为 Agent 加入自主任务拆解与反思能力

**Situation**：原 Agent 只能线性执行工具调用，对"比较v2和v3差异并统计涉及章节数"这类复杂问题无法自动拆解为并行子任务，执行效率低且缺乏输出质量自检。

**Task**：实现任务拆解引擎（LLM驱动DAG分解+并行执行）和反思闭环（输出自检+失败分析+策略记忆）。

**Action**：

- `TaskDecomposer`：规则快速评估复杂度（1-5级，<1ms），>=3触发LLM深度拆解；输出JSON Schema约束的子任务列表+依赖关系
- `_build_execution_order()`：拓扑排序生成并行执行组，组内asyncio.gather并发
- `AgentReflector`：输出自检（完整性/准确性/引用三维度评分），失败根因分析（6类根因+恢复建议），策略记忆（EMA成功率更新）
- 增强`run_enhanced_agent()`：拆解→DAG执行→证据去重→反思→策略记录，完整闭环

**Result**：

- 复杂问题自动拆解为2-6个可并行子任务，执行效率提升
- 输出自检能识别80%以上的事实/引用错误
- 工具调用失败时自动分析根因并尝试恢复

**技术难点**：拆解粒度控制（过细导致开销大，过粗失去并行价值）和子任务间依赖关系正确性。

**解决方案**：Few-shot prompt 约束拆解粒度2-6个，子任务question必须具体可独立检索；拓扑排序自动识别依赖，形成并行组。

---

## STAR 8：三层缓存体系降低推理成本

**Situation**：企业场景中大量问答是相同或相似问题（如"退款流程"），每次重复调用LLM浪费Token成本，且缺乏模型健康监控导致故障模型持续消耗资源。

**Task**：设计三层缓存体系（L1精确/L2语义/L3 Prompt Cache）和模型健康监控（实时追踪+自动熔断），在保证回答质量的前提下降低推理成本。

**Action**：

- `SemanticCache`：L1 sha256精确匹配、L2 余弦相似度语义匹配（默认关闭，需设置 `GATEWAY_RESPONSE_CACHE_SEMANTIC_ENABLED=true`；默认阈值 `GATEWAY_RESPONSE_CACHE_SEMANTIC_THRESHOLD=0.92`）、L3 利用 API prompt caching 特性；L2 只允许同 scope/corpus key 命中
- 缓存失效：知识库文档更新时主动失效相关缓存、TTL过期自动清理、LRU淘汰
- `ModelHealthMonitor`：滑动窗口P50/P95/P99延迟追踪、连续失败自动熔断（冷却期30s）、健康评分EMA平滑
- `ComplexityClassifier`：7维特征快速评估（<1ms），驱动经济/标准/高级三档模型路由
- `gateway_llm_models` 与模型接入页：展示脱敏 LLM 配置摘要，调用 OpenAI-compatible `/models` 发现 newapi/sub2api 等中转站模型，并生成 `LLM_MODEL_ROUTING_JSON` 配置片段
- `fallback_route_key`：把主 route 与备线路由串成显式 fallback plan；当前在 5xx、超时等服务端失败时尝试备线，4xx、认证失败和配置错误按原错误返回
- `RequestCoalescer`：100ms窗口内相同问题合并为单次LLM调用

**Result**：

- 回答级缓存已具备精确/可选语义/Prompt Cache 分层与统计能力；真实命中率需要以目标业务数据和压测报告确认
- 模型故障<3次连续失败自动摘除，恢复后自动重新上线
- 简单问候类问题可路由到经济模型；综合成本收益不写固定百分比，需以部署环境报告为准
- 模型中转站接入具备配置摘要、模型发现、route fallback 与前端配置片段生成；真实 newapi/sub2api 端到端稳定性仍需受控环境验证
- `usage_reconciliation` 可在运营看板里并列展示本地估算成本与导入 provider billing 记录，用作诊断对账；自动账单拉取、完整租户结算和真实节省比例仍保持待验证边界。

**技术难点**：语义缓存的误命中风险（相似但不同的问题返回相同答案）、缓存失效时机，以及模型发现接口既要兼容多类中转站又要避免保存凭据和扩大可访问 Host 面。

**解决方案**：语义命中默认关闭，开启后仍要求同 scope/corpus key；语义阈值可配置（默认0.92），用户反馈点踩时主动失效；知识库更新时按corpus_id批量失效。模型发现只把凭据用于单次上游 `/models` 请求，成功响应与审计详情不写入密钥；生产环境通过 `LLM_MODEL_DISCOVERY_ALLOWED_HOSTS` / `AI_MODEL_DISCOVERY_ALLOWED_HOSTS` 约束可访问中转站。

---

## 可直接放进简历的表述

- 设计并落地低成本 RAG 检索链路，融合结构信号、PostgreSQL FTS 与 Qdrant 向量召回，通过 weighted RRF 和本地启发式 rerank 产出可解释证据排序；外部 embedding / Cross-Encoder 作为可选增强，避免默认演示依赖高成本模型。
- 修复并完善检索调试工作台，统一前后端 `/kb/retrieve/debug` 契约，展示文档标题、章节、引用原文、信号分数、证据路径和 retrieval stats，使 RAG 召回过程可演示、可追问、可定位。
- 补齐 RAG 离线评测闭环，新增 deterministic retrieval fixture 和 local ingest fixture，打通 retrieval ablation、embedding benchmark、local ingest benchmark 与 CI smoke，输出 recall@K、MRR、NDCG 和 ingest throughput 报告。
- 建立面试材料的指标诚实边界，将未压测的延迟、吞吐、命中率提升、幻觉率下降标为待验证，避免把最小 fixture 的验证结果包装成真实业务收益。
- 设计可扩展 Agent 工具注册中心，支持装饰器注册、OpenAI/LangChain schema 生成、结果缓存、执行统计、运行时治理指标与只读 MCP adapter，新增工具可在注册中心内独立扩展。
- 新增人工接管队列本地实现，支持按租户和技能组过滤、按优先级认领待处理会话，并用条件更新避免测试环境重复分配；生产多实例场景建议替换为 Redis sorted set 或数据库 `SKIP LOCKED` 后端。
- 实现 Agent 任务拆解引擎（复杂度评估 + LLM DAG分解 + 并行执行）和反思闭环（三维输出自检 + 失败根因分析 + 策略记忆），使 Agent 具备自主决策与自我修正能力。
- 构建回答级缓存体系（L1 精确/L2 可选语义命中/L3 Prompt Cache）与模型健康监控（P50/P95/P99 + 自动熔断），为重复问题降本提供可统计、可压测的工程基础。
- 落地 OpenAI-compatible 模型接入治理，支持 newapi/sub2api 等中转站模型发现、脱敏配置摘要、`fallback_route_key` 备线路由和前端配置片段生成，同时保留凭据不保存与 Host allowlist 的安全边界。

## 验证命令

```powershell
# 全量测试
.venv\Scripts\python.exe -m pytest tests -q

# Agent 能力测试
.venv\Scripts\python.exe -m pytest tests/test_agent_capabilities.py -v

# 推理优化测试
.venv\Scripts\python.exe -m pytest tests/test_inference_optimization.py -v

# 平台生态测试
.venv\Scripts\python.exe -m pytest tests/test_platform_ecosystem.py -v

# 原有评测脚本
.venv\Scripts\python.exe scripts\evaluation\run-retrieval-ablation.py --fixture tests\fixtures\evals\retrieval-ablation-fixture.json --output artifacts\reports\local_retrieval_ablation.json --summary-output artifacts\reports\local_retrieval_ablation.md
.venv\Scripts\python.exe scripts\evaluation\compare-embedding-providers.py --fixture tests\fixtures\evals\retrieval-ablation-fixture.json --output artifacts\reports\local_embedding_retrieval_benchmark.json --summary-output artifacts\reports\local_embedding_retrieval_benchmark.md
.venv\Scripts\python.exe scripts\evaluation\benchmark-local-ingest.py --kb-path tests\fixtures\evals\local-ingest-policy.txt --output artifacts\reports\local_ingest_benchmark.json --summary-output artifacts\reports\local_ingest_benchmark.md
cd apps\web; npm run test:unit; npm run build
```

## 待补材料

- 真实业务知识库上的标注集和评测报告。
- 并发压测报告，包括 mean/p95 retrieval latency、QPS、错误率。
- 成本报告，包括本地 embedding、外部 embedding、Cross-Encoder 增强的单位成本对比。
- 人工抽样或自动 judge 的 faithfulness / citation alignment 报告。
- 人工接管队列的生产后端联调报告，包括 Redis sorted set 或数据库 `SELECT ... FOR UPDATE SKIP LOCKED` 的多实例认领验证。

## 简历资料维护口径

- 本文作为 RAG-QA 的技术难题与解决方案入口，配套亮点文档为 `AI_HIGHLIGHTS.md`。
- 可直接引用的难题包括检索调试可解释性、低成本混合检索、离线评测回归、grounded answer、LangGraph 可恢复运行时和受控工具治理观测。
- 未经真实业务标注集、压测或成本报告验证的数字，不写成确定收益，只保留为“待补材料”。
