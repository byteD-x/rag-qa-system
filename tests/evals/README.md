# Eval Datasets

当前目录用于存放离线评测输入。

## 文件说明

- `novel-large-doc-eval.json`：长篇小说模式评测样本
- `kb-smoke-eval.json`：企业文档 smoke 评测样本
- `adversarial-refusal-eval.json`：拒答与越权场景样本
- `retrieval-ablation-fixture.json`：离线检索 ablation 固定夹具
- `suite.sample.json`：多评测作业配置模板

## 使用方式

- 单作业：`python scripts/evals/eval-long-rag.py ...`
- 多作业：`python scripts/evals/run-eval-suite.py --config tests/evals/suite.sample.json ...`
- 离线 ablation：`python scripts/evals/run-retrieval-ablation.py`
