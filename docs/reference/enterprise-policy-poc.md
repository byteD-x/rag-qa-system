# 企业制度可信问答 PoC

> 本 PoC 用于验证 RAG-QA 2.0 在中文企业制度/流程文档场景下的最小可行价值：能否围绕 HR、财务、IT 和采购制度给出可引用、可拒答、可回归的答案。样例语料均为虚构脱敏内容，不代表真实公司制度。

## 目标

- 让陌生试用者在 10 到 30 分钟内看懂产品能解决什么问题。
- 用固定问题集验证检索命中、引用对齐和拒答边界。
- 把 badcase 沉淀为后续 chunking、检索改写、重排和治理工作台的输入。

## 样例资产

| 文件 | 作用 |
| --- | --- |
| `tests/fixtures/evals/enterprise-policy-poc-corpus.txt` | 可上传到知识库的中文企业制度样例语料 |
| `tests/fixtures/evals/enterprise-policy-poc-retrieval.json` | 离线检索消融 fixture，不依赖 Docker、模型或在线服务 |
| `tests/fixtures/evals/enterprise-policy-poc-online.json` | 在线问答评测问题集，覆盖正常问答和无依据拒答 |
| `tests/fixtures/evals/enterprise-policy-poc-badcases.jsonl` | badcase 记录模板，提交样例格式，不存放真实客户数据 |

## 一键验证

默认只跑离线检索消融，并生成 PoC 汇总：

```powershell
python scripts/evaluation/run-enterprise-policy-poc.py
```

预期输出：

- `artifacts/reports/enterprise_policy_poc_retrieval.json`
- `artifacts/reports/enterprise_policy_poc_retrieval.md`
- `artifacts/reports/enterprise_policy_poc_summary.md`

如果已启动本地服务、完成语料上传，并拿到知识库 ID，可以继续跑在线评测：

```powershell
python scripts/evaluation/run-enterprise-policy-poc.py `
  --online `
  --password <ADMIN_PASSWORD> `
  --corpus-id kb:<KB_ID>
```

## 离线验证

也可以单独跑离线检索消融，确认候选证据融合、query rewrite 和 rerank 的基础指标没有退化：

```powershell
python scripts/evaluation/run-retrieval-ablation.py `
  --fixture tests/fixtures/evals/enterprise-policy-poc-retrieval.json `
  --output artifacts/reports/enterprise_policy_poc_retrieval.json `
  --summary-output artifacts/reports/enterprise_policy_poc_retrieval.md
```

预期输出：

- `artifacts/reports/enterprise_policy_poc_retrieval.json`
- `artifacts/reports/enterprise_policy_poc_retrieval.md`

建议首轮门槛：

| 指标 | 最低门槛 |
| --- | ---: |
| recall@1 | 0.80 |
| recall@3 | 1.00 |
| mrr | 0.85 |
| ndcg@3 | 0.85 |

## 在线验证

在线验证需要已启动 Gateway、KB Service、Postgres、MinIO、Qdrant，并配置可用模型。

1. 创建知识库，例如 `企业制度 PoC`。
2. 上传 `tests/fixtures/evals/enterprise-policy-poc-corpus.txt`。
3. 等待文档状态进入 `ready`。
4. 记录知识库 ID，并按 `kb:<KB_ID>` 传入评测脚本。

```powershell
python scripts/evaluation/eval-long-rag.py `
  --base-url http://localhost:8080/api/v1 `
  --email admin@local `
  --password <ADMIN_PASSWORD> `
  --eval-file tests/fixtures/evals/enterprise-policy-poc-online.json `
  --scope-mode single `
  --corpus-id kb:<KB_ID> `
  --execution-mode grounded `
  --output artifacts/reports/enterprise_policy_poc_online.json `
  --summary-output artifacts/reports/enterprise_policy_poc_online.md
```

建议首轮门槛：

| 指标 | 最低门槛 |
| --- | ---: |
| correctness | 0.75 |
| citation alignment | 0.80 |
| faithfulness | 0.75 |
| refusal recall | 1.00 |

## 试用问题

建议让 3 到 5 名非研发试用者直接提问：

- 年假要提前几天申请？
- 报销超过三千元需要谁审批？
- VPN 密码多久换一次？
- 设备丢了并且里面有客户资料，要补什么报告？
- 软件订阅续费要提前多久发起？
- 公司股票期权的归属周期是多少？
- 首次给供应商付款前要上传哪些资料？

## badcase 记录口径

每个 badcase 至少记录：

- `question`：用户原始问题。
- `expected_behavior`：应回答、应补问还是应拒答。
- `expected_evidence`：应命中的制度标题和段落。
- `actual_answer`：实际回答。
- `actual_citations`：实际引用。
- `failure_type`：召回失败、重排失败、引用不对齐、答案幻觉、过度拒答、未拒答、权限问题。
- `next_action`：补语料、调 chunk、改 query rewrite、调 rerank、加拒答规则、加 ACL。

可先复制 `tests/fixtures/evals/enterprise-policy-poc-badcases.jsonl` 的结构到 `artifacts/reports/enterprise_policy_poc_badcases.jsonl`，把本地试用产生的 badcase 记录在 artifacts 下，避免把真实业务问题直接提交到仓库。

## 下一步

首轮 PoC 不建议继续加平台功能。先用这组固定资产跑出真实 badcase，再决定是否优先做：

1. token-aware chunking 入库主路径 A/B。
2. 检索调试页一键保存 badcase。
3. 文档级或切片级 ACL。
4. 飞书、钉钉或本地共享盘的一个深度连接器。
