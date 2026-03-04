# RAG-QA System

[![Go](https://img.shields.io/badge/Go-1.25+-00ADD8?logo=go&logoColor=white)](https://go.dev/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5+-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

**企业级 RAG（检索增强生成）问答系统** - 基于私有知识库提供准确、可溯源的智能问答服务。

上传您的文档（PDF/DOCX/TXT），系统会自动构建向量索引。当用户提问时，通过语义检索定位相关段落，结合大语言模型生成带引用的准确回答。

---

## ✨ 核心特性

### 📁 智能文档管理

- **多格式支持**：自动解析 PDF、DOCX、TXT 等常见文档格式
- **双阶段上传**：采用预签名 URL 机制，支持最大 500MB 大文件上传，降低失败成本
- **在线预览与编辑**：TXT 文档可直接查看和编辑，PDF/DOCX 提供临时预览链接
- **批量操作**：支持知识库和文档的批量删除（最大 100 个/次）
- **自动索引**：文档上传后自动解析、切分、向量化并构建索引

### 🔍 检索与问答

- **语义检索**：基于 Qdrant 向量数据库，支持 Top-N=24 的语义相似度检索
- **混合重排序**：结合向量分数和词汇匹配分数双重排序，保留 Top-K=8 最相关结果
- **引用溯源**：每个回答句子都标注来源引用（文件名、页码、片段），支持点击跳转
- **作用域灵活控制**：
  - 单知识库检索模式（`single`）
  - 跨知识库联合检索模式（`multi`）
  - 支持精确到文档级别的检索范围控制

### 🏢 企业级特性

- **权限管理**：基于 JWT 的身份验证，支持 admin/member 角色划分
- **异步处理架构**：文档入库任务进入 Redis 队列，由 Worker 异步处理（解析→切分→向量化→入库）
- **质量保障**：
  - 证据最小相关性分数约束（默认 0.05）
  - 常识补充最大比例限制（默认 15%）
  - 回答句子必须基于证据或明确标注为常识
- **会话管理**：支持多会话并行，每个会话关联特定知识库集合

### 🛡️ 高可用设计

- **降级策略**：RAG 服务异常时返回可识别的降级结果
- **错误处理**：完善的错误码体系和重试机制（最大重试 2 次）
- **健康检查**：各组件独立健康检查端点（`/healthz`）
- **超时控制**：请求超时 30 秒，LLM 调用超时 30 秒

---

## 🏗️ 系统架构

### 组件架构

```
┌─────────────────┐
│   Client        │
│   (Browser)     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         go-api (Port 8080)          │
│  - REST API Gateway (Chi)           │
│  - JWT Authentication               │
│  - Business Orchestration           │
│  - S3 Pre-signed URL Generation     │
└─┬──────────┬──────────────┬────────┘
  │          │              │
  ▼          ▼              ▼
┌────────────┴──────┐  ┌─────────────────┐
│   PostgreSQL      │  │   MinIO/S3      │
│   (Metadata)      │  │   (Raw Files)   │
│   - Corpora       │  │   - Raw Documents│
│   - Documents     │  └─────────────────┘
│   - Sessions      │
│   - Jobs          │
│   - Users         │
└───────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      py-rag-service (Port 8000)     │
│  - Vector Retrieval (Qdrant)        │
│  - Hybrid Reranking                 │
│  - LLM Answer Generation            │
│  - Evidence Contract Validation     │
└─────────────────────────────────────┘
         ▲
         │
┌────────┴─────────┐
│   Redis Queue    │
│   (Ingest Jobs)  │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         py-worker                   │
│  - Document Parsing (PDF/DOCX/TXT)  │
│  - Text Chunking                    │
│  - Embedding Generation             │
│  - Vector Upsert (Qdrant)           │
└─────────────────────────────────────┘
         ▲
         │
┌────────┴─────────┐
│   Qdrant         │
│   (Vector DB)    │
│   - rag_chunks   │
└──────────────────┘
```

### 数据流

#### 文档上传流程

1. 客户端申请上传 URL
2. 生成预签名 URL 并返回
3. 客户端直接上传文件到对象存储（MinIO/S3）
4. 确认入库，创建数据库记录
5. 推送任务到 Redis 队列
6. Worker 异步处理：解析 → 切分 → 向量化 → 写入 Qdrant

#### 问答流程

1. 客户端发送问题（带作用域配置）
2. RAG 服务执行向量检索（Top-N=24）
3. 混合重排序（Top-K=8）
4. 调用 LLM 生成带证据的摘要
5. 构建结构化回答（句子 + 引用）
6. 返回给客户端

---

## 📦 安装部署

### 前置要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Docker Desktop | 20+ | 包含 Docker Compose |
| Node.js | 18+ | 前端开发服务（可选） |
| PowerShell | 5.1+ | Windows 脚本执行 |
| Git | Latest | 代码克隆 |

### 快速部署

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/rag-qa-system.git
cd rag-qa-system

# 2. 配置环境变量
cp .env.example .env

# 3. 编辑 .env 文件，配置 LLM API Key

# 4. 一键启动
powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1

# 5. 访问前端
# 浏览器打开 http://localhost:5173
```

默认登录账号：
- **管理员**: `admin@local` / `ChangeMe123!`
- **普通用户**: `member@local` / `ChangeMe123!`

---

## 📁 项目结构

```
rag-qa-system/
├── go-api/                 # Go API 网关（Chi + GORM）
│   ├── cmd/server/         # 应用入口
│   ├── internal/
│   │   ├── api/            # HTTP 处理器
│   │   ├── auth/           # JWT 认证
│   │   ├── config/         # 配置加载
│   │   ├── db/             # 数据库访问
│   │   ├── queue/          # Redis 队列
│   │   └── storage/        # S3 客户端
│   └── Dockerfile
│
├── py-rag-service/         # Python RAG 服务（FastAPI）
│   ├── app/
│   │   └── main.py         # 主服务
│   ├── tests/              # 单元测试
│   └── Dockerfile
│
├── py-worker/              # Python 异步任务处理器
│   ├── worker/
│   │   ├── main.py         # Worker 入口
│   │   ├── processor.py    # 文档处理器
│   │   ├── parser.py       # PDF/DOCX 解析
│   │   ├── chunking.py     # 文本切分
│   │   ├── embedding.py    # 向量化
│   │   ├── qdrant_indexer.py  # Qdrant 写入
│   │   ├── storage.py      # S3 读取
│   │   ├── db.py           # 数据库访问
│   │   └── config.py       # 配置
│   ├── tests/              # 单元测试
│   └── Dockerfile
│
├── frontend/               # Vue 3 前端（Vite + TypeScript）
│   ├── src/
│   │   ├── api/            # API 客户端
│   │   ├── components/     # Vue 组件
│   │   ├── views/          # 页面视图
│   │   ├── store/          # 状态管理（Pinia）
│   │   └── router/         # 路由配置
│   ├── package.json
│   └── vite.config.ts
│
├── infra/
│   └── postgres/
│       └── init/           # 数据库初始化脚本
│           ├── 001_schema.sql
│           └── 002_phase2_ingest.sql
│
├── scripts/
│   ├── dev-up.ps1          # 启动脚本
│   ├── dev-down.ps1        # 停止脚本
│   └── check_encoding.py   # 编码检查
│
├── docker-compose.yml      # Docker 编排配置
├── .env.example            # 环境变量模板
└── AGENTS.md               # AI 协作规范
```

---

## 🔧 技术选型

### 为什么选择 Go 作为 API 网关？

**核心考量**：高性能、并发处理、类型安全

- **Chi 路由器**：轻量级、高性能的 HTTP 路由器，支持中间件链
- **GORM**：强大的 ORM 库，简化数据库操作
- **原生并发**：Goroutine 处理高并发请求，资源占用低
- **编译型语言**：类型安全，减少运行时错误
- **部署简单**：单一二进制文件，无运行时依赖

**替代方案对比**：
- Python (FastAPI)：开发效率高，但并发性能不如 Go
- Node.js：异步 IO 优秀，但类型系统较弱（需 TypeScript 补充）
- Java (Spring)：功能全面，但启动慢、内存占用高

### 为什么选择 Python 作为 RAG 服务？

**核心考量**：AI 生态、快速迭代、丰富的库支持

- **FastAPI**：现代 Python Web 框架，自动 OpenAPI 文档，高性能
- **AI 生态**：LangChain、LlamaIndex 等库的原生支持
- **文档处理**：pypdf、python-docx 等成熟的解析库
- **向量处理**：NumPy、SciPy 等科学计算库
- **快速原型**：适合算法实验和快速迭代

**替代方案对比**：
- Go：性能好但 AI 生态薄弱
- Java：企业级但开发效率低
- Rust：性能极佳但学习曲线陡峭

### 为什么选择 Vue 3 作为前端框架？

**核心考量**：渐进式、易上手、性能优秀

- **组合式 API**：更好的代码组织和类型推断
- **响应式系统**：基于 Proxy 的响应式，性能优于 Vue 2
- **TypeScript 支持**：一流的类型支持
- **Element Plus**：丰富的企业级 UI 组件库
- **Vite 构建**：极速的开发服务器启动和热更新

**替代方案对比**：
- React：生态更大但学习曲线陡峭
- Angular：功能全面但过于重量级
- Svelte：轻量但生态较小

### 为什么选择这些基础设施？

#### PostgreSQL（关系型数据库）

**选型原因**：
- **JSONB 支持**：同时支持关系型和文档型数据
- **ACID 事务**：保证数据一致性
- **扩展性**：支持自定义类型和索引
- **成熟稳定**：20+ 年开发历史，社区活跃

**替代方案**：MySQL（功能较少）、MongoDB（事务支持弱）

#### Redis（缓存与队列）

**选型原因**：
- **高性能**：内存存储，微秒级访问
- **数据结构丰富**：List、Set、Hash 等
- **持久化**：RDB 和 AOF 两种持久化方式
- **发布订阅**：支持消息队列模式

**替代方案**：RabbitMQ（功能重）、Kafka（过于重量级）

#### Qdrant（向量数据库）

**选型原因**：
- **高性能**：Rust 编写，支持 HNSW 索引
- **过滤查询**：支持向量 + 标量混合查询
- **易于部署**：Docker 一键启动
- **开源免费**：无商业许可限制

**替代方案**：
- Milvus：功能更多但部署复杂
- Pinecone：托管服务但有成本
- Weaviate：功能类似但性能略低

#### MinIO（对象存储）

**选型原因**：
- **S3 兼容**：无缝对接 AWS S3
- **高性能**：针对云原生优化
- **易于部署**：Docker 一键启动
- **开源免费**：AGPL 许可证

**替代方案**：AWS S3（有成本）、Ceph（过于复杂）

---

## ⚙️ 核心配置

### LLM 配置（必须）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai` | LLM 提供商：`qwen`, `deepseek`, `moonshot`, `zhipu`, `openai`, `ollama`, `custom` |
| `LLM_BASE_URL` | - | 自定义 API 地址 |
| `LLM_API_KEY` | - | **必须配置** - API 密钥 |
| `LLM_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型名称 |
| `LLM_CHAT_MODEL` | `gpt-4o-mini` | 对话模型名称 |

**常用提供商预设 URL**：
- `qwen`: https://dashscope.aliyuncs.com/compatible-mode/v1
- `deepseek`: https://api.deepseek.com/v1
- `openai`: https://api.openai.com/v1
- `zhipu`: https://open.bigmodel.cn/api/paas/v4

### RAG 服务配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant 向量库地址 |
| `QDRANT_COLLECTION` | `rag_chunks` | Qdrant 集合名称 |
| `EMBEDDING_DIM` | `256` | 嵌入向量维度 |
| `RAG_RETRIEVAL_TOP_N` | `24` | 检索返回数量 |
| `RAG_RERANK_TOP_K` | `8` | 重排序保留数量 |
| `RAG_EVIDENCE_MIN_SCORE` | `0.05` | 证据最小相关性分数 |
| `RAG_COMMON_KNOWLEDGE_MAX_RATIO` | `0.15` | 常识补充最大比例 |

---

## 🛠️ 开发指南

### 本地开发

#### 1. 启动基础服务

```bash
docker compose up -d postgres redis qdrant minio
```

#### 2. 开发 Go API

```bash
cd go-api
go mod download
go run cmd/server/main.go
go test ./... -v
```

#### 3. 开发 RAG 服务

```bash
cd py-rag-service
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
python -m pytest -v
```

#### 4. 开发 Worker

```bash
cd py-worker
pip install -r requirements.txt
python -m worker.main
```

#### 5. 开发前端

```bash
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
# Go 测试
cd go-api && go test ./... -v

# Python 测试
cd py-rag-service && python -m pytest -v
cd py-worker && python -m pytest -v

# 编码检查
python scripts/check_encoding.py

# Docker 配置检查
docker compose config
```

---

## ❓ 常见问题

### 1. 文档上传后任务卡在 queued

**排查步骤**：
```bash
# 检查 worker 日志
docker compose logs py-worker

# 检查 Redis 队列
docker compose exec redis redis-cli
> LLEN ingest_queue
```

**解决方案**：
- 确保 py-worker 容器正常运行
- 检查 Redis 连接配置
- 重启 worker：`docker compose restart py-worker`

### 2. 问答返回无引用

**可能原因**：
- 文档尚未完成入库（状态不是 `done`）
- 向量检索未返回结果

**排查步骤**：
```bash
# 检查文档状态
curl http://localhost:8080/v1/documents/{doc_id}

# 检查 RAG 服务日志
docker compose logs py-rag-service
```

### 3. LLM 调用失败

**解决方案**：
- 确认 `.env` 中 `LLM_API_KEY` 已正确配置
- 检查 `LLM_PROVIDER` 和 `LLM_BASE_URL` 匹配
- 验证网络连接和防火墙规则

---

## 🤝 贡献指南

### 开发流程

1. **Fork 仓库**
   ```bash
   git clone https://github.com/your-username/rag-qa-system.git
   ```

2. **创建特性分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **提交代码**（遵循 Conventional Commits）
   ```bash
   git commit -m "feat: add batch delete API"
   ```

4. **运行测试**
   ```bash
   # 所有测试
   cd go-api && go test ./...
   cd ../py-rag-service && python -m pytest -q
   cd ../py-worker && python -m pytest -q
   ```

### 代码审查清单

- [ ] 代码符合项目风格规范
- [ ] 新增功能包含测试
- [ ] 文档已同步更新
- [ ] 无敏感信息泄露（密钥、密码等）
- [ ] 性能影响已评估
- [ ] 向后兼容性已考虑
- [ ] 错误处理完善

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE) - 详见 LICENSE 文件。

### 主要依赖

#### Go (go-api)
- [chi/v5](https://github.com/go-chi/chi) - HTTP 路由器
- [pgx/v5](https://github.com/jackc/pgx) - PostgreSQL 驱动
- [minio-go/v7](https://github.com/minio/minio-go) - S3 客户端
- [go-redis/v9](https://github.com/redis/go-redis) - Redis 客户端

#### Python (py-rag-service, py-worker)
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [pydantic](https://docs.pydantic.dev/) - 数据验证
- [qdrant-client](https://qdrant.tech/) - 向量数据库客户端
- [pypdf](https://pypdf.readthedocs.io/) - PDF 解析
- [python-docx](https://python-docx.readthedocs.io/) - DOCX 解析

#### Frontend
- [Vue 3](https://vuejs.org/) - 前端框架
- [Vite](https://vitejs.dev/) - 构建工具
- [TypeScript](https://www.typescriptlang.org/) - 类型系统
- [Element Plus](https://element-plus.org/) - UI 组件库

#### Infrastructure
- [PostgreSQL 16](https://www.postgresql.org/) - 关系型数据库
- [Redis 7](https://redis.io/) - 缓存与队列
- [Qdrant](https://qdrant.tech/) - 向量数据库
- [MinIO](https://min.io/) - 对象存储

---

## 📬 支持与反馈

### 获取帮助

- 📖 [完整文档](docs/)
- 🐛 [问题追踪](https://github.com/your-org/rag-qa-system/issues)
- 💬 [讨论区](https://github.com/your-org/rag-qa-system/discussions)

### 报告问题

提交 issue 时请包含：
1. **问题描述**：清晰简洁的问题说明
2. **复现步骤**：详细步骤让我们能够复现问题
3. **环境信息**：OS、Docker 版本等
4. **相关日志**：`docker compose logs` 输出
5. **预期行为**：你期望发生什么
6. **实际行为**：实际发生了什么

---

**最后更新**: 2024-03-04

**维护者**: RAG-QA Team
