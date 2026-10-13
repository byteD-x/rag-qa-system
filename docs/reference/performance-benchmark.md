# 检索性能与质量验证

## 本次改动

- KB 查询复用 PostgreSQL 连接池（KB_DB_POOL_MAX_SIZE，默认 10），服务退出时关闭。
- 三路召回复用有界线程池（KB_RETRIEVAL_WORKERS，默认 12），避免并发请求各自创建线程池。
- 热路径检索启用 ACL 感知的短 TTL LRU 缓存（KB_RETRIEVAL_CACHE_TTL_SECONDS，默认 5 秒；KB_RETRIEVAL_CACHE_MAX_ENTRIES，默认 2048），相同问题并发请求采用 single-flight 合并；接口 `retrieval.cache_hit` 和 `rag_kb_retrieval_cache_total` 可审计命中收益。
- 并发压测用固定数量 worker 持续补位，支持多问题混合负载；分别统计成功请求 QPS、成功请求 P95、错误数、非空检索率和检索缓存命中率。
- 离线检索 Recall@K 以全部预期证据为分母；在线评测以全部预期章节为分母，并输出拒答率、拒答 precision/recall 与模型估算成本/千次请求。

这些改动不调整召回权重、重排阈值或拒答策略。非空检索率只表示返回过候选，不能代替有标注数据的 Recall@K。

## 同口径压测

在相同硬件、语料、模型、权限、限流配置下分别运行改动前后版本。两侧必须使用同一版本的压测脚本，避免旧脚本的分批等待改变 QPS 口径。先把真实代表性问题逐行写入 UTF-8 文本文件；不要使用敏感生产问题。将凭据通过 BENCHMARK_PASSWORD 环境变量注入，不写入报告。

    $baseId = '<KB_ID>'
    $questions = 'artifacts/reports/perf-questions.txt'
    $revision = 'after' # 基线部署时改为 before
    foreach ($concurrency in @(1, 4, 8, 16, 32)) {
      .venv\Scripts\python.exe scripts/evaluation/benchmark-retrieval-concurrency.py --base-id $baseId --questions-file $questions --total-requests 200 --concurrency $concurrency --warmup-requests 10 --output "artifacts/reports/$revision-$concurrency.json" --summary-output "artifacts/reports/$revision-$concurrency.md"
    }

每档至少重复 3 次。只比较成功率和非空检索率相近的档位；若高并发出现 429、超时或 5xx，需报告错误率，不能仅引用成功请求 P95。summary.success_throughput_rps 是成功 QPS，summary.latency.p95_ms 只统计成功请求；summary.throughput_rps 和 summary.all_latency 包含失败尝试。`summary.retrieval_cache_hit_rate` 只统计成功请求中的 `retrieval.cache_hit=true`，不能把缓存命中率直接等同于 Recall@K。报告 JSON 保留逐请求耗时与状态，便于审计。

## 质量与成本

    .venv\Scripts\python.exe scripts/evaluation/run-enterprise-policy-poc.py
    .venv\Scripts\python.exe scripts/evaluation/eval-policy-quality.py
    .venv\Scripts\python.exe scripts/evaluation/eval-long-rag.py --base-url http://localhost:8080/api/v1 --email admin@local --eval-file tests/fixtures/evals/enterprise-policy-poc-online.json --scope-mode single --corpus-id "kb:$baseId" --execution-mode grounded --output artifacts/reports/perf-online.json --summary-output artifacts/reports/perf-online.md

质量扩展基线由 eval-policy-quality.py 生成：24 个章节、120 道单章节题、8 道多章节题、12 道无证据题，并固定 58 道 holdout（52 道可回答、6 道无证据）。脚本直接读取原始脱敏语料，只做词法诊断，不调用向量库、LLM、ACL 或网络；Recall@K 用于数据集和检索改动的快速回归，不能替代线上接口结果。脚本同时生成 artifacts/reports/policy-quality-v2-online.json，可交给 eval-long-rag.py 做真实接口评测。

原始 PoC 离线样例很小，满分不代表实际线上召回率；质量扩展基线见上方的 140 道标注集。线上数据集应包含可回答、无证据、跨部门权限、同义问法等独立标注样本，改动前后使用同一份数据集。estimated_cost_per_1000_requests 来自 Gateway 返回的 cost.estimated_cost，取决于价格配置；对比前先确认 estimated_cost_sample_count_by_currency 覆盖全部评测请求。真实金额下降还需核对供应商账单。订单数、设备数并非本知识库系统的业务指标，不应写入项目经历。若需要规模指标，使用经验证的请求量、独立用户数和文档数。

## 简历证据模板

只有在两侧报告齐全后，才填入实际值：

> 优化企业知识库检索链路，复用 PostgreSQL 连接和有界召回线程池；在同语料、同模型、C 并发、N 次混合请求下，成功请求 P95 从 A ms 降至 B ms，成功 QPS 从 X 提升至 Y，错误率 E；标注集 Recall@3 为 R，拒答召回为 F，模型估算成本/千次请求为 M（货币单位）。

若压测包含重复问题，可补充：

> 为检索接口增加 ACL 感知 TTL/LRU 与 single-flight 合并，在 C 并发重复/混合问题负载下，检索缓存命中率 H%，接口请求 P95 为 P ms，成功 QPS 为 Q；未命中请求的 Recall@K 与基线持平。

没有前后压测、线上标注集或账单证据时，不填写改善百分比、用户规模或金额。
