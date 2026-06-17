# 岗位数据驱动的 RAG-QA 项目增强报告

> Last updated: 2026-06-18  
> 目标项目：`E:\Project\rag-qa-system`  
> 岗位数据源：`E:\Project\resume-new`，本报告只读取，不修改。  
> 口径：结论基于当前可解析的结构化岗位数据、目标项目代码、测试、文档和配置；没有证据的数据不写成已实现收益。

## 1. 关键假设与数据口径

- 用户未填写目标项目绝对路径，本次按当前工作区 `E:\Project\rag-qa-system` 作为目标项目。
- `data/jobs/normalized-jobs.json` 的实际结构为 `{meta, jobs}`，当前 `jobs` 列表为 332 条；`job-market-stats.json` 的 `sampleCount` 也是 332。
- `application-priority-list.json` 和部分早期文档记录 333 条，生成时间早于当前 normalized/stats 文件；本报告以 332 条主数据为准，333 条优先级分桶作为投递节奏参考。
- `job-data-expansion-2026-06-11-multi-platform.md` 提到后续扩展到 383 条，但当前主结构化文件没有同步到 383 条；不把 383 条作为当前统计口径。
- 全部 332 条岗位的 `verificationStatus` 均为“需人工核验”，因此岗位方向和薪资只代表公开样本画像，不代表真实在招状态或 offer 水平。

## 2. 岗位画像

| 维度 | 主要分布 |
|---|---|
| 岗位总数 | 332 条 |
| 来源平台 | Boss直聘 172、智联招聘 71、猎聘 66、实习僧 6、牛客网 5、企业官网 5，其他平台合计 7 |
| 城市 | 上海 86、北京 48、深圳 37、杭州 30、广州 19、成都 13、南京 12、长沙 12、苏州 11、合肥 9 |
| 薪资阶段 | 主投 15-25K 153、进阶 25-40K 65、保底 7-15K 49、冲刺 40K+ 42、实习/日薪 21、不确定 2 |
| 经验要求 | 3-5年 114、1-3年 70、未明确 52、经验不限 39、实习 18、3年以上 12 |
| 学历要求 | 本科 306、统招本科 8、大专 8、学历不限 7、未明确 3 |
| 匹配等级 | 强投 137、可投 77、冲刺 48，另有复合等级 69 条 |
| 方向分布 | AI应用/RAG 106、AI Agent/智能体 104、Python/FastAPI后端 52、AI平台/模型服务化 26，其余方向较分散 |
| 数据质量风险 | 全量需人工核验；智联列表页样本较多；部分岗位公司主体、外包属性、薪资月份、JD 深度和岗位是否下线需复核 |

## 3. 八类岗位方向画像

