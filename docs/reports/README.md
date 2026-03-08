# Reports

本目录存放可提交、可复现的阶段性验证输出。

## 当前报告

- `local_ingest_benchmark.*`：本地解析吞吐 benchmark
- `retrieval_ablation_report.*`：离线 query rewrite / rerank ablation
- `*_eval_report.*`：统一聊天评测输出

## 约定

- `json` 用于机器读取与 CI 归档
- `md` 用于人工浏览与简历素材提炼
- 新报告应尽量由脚本直接生成，不手工改数
