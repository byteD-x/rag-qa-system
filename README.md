# RAG-QA 2.0

面向企业知识库场景的本地化 RAG 问答系统。

当前仓库只保留一条业务主线：企业文档接入、异步 ingest、混合检索、证据化问答、评测与观测。项目不再维护独立的“纯大模型聊天”分支，也不再包含小说或泛内容检索逻辑。

## 项目定位

系统围绕企业 RAG-QA 的四段式业务边界组织：

1. 接入层：认证、会话管理、统一问答入口、成本与时延回传。
2. 知识处理层：上传、对象存储、文档解析、切段、索引构建、异步任务推进。
3. 检索编排层：结构检索、全文检索、向量检索、重写、融合、轻量 rerank、证据筛选。
4. 运维评测层：本地启动脚本、质量门禁、离线 benchmark、在线 eval、日志汇总。

默认最小运行闭环如下：

- `gateway`：统一登录、统一会话、证据化回答、跨库检索编排、成本估算。
- `kb-service`：知识库、文档上传、解析、索引、检索、ingest 状态管理。
- `kb-worker`：异步向量化、增强处理、任务收尾。
- `web`：统一控制台，承载登录、上传、问答和文档详情。
- `postgres + minio`：结构化数据、检索索引与对象存储基础设施。

`docker-compose.yml` 当前只保留企业 RAG-QA 所需的 5 个长期运行服务：

- `postgres`
- `minio`
- `kb-service`
- `kb-worker`
- `gateway`

## 仓库结构

| 路径 | 作用 |
| --- | --- |
| `apps/services/api-gateway/` | 网关服务；`src/app` 放 Python 源码，`database/migrations` 放迁移 |
| `apps/services/knowledge-base/` | 企业知识库服务；`src/app` 放 API / 解析 / 检索 / worker |
| `apps/web/` | Vue 3 企业 RAG 控制台 |
| `packages/python/shared/` | 跨服务共享 Python 包，如 `auth`、`storage`、`embeddings`、`eval_metrics` |
| `ops/docker/postgres/` | PostgreSQL 镜像与初始化脚本 |
| `ops/logging/` | 日志查看与导出辅助资源 |
| `scripts/dev/` | 一键启动、一键停止、前端托管与本地开发辅助脚本 |
| `scripts/evaluation/` | 在线评测、离线 ablation、embedding 对照、ingest benchmark |
| `scripts/observability/` | 日报与日志汇总 |
| `scripts/quality/` | 编码检查、CI 聚合校验 |
| `tests/fixtures/evals/` | 统一问答、拒答、检索 fixture |
| `datasets/demo/` | Demo 语料、评测样例与对抗样例 |
| `docs/reference/` | API 参考文档 |
| `docs/development/` | 开发脚本与本地工作流说明 |
| `docs/operations/` | Runbook 与排障说明 |
| `docs/reports/` | 需要长期留档的报告快照 |
| `artifacts/reports/` | 本地运行、测试与 CI 生成物 |
| `artifacts/evals/` | 评测动态配置与资产清单 |
| `data/` | 本地运行态数据 |
| `logs/` | 本地日志与前端托管状态 |

前端源码位于 `apps/web/src/`：

- `api/`：HTTP 请求封装
- `components/`：复用组件
- `layouts/`：页面壳层
- `router/`：前端路由
- `store/`：Pinia 状态
- `utils/`：纯工具函数
- `views/`：页面级视图

## 业务主线

### 1. 企业文档接入

- 浏览器按 `5 MiB / part` 直传对象存储。
- 服务端维护 `upload_sessions / upload_parts`，支持缺失 part 补传。
- 上传完成后立即返回 `document_id + job_id`。

### 2. 异步 ingest

- `kb-worker` 负责解析文档、抽取 section/chunk、向量化与增强处理。
- 文档状态按 `uploaded -> fast_index_ready -> hybrid_ready -> ready` 推进。
- `fast_index_ready` 后即可参与基础问答，`ready` 表示混合检索链完整可用。

### 3. 统一问答

- 前端主入口：`/workspace/chat`
- 问答接口入口：`/api/v1/chat/*`
- scope 支持：`single / multi / all`
- 统一 corpus 编码：`kb:<uuid>`

### 4. 混合检索与证据化回答