| 方向 | 样本与常见标题 | 高频能力 | 当前项目可承接能力 | 不建议硬凑 |
|---|---|---|---|---|
| AI应用/RAG | 标准方向 106 条；关键词扩展约 150 条。常见标题：AI应用工程师、AI应用开发工程师、AI大模型应用开发工程师、RAG应用开发工程师。 | 文档解析、chunk、向量检索、全文检索、RRF/rerank、引用溯源、拒答、评测、知识库治理。 | 多格式入库、Qdrant+FTS+结构信号、weighted RRF、grounded answer、citation、strict refusal、retrieval ablation、治理页。 | 不建议为了 RAG 岗位新增复杂微调或视觉生成能力。 |
| AI Agent/智能体 | 标准方向 104 条；关键词扩展约 136 条。常见标题：AI Agent 工程师、智能体开发工程师、AI Agent 全栈开发工程师。 | 工具调用、任务拆解、状态编排、记忆、反思、interrupt/resume、人工接管、step trace。 | Agent 编排器、任务拆解、ToolRegistry、Tool Workflow、只读 MCP adapter、人工接管队列、LangGraph 可恢复运行时。 | 不建议把 Agent 说成无限自治或任意工具执行。 |
| Python/FastAPI后端 | 标准方向 52 条；关键词扩展约 140 条。常见标题：Python后端、FastAPI 后端、大模型方向后端开发。 | FastAPI、异步任务、SSE、API 契约、权限、日志、数据库、缓存、测试。 | Gateway/KB 两个 FastAPI 服务、统一异常、trace middleware、SSE、后台队列、pytest、Docker Compose。 | 不建议把项目包装成纯后端 CRUD，AI 链路才是差异点。 |
| AI平台/模型服务化 | 标准方向 26 条；关键词扩展约 8 条更保守。常见标题：AI平台开发、模型服务平台、AI MaaS。 | provider 接入、模型路由、健康检查、熔断、限流、成本、token 统计、配置脱敏。 | 模型路由 fallback、模型发现配置片段、模型健康、成本估算、语义缓存、TTFT、Provider billing。 | 不建议宣称已有大规模 GPU 集群或生产级模型平台 SLO。 |
| Dify/Coze/MCP/工作流 | 标准方向 5 条；关键词扩展约 39 条。常见标题：Dify 方向 AI 应用、AI 工作流、MCP 工程师。 | 工作流节点、工具 schema、插件/API、知识库配置、MCP、低代码平台理解。 | Tool Workflow、只读 MCP JSON-RPC adapter、Prompt/Agent Profile/Scene 模板、工作流 trace。 | 不建议把只读 MCP adapter 说成动态插件市场或完整 Dify/Coze 替代品。 |
| Java后端+AI | 标准方向 2 条；关键词扩展约 45 条。常见标题：Java开发工程师、有 AI 应用优先、AI Agent Java 高级开发。 | Spring Boot、业务状态机、数据库、Redis、权限、AI API 接入。 | 当前项目主栈不是 Java，可把工程治理、幂等、状态机思维迁移到 Java+AI 面试，但不作为本项目主打。 | 不建议在本项目硬加 Java 服务。 |
| 行业AI实施/解决方案 | 标准方向 2 条；岗位通常和金融、客服、制造、内部系统、知识库落地相关。 | 需求澄清、业务对象建模、RAG 场景设计、交付文档、效果验收。 | 企业知识库、智能客服、内部制度检索、多知识库统一聊天、治理看板，适合作为行业 AI 方案样板。 | 不建议编造真实客户、用户量或 ROI。 |
| 算法/微调/RL 或多模态 | 标准方向 4 条；关键词扩展约 15 条。 | 微调、Embedding/Rerank 原理、多模态 OCR、模型训练、推理优化。 | 可讲本地 embedding、可选 rerank、多模态 OCR、评测指标；定位是应用工程层。 | 不建议把主线改成算法训练、RLHF 或底层推理优化。 |

## 4. 岗位能力模型

### 主投必备

1. **RAG 可信回答**：文档解析、切分、混合检索、RRF、rerank、引用、拒答、知识库治理。
2. **Agent 工程化**：工具白名单、任务拆解、工作流编排、记忆、反思、人工接管、step events。
3. **Python/FastAPI 后端**：API 契约、异步任务、SSE、统一异常、权限、数据库、缓存和测试。
4. **评测闭环**：Recall@K、MRR/NDCG、faithfulness、citation alignment、strict refusal、golden fixture、回归门禁。
5. **工程交付**：Docker Compose、本地一键启动、CI、README、示例数据、演示脚本。

### 进阶强化

6. **模型服务治理**：多 provider、模型路由、fallback、健康检查、限流、token/cost 估算。
7. **可观测性**：trace id、llm_trace、retrieval stats、工具调用事件、失败原因、Prometheus 指标。
8. **稳定性**：超时、重试、熔断、降级、幂等、失败恢复、人工兜底。
9. **安全与权限**：Prompt injection 防护、PII 检测、工具权限、MCP 只读边界、审计事件。

### 冲刺加分

10. **行业落地表达**：企业知识库、智能客服、内部系统 AI 嵌入、金融/制造/客服场景验收指标。
11. **平台化边界**：场景模板、Prompt 版本、A/B 评估、SDK、运营看板。
12. **多模态与算法理解**：OCR、视觉区域、Embedding/Rerank 原理、微调边界，重点讲应用层取舍。

## 5. 目标项目现状

