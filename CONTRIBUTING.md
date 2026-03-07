# 贡献指南

感谢你为 `RAG-QA 2.0` 贡献改动。

## 当前工程结构

- `apps/backend/gateway`：统一认证与路由聚合
- `apps/backend/novel-service`：小说上传、解析、索引、问答
- `apps/backend/kb-service`：企业知识库上传、解析、索引、问答
- `apps/web`：统一前端，提供小说和企业库两条独立入口
- `packages/shared`：认证、日志、HTTP 基础件
- `scripts/dev`：开发启动与停止脚本
- `scripts/quality`：编码检查与 CI 校验
- `scripts/observability`：日志导出和观察工具
- `scripts/evals`：评测与基准脚本

## 开始之前

- 先阅读 [README.md](README.md)
- 再阅读 [docs/README.md](docs/README.md)
- 使用 `.env.example` 创建本地 `.env`
- 不要提交任何密钥、`.env` 内容、token 或其他敏感信息

```powershell
Copy-Item .env.example .env
```

## 推荐工作流

### 启动本地环境

```powershell
make up
```

### 基础验证

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/shared/python apps/backend/gateway apps/backend/novel-service apps/backend/kb-service
docker compose config --quiet
```

## 提交信息格式

本仓库使用 Conventional Commits。

示例：
- `feat: add kb base upload wizard`
- `fix: normalize gateway auth response`
- `docs: rewrite project structure guide`
- `chore: split scripts by responsibility`

## Pull Request 要求

每个 Pull Request 都应说明：
- `What`
- `Why`
- `How to verify`
- `Risk`

## 文档同步要求

如果改动影响以下任一内容，需同步更新文档：
- API 行为
- 环境变量
- 启动方式
- 目录结构或脚本入口
- 用户可见页面或路由
