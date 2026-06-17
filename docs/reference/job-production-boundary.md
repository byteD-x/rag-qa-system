# 岗位包装生产边界说明

> 目标：面向 25-40K 及以上岗位，把“已实现能力”“可演示能力”“生产仍需补强”分清楚，避免把项目包装成无法验证的伪生产系统。

## 1. 已有工程证据

| 能力 | 当前证据 | 可对面试官说明 |
|---|---|---|
| FastAPI 服务拆分 | `apps/services/api-gateway/src/app/main.py`、`apps/services/knowledge-base/src/app/main.py` | Gateway 负责聊天、Agent、平台治理；KB Service 负责知识库和检索 |
| 混合检索 | `apps/services/knowledge-base/src/app/retrieve.py`、`packages/python/shared/retrieval.py` | 结构信号、FTS、向量召回通过 weighted RRF 融合，再进入 rerank |
| 可信回答 | `packages/python/shared/grounded_answering.py`、`apps/services/api-gateway/src/app/gateway_answering.py` | 按证据强度选择 grounded、weak grounded、refusal 或 common knowledge |
| Agent 工具治理 | `tool_registry.py`、`tool_workflow.py`、`gateway_mcp_adapter.py` | 工具 schema、白名单、只读 MCP adapter、执行统计和受控修复 |
| LangGraph 运行时 | `gateway_graph.py`、`gateway_chat_graph_routes.py` | 支持 run、interrupt、resume、checkpoint、step_events |
| 模型服务化 | `packages/python/shared/model_routing.py`、`model_health.py`、`semantic_cache.py` | 路由 fallback、健康熔断、语义缓存、成本估算 |
| 评测回归 | `tests/test_eval_pipeline.py`、`scripts/evaluation/*`、`.github/workflows/ci.yml` | 评测 fixture、检索消融、embedding benchmark、smoke eval 和 regression gate |

## 2. 可演示但需说明边界

| 能力 | 当前边界 | 推荐说法 |
|---|---|---|
| 在线 smoke eval | 依赖本地 Docker、PostgreSQL、MinIO、Qdrant 和服务启动 | “可以在本地栈跑端到端 smoke；没有 Docker 时先跑离线评测资产校验。” |
| 模型发现 | 手动调用 OpenAI-compatible `/models`，成功响应不保存 API Key | “这是配置辅助，不是生产密钥托管系统。” |
| 成本看板 | 支持本地估算和 provider billing 记录导入 | “当前不自动拉云厂商账单，生产对账应由外部结算任务导入。” |
| 人工接管 | 本地进程锁与条件更新适合测试环境 | “生产多实例建议换 Redis sorted set 或数据库 `SELECT ... FOR UPDATE SKIP LOCKED`。” |
| 语义缓存 | L1 精确缓存默认可用；L2 语义命中需显式开启并限定 scope | “能讲缓存机制和测试，不编造真实命中率收益。” |
| MCP adapter | 只暴露 `kb_scope_summary`、`workflow_trace_summary`、`tool_registry_stats` | “这是受控只读 adapter，不是任意工具执行平台。” |

## 3. 生产仍需补强

1. **真实业务数据集**：需要行业语料、人工标注 query、badcase 和线上反馈样本。
2. **容量与压测报告**：需要 P95/P99 延迟、并发、队列积压、Qdrant/PostgreSQL 资源占用。
3. **跨实例队列和锁**：人工接管、worker lease、任务恢复需要在多实例部署下验证。
4. **告警与仪表盘**：已有 `/metrics` 和 `metrics-summary`，还需要 Prometheus/Grafana 告警规则。
5. **密钥与租户隔离**：生产需密钥管理系统、租户隔离策略、审计留存和访问审批。
6. **成本对账闭环**：当前有估算和导入接口，生产需要供应商账单采集任务与异常对账。

## 4. 进阶岗位回答模板

### 你这个项目生产化了吗？

“我会分三层回答。第一层，工程链路已经比较完整：服务拆分、Docker Compose、RAG 检索融合、Agent 工具治理、模型路由、trace、评测和 CI 都有本地证据。第二层，它可以做本地端到端 smoke 和固定 fixture 回归，适合作为 AI 应用工程作品。第三层，我不会把它说成已经经历大规模生产流量，因为还缺真实业务数据集、压测、SLO、告警和多实例队列验证。”

### 如果线上模型不可用怎么办？

“模型调用侧有 route plan 和 `fallback_route_key`，本地调用遇到上游 5xx、不可用、非法响应或空回答时可以尝试备线路由；模型健康监控会记录失败和熔断。生产上还需要把错误预算、供应商状态、重试策略和告警联动起来。”

### 你如何证明不是 Demo？

“普通 Demo 通常只有单脚本检索或单页面聊天。这个项目有 Gateway、KB Service、Worker、前端控制台、对象存储、向量库、评测脚本、CI、Docker Compose 和 SDK；更重要的是回答有引用、拒答、trace 和回归门禁。它仍然不是已经证明过大流量的生产系统，但已经具备工程化闭环。”

## 5. 面试中不要越界

- 没有真实业务数据前，不说“准确率提升 X%”。
- 没有压测报告前，不说“支持 X 并发”。
- 没有供应商账单采集前，不说“成本下降 X%”。
- 没有生产部署记录前，不说“已稳定运行 X 个月”。
- 没有多实例验证前，不把本地接管队列说成生产级分布式队列。