| 项目维度 | 证据 |
|---|---|
| 技术栈 | Vue 3、TypeScript、Vite、Element Plus、FastAPI、Python、LangChain/LangGraph、PostgreSQL、MinIO、Qdrant、Docker、Pytest。见 `README.md` 和 `apps/web/package.json`。 |
| 后端入口 | Gateway：`apps/services/api-gateway/src/app/main.py`；KB Service：`apps/services/knowledge-base/src/app/main.py`。 |
| RAG 核心 | `packages/python/shared/retrieval.py`、`apps/services/knowledge-base/src/app/retrieve.py`、`packages/python/shared/rerank.py`、`packages/python/shared/grounded_answering.py`。 |
| Agent 核心 | `apps/services/api-gateway/src/app/agent_orchestrator.py`、`task_decomposer.py`、`agent_reflection.py`、`memory_*`、`tool_registry.py`、`tool_workflow.py`。 |
| 模型服务化 | `packages/python/shared/model_routing.py`、`model_health.py`、`semantic_cache.py`、`gateway_pricing.py`、`cost_*`、`ttft_optimizer.py`。 |
| 工程配置 | `Makefile`、`docker-compose.yml`、服务级 Dockerfile、`.github/workflows/ci.yml`。 |
| 测试与评测 | `tests/test_eval_pipeline.py`、`tests/test_agent_capabilities.py`、`tests/test_inference_optimization.py`、`tests/test_backend_infra.py`、`scripts/evaluation/*`。 |

当前最适合包装成：**AI应用/RAG + AI Agent/智能体 + Python/FastAPI 后端**。  
次级可包装：**AI平台/模型服务化**。  
不适合作为主线：**Java后端+AI、纯算法/微调/RL**。

## 6. 优先级增强方案

| 优先级 | 优化目标 | 对应岗位要求与方向 | 修改范围 | 实现思路 | 为什么值得做 | 为什么不过度设计 | 验证方式 | 简历/面试价值 | 耗时 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| P0 | 建立岗位匹配证据包 | AI应用/RAG、Agent、FastAPI | `docs/job-driven-project-enhancement.md`、`scripts/quality/check-job-alignment-evidence.py` | 把岗位画像、项目证据、路线图和校验脚本固化 | 快速提升可讲性和可信度 | 不改运行链路，不引入依赖 | 运行证据校验与编码检查 | 面试官可按路径核验能力 | 0.5 天 | 只能证明仓库证据，不证明线上效果 |
| P0 | 补最小演示闭环 | RAG、Agent、评测 | `scripts/dev/smoke_eval.py`、README 演示章节、fixtures | 明确“上传/入库/提问/引用/拒答/评测”的 10 分钟演示路径 | 面试展示成本低 | 复用现有 smoke eval，不新增平台 | smoke eval + regression gate | 能讲端到端闭环 | 0.5-1 天 | 依赖本地 Docker 环境 |
| P1 | 强化评测与 badcase 报告 | RAG eval、回归测试 | `scripts/evaluation/*`、`artifacts/reports`、docs | 增加固定 badcase 清单和报告模板 | 对 25-40K 岗位有区分度 | 不追求大数据集 | pytest + eval scripts | 能讲 Recall@K、faithfulness、citation alignment | 1-2 天 | 指标只代表 fixture |
| P1 | 梳理 step events 与 trace 展示 | Agent 可观测 | Gateway 工作流、前端 Agent Monitor、聊天 Trace Drawer、文档 | 把工具调用、失败原因、恢复动作串成可读事件 | Agent 岗位高频追问 | 先做展示和测试，不改深层编排 | 现有 tests + 截图/接口响应 | 能讲多步骤可观测 | 1-2 天 | 前端改动需视觉回归 |
| P1 | 模型服务化演示配置 | AI平台/模型服务化 | README、ModelProviderView、测试 | 给 newapi/sub2api、fallback、成本估算准备一套脱敏示例；模型接入页已能生成主/备 route 配置片段 | 主投进阶岗位常问 | 不接真实密钥，不做账单拉取 | 单测 + 配置片段校验 | 能讲 provider、路由、降级和成本 | 1 天 | 真实中转站稳定性待测 |
| P2 | Dify/Coze/MCP 对照 demo | 工作流/MCP | docs/reference 或独立 demo 文档 | 用现有 Tool Workflow/MCP 对照 Dify/Coze 概念 | 覆盖 11.7% 扩展关键词岗位 | 不引入完整低代码平台 | 文档 + MCP adapter 测试 | 回答“会不会 Dify/Coze” | 1-2 天 | 不是直接 Dify 经验 |
| P2 | 行业场景样例包 | 行业AI解决方案 | `tests/fixtures`、docs | 准备制度问答、客服查单、财务知识库三个场景 | 方便投行业落地岗 | 不编造客户数据 | fixture eval | 能讲业务对象和验收 | 2-3 天 | 需要真实业务样本会更强 |

## 7. 三档实施路线

