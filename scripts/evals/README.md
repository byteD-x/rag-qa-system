# Eval Scripts

评测与基准相关脚本。

## 文件说明

- `benchmark-long-ingest.py`：在线 multipart 上传与 staged ingest 基准
- `benchmark-local-ingest.py`：不依赖服务启动的本地解析吞吐 benchmark
- `eval-long-rag.py`：统一聊天评测，输出 recall、MRR、nDCG、citation precision、latency、refusal 指标
- `run-eval-suite.py`：按配置串行跑 `novel / kb / adversarial` 多套评测
- `run-retrieval-ablation.py`：离线 `query rewrite + rerank` ablation

## 输出

默认写入 `docs/reports/`：

- `*_report.json`
- `*_report.md`

## 与成本字段的边界

- 当前评测脚本重点覆盖检索质量、拒答和时延，不会重算 DashScope 阶梯价格。
- 在线聊天响应中的 `cost` 字段以 `gateway` 服务端计算结果为准。
- 如需变更模型价格，请修改根目录 [`.env`](/E:/Project/rag-qa-system/.env) 中的 `AI_PRICE_CURRENCY` 与 `AI_PRICE_TIERS_JSON`，而不是改评测脚本。
