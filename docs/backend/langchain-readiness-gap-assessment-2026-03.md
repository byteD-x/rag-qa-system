# LangChain 集成度与 AI 应用能力差距评估

Last updated: 2026-03-10

## 概览

这份文档用于把当前仓库的 LangChain 集成现状、距离更完整 AI 应用工程能力的差距，以及后续优先改造方向沉淀为可复查、可拆解、可验证的路线图。

结论先行：

- 以“RAG 主链路是否已由 LangChain 接管”为标准，当前项目大约完成了 `75%-85%`。
- 以“完整 LangChain 生态集成”为标准，也就是补齐 `LangGraph + LangSmith/Tracing + durable workflow + prompt/experiment management`，当前大约在 `45%-55%`。
- 以“AI 应用开发岗位的工程能力证明”为标准，当前项目已经明显超过纯 demo，但还没有把生产级 AI 应用最难的几类问题闭环。

## 现状判断依据

当前仓库已经不是“局部试用 LangChain”，而是把它放进了检索、生成和受限 agent 编排主链路：

- `api-gateway` 已显式引入 `langchain-core` 与 `langchain-openai`。
- `knowledge-base` 已显式引入 `langchain-community`、`langchain-core`、`langchain-openai`、`langchain-qdrant`。
- KB 检索链路已经使用 `RunnableLambda`、`BaseRetriever`、`Document`、`weighted_rrf` 和 rerank 组成主路径。
- Qdrant 读写已经统一走 `QdrantVectorStore` 的 hybrid retrieval 模式。
- Gateway 生成链路已经统一走 `ChatPromptTemplate | ChatOpenAI`，同时支持 `ainvoke` 与 `astream`。
- 统一聊天已经支持受限工具调用的 `agent` 模式，但仍是有限轮数的轻量编排，而不是持久化图工作流。

可直接对照的代码与文档：

- [`apps/services/api-gateway/requirements.runtime.txt`](../../apps/services/api-gateway/requirements.runtime.txt)
- [`apps/services/knowledge-base/requirements.runtime.txt`](../../apps/services/knowledge-base/requirements.runtime.txt)
- [`apps/services/knowledge-base/src/app/retrieve.py`](../../apps/services/knowledge-base/src/app/retrieve.py)
- [`apps/services/knowledge-base/src/app/vector_store.py`](../../apps/services/knowledge-base/src/app/vector_store.py)
- [`apps/services/api-gateway/src/app/gateway_agent.py`](../../apps/services/api-gateway/src/app/gateway_agent.py)
- [`packages/python/shared/langchain_chat.py`](../../packages/python/shared/langchain_chat.py)
- [`docs/backend/langchain-integration-2026-03.md`](./langchain-integration-2026-03.md)

## 差距清单

### 1. LangGraph / durable workflow 尚未落地

当前 `agent` 仅支持最多 3 轮工具调用，适合受限检索编排，但还不具备以下能力：

- 节点级状态持久化
- 中断恢复与重放
- 人工审批节点
- 多步子任务拆解与回溯

这意味着它已经能证明“会做 tool calling”，但还不足以证明“会做复杂 agent workflow 工程化”。

### 2. LLM 链路级 tracing / prompt management 不完整

仓库已经有：

- 自建 `trace_id`
- readiness / metrics
- 请求级链路透传

但仍缺：

- LLM span 级 tracing
- prompt 版本管理
- run-level 实验对比
- 链路级调用回放
- 面向模型效果和成本的统一观测面板

### 3. 检索质量上限还未打透

当前检索链路已经具备：

- query rewrite
- structure hit
- FTS
- hybrid vector retrieval
- Weighted RRF
- 轻量 lexical rerank

但 rerank 仍偏规则化，尚未进入：

- cross-encoder reranker
- LLM-as-reranker
- 多段证据聚合排序
- 按问题类型自适应检索策略

这会限制长尾 query、复杂跨段证据对齐和高精度 top-k 排序能力。

### 4. 真实评测数据闭环不完整

仓库已有：

- retrieval ablation
- unified eval suite
- ingest benchmark
- 并发 retrieval benchmark

但 README 明确采用“零数据基线”，说明脚本入口齐全，不代表已经沉淀出真实业务 fixture、长期回归集和 A/B 报告。当前更像“评测框架已具备”，不是“评测运营已闭环”。

### 5. 生产治理能力仍偏薄

对 AI 应用岗位而言，真正拉开差距的往往不是是否会接 LangChain，而是是否解决了：

