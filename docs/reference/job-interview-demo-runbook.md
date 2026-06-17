# 岗位面试演示运行手册

> 目标：把 RAG-QA 项目从“功能很多”收敛成面试中 10 分钟可讲、可跑、可验证的闭环。
> 适用岗位：AI 应用/RAG、AI Agent/智能体、Python/FastAPI 后端、AI 平台/模型服务化。

## 1. 演示主线

本演示只使用仓库已有能力，不额外引入平台或外部依赖。建议按下面顺序讲：

1. 知识入库：上传政策和差旅语料，触发 KB Service 解析、切分和索引。
2. 混合检索：展示结构信号、PostgreSQL FTS、Qdrant 向量召回、weighted RRF、rerank。
3. 可信回答：展示引用、`answer_mode`、`evidence_status`、`grounding_score`、`trace_id`。
4. 安全边界：展示证据不足时的 strict refusal，不强行生成答案。
5. Agent 多步：展示 agent 多知识库任务和 `step_events` / `llm_trace`。
6. 评测回归：用固定 fixture 校验 correctness、faithfulness、citation alignment、refusal precision / recall。

## 2. 轻量离线验证

不启动 Docker 时，先验证评测资产和回归脚本仍然可用：

```powershell
python scripts/evaluation/verify-agent-smoke-evidence.py
python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json
python scripts/evaluation/check-eval-regression.py --help
```

预期结果：

- `verify-agent-smoke-evidence.py` 生成 `artifacts/reports/agent_smoke_evidence_pack.json` 与 `.md`。
- `run-retrieval-ablation.py` 输出 `recall@1`、`recall@3`、`MRR`、`NDCG@3` 等检索指标。
- `check-eval-regression.py --help` 能展示回归门禁参数。

这组命令证明的是：仓库内置评测资产完整、检索消融脚本可运行、回归门禁入口存在。它不等同于在线服务已经启动。

## 3. 在线 smoke 演示

有 Docker 环境时，使用完整本地栈演示端到端流程：

```powershell
make init
make up
python scripts/dev/smoke_eval.py --password ChangeMe123! --wait-for-ready
```

等价 PowerShell 入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/smoke-eval.ps1
```

预期产物：

- `artifacts/reports/agent_smoke_report.json`
- `artifacts/reports/agent_smoke_report.md`
- `artifacts/reports/agent_smoke_regression_gate.json`
- `artifacts/reports/agent_smoke_regression_gate.md`

演示时重点讲三类 job：

| job | 面试价值 | 对应岗位能力 |
|---|---|---|
| `grounded_single` | 单知识库可信回答，引用对齐 | RAG、citation、faithfulness |
| `agent_multi` | 多知识库 Agent 任务 | Agent 编排、工具调用、step trace |
| `strict_refusal` | 无依据拒答 | 安全边界、幻觉控制、企业可信回答 |

## 4. 面试讲解口径

### AI 应用/RAG

“我不是只把文档塞进向量库，而是把入库、切分、结构/全文/向量召回、RRF 融合、rerank、引用、拒答和评测串成闭环。演示里的 `run-retrieval-ablation.py` 用固定 fixture 验证检索质量，在线 smoke eval 再验证 grounded / agent / refusal 三类回答。”

### AI Agent/智能体

“Agent 不是无限自治。这个项目里工具调用有 ToolRegistry、白名单、只读 MCP adapter 和 workflow mode；LangGraph runtime 支持 run、interrupt、resume 和 step events。面试演示时我会重点展示可观测和可恢复，而不是只说模型会自己规划。”

### Python/FastAPI 后端

“Gateway 和 KB Service 是两个 FastAPI 服务，前者负责聊天、模型接入、Agent 和治理，后者负责知识库、上传、解析和检索。统一异常、trace middleware、SSE、后台 worker、Docker Compose 和 pytest 都是后端工程能力证据。”

### AI 平台/模型服务化

“模型接入不是写死一个 API Key。项目里有 OpenAI-compatible 配置、模型发现、路由 fallback、模型健康熔断、语义缓存、TTFT 和成本估算。当前可证明的是本地工程能力和 fixture 闭环，不编造生产账单收益。”

## 5. 不宣称的内容

- 不宣称已经有真实线上 QPS、SLA、用户量或成本节省比例。
- 不宣称 MCP adapter 是完整插件市场；当前边界是本机只读 JSON-RPC adapter。
- 不宣称人工接管队列已经是跨实例生产队列；当前实现适合本地验证，生产建议 Redis sorted set 或数据库 `SKIP LOCKED`。
- 不把本项目包装成算法训练、RLHF 或底层推理优化项目。

## 6. 快速排障

| 现象 | 处理方式 |
|---|---|
| `docker` 命令不存在 | 先只跑轻量离线验证，并说明当前机器未安装或未暴露 Docker CLI |
| smoke eval 等待服务超时 | 查看 `docker compose ps` 和 `docker compose logs --no-color gateway kb-service kb-worker` |
| 回归门禁失败 | 打开 `agent_smoke_regression_gate.md`，确认是 correctness、faithfulness、citation alignment 还是 refusal 指标失败 |
| 检索指标下降 | 先跑 `run-retrieval-ablation.py`，再用 `/api/v1/kb/retrieve/debug` 检查候选和 rerank |

