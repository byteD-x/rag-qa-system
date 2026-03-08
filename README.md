# RAG-QA 2.0

这是一个面向 QA 场景的本地优先 RAG 系统，当前版本重点解决三件事：

- 统一 `KB + Novel` 会话问答，支持单库、多库、全库 scope
- 34MB 级 TXT 与企业文档的极速上传，走 `MinIO multipart` 分块直传
- 回答必须绑定知识库证据，证据不足时明确拒答
- 把检索质量、时延和 ingest 阶段耗时做成可量化、可回归的报告

## 当前架构

```text
apps/
  backend/
    gateway/        统一登录、统一 QA 会话、跨库检索编排
    novel-service/  小说上传、流式解析、检索、增强
    kb-service/     企业文档上传、分段、检索、增强
  web/              统一聊天页、上传页、文档详情页
packages/shared/    共享认证、SSE、对象存储、检索与 embedding 工具
infra/postgres/     pgvector + pg_trgm
scripts/evals/      长文上传与 RAG 评测脚本
```

## 关键能力

### 1. 统一 QA

- 主入口：`/workspace/chat`
- 接口入口：`/api/v1/chat/*`
- scope 支持：
  - `single`
  - `multi`
  - `all`
- corpus 统一编码：
  - `kb:<uuid>`
  - `novel:<uuid>`
- 回答固定返回：
  - `answer`
  - `answer_mode`
  - `evidence_status`
  - `grounding_score`
  - `citations[]`
  - `evidence_path[]`

### 2. 极速上传

- 浏览器按 `5 MiB/part` 直传对象存储
- 默认并发 `4` 个 part
- 支持续传：
  - 服务端保存 `upload_sessions / upload_parts`
  - 前端按文件指纹缓存 `upload_id`
  - 重新上传时只补传缺失 part
- 上传完成立即返回 `document_id + job_id`
- 解析、摘要、向量化由 worker 异步推进

### 3. 超长文本处理

- 小说 TXT 走 `mmap + 流式行扫描`
- 每 `10` 章批量刷库并更新 `query_ready_until_chapter`
- 企业文档按 section/chunk 分批落库
- `fast_index_ready` 后即可问答
- `hybrid_ready` 后摘要层向量可用
- `ready` 后叶子向量、摘要树和关系增强完成

## 检索策略

- 结构检索：章节 / scene / alias / event / section
- FTS：应用层 tokenizer 产出 `tsvector`
- Query rewrite：实体/章节聚焦 + 问句词裁剪 + 词项扩展
- 向量：`pgvector vector(512)` + HNSW
- 默认本地 baseline：`local-projection-512`
- 可选 benchmark baseline：外部 embedding provider
- Rerank：融合后追加轻量 lexical rerank
- 融合：加权 RRF
  - `structure = 1.3`
  - `fts = 1.0`
  - `vector = 0.9`

## 可观测性

- 网关、Novel、KB 全链路透传 `X-Trace-Id`
- 聊天返回补充：
  - `trace_id`
  - `retrieval`
  - `latency`
  - `cost`
- ingest worker 事件记录：
  - 阶段耗时
  - embedding cache hits / misses
- 可直接生成日报：
  - `python scripts/observability/rag-daily-report.py`

## 上传与状态

统一状态流：

- `pending_upload`
- `uploading`
- `uploaded`
- `parsing_fast`
- `fast_index_ready`
- `hybrid_ready`
- `ready`
- `failed`

## 运行

### 1. 初始化环境变量

```powershell
Copy-Item .env.example .env
```

### 2. 启动

```powershell
make up
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/up.ps1
```

### 3. 访问地址

- Web: `http://localhost:5173`
- Gateway: `http://localhost:8080`
- Novel Service: `http://localhost:8100`
- KB Service: `http://localhost:8200`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`

默认本地账号：

- `admin@local / ChangeMe123!`
- `member@local / ChangeMe123!`

## 主要接口

### 统一聊天

- `GET /api/v1/chat/corpora`
- `GET /api/v1/chat/corpora/{corpus_id}/documents`
- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{id}`
- `GET /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`

### 小说上传

- `POST /api/v1/novel/uploads`
- `GET /api/v1/novel/uploads/{upload_id}`
- `POST /api/v1/novel/uploads/{upload_id}/parts/presign`
- `POST /api/v1/novel/uploads/{upload_id}/complete`
- `GET /api/v1/novel/ingest-jobs/{job_id}`
- `POST /api/v1/novel/retrieve`

### 企业文档上传

- `POST /api/v1/kb/uploads`
- `GET /api/v1/kb/uploads/{upload_id}`
- `POST /api/v1/kb/uploads/{upload_id}/parts/presign`
- `POST /api/v1/kb/uploads/{upload_id}/complete`
- `GET /api/v1/kb/ingest-jobs/{job_id}`
- `POST /api/v1/kb/retrieve`

## 评测脚本

- `python scripts/evals/benchmark-long-ingest.py --service novel --corpus-id <library-id> --file <path> --password <pwd>`
- `python scripts/evals/benchmark-long-ingest.py --service kb --corpus-id <base-id> --file <path> --password <pwd>`
- `python scripts/evals/eval-long-rag.py --scope-mode single --corpus-id novel:<uuid> --password <pwd>`
- `python scripts/evals/run-eval-suite.py --password <pwd> --config tests/evals/suite.sample.json`
- `python scripts/evals/run-retrieval-ablation.py`
- `python scripts/evals/benchmark-local-ingest.py`

已提交报告：

- `docs/reports/retrieval_ablation_report.json`
- `docs/reports/retrieval_ablation_report.md`
- `docs/reports/local_ingest_benchmark.json`
- `docs/reports/local_ingest_benchmark.md`

## 验证

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/shared/python apps/backend/gateway apps/backend/novel-service apps/backend/kb-service
python -m pytest tests -q
python scripts/evals/run-retrieval-ablation.py
python scripts/evals/benchmark-local-ingest.py
docker compose config --quiet
```

## 文档

- [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md)
- [docs/dev-scripts.md](docs/dev-scripts.md)
- [docs/runbook.md](docs/runbook.md)
- [docs/reports](docs/reports)

## Pricing

- `cost.currency` defaults to `CNY`.
- `cost` uses `AI_PRICE_TIERS_JSON` first and falls back to flat `AI_INPUT_PRICE_PER_1K_TOKENS` / `AI_OUTPUT_PRICE_PER_1K_TOKENS`.
- The bundled sample tiers match DashScope `qwen3.5-plus` mainland pricing for `<=128K`, `<=256K`, and `<=1M` input token ranges.
