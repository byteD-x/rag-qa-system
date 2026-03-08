# 开发脚本与本地工作流

仓库按职责拆分脚本目录，默认使用 PowerShell 管理本地开发环境。

## 脚本目录

- `scripts/dev`：启动、停止、本地前端托管
- `scripts/quality`：编码检查、pytest、CI 校验
- `scripts/observability`：日志导出和日报脚本
- `scripts/evals`：评测、ablation 和 ingest benchmark

## 前置条件

- Docker Desktop 可用
- PowerShell 可以执行 `.ps1`
- 已从 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 复制出 [`.env`](/E:/Project/rag-qa-system/.env)

```powershell
Copy-Item .env.example .env
```

## 启动与停止

启动：

```powershell
make up
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/up.ps1
```

停止：

```powershell
make down
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/down.ps1 -Force
```

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `make up` | 启动本地环境 |
| `make down` | 停止本地环境 |
| `make logs` | 查看最近日志 |
| `make logs-follow` | 持续跟随日志 |
| `make export-logs` | 导出日志快照 |
| `make ci` | 执行基础回归检查 |
| `make test` | 执行前端构建和 Python 编译检查 |
| `python -m pytest tests -q` | 运行 shared、eval、pricing smoke 测试 |
| `python scripts/evals/run-retrieval-ablation.py` | 生成离线检索 ablation 报告 |
| `python scripts/evals/benchmark-local-ingest.py` | 生成本地 ingest benchmark 报告 |
| `python scripts/observability/rag-daily-report.py` | 汇总最新报告并输出日报摘要 |

## 访问地址

| 服务 | 地址 |
| --- | --- |
| Web Console | `http://localhost:5173` |
| Gateway | `http://localhost:8080` |
| Novel Service | `http://localhost:8100` |
| KB Service | `http://localhost:8300` |
| PostgreSQL | `localhost:5432` |

宿主机端口可通过 [`.env`](/E:/Project/rag-qa-system/.env) 中的 `GATEWAY_HOST_PORT`、`NOVEL_HOST_PORT`、`KB_HOST_PORT`、`POSTGRES_HOST_PORT` 覆盖。

## AI 定价配置

- 默认环境模板已包含 `AI_PRICE_CURRENCY=CNY` 与 `AI_PRICE_TIERS_JSON`。
- 如需按模型阶梯计费估算成本，优先修改 `AI_PRICE_TIERS_JSON`。
- 如不使用阶梯计费，可仅维护 `AI_INPUT_PRICE_PER_1K_TOKENS` 与 `AI_OUTPUT_PRICE_PER_1K_TOKENS`。
- 修改定价变量后，至少重新执行一次 `docker compose config --quiet`，并重启 `gateway` 服务。

## 发布前检查

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/shared/python apps/backend/gateway apps/backend/novel-service apps/backend/kb-service
python -m pytest tests -q
python scripts/evals/run-retrieval-ablation.py
python scripts/evals/benchmark-local-ingest.py
docker compose config --quiet
```
