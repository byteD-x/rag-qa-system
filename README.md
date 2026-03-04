# RAG-QA System

企业知识库问答后端示例工程，覆盖从文档上传、入库索引到带引用回答的完整链路。

## 目录
- [项目简介](#项目简介)
- [系统架构](#系统架构)
- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [接口总览](#接口总览)
- [典型调用流程](#典型调用流程)
- [配置说明](#配置说明)
- [测试与校验](#测试与校验)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [贡献规范](#贡献规范)

## 项目简介
本项目用于构建一个可本地运行的 RAG（Retrieval-Augmented Generation）问答后端，主要组件如下：

- `go-api`：API 网关与业务编排（鉴权、语料管理、会话接口、上传流程）
- `py-worker`：异步入库任务执行器（解析、切分、向量化、写入向量库）
- `py-rag-service`：检索与重排服务（返回回答句与引用信息）
- `PostgreSQL / Redis / Qdrant / MinIO`：元数据、队列、向量索引、对象存储

适用场景：
- 需要验证 RAG 文档问答链路的团队内 PoC
- 需要前后端联调上传与引用型回答的项目

不适用场景：
- 直接用于生产环境（默认配置为开发用途）

## 系统架构
```text
Client / Frontend
      |
      v
go-api (REST + Auth + Scope Validation)
  |            |                 |
  |            |                 +--> Redis (ingest queue)
  |            |
  |            +--> MinIO/S3 (raw files)
  |
  +--> PostgreSQL (metadata, sessions, jobs)
  |
  +--> py-rag-service (retrieve/rerank/answer)
                 |
                 +--> Qdrant (vector search)

Redis queue consumer:
py-worker (parse -> chunk -> embed -> upsert Qdrant)
```

## 核心能力
- 双阶段上传：先申请预签名地址，再确认入库，降低大文件上传失败成本
- 入库异步化：上传确认后进入队列，由 `py-worker` 异步处理
- 作用域问答：`scope.mode` 支持 `single` / `multi`，可限制语料与文档范围
- 引用化回答：返回 `answer_sentences + citations`，可直接渲染引用卡片
- 删除闭环：支持知识库单删/批删，并同步清理 MinIO 原始文件与 Qdrant 向量点
- 合同校验：对回答结构、引用一致性、常识补充比例进行约束
- 基础容错：RAG 服务异常时仍返回可识别的降级结果

## 快速开始

### 1. 前置条件
- Docker Desktop（需包含 Docker Compose）
- Windows PowerShell
- Node.js 18+（用于启动前端开发服务）

### 2. 一键启动（推荐）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1
```

脚本会自动完成：
- 检查 Docker CLI 与守护进程
- 若缺失 `.env`，从 `.env.example` 复制
- `docker compose up -d --build`
- 启动前端开发服务（`frontend` / Vite，默认端口 `5173`）
- 健康检查：`go-api`、`py-rag-service` 与 `frontend`

### 3. 手动启动（可选）
```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

### 4. 健康检查
```powershell
Invoke-WebRequest http://localhost:8080/healthz
Invoke-WebRequest http://localhost:8000/healthz
Invoke-WebRequest http://localhost:5173
```

### 5. 停止服务
```powershell
docker compose down
```

## 接口总览

基础地址：`http://localhost:8080/v1`

| 模块 | 方法 | 路径 |
|---|---|---|
| 健康检查 | `GET` | `/healthz`（网关根路径） |
| 登录 | `POST` | `/auth/login` |
| 创建语料库 | `POST` | `/corpora` |
| 查询语料库 | `GET` | `/corpora` |
| 删除语料库 | `DELETE` | `/corpora/{corpus_id}` |
| 批量删除语料库 | `POST` | `/corpora/batch-delete` |
| 查询语料库文档 | `GET` | `/corpora/{corpus_id}/documents` |
| 查询文档详情 | `GET` | `/documents/{document_id}` |
| 在线查看文档 | `GET` | `/documents/{document_id}/preview` |
| 在线修改文档（仅 txt） | `PUT` | `/documents/{document_id}/content` |
| 申请上传 URL | `POST` | `/documents/upload-url` |
| 确认文档入库 | `POST` | `/documents/upload` |
| 查询入库任务 | `GET` | `/ingest-jobs/{job_id}` |
| 创建会话 | `POST` | `/chat/sessions` |
| 查询会话列表 | `GET` | `/chat/sessions` |
| 发送问题 | `POST` | `/chat/sessions/{session_id}/messages` |

## 典型调用流程

1. 登录获取 `Bearer token`
2. 创建语料库（管理员）
3. 申请上传 URL（返回 `upload_url` 与 `storage_key`）
4. 客户端直传文件到对象存储（HTTP PUT）
5. 调用 `/documents/upload` 完成入库登记并入队
6. 轮询任务状态直到 `done`
7. 创建会话并发送问题（携带 `scope`）
8. 渲染 `answer_sentences`，按 `citation_ids` 映射 `citations`

### 文档详情/在线查看/在线修改

- 文档详情：`GET /documents/{document_id}`
- 在线查看：
  - `txt` 返回 `preview_mode=text` 与文本内容（`max_inline_bytes=1048576`）
  - `pdf/docx` 返回 `preview_mode=url` 与临时预览链接（有时效）
- 在线修改（仅 `txt`）：`PUT /documents/{document_id}/content`
  - 请求体：`{"content":"..."}`
  - 保存后会自动创建新的入库任务并重建索引

### 问答请求体示例
```json
{
  "question": "请总结该文档中的关键结论",
  "scope": {
    "mode": "single",
    "corpus_ids": ["<corpus_uuid>"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

### 回答字段说明
- `answer_sentences[]`：主答案句列表
- `evidence_type=source`：句子必须关联 `citation_ids`
- `evidence_type=common_knowledge`：句子不包含引用，表示非文档证据
- `citations[]`：引用详情（`file_name/page_or_loc/chunk_id/snippet`）

## 配置说明

配置文件：`.env`（本地开发请从 `.env.example` 复制）

建议重点关注以下变量（按类别）：
- API：`HTTP_ADDR`、`MAX_UPLOAD_BYTES`、`AUTH_TOKEN_TTL_MINUTES`
- 数据源：`POSTGRES_*`、`REDIS_URL`
- 对象存储：`S3_*`、`MINIO_*`
- RAG：`QDRANT_*`、`RAG_RETRIEVAL_TOP_N`、`RAG_RERANK_TOP_K`
- 证据约束：`RAG_EVIDENCE_MIN_SCORE`、`RAG_COMMON_KNOWLEDGE_MAX_RATIO`
- Worker：`WORKER_POLL_INTERVAL_SECONDS`、`WORKER_MAX_RETRIES`

安全建议：
- 不要提交 `.env`
- 不要在日志或截图中暴露密钥、口令、连接串

## 测试与校验
在仓库根目录执行：

```powershell
python scripts/check_encoding.py
cd go-api; go test ./...
cd ../py-rag-service; python -m pytest -q
cd ../py-worker; python -m pytest -q
cd ..; docker compose config
```

若需要一键测试：
```powershell
make test
```

## 项目结构
```text
.
|-- go-api/                # 网关与业务接口（Go）
|-- py-rag-service/        # 检索/重排/回答服务（Python）
|-- py-worker/             # 入库异步处理（Python）
|-- infra/postgres/init/   # PostgreSQL 初始化脚本
|-- docs/                  # 说明文档与联调清单
|-- scripts/               # 启停与校验脚本
|-- docker-compose.yml
|-- AGENTS.md              # AI 协作规范
`-- README.md
```

## 常见问题

1. `healthz` 不通  
检查 Docker Desktop 是否启动，执行 `docker compose ps` 查看容器状态。

2. 上传后任务卡在 `queued`  
检查 `py-worker` 日志与 Redis 连通性。

3. 问答返回无引用  
确认任务状态为 `done`，并检查 `scope` 是否选中了已就绪文档。

## 贡献规范
- 提交信息采用 Conventional Commits（如 `feat: ...`、`fix: ...`）
- 单次提交只做一类变更，避免“功能 + 大改格式”混合
- 改动 API / 配置 / 使用方式时，需同步更新文档
