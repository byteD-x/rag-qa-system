# 开发脚本与本地工作流

仓库默认围绕“零数据基线”的企业知识库 RAG 工作流组织脚本。

## 目录

- `scripts/dev`: 初始化、启动、停止与前端托管
- `scripts/quality`: 编码检查与聚合验证
- `scripts/observability`: 日志导出与日报聚合
- `scripts/evaluation`: 评测与 benchmark 脚本骨架

## 前置条件

- Docker Desktop 可用
- PowerShell 可执行 `.ps1`
- 已从 `.env.example` 复制出 `.env`

```powershell
Copy-Item .env.example .env
```

## 初始化与启动

```powershell
make init
make up
make down
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/init.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/up.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/down.ps1 -Force
```

说明：

- `init` 显式初始化数据库 schema 与对象存储桶。
- `up` 先启动基础设施，再执行显式初始化，最后启动应用服务。
- 服务启动本身不再承担 migration 职责。

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `make init` | 初始化数据库与对象存储 |
| `make up` | 启动本地环境 |
| `make down` | 停止本地环境 |
| `make logs` | 查看最近日志 |
| `make logs-follow` | 持续跟随日志 |
| `make export-logs` | 导出日志快照 |
| `make ci` | 执行基础回归检查 |
| `make test` | 执行前端构建与 Python 编译检查 |
| `python -m pytest tests -q` | 运行回归测试 |
| `python scripts/evaluation/benchmark-local-ingest.py --kb-path <glob-or-file>` | 解析吞吐 benchmark，必须显式给出文档路径 |
| `python scripts/evaluation/run-retrieval-ablation.py --fixture <fixture.json>` | 运行离线检索对照 |
| `python scripts/evaluation/compare-embedding-providers.py --fixture <fixture.json>` | 运行 embedding 对照 |
| `python scripts/evaluation/eval-long-rag.py --password <pwd> --eval-file <eval.json> --corpus-id kb:<uuid>` | 执行统一问答评测 |
| `python scripts/evaluation/run-eval-suite.py --password <pwd> --config <suite.json>` | 执行多任务评测 |
| `python scripts/evaluation/verify-multipart-resume.py --corpus-id <base-id> --file <path> --password <pwd>` | 验证断点续传恢复链路 |
| `python scripts/observability/rag-daily-report.py` | 汇总报告目录下的最新结果 |

## 零数据基线约束

- 仓库不再预置 demo 文档、fixture 或 demo eval 配置。
- 所有评测脚本都必须显式传入输入文件。
- `artifacts/` 与 `logs/` 仅作为运行期输出目录，不应提交生成物。

## 发布前检查

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
docker compose config --quiet
```
