# Scripts

`scripts/` 按职责拆分，避免所有脚本平铺在仓库根目录。

## 目录说明

- `dev/`：启动、停止、前端托管
- `quality/`：编码检查、pytest、构建校验、CI 汇总
- `observability/`：日志导出和日报脚本
- `evals/`：评测、ablation 和 ingest benchmark

## 常用入口

```powershell
.\scripts\dev\up.ps1
.\scripts\dev\down.ps1 -Force
.\scripts\quality\ci-check.ps1
.\scripts\observability\aggregate-logs.ps1
python scripts/observability/rag-daily-report.py
```

## 与 AI 定价相关的边界

- `scripts/dev/*` 负责读取 [`.env`](/E:/Project/rag-qa-system/.env) 并启动服务，但不解释价格档位本身。
- `scripts/observability/rag-daily-report.py` 当前汇总 benchmark、ablation 和 eval 报告，不会重算聊天 `cost`。
- 统一聊天中的成本估算以 `gateway` 返回的 `cost` 字段为准，环境变量来源见 [`.env.example`](/E:/Project/rag-qa-system/.env.example)。
