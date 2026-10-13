# RAG-QA 2.0 - AI应用开发亮点

> Last updated: 2026-09-27
> 本文是作品集和简历口径入口；涉及收益指标时必须区分“已验证结果”“已交付能力”和“待补指标”。

## 项目简介

面向中文场景的企业级RAG问答系统，支持多知识库管理、多模态文档解析、Agent工具调用、工作流编排等完整AI能力。

**技术栈**: FastAPI | LangChain/LangGraph | Vue 3 | PostgreSQL | Qdrant | Docker

---

## 项目指标数据台账（原始统计值）

> 本节只登记“测到了多少”，不计算提升、降低或节省比例。版本 A 为 `HEAD` 基线，版本 B 为当前实现；性能数据来自同一份脱敏语料和同一问题集，接口为纯检索 `POST /api/v1/kb/retrieve`。

### P95 延迟与 QPS 原始值

| 并发数 | 版本 A QPS | 版本 B QPS | 版本 A P95 | 版本 B P95 |
|---:|---:|---:|---:|---:|
| 1 | 24.5 | 54.0 | 45.4 ms | 21.8 ms |
| 4 | 44.0 | 69.9 | 105.5 ms | 67.2 ms |
| 8 | 40.5 | 64.5 | 252.5 ms | 167.2 ms |
| 16 | 40.2 | 62.2 | 498.8 ms | 354.0 ms |
| 32 | 38.8 | 57.8 | 1038.1 ms | 735.1 ms |

统计条件：并发 1/4/8/16/32，每档 500 请求；第二轮采用 ABBA 交替顺序；QPS 只统计成功请求，P95 为成功请求响应耗时分位值。

### 召回率、命中率与拒答率原始值

| 指标 | 版本 A | 版本 B | 样本/说明 |
|---|---:|---:|---|
| Recall@1 | 0.6179 | 0.6250 | 140 道端到端评测题 |
| MRR | 0.7536 | 0.7571 | 140 道端到端评测题 |
| NDCG@5 | 0.7826 | 0.7852 | 140 道端到端评测题 |
| 检索 Accuracy（`matched` 比例） | 0.8643 | 0.8643 | 140 道评测题；不是 LLM 答案正确率 |
| 非空检索率 | 100% | 100% | ABBA 并发压测请求 |
| 拒答率 | 0 | 2.86% | 140 道评测题 |
| 拒答 precision | 0 | 0.75 | 12 道无证据题标注 |
| 拒答 recall | 0 | 0.25 | 12 道无证据题标注 |
| 无证据题 `grounded` 判定 | 12/12 | 0/12 | 12 道无证据题 |
| 可回答题硬误拒 | — | 1/128（0.8%） | 128 道可回答题 |
| `weak_grounded` 无证据题 | — | 9/12 | 仍会保守作答，不等同于硬拒答 |

### 订单、用户与设备数原始值

| 指标 | 当前数据 | 数据状态 |
|---|---:|---|
| 订单数 | — | 本项目无订单域数据 |
| 用户数 / DAU / MAU | — | 未接入线上用户埋点 |
| 租户数 | — | 未提供生产租户统计 |
| 设备数 / 峰值设备并发 | — | 未接入设备 ID 或在线设备指标 |

这些指标不能用仓库测试数量、请求样本数或知识库文档数替代。

### 金额与成本原始值

| 指标 | 当前数据 | 数据状态 |
|---|---:|---|
| 单请求 Token 成本 | — | 已有估算能力，暂无有效线上账单 |
| LLM 总成本 | — | 供应商额度限制，未形成可比周期账单 |
| 缓存命中率 | — | 已有 `cache_hit` 字段和 Prometheus 指标，尚无活体 A/B 比例 |
| fallback 成本占比 | — | 未完成稳定线上流量统计 |
| 金额节省 | — | 没有基线周期与优化周期财务数据 |

成本统计需要固定请求量、问题分布、模型单价、输入/输出 Token、缓存命中率、fallback 比例和统计周期后再计算：

