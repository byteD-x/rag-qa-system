# RAG-QA System

[![Go](https://img.shields.io/badge/Go-1.25+-00ADD8?logo=go&logoColor=white)](https://go.dev/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

面向私有知识库的 RAG 问答平台，提供文档上传、异步解析、向量检索、证据化回答和管理后台。仓库采用 monorepo 结构，包含 Web 控制台、Go API 网关、Python RAG 服务和 Python 文档处理 Worker。

## 目录

- [项目概览](#项目概览)
- [技术栈](#技术栈)
- [系统组成](#系统组成)
- [快速开始](#快速开始)
- [仓库结构](#仓库结构)
- [开发与验证](#开发与验证)
- [文档](#文档)
- [说明](#说明)

## 项目概览

### 核心能力

- 文档上传后自动完成解析、切分、向量化与索引写入。
- 问答链路支持混合检索、重排、SSE 流式输出与引用溯源。
- API 网关提供 JWT 鉴权、对象存储预签名上传和业务编排。
- Worker 通过 Redis 异步消费任务，和在线问答链路解耦。
- 本地开发通过 Docker Compose 与 PowerShell 脚本一键启动。

### 适用场景

- 内部知识库问答
- 产品/运维文档检索
- 私有文件归档后的 RAG 接入
- 需要证据约束与引用溯源的问答系统

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3, TypeScript, Vite, Element Plus |
| API 网关 | Go, Chi, pgx, MinIO SDK, Redis |
| RAG 服务 | FastAPI, httpx, Qdrant Client, BM25 |
| 异步处理 | Python Worker, Redis, Qdrant |
| 基础设施 | Docker Compose, PostgreSQL, Redis, Qdrant, MinIO, Nginx |

## 系统组成

| 组件 | 路径 | 说明 | 默认端口 |
| --- | --- | --- | --- |
| Web Console | `apps/web` | Vue 3 + TypeScript 管理后台与问答前端 | `5173` |
| API Gateway | `services/go-api` | Go REST API、JWT、上传编排、业务聚合 | `8080` |
| RAG Service | `services/py-rag-service` | FastAPI 检索、重排、答案生成与证据约束 | `8000` |
| Ingest Worker | `services/py-worker` | 文档解析、切分、嵌入生成、Qdrant 写入 | - |
| Infrastructure | `infra` | PostgreSQL 初始化、Nginx、日志工具等 | `80` / `19000` / `19001` |

## 快速开始

### 前置要求

| 依赖 | 建议版本 |
| --- | --- |
| Docker Desktop | 24+ |
| Docker Compose | v2 |
| Node.js | 18+ |
| Python | 3.9+ |
| Go | 1.25+ |
| PowerShell | 5.1+ |

### 1. 配置环境变量

```bash
cp .env.example .env
```

在 PowerShell 中可使用：

```powershell
Copy-Item .env.example .env
```

至少补齐以下配置：

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_CHAT_MODEL`
- `LLM_EMBEDDING_MODEL`

### 2. 启动本地环境

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-up.ps1
```

启动完成后可访问：

- Web: `http://localhost:5173`
- API: `http://localhost:8080`
- RAG Health: `http://localhost:8000/healthz`
- MinIO API: `http://localhost:19000`
- MinIO Console: `http://localhost:19001`

### 3. 停止环境

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-down.ps1 -Force
```

## 仓库结构

```text
rag-qa-system/
  apps/
    web/
  services/
    go-api/
    py-rag-service/
    py-worker/
  docs/
  infra/
  scripts/
  tests/
  docker-compose.yml
  Makefile
```

## 开发与验证

### 常用命令

```powershell
make up
make down
make test
.\logs.bat -f
.\scripts\aggregate-logs.ps1
python scripts/check_encoding.py
docker compose config --quiet
```

### 开发脚本

```powershell
.\scripts\dev-up.ps1
.\scripts\dev-up.ps1 -NoBuild
.\scripts\dev-up.ps1 -SkipFrontend
.\scripts\dev-up.ps1 -AttachLogs
.\scripts\dev-down.ps1 -Force
.\scripts\aggregate-logs.ps1 -Tail 2000
```

- `scripts/dev-up.ps1` 启动 Docker Compose 服务，并托管前端开发进程。
- `-NoBuild` 跳过镜像重建，适合重复启动。
- `-SkipFrontend` 只启动后端与基础设施，不启动前端开发服务。
- `-AttachLogs` 启动完成后直接进入实时日志跟随模式。
- `scripts/dev-down.ps1 -Force` 关闭 Compose 服务并结束托管前端进程。
- `scripts/aggregate-logs.ps1` 导出当前日志快照到 `logs/export/`。

### 日志查看

```powershell
.\logs.bat
.\logs.bat -f
.\logs.bat -s go-api py-rag-service
.\logs.bat -s frontend -f
.\logs.bat -l ERROR
.\logs.bat --stats
```

- `.\logs.bat` 查看最近日志。
- `.\logs.bat -f` 跟随 Docker 服务日志和托管前端日志。
- `-s` 可以按服务过滤；`frontend` 表示脚本托管的 Vite 日志。
- `-l ERROR` 只看错误级别日志。
- `--stats` 输出最近日志的服务分布和级别分布。

### 单独调试前端

```powershell
cd apps/web
npm install
npm run dev
npm run build
```

### 基线验证

```powershell
python scripts/check_encoding.py
cd services/go-api; go test ./...
cd ../py-rag-service; python -m pytest -q
cd ../py-worker; python -m pytest -q
cd ../../apps/web; npm run build
cd ../..; docker compose config --quiet
```

预期结果：

- 编码检查通过
- Go / Python 测试通过
- 前端构建成功
- Compose 配置校验通过且无路径错误

## 文档

- API 说明：[docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md)
- OpenAPI 定义：[docs/openapi.yaml](docs/openapi.yaml)
- 开发脚本：[docs/dev-scripts.md](docs/dev-scripts.md)
- 检索优化：[docs/optimization.md](docs/optimization.md)

## 说明

- `scripts/dev-up.ps1` 会托管前端开发进程，并把 PID 与日志写入 `logs/dev/`。
- 本地开发账号定义在 `.env.example`，仅适用于开发环境，非本地环境请替换。
- 根目录 `docker-compose.yml` 仍然是统一编排入口；本次重构只调整仓库布局，不改变服务名与接口协议。
