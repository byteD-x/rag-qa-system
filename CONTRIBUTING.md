# 贡献指南

感谢你为 `RAG-QA 2.0` 提交改动。

## 开始之前

- 先阅读 [README.md](/E:/Project/rag-qa-system/README.md)
- 再阅读 [docs/README.md](/E:/Project/rag-qa-system/docs/README.md)
- 使用 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 创建本地 [`.env`](/E:/Project/rag-qa-system/.env)
- 不要提交任何密钥、`.env` 内容、token 或其他敏感信息

```powershell
Copy-Item .env.example .env
```

## 推荐工作流

启动本地环境：

```powershell
make up
```

基础验证：

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/shared/python apps/backend/gateway apps/backend/novel-service apps/backend/kb-service
python -m pytest tests -q
docker compose config --quiet
```

## 提交信息格式

仓库使用 Conventional Commits。

示例：

- `feat: add kb base upload wizard`
- `fix: normalize gateway auth response`
- `docs: update pricing and runbook docs`
- `chore: split scripts by responsibility`

## Pull Request 要求

每个 Pull Request 都应说明：

- `What`
- `Why`
- `How to verify`
- `Risk`

## 文档同步要求

如改动影响以下任一内容，必须同步更新文档：

- API 行为
- 环境变量
- 启动方式
- 目录结构或脚本入口
- 用户可见页面或路由

## AI 定价相关补充

- 如修改 `AI_PRICE_CURRENCY`、`AI_PRICE_TIERS_JSON`、`AI_INPUT_PRICE_PER_1K_TOKENS` 或 `AI_OUTPUT_PRICE_PER_1K_TOKENS`，必须同步更新 [README.md](/E:/Project/rag-qa-system/README.md)、[docs/README.md](/E:/Project/rag-qa-system/docs/README.md) 和 [docs/API_SPECIFICATION.md](/E:/Project/rag-qa-system/docs/API_SPECIFICATION.md)。
- 价格来源变更时，提交说明中要写清楚供应商、模型名、币种和档位。
- 禁止把真实 `AI_API_KEY`、账单截图或控制台敏感信息写入文档。