`成本下降率 =（基线周期成本 − 优化周期成本）/ 基线周期成本 × 100%`

数据来源：`.codex/verification-report-perf-2026-09-27.md`；详细复现命令见 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`。

---

## 面向简历的 STAR 亮点（主版本）

以下内容按“背景/困难 → 目标 → 解决办法 → 成效”组织。除特别说明外，指标均来自本地完整服务栈、固定脱敏语料或离线评测集，不等同于线上 SLA。

### 1. 检索热路径并发优化：同时治理 QPS、P95 与资源开销

- **背景**：知识库检索接口在并发升高后出现连接建立、线程池创建和重复查询开销，QPS 在并发 8 以上趋于饱和，P95 随并发明显上升。
- **困难**：三路召回需要并行但必须有界；性能对比还会受到页缓存、索引预热和问题顺序影响，不能只跑一轮得到结论。
- **解决办法**：复用 PostgreSQL 连接池；跨请求复用有界三路召回线程池；增加 ACL 感知 TTL/LRU 检索缓存和相同问题 single-flight 合并；压测器统一统计成功 QPS、P95、错误率和非空召回率，并采用 ABBA 交替对照。
- **成效**：同语料、同问题集、每档 500 次请求的纯检索接口压测中，并发 4–32 的 QPS 提升 **48.8%–59.1%**，P95 降低 **29.0%–36.3%**；ABBA 轮成功率 **100%**、错误数 **0**、非空检索率 **100%**。检索结果跨栈一致率 135/140（96.4%），与同栈重复查询噪声同量级，未观察到质量回归。
- **简历表述**：`针对 RAG 检索高并发下的连接/线程池重复创建瓶颈，落地连接池、有界召回线程池、ACL 感知缓存与 single-flight 合并；在固定脱敏语料 ABBA 压测中使并发 4–32 的检索 QPS 提升 48.8%–59.1%、P95 降低 29.0%–36.3%，成功率 100%。`
- **证据**：`.codex/verification-report-perf-2026-09-27.md`、`apps/services/knowledge-base/src/app/retrieval_cache.py`、`apps/services/knowledge-base/src/app/retrieve.py`。

### 2. 召回与拒答质量治理：修复评分量纲错误，避免“有结果就作答”

- **背景**：RRF 是相对排名分，却被当作绝对相关性阈值使用，导致无证据问题也被判为 `grounded`；同时 Gateway 会裁剪证据，离线阈值不能直接照搬线上链路。
- **困难**：结构、全文、向量三路分数不可直接比较；相关性分布在可回答和无证据问题之间存在重叠，阈值过严会误拒答，过松又会放过无证据问题。
- **解决办法**：新增 dense 单路绝对余弦相关性 `relevance`，贯通 `EvidencePath` 与 Gateway；按章节去重后重新标定 `STRONG_RELEVANCE=0.68`、`WEAK_RELEVANCE=0.62`；补充 RRF 误用、同章节去重和弱证据路径回归测试。
- **成效**：140 道固定评测题（128 可回答、12 无证据）端到端评测中，整体拒答率 **0→2.86%**，无证据题误判 `grounded` 从 **12/12 降至 0/12**；拒答 precision **0.75**、recall **0.25**；可回答题硬误拒 **1/128（0.8%）**。Recall@1 **0.6179→0.6250**、MRR **0.7536→0.7571**、NDCG@5 **0.7826→0.7852**，检索 Accuracy（`matched` 比例）**0.8643 保持不变**。
- **边界**：无证据题仍有 9/12 进入 `weak_grounded`，拒答召回只有 25%；阈值来自单一脱敏语料和 12 道无证据题，不能直接迁移到生产数据。
- **简历表述**：`定位并修复 RRF 相对排名分被误当绝对相关性阈值的问题，引入 dense relevance 并按端到端证据裁剪口径重标拒答阈值；在 140 题评测中将无证据题 grounded 误判由 12/12 降至 0/12，拒答 precision 达 0.75，同时保持 Accuracy 0.8643 不变。`
- **证据**：`.codex/verification-report-perf-2026-09-27.md` 附录 B/C、`packages/python/shared/grounded_answering.py`、`packages/python/shared/retrieval.py`、`tests/test_shared_stack.py`。

### 3. 企业权限与缓存隔离：避免跨部门检索结果泄露

- **背景**：企业知识库中的文档权限随人员和部门变化，不能把人员权限复制进文档；结构、全文、向量召回以及显式 `document_ids` 都不能成为绕过入口。
- **困难**：权限过滤必须在三路召回前统一生效，还要覆盖语义缓存和工作流恢复，否则可能出现“查询已过滤、缓存却复用他人答案”的侧漏。
- **解决办法**：文档只持久化 `allowed_departments`，当前部门从签名 JWT 的 `CurrentUser.department` 获取；KB 在召回前统一求交过滤，显式文档范围不能越权；部门/管理员范围纳入 Gateway 缓存键，并在 checkpoint 恢复时校验访问上下文。
- **成效**：已交付查询、显式范围、缓存和恢复链路一致的 ACL 语义，并补充部门权限与文档 ACL 回归测试；当前没有真实租户规模或安全审计数据，不宣称线上零泄露或用户覆盖规模。
- **简历表述**：`将文档 ACL 与人员身份解耦，基于 JWT 部门上下文在结构/全文/向量召回前统一过滤，并把权限范围纳入语义缓存和工作流恢复校验，阻断显式文档 ID 与缓存复用造成的越权路径。`
- **证据**：`apps/services/knowledge-base/database/migrations/011_document_department_permissions.sql`、`apps/services/knowledge-base/src/app/retrieve.py`、`tests/test_auth_department.py`、`tests/test_kb_document_acl.py`。

### 4. 长链路可恢复与 Agent 治理：把“能调用”变成“可控制、可排障”

- **背景**：RAG 问答包含准备、检索、工具调用、人工审核、生成和持久化等阶段，单体 service 失败时难以定位；复杂问题还需要并行拆解，工具调用必须有预算和安全边界。
- **困难**：阶段拆分过粗无法定位，过细又会增加状态复杂度；工具既要兼容 OpenAI/LangChain schema，又不能开放任意动态执行入口。
- **解决办法**：用 LangGraph 建模可恢复节点和 checkpoint；通过任务复杂度评估、DAG 拆解、并行执行、反思评分和策略记忆形成 Agent 闭环；工具注册中心统一 schema、超时、缓存、统计与只读 MCP adapter；以模型健康 P50/P95/P99、熔断、fallback 和治理指标提供排障入口。
- **成效**：已交付节点级恢复、工具预算、执行统计、只读工具准入和运行时治理指标；相关能力有定向测试支撑，但尚无生产多实例稳定性、模型端到端 P95 或 Agent 成本下降数据。
- **简历表述**：`基于 LangGraph 构建可恢复 RAG 工作流，补齐 Agent 任务拆解、并行执行、反思闭环、工具注册与只读 MCP 治理能力，实现阶段级 trace、预算控制和故障恢复。`

### 5. 成本治理口径：能力已交付，收益不虚构

- **已交付**：L1 精确/L2 可选语义/L3 Prompt Cache、请求合并、复杂度路由、Token 估算、预算控制、模型健康熔断和 `usage_reconciliation` 诊断口径。
- **当前成效**：接口已返回 `cache_hit`，Prometheus 已暴露检索缓存统计；但新增检索缓存尚未完成活体命中率 A/B，在线 LLM 评测还受供应商额度限制，不能据此写“成本下降 X%”。
- **待补**：按真实业务问题分布补充缓存命中率、Token/请求、LLM 成本、金额节省和长期稳定性。

## 指标口径与不可外推项

| 指标 | 当前可写口径 | 当前不能写成的结论 |
|---|---|---|
| QPS / P95 | 纯检索接口、并发 4–32：QPS +48.8%–59.1%，P95 -29.0%–36.3% | 端到端（含 LLM）P95/QPS 或线上 SLA |
| 命中/召回 | 非空检索率 100%；Recall@1、MRR、NDCG@5 有 140 题前后评测 | 线上搜索命中率、长期召回率 |
| 拒答 | 固定 140 题拒答率 0→2.86%；无证据题 grounded 误判 12/12→0/12；precision 0.75、recall 0.25 | “拒答问题已彻底解决”或可迁移阈值 |
| 缓存 / 成本 | 已实现 `cache_hit`、TTL/LRU、single-flight 和成本估算 | 缓存命中率、Token/金额下降百分比 |
| 订单 / 用户 / 设备 | 本项目是企业知识库 RAG，当前无订单、设备或线上用户规模数据 | 订单数、用户数、设备数、GMV/金额等业务成果 |

---

## 按统计口径整理的简历亮点

> 统一范围：本地完整服务栈、同一份脱敏语料、同一问题集；性能数据来自纯检索接口，质量数据来自 140 题端到端评测。除非特别标注，不代表线上长期 SLA。

### 1. P95 延迟（Latency）

**统计口径**：`POST /api/v1/kb/retrieve` 成功请求的响应耗时 P95；不包含 LLM 生成、网络跨地域和前端渲染。

| 并发 | 优化前 P95 | 优化后 P95 | 降低幅度 |
|---:|---:|---:|---:|
| 4 | 105.5 ms | 67.2 ms | **36.3%** |
| 8 | 252.5 ms | 167.2 ms | **33.8%** |
| 16 | 498.8 ms | 354.0 ms | **29.0%** |
| 32 | 1038.1 ms | 735.1 ms | **29.2%** |

**简历亮点**：针对 RAG 检索链路每请求建连、建线程池导致的尾延迟劣化，采用连接池和共享有界召回线程池，在并发 4–32 下将纯检索 P95 降低 **29.0%–36.3%**。

**边界**：不能写成端到端问答 P95，也不能写成线上 SLA；缓存新增后的单独 P95 收益尚未拆分验证。

### 2. QPS / 并发能力

**统计口径**：ABBA 交替压测；并发 4/8/16/32，每档 500 请求；QPS 只统计成功请求，基线与优化使用同语料、同 Qdrant/PostgreSQL 依赖。

| 并发 | 优化前 QPS | 优化后 QPS | 提升幅度 |
|---:|---:|---:|---:|
| 4 | 44.0 | 69.9 | **58.8%** |
| 8 | 40.5 | 64.5 | **59.1%** |
| 16 | 40.2 | 62.2 | **55.0%** |
| 32 | 38.8 | 57.8 | **48.8%** |

**简历亮点**：通过连接池、共享线程池、ACL 感知 TTL/LRU 检索缓存和 single-flight 合并，将检索接口并发 4–32 的 QPS 提升 **48.8%–59.1%**；ABBA 轮成功率 **100%**、错误数 **0**。

**边界**：这是检索段吞吐，不是含 LLM 的问答吞吐；没有线上用户数或设备并发数，不能改写成生产容量结论。

### 3. 召回率 / 命中率 / 拒答率

**统计口径**：召回质量使用 140 道标注题；“非空检索率”表示返回至少一条证据，不等同于缓存命中率；拒答 precision/recall 按 12 道无证据题标注计算。

| 指标 | 优化前 | 优化后 | 口径与解释 |
|---|---:|---:|---|
| Recall@1 | 0.6179 | 0.6250 | 140 题端到端检索结果 |
| MRR | 0.7536 | 0.7571 | 140 题端到端检索结果 |
| NDCG@5 | 0.7826 | 0.7852 | 140 题端到端检索结果 |
| 检索 Accuracy | 0.8643 | 0.8643 | 140 题 `matched` 比例，不是 LLM 答案正确率 |
| 非空检索率 | — | **100%** | 并发压测请求均返回非空证据 |
| 拒答率 | 0 | **2.86%** | 140 题中 4 题拒答 |
| 无证据题 grounded 误判 | 12/12 | **0/12** | 修复 RRF 相对排名分误用 |
| 拒答 precision / recall | 0 / 0 | **0.75 / 0.25** | 仍有 9/12 进入 `weak_grounded` |

**解决办法**：将 RRF 相对排名分与 dense 单路绝对相关性拆开，新增 `EvidencePath.relevance`，按章节去重，并基于 Gateway 证据裁剪后的真实输入重标阈值。

**简历亮点**：修复 RRF 分数量纲错误导致的“有结果就作答”，在 140 题评测中将无证据题 grounded 误判由 **12/12 降至 0/12**，拒答 precision 达 **0.75**，同时保持检索 Accuracy **0.8643** 不变。

**边界**：拒答 recall 仅 **0.25**，阈值来自单一脱敏语料，不能写成“拒答问题已彻底解决”；缓存 `cache_hit` 当前只有接口与 Prometheus 统计能力，没有可引用的活体命中率。LLM 未真正完成在线调用，faithfulness、答案正确率和生成质量不作为本轮成果。

### 4. 订单 / 用户 / 设备数

**当前统计结论**：本项目是企业知识库 RAG，现有证据中没有订单数、活跃用户数、设备数、租户数或线上请求规模，因此这些指标不能写成项目成果。

**后续补数口径**：

- 订单：统计周期内成功订单数、支付成功率、订单链路错误率。
- 用户：DAU/MAU、去重用户数、租户数、问答请求用户覆盖数。
- 设备：去重设备数、在线设备数、峰值并发设备数；必须明确设备 ID 去重规则。

**当前可写表述**：`实现多知识库与部门 ACL 隔离能力，支持按认证上下文控制检索范围；线上用户、租户和设备规模待业务埋点确认。`

### 5. 金额 / 成本下降

**已交付能力**：Token 成本估算、预算控制、L1/L2/L3 缓存、请求合并、复杂度路由、模型健康熔断、`usage_reconciliation` 对账诊断和 `cache_hit` 观测字段。

**当前统计结论**：没有完成同流量、同问题分布、同模型价格下的在线 A/B，也受供应商额度限制，不能写“成本下降 X%”“节省 X 元”或“Token 降低 X%”。

**后续补数口径**：

`成本下降率 =（基线周期成本 − 优化周期成本）/ 基线周期成本 × 100%`

需同时记录请求量、输入/输出 Token、模型单价、缓存命中率、fallback 比例和统计周期，避免把流量下降误判为单请求降本。

**当前可写表述**：`构建 Token 成本归因、预算控制与多级缓存治理闭环，为后续按请求成本和缓存收益 A/B 提供可观测基础；实际金额节省待线上账单与流量数据验证。`

### 6. 可直接放入简历的指标版组合

- `优化 RAG 检索热路径，采用 PostgreSQL 连接池、共享有界召回线程池、ACL 感知 TTL/LRU 缓存和 single-flight；在 ABBA 对照压测中，并发 4–32 的纯检索 QPS 提升 48.8%–59.1%，P95 降低 29.0%–36.3%，成功率 100%。`
- `定位并修复 RRF 相对排名分被误当绝对相关性阈值的问题，引入 dense relevance 与章节去重；140 题评测中无证据题 grounded 误判由 12/12 降至 0/12，拒答 precision 0.75，Recall@1/MRR/NDCG@5 分别提升至 0.6250/0.7571/0.7852。`
- `建立 Token 成本归因、预算控制、三级缓存和模型熔断能力；由于尚无线上账单、用户规模和缓存命中率 A/B，暂不宣称金额、成本或用户规模收益。`

---

## 技术能力清单（实现范围）

### 1. RAG检索增强
- 多路召回（结构+全文+向量）+ RRF融合算法
- 查询重写（实体识别、章节定位、词法扩展）
- 默认本地启发式重排序，Cross-Encoder 作为可选增强

### 2. 基于证据的生成
- 证据分类评分（grounded/weak/refusal）
- 强制引用标记 [1][2]
- 幻觉检测与保守回答策略

### 3. LangGraph工作流引擎
- 状态机编排复杂AI流程
- 支持中断恢复（人工审核、证据不足）
- PostgreSQL持久化，故障可恢复

### 4. Agent工具框架
- 多工具调用（检索、列表、搜索）
- 预算控制（3次调用/8条证据上限）
- 跨工具证据聚合去重
- 本地人工接管队列支持按租户与技能组原子认领待处理会话

### 5. 模型路由与降级
- 按场景配置不同模型参数
- 通过 `fallback_route_key` 在本地 5xx、上游不可用、非法响应或空回答等失败后尝试备线路由
- 支持 OpenAI-compatible 中转站接入、newapi/sub2api 模型发现和 `fallback_route_key` 备线路由
- 支持流式生成 + Token实时追踪

### 6. 多模态视觉处理
- PDF/DOCX/图片视觉资产提取
- 多Provider OCR（Tesseract + API）
- 内容哈希去重、缩略图生成

### 7. AI安全防护
- 提示注入检测（指令覆盖、提示词泄露、引用绕过）
- 多源扫描（问题+历史+证据）
- 分级响应（阻断/降级/警告）
- 文档级 ACL：知识库只保存文档 `allowed_departments`，不保存人员权限；查询从签名 JWT 的 `CurrentUser.department` 取部门，并在结构/全文/向量召回前统一过滤，显式 `document_ids` 不能绕过
- 空 `allowed_departments` 表示公开文档；无部门用户仅可访问公开文档，管理员按管理权限执行范围查询；部门范围同时纳入 Gateway 语义缓存隔离键

### 8. 评测与可观测
- 多维度评估（Accuracy/Faithfulness/Citation/Recall@K），并补充 deterministic retrieval fixture
- 全链路Trace ID追踪
- 运行时治理指标：Tool Workflow / Prompt rollback 聚合计数、成功率、耗时和短失败原因，通过 `metrics-summary` 与 Prometheus 指标族暴露
- 知识库治理页受控 rebuild：单文档 dry-run 签名匹配后才执行固定端点调用，只基于服务端已有 section/chunk 重建向量，不开放文件上传、目录扫描或任意路径重建
- 知识库治理页批量 JSON：显式粘贴 `{documents:[...]}` 后必须先 batch dry-run，签名匹配才允许 batch-ingest；写入成功后可对生成的 document_id 逐个触发受控 rebuild
- 知识库批量 dry-run 预览：`POST /api/knowledge_base/batch-dry-run` 只处理请求体内联多文档内容，输出分块摘要和脱敏文件名，不读取路径、不写入向量库、不触发批量 rebuild
- 知识库批量写入 API：`POST /api/knowledge_base/batch-ingest` 只写入请求体内联文档并索引 section/chunk，不读取路径、不上传文件、不批量 delete
- 知识库后台任务队列：`POST /api/knowledge_base/jobs` 支持把内联 ingest/rebuild 放入进程内串行队列，状态接口只返回任务摘要和脱敏文件名，不持久化、不扫描目录、不读取 source_file/source_path
- 知识库固定 inbox 预览：`GET /api/knowledge_base/auto-index/preview` 只读扫描固定 `KB_BLOB_ROOT/knowledge_base/inbox` 一层文本/Markdown，输出分块摘要和跳过原因，不接收任意路径、不递归扫描、不自动入库
- 知识库只读索引 API：`GET /api/knowledge_base/index` 只返回已入库 metadata 摘要，不做文件系统索引，不回显正文、embedding 或完整路径
- Token级成本估算 + 本地 embedding / 证据数量上限等成本控制

### 9. 受控 Agent 编排与反思闭环
- **任务拆解引擎**：自动评估问题复杂度（1-5级），复杂问题自动拆解为DAG子任务并行执行
- **反思闭环**：输出自检（完整性/准确性/引用三维度评分）+ 失败根因分析 + 策略记忆
- **三层记忆系统**：短期（会话窗口）/长期（三元组提取+Qdrant检索）/工作记忆（Scratchpad）
- **可扩展工具注册中心**：装饰器注册 + OpenAI/LangChain schema 生成 + 结果缓存 + 执行统计，并通过只读 MCP adapter 暴露安全摘要工具

### 10. 推理性能优化
- **三层语义缓存**：L1精确/L2语义（余弦相似度）/L3 Prompt Cache，命中收益通过缓存统计与压测报告确认，不在无数据时写固定百分比
- **检索热路径优化**：PostgreSQL 连接池 + 有界三路召回线程池 + ACL 感知 TTL/LRU 检索缓存；相同问题并发使用 single-flight 合并，接口返回 `cache_hit`，压测脚本统一统计成功 QPS、P95、错误率和缓存命中率
- **模型健康监控**：实时P50/P95/P99延迟追踪 + 自动熔断（连续失败阈值）+ 健康评分EMA
- **智能路由v2**：复杂度驱动模型选择（简→经济模型/中→标准模型/难→高级模型）
- **请求合并器**：100ms窗口内相同问题自动合并，减少重复LLM调用

### 11. 平台化与生态
- **五层分层指令体系**：L1系统→L2场景→L3 Agent→L4会话→L5调用级，优先级合并+冲突检测+安全校验
- **6大场景模板**：企业QA/技术支持/合规审查/培训教练/数据分析/代码审查，一键切换
- **RAG幻觉检测**：引用一致性+数字一致性+LLM深度分析三路径，自动标记高风险回答
- **模型接入页**：展示脱敏 LLM 配置摘要，发现 OpenAI-compatible 中转站模型并生成 `LLM_MODEL_ROUTING_JSON` 配置片段
- **Python SDK**：同步/异步双客户端，覆盖问答/流式/知识库管理/Agent模式/成本查询/缓存管理

---

## 简历一句话描述

> 独立设计并实现企业级RAG问答系统，涵盖多路检索融合、LangGraph工作流编排、**受控 Agent 编排**（任务拆解+反思闭环+三层记忆+工具注册中心）、多模态视觉处理、AI安全防护、**模型中转站接入与路由 fallback**、**推理优化**（三层缓存+模型健康熔断+智能路由）、**五层指令体系**、RAG幻觉检测和Python SDK等完整AI工程能力。

---

## 作品集展示建议

| 模块 | 展示要点 |
|------|----------|
| 架构图 | 微服务拆分 + 数据流 |
| 检索流程 | 查询重写 → 多路召回 → RRF融合 → 重排序 |
| 工作流 | LangGraph状态机 + 中断恢复界面 |
| Agent演示 | 多步工具调用过程可视化 |
| 安全演示 | 提示注入拦截示例 |
| 评测报告 | recall@K、MRR、NDCG、ingest throughput 报告 |

---

## 技术深度点

- **RRF融合算法**: 实现加权倒数排序融合，支持结构/FTS/向量三路信号融合
- **LangGraph工作流**: 基于状态机的复杂AI流程编排，支持中断恢复和PostgreSQL持久化
- **Grounded Answering**: 证据感知的生成框架，强制引用标记和幻觉检测
- **多Provider嵌入**: 本地轻量嵌入与外部API的统一抽象，支持查询缓存
- **提示词安全防护**: 多层防御体系，中英文提示注入检测与分级响应

---

## STAR 技术难点索引

完整 STAR 材料见 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`，建议面试时优先讲下面这些难点：

