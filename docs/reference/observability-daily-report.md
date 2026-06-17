# 可观测日报

`scripts/observability/rag-daily-report.py` 用于把本地评测、回归和韧性报告汇总成一份可读 Markdown，同时输出机器可读 JSON。它不启动服务、不访问数据库，适合作为面试演示前的快速证据汇总，也可以放进 CI 做轻量门禁。

## 输入报告

默认读取 `artifacts/reports`，其中必需报告用于证明最小 AI 工程闭环，缺失时日报状态会变为 `partial`：

| 报告 | 作用 | 必需 |
| --- | --- | --- |
| `local_ingest_benchmark.json` | 文档解析吞吐、sections、chunks、parse ms | 是 |
| `retrieval_ablation_report.json` | recall@K、MRR、NDCG 与最佳检索配置 | 是 |
| `embedding_retrieval_benchmark.json` | 本地 embedding backend 对比 | 是 |
| `agent_smoke_evidence_pack.json` | smoke eval baseline、fixture、语料版本一致性 | 是 |
| `eval_suite_report.json` | grounded / agent / refusal 在线评测结果 | 否 |
| `eval_regression_gate.json` | 通用评测回归门禁 | 否 |
| `agent_smoke_regression_gate.json` | smoke eval 回归门禁 | 否 |
| `safety_regression_report.json` | prompt safety / badcase 回归结果 | 否 |
| `multipart_resume_report.json` | 分片上传恢复验证 | 否 |
| `pytest-groups-summary.json` | pytest 分组执行摘要、并发度、慢组、失败/超时组和日志路径 | 否 |

## 常用命令

```powershell
python scripts/observability/rag-daily-report.py
python scripts/observability/rag-daily-report.py --output artifacts/reports/rag_daily_report.md --json-output artifacts/reports/rag_daily_report.json
python scripts/observability/rag-daily-report.py --strict
```

`--strict` 会在必需报告缺失或状态失败时返回非零退出码，适合 CI；不加 `--strict` 时会继续输出 Markdown，方便本地诊断。

## 输出字段

JSON 输出包含：

- `status`：`passed` / `partial` / `failed`
- `missing_required_reports`：缺失的必需报告
- `missing_optional_reports`：缺失的可选报告
- `reports`：每个报告的加载状态和业务状态
- `metrics.ingest`：解析吞吐、sections、chunks、平均解析耗时
- `metrics.retrieval`：最佳检索配置、MRR、recall@1、recall@3
- `metrics.embedding`：embedding backend 召回指标与跳过原因
- `metrics.evidence_pack`：smoke eval 证据包版本、case 数和语料数
- `metrics.eval_suite`：在线评测 job 的 accuracy、correctness、faithfulness、p95 latency
- `metrics.regression_gate` / `metrics.agent_smoke_regression_gate`：门禁状态与失败原因
- `metrics.safety_regression`：安全回归总 case、通过数、失败数、动作分布与延迟摘要
- `metrics.multipart_resume`：分片上传恢复是否通过
- `metrics.pytest_groups`：pytest 分组状态、完成组数、未执行组数/名称、并发度、失败/超时组数和最慢组日志路径

## 推荐顺序

```powershell
python scripts/evaluation/benchmark-local-ingest.py --kb-path tests/fixtures/evals/local-ingest-policy.txt
python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json
python scripts/evaluation/compare-embedding-providers.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json
python scripts/evaluation/verify-agent-smoke-evidence.py
python scripts/evaluation/run-safety-regression.py --password <pwd>
.venv\Scripts\python.exe scripts/quality/run_pytest_groups.py --timeout-seconds 90 --heartbeat-seconds 10 --summary-output artifacts/reports/pytest-groups-summary.json tests/test_eval_pipeline.py tests/test_observability_report.py
.venv\Scripts\python.exe scripts/quality/run_pytest_groups.py --timeout-seconds 90 --heartbeat-seconds 10 --max-workers 2 --summary-output artifacts/reports/pytest-groups-summary.json tests/test_eval_pipeline.py tests/test_observability_report.py
python scripts/observability/rag-daily-report.py --output artifacts/reports/rag_daily_report.md --json-output artifacts/reports/rag_daily_report.json --strict
```

默认串行执行 pytest 分组以保持稳定的 fail-fast 语义；本地需要缩短耗时时，可以显式加 `--max-workers 2` 让多个测试文件分批并行执行。

如果只想快速检查当前已有报告，不需要加 `--strict`。