- 模型路由与 provider fallback
- 令牌、成本、配额、预算治理
- 缓存与限流
- 人工审核与反馈回流
- 灰度发布与回滚策略

这些能力当前仓库还没有形成一套完整机制。

### 6. 数据接入与知识生命周期仍偏“文件上传型 RAG”

当前项目非常适合演示文档上传、解析、索引、问答，但距离企业 AI 应用常见需求还差：

- 外部系统连接器
- 增量同步
- 权限继承
- 失效文档重建索引
- freshness 与版本化知识治理

### 7. 记忆与会话策略仍较轻

当前已有 history 裁剪和问题上下文化，但还缺：

- 长期记忆
- 用户偏好记忆
- 摘要记忆分层
- 多会话共享记忆
- 记忆质量评测与淘汰策略

### 8. 安全治理只有基础层

当前已有 prompt injection 模式匹配、fallback/refusal 和 grounded answer 边界约束。这说明仓库已经意识到安全问题，但还没有进入更完整的治理层：

- 分类器或策略引擎
- 分层 guardrails
- 高风险问题自动升级
- 安全事件复盘与审计平台

## 结论

如果目标是“证明已经把 LangChain 接入主链路”，当前仓库已经达标。

如果目标是“证明已经完成完整 LangChain 平台化”，当前仓库还缺 durable workflow、LLM tracing、prompt/experiment management 等关键模块。

如果目标是“证明已经具备 AI 应用开发岗位最核心的生产能力”，当前最需要继续补强的是以下五块：

1. workflow durability
2. 真实评测闭环
3. 成本与配额治理
4. 在线观测与实验管理
5. 真实业务数据运营能力

一句话判断：

> 这个项目已经能证明“会做工程化 RAG”，但还不能完全证明“已经解决生产级 AI 应用开发中最难的系统问题”。

## 里程碑表

| milestone | description | owner | status | updated_at |
| --- | --- | --- | --- | --- |
| M1 | 补齐 LangGraph / durable workflow 最小原型 | `@agent` | `todo` | 2026-03-10 |
| M2 | 建立 LLM tracing、prompt versioning 与实验记录基线 | `@agent` | `todo` | 2026-03-10 |
| M3 | 提升检索与 rerank 上限并形成对比评测 | `@agent` | `todo` | 2026-03-10 |
| M4 | 补齐真实评测数据闭环与回归报告 | `@agent` | `todo` | 2026-03-10 |
| M5 | 建立生产治理基线：成本、限流、缓存、反馈 | `@agent` | `todo` | 2026-03-10 |

## 任务表

| task_id | milestone | title | assignee | status | verify_cmd | expected_result | updated_at |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-LC-001 | M1 | 为 agent 模式补充可恢复状态机与节点级日志 | `@agent` | `todo` | `pytest tests/test_backend_infra.py -q` | Agent 退化与恢复路径有可重复验证 | 2026-03-10 |
| T-LC-002 | M2 | 为 LLM 调用增加链路级 tracing 字段与版本标识 | `@agent` | `todo` | `pytest tests/test_backend_infra.py -q` | 关键回答路径保留可追踪元数据 | 2026-03-10 |
| T-LC-003 | M3 | 引入更强 rerank 实验位并输出对比报告 | `@agent` | `todo` | `python scripts/evaluation/run-retrieval-ablation.py --fixture <fixture.json>` | 报告包含新旧排序策略差异 | 2026-03-10 |
| T-LC-004 | M4 | 建立真实业务 fixture 与统一回归 eval 配置 | `@agent` | `todo` | `python scripts/evaluation/run-eval-suite.py --password <pwd> --config <suite.json>` | 输出可复用回归报告 | 2026-03-10 |
| T-LC-005 | M5 | 增加成本/配额/限流基础治理能力 | `@agent` | `todo` | `docker compose config --quiet` | 配置层可声明治理开关且不破坏现有编排 | 2026-03-10 |

## How to verify

文档层面的最小验证：

```powershell
python scripts/quality/check-encoding.py
docker compose config --quiet
```

如果要重新核对当前结论所依据的后端主链路测试，可额外执行：

```powershell
pytest tests/test_backend_infra.py -q
```

## Risk

- 本文档中的百分比属于工程判断，不等同于线上流量、真实客户数据和生产 SLA 结论。
- 本文档刻意不把“可继续做”的方向写成“已经完成”，避免夸大项目成熟度。
- 任务表是路线图，不代表这些高阶能力已在当前仓库实现。