- 检索信号：结构检索、全文检索、向量检索。
- 重写策略：实体聚焦、问句裁剪、检索增强词扩展。
- 融合策略：加权 RRF + 轻量 lexical rerank。
- 回答约束：必须附带引文，证据不足时拒答或保守回答。

### 5. 观测与评测

- 网关透传 `X-Trace-Id`。
- 聊天响应返回 `trace_id`、`retrieval`、`latency`、`cost`。
- 仓库内保留离线检索对照、本地 ingest benchmark、在线 eval suite。

## 服务边界

### Gateway

`apps/services/api-gateway/` 负责：

- JWT 登录与本地账号鉴权
- 会话与消息持久化
- 调用 `kb-service` 检索并组织证据化回答
- LLM 答案生成、token 用量与成本估算

关键环境变量：

- `GATEWAY_DATABASE_DSN`
- `KB_SERVICE_URL`
- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_PRICE_CURRENCY`
- `LLM_PRICE_TIERS_JSON`

兼容说明：

- 历史 `AI_*` 变量仍可读取，但已降级为兼容别名。
- 新增配置请统一使用 `LLM_*` 命名。

### Knowledge Base

`apps/services/knowledge-base/` 负责：

- 上传会话创建、分片直传预签名、完成确认
- 文档解析、切段、索引、检索
- ingest 状态推进与文档详情查询

核心代码分层：

- `src/app/main.py`：服务入口
- `src/app/parsing.py`：文档解析
- `src/app/retrieve.py`：检索与引文构造
- `src/app/query.py`：查询协议
- `src/app/worker.py`：异步 ingest worker
- `database/migrations/`：知识库迁移

### Web

`apps/web/` 负责：

- 登录与权限展示
- 企业知识库上传、统一问答、文档详情

主要路由：

| 路由 | 说明 |
| --- | --- |
| `/login` | 登录页 |
| `/workspace/entry` | 业务入口页 |
| `/workspace/chat` | 统一企业问答 |
| `/workspace/kb/upload` | 文档上传 |
| `/workspace/kb/chat` | 知识库问答入口 |
| `/workspace/kb/documents/:id` | 文档详情 |

## 运行

### 1. 初始化

```powershell
Copy-Item .env.example .env
```

### 2. 一键启动

```powershell
make up
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/up.ps1
```

### 3. 一键停止

```powershell
make down
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/down.ps1 -Force
```

### 4. 访问地址

- Web：`http://localhost:5173`
- Gateway：`http://localhost:8080`
- KB Service：`http://localhost:8300`
- MinIO API：`http://localhost:9000`
- MinIO Console：`http://localhost:9001`

默认本地账号：

- `admin@local / ChangeMe123!`
- `member@local / ChangeMe123!`

## 常用命令

```powershell
.\logs.bat -s gateway kb-service
.\logs.bat -l ERROR -s gateway kb-service
python -m pytest tests -q
python scripts/evaluation/run-retrieval-ablation.py
python scripts/evaluation/benchmark-local-ingest.py
python scripts/evaluation/compare-embedding-providers.py
python scripts/evaluation/run-demo-eval-suite.py --password <pwd>
```

## 测试、语料与报告

### 测试

`tests/` 当前覆盖：

- shared 基础能力
- 统一评测指标
- 网关成本估算
- 评测脚本 smoke

### 评测资产

`tests/fixtures/evals/` 当前包含：

- `kb-smoke-eval.json`
- `adversarial-refusal-eval.json`
- `retrieval-ablation-fixture.json`
- `suite.sample.json`

### Demo 数据

`datasets/demo/` 当前包含：

- `documents/`：demo 企业文档
- `evaluation/`：在线 eval 问题集
- `adversarial/`：拒答与异常输入样例

### 报告目录约定

- `artifacts/reports/`：脚本、测试和 CI 默认输出位置
- `artifacts/evals/`：临时 config 与 asset manifest
- `docs/reports/`：筛选后需要留档的快照

## 验证

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
python scripts/evaluation/run-retrieval-ablation.py
python scripts/evaluation/benchmark-local-ingest.py
python scripts/evaluation/compare-embedding-providers.py
docker compose config --quiet
```

## 进一步文档

- [docs/reference/api-specification.md](docs/reference/api-specification.md)
- [docs/development/dev-scripts.md](docs/development/dev-scripts.md)
- [docs/operations/runbook.md](docs/operations/runbook.md)
