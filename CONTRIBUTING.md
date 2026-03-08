# 贡献指南

感谢你为 `RAG-QA 2.0` 提交改动。

## 开始之前

- 先阅读 [README.md](/E:/Project/rag-qa-system/README.md)
- 需要细节时再看 [docs/reference/api-specification.md](/E:/Project/rag-qa-system/docs/reference/api-specification.md) 和 [docs/operations/runbook.md](/E:/Project/rag-qa-system/docs/operations/runbook.md)
- 使用 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 创建本地 [`.env`](/E:/Project/rag-qa-system/.env)
- 不要提交任何敏感信息，包括 `.env`、token、连接串或账单截图

```powershell
Copy-Item .env.example .env
```

## 推荐工作流

```powershell
make up
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
docker compose config --quiet
```

## 提交格式

仓库使用 Conventional Commits：

- `feat: add grounded answer retry policy`
- `fix: normalize kb upload status mapping`
- `docs: update enterprise rag runbook`
- `chore: move eval fixtures under tests/fixtures`

## Pull Request 要求

每个 PR 描述必须包含：

- `What`
- `Why`
- `How to verify`
- `Risk`

## 文档同步要求

以下内容发生变化时，必须同步更新 README 或对应文档：

- API 行为
- 环境变量
- 启动方式
- 目录结构或脚本入口
- 用户可见页面或路由

## LLM 定价配置补充

- 如修改 `LLM_PRICE_CURRENCY`、`LLM_PRICE_TIERS_JSON`、`LLM_INPUT_PRICE_PER_1K_TOKENS` 或 `LLM_OUTPUT_PRICE_PER_1K_TOKENS`，必须同步更新 [README.md](/E:/Project/rag-qa-system/README.md) 和 [docs/reference/api-specification.md](/E:/Project/rag-qa-system/docs/reference/api-specification.md)
- 历史 `AI_*` 定价变量仅作为兼容别名，不应再作为新改动的主命名
- 禁止把真实 `LLM_API_KEY`、供应商账单或控制台敏感信息写入文档
