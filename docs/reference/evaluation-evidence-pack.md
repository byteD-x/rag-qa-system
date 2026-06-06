# 离线评测证据包

本页说明 `agent_smoke` 最小评测证据包的组成和校验方式。它的目标不是替代在线 smoke-eval，而是在不启动 Gateway、KB、Qdrant、Postgres 的情况下，快速确认仓库内置评测资产是否仍然完整、可追溯、可复现。

## 适用场景

- 面试或代码审查前，先确认项目确实保留了可运行的评测闭环资产。
- CI 中做轻量门禁，避免 fixture、baseline 或语料文件被误删。
- 在线 `smoke_eval.py` 运行失败时，先排除本地评测资产缺失或版本漂移问题。

## 证据包内容

| 文件 | 作用 |
| --- | --- |
| `scripts/evaluation/fixtures/agent_smoke_baseline.json` | 定义 suite version、required dataset versions、job 阈值和 regression gate 要求 |
| `scripts/evaluation/fixtures/agent_smoke_grounded.json` | grounded 单知识库问答评测 case |
| `scripts/evaluation/fixtures/agent_smoke_agent.json` | agent 多知识库问答评测 case |
| `scripts/evaluation/fixtures/agent_smoke_refusal.json` | 无依据拒答评测 case |
| `scripts/evaluation/fixtures/agent_smoke_policy.txt` | smoke 评测政策语料 |
| `scripts/evaluation/fixtures/agent_smoke_travel.txt` | smoke 评测差旅语料 |

## 本地校验

```powershell
python scripts/evaluation/verify-agent-smoke-evidence.py
```

通过后会输出：

- `artifacts/reports/agent_smoke_evidence_pack.json`
- `artifacts/reports/agent_smoke_evidence_pack.md`

脚本校验内容：

- baseline 存在且包含 `suite_name`、`suite_version`、`required_dataset_versions` 和 `jobs`
- baseline 中 `required_dataset_versions` 与各 job 的 `dataset_version` 一致
- grounded / agent / refusal 三类 eval fixture 存在且为非空 case 数组
- 每个 case 包含 `id`、`category`、`question`、`min_citations`、`must_refuse_without_evidence`
- case 的 `category` 与对应 job 名称一致
- smoke 语料文件存在且非空

## 与在线 smoke-eval 的关系

`verify-agent-smoke-evidence.py` 只验证“评测资产是否完整且版本一致”，不验证模型回答质量、召回质量或拒答效果。

完整效果验证仍使用：

```powershell
python scripts/dev/smoke_eval.py --password <pwd> --wait-for-ready
```

在线 smoke-eval 会上传语料、生成运行时 suite、执行 grounded / agent / refusal 三类任务，并通过 `check-eval-regression.py` 校验 correctness、faithfulness、citation alignment、refusal precision 和 refusal recall。

## 推荐 CI 顺序

```powershell
python scripts/evaluation/verify-agent-smoke-evidence.py
.venv\Scripts\python.exe scripts/quality/run_pytest_groups.py --timeout-seconds 90 --heartbeat-seconds 10 --summary-output artifacts/reports/eval_pipeline_pytest_summary.json tests/test_eval_pipeline.py
```

如果第一步失败，优先修复 fixture 或 baseline；如果第二步失败，再检查评测脚本逻辑或测试执行器。`run_pytest_groups.py` 会同时写出 stdout/stderr 分组日志和 JSON 摘要，便于快速定位慢测试、失败组和超时组。