### 轻量版：1 天内完成

- 任务列表：岗位匹配报告、证据校验脚本、README 增加报告入口、跑基础验证。
- 修改文件范围：`docs/job-driven-project-enhancement.md`、`scripts/quality/check-job-alignment-evidence.py`，可选更新 `docs/README.md`。
- 验收标准：报告覆盖岗位画像、项目证据、优先级路线、简历/面试表达；脚本可本地通过。
- 本地验证命令：
  - `python scripts/quality/check-job-alignment-evidence.py`
  - `python scripts/quality/check-encoding.py --root .`
  - `docker compose config --quiet`
- 简历成果：可写“基于岗位画像重构项目展示口径，建立 RAG/Agent/FastAPI 能力证据索引与本地校验脚本”。
- 不做：不改核心服务、不做 Dify/Coze 真平台、不做算法训练，因为 1 天内最需要的是投递和面试可讲性。

### 标准版：2-5 天完成

- 任务列表：补完整 demo 脚本、扩展 badcase/评测集、增加演示数据、完善架构图和面试材料。
- 修改文件范围：`scripts/dev/smoke_eval.py`、`scripts/evaluation/*`、`tests/fixtures/evals/*`、`README.md`、`docs/reference/*`。
- 验收标准：本地能跑通入库、检索、grounded answer、strict refusal、agent 多步、评测报告。
- 本地验证命令：
  - `python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json`
  - `python scripts/dev/smoke_eval.py --password ChangeMe123! --wait-for-ready`
  - `python scripts/evaluation/check-eval-regression.py --help`
- 简历成果：可写“通过固定评测集验证检索融合、引用对齐、拒答和 Agent 多步流程，形成可回归的 RAG/Agent Demo”。
- 不做：不引入重型评测平台或真实中转站账单，因为主线是本地可验证闭环。

### 增强版：1-2 周完成

- 任务列表：强化 step events、运行时指标、模型路由压测、缓存命中报告、行业场景样例、Dify/Coze/MCP 对照 demo。
- 修改文件范围：Gateway 工作流/指标模块、前端 Agent Monitor/Cost Dashboard、`scripts/evaluation/*`、`docs/reference/*`。
- 验收标准：能展示 trace、工具调用、失败恢复、成本估算、缓存命中、模型 fallback、行业场景 badcase。
- 本地验证命令：
  - `python scripts/quality/run_pytest_groups.py --timeout-seconds 900 tests`
  - `cd apps/web && npm run test:unit`
  - `cd apps/web && npm run build`
  - `docker compose config --quiet`
- 简历成果：可写“建设 RAG/Agent 工程化治理闭环，覆盖模型路由、成本、缓存、trace、评测和人工兜底”。
- 不做：不做 RLHF、复杂微调、GPU/K8s 大平台重构，因为这会偏离当前主投岗位和项目证据。

## 8. 可执行任务拆解

| 任务 | 背景 | 输入 | 输出 | 修改点 | 依赖 | 验收标准 | 验证命令 | 可并行 | 简历价值 |
|---|---|---|---|---|---|---|---|---|---|
| T1 岗位画像固化 | 投递目标需要证据 | 岗位 JSON/Markdown | 岗位画像章节 | 文档 | 无 | 统计口径清楚 | 编码检查 | 否 | 中 |
| T2 项目证据索引 | 避免空泛包装 | README、代码、测试 | 证据表 | 文档 | T1 | 每个能力有路径 | 证据脚本 | 否 | 高 |
| T3 演示闭环补齐 | 面试需要可跑流程 | smoke/eval fixtures | 演示脚本与说明 | scripts/docs | T2 | 10 分钟可演示 | smoke eval | 部分可并行 | 高 |
| T4 badcase/回归集 | 岗位高频问评测 | eval fixtures | badcase 报告 | fixtures/scripts | T2 | 指标输出稳定 | eval scripts | 是 | 高 |
| T5 step events 展示 | Agent 需要可观测 | workflow trace | 事件展示/文档 | Gateway/UI/docs | T2 | 可看工具调用和失败原因 | pytest + 前端单测 | 部分可并行 | 高 |
| T6 模型路由示例 | 平台岗问服务治理 | routing config | 脱敏配置示例 | docs/tests | T2 | fallback/cost 口径清楚 | pytest | 是 | 中高 |
| T7 行业样例包 | 方案岗问场景 | 合成制度/客服样本 | 三类场景 fixture | tests/docs | T3 | 不含真实敏感数据 | eval scripts | 是 | 中 |

