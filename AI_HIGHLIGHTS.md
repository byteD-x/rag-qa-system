# RAG-QA 2.0 - AI应用开发亮点

> Last updated: 2026-06-06
> 本文是作品集和简历口径入口；涉及收益指标时必须区分“最小 fixture 已验证”和“真实业务待补指标”。

## 项目简介

面向中文场景的企业级RAG问答系统，支持多知识库管理、多模态文档解析、Agent工具调用、工作流编排等完整AI能力。

**技术栈**: FastAPI | LangChain/LangGraph | Vue 3 | PostgreSQL | Qdrant | Docker

---

## 核心亮点

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
- 级联降级，主模型失败自动切换
- 支持流式生成 + Token实时追踪

### 6. 多模态视觉处理
- PDF/DOCX/图片视觉资产提取
- 多Provider OCR（Tesseract + API）
- 内容哈希去重、缩略图生成

### 7. AI安全防护
- 提示注入检测（指令覆盖、提示词泄露、引用绕过）
- 多源扫描（问题+历史+证据）
- 分级响应（阻断/降级/警告）

### 8. 评测与可观测
- 多维度评估（Accuracy/Faithfulness/Citation/Recall@K），并补充 deterministic retrieval fixture
- 全链路Trace ID追踪
- Token级成本估算 + 本地 embedding / 证据数量上限等成本控制

### 9. AI Agent 自主决策体系
- **任务拆解引擎**：自动评估问题复杂度（1-5级），复杂问题自动拆解为DAG子任务并行执行
- **反思闭环**：输出自检（完整性/准确性/引用三维度评分）+ 失败根因分析 + 策略记忆
- **三层记忆系统**：短期（会话窗口）/长期（三元组提取+Qdrant检索）/工作记忆（Scratchpad）
- **可扩展工具注册中心**：装饰器注册 + OpenAI/LangChain schema 生成 + 结果缓存 + 执行统计，并通过只读 MCP adapter 暴露安全摘要工具

### 10. 推理性能优化
- **三层语义缓存**：L1精确/L2语义（余弦相似度）/L3 Prompt Cache，命中收益通过缓存统计与压测报告确认，不在无数据时写固定百分比
- **模型健康监控**：实时P50/P95/P99延迟追踪 + 自动熔断（连续失败阈值）+ 健康评分EMA
- **智能路由v2**：复杂度驱动模型选择（简→经济模型/中→标准模型/难→高级模型）
- **请求合并器**：100ms窗口内相同问题自动合并，减少重复LLM调用

### 11. 平台化与生态
- **五层分层指令体系**：L1系统→L2场景→L3 Agent→L4会话→L5调用级，优先级合并+冲突检测+安全校验
- **6大场景模板**：企业QA/技术支持/合规审查/培训教练/数据分析/代码审查，一键切换
- **RAG幻觉检测**：引用一致性+数字一致性+LLM深度分析三路径，自动标记高风险回答
- **Python SDK**：同步/异步双客户端，覆盖问答/流式/知识库管理/Agent模式/成本查询/缓存管理

---

## 简历一句话描述

> 独立设计并实现企业级RAG问答系统，涵盖多路检索融合、LangGraph工作流编排、**Agent自主决策**（任务拆解+反思闭环+三层记忆+工具注册中心）、多模态视觉处理、AI安全防护、**推理优化**（三层缓存+模型健康熔断+智能路由）、**五层指令体系**、RAG幻觉检测和Python SDK等完整AI工程能力。

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

完整 STAR 材料见 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`，建议面试时优先讲下面五个难点：

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

这些难点适合用 STAR 结构展开：先讲真实问题，再讲工程约束、取舍和验证证据。没有真实业务报告前，不把最小 fixture 的指标写成线上收益。

---

## 面试口径校准

- **已实现**：本地 embedding 抽象、Qdrant 向量召回、PostgreSQL FTS、结构信号、weighted RRF、启发式 rerank、grounded answer 引用、提示注入防护、LangGraph 可恢复运行时、人工接管队列、**Agent自主决策（任务拆解+反思+记忆+工具注册）、三层缓存、模型健康熔断、五层指令体系、6大场景模板、RAG幻觉检测、Python SDK**。
- **已验证**：最小离线 fixture 可产出 retrieval ablation、embedding benchmark 和 local ingest benchmark 报告；当前仓库包含 22 个后端 `test_*.py` 与 9 个前端 `*.test.ts`，覆盖 400+ 测试项。
- **可选增强**：外部 embedding provider 和 Cross-Encoder rerank 已预留配置入口，但不是默认低成本路线。
- **待补指标**：真实业务数据上的延迟、吞吐、命中率提升和成本节省，需要以线上或压测报告补充，不在简历中写成确定收益。

## 简历资料维护口径

- 本文作为 RAG-QA 的项目亮点入口，负责概括 AI 能力、工程边界和可展示模块。
- 技术难题与解决方案入口为 `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`，其中包含 STAR 展开、追问表和验证命令。
- 简历中涉及“中软国际 / 企业知识库 RAG”时，可与本文合并引用；真实业务准确率、延迟和成本收益继续标注为待补指标。