| 难点 | 解决方案 | 证据 |
|---|---|---|
| 检索调试链路原本不可解释 | 统一 `/kb/retrieve/debug` 契约，展示 `signal_scores`、`evidence_path`、debug rank 和 retrieval stats | `RetrievalDebuggerView.vue`、`tests/test_backend_infra.py` |
| 低成本 RAG 容易依赖外部模型 | 默认本地 embedding + Qdrant + PostgreSQL FTS + 结构信号 + weighted RRF + heuristic rerank，Cross-Encoder 作为增强 | `retrieve.py`、`rerank.py`、`embeddings.py` |
| RAG 效果缺少回归门禁 | 新增 deterministic retrieval fixture 与 local ingest fixture，CI smoke 补齐评测脚本参数 | `tests/fixtures/evals/*`、`.github/workflows/ci.yml` |
| 回答可信度不能只靠 prompt | 使用证据块、引用、grounded answer 与安全测试约束回答边界 | `grounded_answering.py`、`test_safety_guardrails.py` |
| 长链路故障难定位 | Gateway 与 KB 侧拆成可观测阶段，保留 trace、retrieval stats、warnings | `gateway_chat_service.py`、`retrieve.py`、`test_langgraph_runtime.py` |
| 人工接管容易重复分配 | 本地接管队列抽象（租户+技能组过滤、优先级排序、条件更新认领） | `gateway_handoff.py`、`tests/test_backend_infra.py` |
| **Agent工具缺乏可扩展性** | **工具注册中心（装饰器注册+schema生成+只读MCP adapter+缓存统计）** | `tool_registry.py`、`test_agent_capabilities.py`、`test_mcp_adapter.py` |
| **复杂问题缺乏自主拆解** | **任务拆解引擎（复杂度评估+DAG+并行执行）** | `task_decomposer.py`、`test_agent_capabilities.py` |
| **重复问题浪费Token成本** | **三层语义缓存（L1精确/L2语义/L3 Prompt Cache）** | `semantic_cache.py`、`test_inference_optimization.py` |
| **缺乏Agent输出质量自检** | **反思闭环（三维评分+失败分析+策略记忆）** | `agent_reflection.py`、`test_agent_capabilities.py` |
| **回答可能包含幻觉** | **幻觉检测（引用一致性+数字一致性+LLM深度分析）** | `hallucination_detector.py`、`test_platform_ecosystem.py` |
| **高并发检索 P95 劣化** | **连接池+有界召回线程池+ACL 感知缓存+single-flight；ABBA 压测** | `.codex/verification-report-perf-2026-09-27.md` |
| **无证据题被错误判为 grounded** | **dense absolute relevance+章节去重+端到端阈值标定** | `grounded_answering.py`、`vector_store.py`、`.codex/verification-report-perf-2026-09-27.md` |