## 9. 简历与面试包装

### 简历 bullet

- 基于 FastAPI、Qdrant、PostgreSQL FTS 与结构信号实现企业知识库 RAG，支持 weighted RRF、启发式 rerank、引用溯源和证据不足拒答，覆盖中文制度问答类场景。
- 引入 grounded answer 与 `llm_trace`，将回答从不可解释文本变为可追踪的证据链路，支持 answer mode、引用标记、成本估算和反馈快照。
- 设计受控 Agent 工具体系，基于 ToolRegistry、Tool Workflow 与只读 MCP adapter 支持工具注册、白名单调用、执行统计和安全边界。
- 建设模型服务治理能力，支持 OpenAI-compatible provider、模型发现、路由 fallback、健康熔断、语义缓存、TTFT 与 token 成本估算。
- 通过 pytest、前端单测、retrieval ablation、embedding benchmark、local ingest benchmark 和 smoke eval 验证 RAG/Agent 关键链路，避免只停留在 Prompt Demo。

### 项目介绍

RAG-QA 是一个面向中文企业知识场景的 RAG 问答与 Agent 工程化项目，覆盖知识库入库、文档解析、混合检索、证据化回答、Agent 工具调用、模型路由、评测回归、trace 可观测和 Docker 本地部署。它适合主投 AI 应用/RAG、AI Agent、Python/FastAPI 后端岗位，也可以作为模型服务化方向的进阶作品。

### 技术难点

难点不在于“调一次大模型 API”，而在于把检索证据、模型生成、工具调用和失败兜底做成可控链路。项目通过 EvidenceBlock 保存文档、章节、quote、分数和 evidence path；通过 grounded/refusal/common knowledge 区分回答边界；通过 ToolRegistry 和只读 MCP adapter 限制工具面；通过 eval fixture 与 CI 检查把 RAG 改动纳入回归验证。

### STAR 回答

S：企业知识库问答最怕回答看似合理但没有依据，也很难在面试中证明系统不是 Prompt Demo。  
T：我需要做一个可本地验证的 RAG/Agent 工程化项目，覆盖检索、引用、拒答、工具调用、评测和可观测。  
A：我把系统拆成 Gateway、KB Service、Worker、Web 管理台和评测脚本，使用 Qdrant、FTS、结构信号做混合检索，通过 weighted RRF 融合；回答阶段按证据强度选择 grounded/weak/refusal；Agent 侧用 ToolRegistry、Tool Workflow 和只读 MCP adapter 约束工具调用；CI 里加入 Python compile、pytest、retrieval ablation 和 Docker compose config。  
R：当前仓库有代码、测试、文档和本地验证命令支撑这些能力；真实业务准确率、延迟和成本收益仍需要业务数据补充，不在简历中编造。

### 为什么匹配 AI 应用岗位

岗位数据里 AI应用/RAG、AI Agent/智能体、Python/FastAPI 后端是最大主线。这个项目正好覆盖文档解析、检索增强、引用拒答、Agent 工具调用、模型路由、评测、trace、Docker 交付等高频能力，且能用本地测试和脚本证明，不只是概念堆砌。

### 为什么不只是 Demo

它不是单页聊天或单脚本向量检索，而是包含服务拆分、权限与异常处理、异步入库、对象存储、向量库、评测脚本、CI、Docker Compose、前端治理页和 SDK 的完整工程项目。需要保守说明的是：它目前证明的是工程能力和本地 fixture 能力，不等同于真实线上规模指标。

### 高频追问与回答思路

| 问题 | 回答思路 |
|---|---|
| chunk 怎么切？ | 讲 token budget、overlap、section/chapter 元数据和召回影响。 |
| 为什么要混合检索？ | 向量补语义，FTS 补关键词，结构信号补章节/标题，RRF 负责融合排名。 |
| rerank 什么时候用？ | 默认启发式低成本，可选 Cross-Encoder；先召回再精排，控制成本。 |
| 如何减少幻觉？ | 证据强度分类、引用标记、拒答、prompt 约束、评测与 badcase。 |
| Agent 工具怎么安全？ | schema、白名单、只读工具、超时、审计、最多轮次、高风险人工确认。 |
| MCP 你做到了什么边界？ | 本机只读 JSON-RPC adapter，不是动态插件市场，不开放 shell/文件写/任意 HTTP。 |
| 模型挂了怎么办？ | route plan、fallback_route_key、健康检查、HTTP 5xx/空回答等失败后切备路。 |
| 怎么评测？ | Recall@K、MRR/NDCG、faithfulness、citation alignment、refusal precision/recall、回归门禁。 |
| 怎么做成本优化？ | 缓存、请求合并、模型路由、证据数量上限、token 估算，不编造节省比例。 |
| 如果投 Java+AI 怎么讲？ | 本项目主打 AI/FastAPI，Java 经验作为工程基础迁移，不在本项目硬加 Java。 |

