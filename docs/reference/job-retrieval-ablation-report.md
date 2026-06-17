# 岗位包装检索消融验证报告

> 目的：为 AI 应用/RAG 岗位面试提供一份可提交、可复现、不过度包装的检索质量证据。

## 1. 验证命令

```powershell
python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json --output artifacts/reports/job_retrieval_ablation.json --summary-output artifacts/reports/job_retrieval_ablation.md
```

## 2. Fixture 范围

本次验证使用仓库内置 `tests/fixtures/evals/retrieval-ablation-fixture.json`，覆盖以下三个企业知识库常见问题：

| case | 问题 | 目标证据 |
|---|---|---|
| `expense-approval-signatures` | 报销审批需要哪些角色签字 | `unit-expense-approval` |
| `vpn-password-rotation` | VPN口令多久轮换一次 | `unit-vpn-rotation` |
| `travel-invoice-deadline` | 差旅发票最晚多久提交 | `unit-travel-invoice` |

## 3. 验证结果

| config | recall@1 | recall@3 | mrr | ndcg@3 |
|---|---:|---:|---:|---:|
| `fusion_only` | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `rewrite_plus_fusion` | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `rewrite_plus_fusion_plus_rerank` | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## 4. 面试表达价值

- 能证明项目不是只做“向量库 + Prompt”，而是有固定 fixture、检索消融和可重复指标。
- 能讲清楚 `fusion_only`、`rewrite_plus_fusion`、`rewrite_plus_fusion_plus_rerank` 三组策略的差异。
- 能把岗位高频追问中的 Recall@K、MRR、NDCG 和 rerank 讲到本地命令与报告层面。

## 5. 边界

- 该报告只代表仓库内置 fixture，不代表真实业务线上准确率。
- 三个 case 是小样本验证，用于证明机制和回归门禁，不用于宣称大规模效果收益。
- 真实投递或面试时，如需写量化结果，应明确表述为“在内置 fixture 上验证”，不要写成生产指标。