这些难点适合用 STAR 结构展开：先讲真实问题，再讲工程约束、取舍和验证证据。没有真实业务报告前，不把最小 fixture 的指标写成线上收益。

---

## 面试口径校准

- **已实现**：本地 embedding 抽象、Qdrant 向量召回、PostgreSQL FTS、结构信号、weighted RRF、启发式 rerank、grounded answer 引用、提示注入防护、LangGraph 可恢复运行时、人工接管队列、**受控 Agent 编排（任务拆解+反思+记忆+工具注册）、三层缓存、模型健康熔断、模型中转站接入与路由 fallback、五层指令体系、6大场景模板、RAG幻觉检测、Python SDK**。
- **已验证**：最小 deterministic fixture 可产出 retrieval ablation、embedding benchmark 和 local ingest benchmark 报告，并接入 CI smoke，形成可重复的评测回归门禁。
- **质量基线**：24 个章节、140 道人工标注题（120 单章节、8 多章节、12 无证据，58 道 holdout，其中 52 道可回答）上，原始语料词法诊断可回答 holdout Recall@3=100%、MRR=100%；另有 140 题 Gateway 端到端拒答/召回对照，具体数字以本文 STAR 2 和验证报告为准。
- **可选增强**：外部 embedding provider 和 Cross-Encoder rerank 已预留配置入口，但不是默认低成本路线。
- **待补指标**：缓存真实命中率、端到端（含 LLM）P95/QPS、真实业务命中率、订单/用户/设备规模、Token/金额成本节省，需要以线上监控、业务埋点或成本报告补充，不在简历中写成确定收益。

## 简历资料维护口径

- 本文作为 RAG-QA 的项目亮点入口，负责概括 AI 能力、工程边界和可展示模块。
- 技术难题与解决方案入口为 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`，其中包含 STAR 展开、追问表和验证命令。
- 简历中涉及“中软国际 / 企业知识库 RAG”时，可与本文合并引用；真实业务准确率、延迟和成本收益继续标注为待补指标。