## 10. 最终结论

最值得优先做的 3 件事：

1. 固化岗位匹配证据包和本地校验脚本。
2. 补 10 分钟可演示的 RAG/Agent 闭环。
3. 扩展 badcase 和评测报告，把 citation/refusal/faithfulness 讲透。

最不建议做的 3 件事：

1. 为了算法岗硬做微调、RLHF 或大模型训练。
2. 为了 Java+AI 岗硬加 Java 服务。
3. 为了“生产级”包装虚构线上 QPS、准确率、成本收益或客户数据。

目标项目应主打关键词：

- RAG、企业知识库、混合检索、RRF、rerank、引用溯源、拒答、RAG eval、AI Agent、Tool Calling、MCP、LangGraph、FastAPI、模型路由、fallback、语义缓存、trace、成本治理、Docker。

当前距离主投岗位还差：

- 更顺滑的一键演示、岗位数据驱动的项目讲法、可展示的 badcase/评测报告和少量行业样例。

当前距离进阶岗位还差：

- 真实业务数据集指标、压测报告、生产 SLO、模型路由收益、缓存命中率、线上故障复盘和更强的多租户/权限验证。

优先顺序：

- 先补文档和 Demo，再补测试/评测，最后再改核心代码。
- 如果只能投入 1 天：跑通 `make demo-offline`，完成本报告、证据校验脚本和演示路径整理。
- 如果投入 1 周：补 smoke demo、badcase 评测集、模型路由示例、step events 展示和 README/面试材料同步。

## 11. 本轮已落地增强与验证记录

### 11.1 新增可交付材料

| 材料 | 作用 | 验证方式 |
|---|---|---|
| `docs/reference/job-interview-demo-runbook.md` | 把 RAG、Agent、评测、拒答和模型服务化收敛成 10 分钟面试演示闭环 | `python scripts/quality/check-job-alignment-evidence.py` |
| `docs/reference/job-production-boundary.md` | 区分已实现、可演示和生产仍需补强的能力，避免虚构生产指标 | `python scripts/quality/check-job-alignment-evidence.py` |
| `docs/reference/job-retrieval-ablation-report.md` | 记录岗位包装可引用的检索消融指标，并给出可重新生成 artifacts 的命令 | `python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json --output artifacts/reports/job_retrieval_ablation.json --summary-output artifacts/reports/job_retrieval_ablation.md` |

### 11.2 已验证命令

```powershell
python scripts/quality/check-job-alignment-evidence.py
python scripts/evaluation/verify-agent-smoke-evidence.py
python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json --output artifacts/reports/job_retrieval_ablation.json --summary-output artifacts/reports/job_retrieval_ablation.md
python scripts/evaluation/check-eval-regression.py --help
make demo-offline
```

验证结论：

- 岗位证据校验通过，覆盖岗位报告、演示手册、生产边界、RAG/Agent/模型服务/评测/CI 关键证据。
- `agent_smoke` 离线证据包校验通过，`grounded_single`、`agent_multi`、`strict_refusal` 三类 job 的 dataset version 和阈值完整。
- 检索消融 fixture 中 `fusion_only`、`rewrite_plus_fusion`、`rewrite_plus_fusion_plus_rerank` 三组策略均输出 `recall_at_1=1.0`、`recall_at_3=1.0`、`mrr=1.0`、`ndcg_at_3=1.0`。
- `make demo-offline` 会复用同一组脚本生成离线证据链，并聚合 `job_readiness_summary.md`。

边界说明：

- 这些指标只代表仓库内置 fixture，不代表真实线上业务准确率。
- 当前机器若缺少 Docker CLI，只能跑离线证据校验；在线 smoke eval 仍需要本地 Docker 栈。
