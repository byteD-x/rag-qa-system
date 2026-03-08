# 开发脚本与本地工作流

仓库默认围绕企业知识库 RAG 工作流组织脚本。

## 脚本目录

- `scripts/dev`：启动、停止、前端托管
- `scripts/quality`：编码检查、pytest、CI 聚合校验
- `scripts/observability`：日志导出与日报
- `scripts/evaluation`：评测、ablation、embedding 对照、ingest benchmark

## 前置条件

- Docker Desktop 可用
- PowerShell 可执行 `.ps1`
- 已从 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 复制出 [`.env`](/E:/Project/rag-qa-system/.env)

```powershell
Copy-Item .env.example .env
```

## 启动与停止

```powershell
make up
make down
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/up.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/down.ps1 -Force
```

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `make up` | 启动本地环境 |
| `make down` | 停止本地环境 |
| `make logs` | 查看最近日志 |
| `make logs-follow` | 持续跟随日志 |
| `make export-logs` | 导出日志快照 |
| `make ci` | 执行基础回归检查 |
| `make test` | 执行前端构建与 Python 编译检查 |
| `python -m pytest tests -q` | 运行回归测试 |
| `python scripts/evaluation/run-demo-eval-suite.py --password <pwd>` | 自动准备 demo KB 并生成统一 eval 报告 |
| `python scripts/evaluation/run-retrieval-ablation.py` | 生成离线检索 ablation 报告 |
| `python scripts/evaluation/benchmark-local-ingest.py` | 生成本地 ingest benchmark 报告 |
| `python scripts/evaluation/compare-embedding-providers.py` | 生成 embedding baseline 对照报告 |
| `python scripts/evaluation/verify-multipart-resume.py --corpus-id <base-id> --file <path> --password <pwd>` | 验证断点续传恢复链路 |
| `python scripts/observability/rag-daily-report.py` | 汇总最新报告并生成日报摘要 |

默认情况下，评测脚本会把生成物写入 `artifacts/reports/` 与 `artifacts/evals/`。只有需要长期留档的报告，才应手动整理到 `docs/reports/`。

## 访问地址

| 服务 | 地址 |
| --- | --- |
| Web Console | `http://localhost:5173` |
| Gateway | `http://localhost:8080` |
| KB Service | `http://localhost:8300` |
| PostgreSQL | `localhost:5432` |

## 发布前检查

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
