# 岗位就绪度聚合检查

> 目标：面试或投递前，用一个轻量命令聚合岗位包装相关证据，快速判断当前项目材料是否仍然可验证。

## 1. 使用方式

先生成或准备相关报告：

```powershell
python scripts/evaluation/verify-agent-smoke-evidence.py
python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json --output artifacts/reports/job_retrieval_ablation.json --summary-output artifacts/reports/job_retrieval_ablation.md
.venv\Scripts\python.exe -m pytest -q tests/test_eval_pipeline.py
```

再运行聚合检查：

```powershell
python scripts/quality/check-job-readiness.py
```

默认输出：

- `artifacts/reports/job_readiness_summary.json`
- `artifacts/reports/job_readiness_summary.md`

也可以只打印 JSON，不写文件：

```powershell
python scripts/quality/check-job-readiness.py --no-write
```

## 2. 聚合信号

| 报告 | 默认文件 | 是否必需 | 作用 |
|---|---|---:|---|
| Agent smoke 证据包 | `agent_smoke_evidence_pack.json` | 是 | 证明 grounded / agent / refusal 三类 fixture、baseline 和语料完整 |
| 检索消融 | `job_retrieval_ablation.json` | 是 | 证明 Recall@K、MRR、NDCG 指标可复现 |
| 评测 pytest 摘要 | `job_eval_pipeline_pytest_summary.json` | 否 | 汇总 `tests/test_eval_pipeline.py` 的分组执行状态 |
| 在线 smoke 回归门禁 | `agent_smoke_regression_gate.json` | 否 | 有 Docker 环境时证明在线 smoke eval 回归结果 |

## 3. 状态含义

| 状态 | 含义 | 建议动作 |
|---|---|---|
| `passed` | 必需报告存在且状态/指标满足检查条件 | 可作为投递和面试前的本地证据 |
| `partial` | 必需报告缺失，但没有明确失败 | 先补跑缺失报告，再对外展示 |
| `failed` | JSON 解析失败、报告状态失败或指标为空 | 先修复报告或评测问题，不要交付 |

## 4. 边界

- 该脚本只聚合本地报告，不启动 Docker，也不调用模型。
- `partial` 不是通过，只表示还缺证据。
- 检索指标来自内置 fixture，不代表真实线上准确率。
- 在线 smoke eval 仍需要本地 Docker 栈和服务就绪。

