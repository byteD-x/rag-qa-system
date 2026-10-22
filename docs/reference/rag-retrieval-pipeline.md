# RAG 五层检索链路

当前知识库问答按“召回层 → 融合层 → 精排层 → 门控层 → 生成层”组织。实现入口是 `apps/services/knowledge-base/src/app/retrieve.py`，Gateway 和 KB 查询接口继续复用原有 `RetrievalResult` 契约。

## 召回层

`run_signal_retrievers` 并行执行结构检索、PostgreSQL FTS 和 Qdrant 向量检索。包含错误码、版本号、函数名或其他稳定标识符的查询会额外启用 grep 兼容的纯文本精确子串通道；普通自然语言不会执行这条扫描。版本、部门、内容类型、标签等硬过滤在解析 `doc_ids` 时前置完成。

召回信号的职责是尽量找全：向量负责语义覆盖，FTS 负责词项覆盖，结构检索负责标题/章节命中，grep 负责字面精确兜底。

## 融合层

`fuse_and_rerank` 使用加权 RRF 对各路排名做融合，不直接比较不同检索器的原始分数；同一个 chunk 通过 `unit_id` 去重后进入候选池。`retrieval.grep_candidates` 和各路候选计数用于调试召回覆盖。

## 精排层

融合后的前部候选进入 `shared.rerank.rerank_evidence_blocks`。默认使用本地启发式排序，配置 `RERANK_PROVIDER=cross-encoder` 后调用外部 Query-Document 精排服务；`RERANK_TOP_N` 控制外部服务的候选上限。

## 门控层

精排结果随后进入 `shared.jevgate.gate_evidence_blocks`。JEV 只做结构化相关性判断，不生成回答：请求包含一个 query state 和一批候选 questions，响应可使用 `yes_probability`、`probability` 或 `score` 字段。

- 概率大于等于 `JEV_HIGH_THRESHOLD`：`keep`
- 位于两个阈值之间：`deprioritize`，保留为低优先级证据
- 小于 `JEV_LOW_THRESHOLD`：`drop`

包含唯一稳定标识符精确命中的请求会由确定性代码直接决策，JEV 远程调用为 0。JEV 未配置或暂时不可用时保留候选并在 `retrieval.warnings` 写入原因，避免门控故障误删证据。启用 JEV 后，`gate_remote_calls`、`gate_provider`、`gate_dropped_candidates` 会出现在检索统计中。

阈值不是固定事实，应使用带相关性标注的数据集在误放和误删之间校准；更换 JEV 模型或版本后重新校准。

## 生成层

KB 查询和 Gateway 只把门控后的 `items` 生成上下文交给回答模型。生成模型的职责是基于高纯度证据回答，不承担从全量召回候选中再次筛选上下文。

## 配置示例

```dotenv
JEV_ENABLED=true
JEV_API_URL=https://jev.example.test/score
JEV_API_KEY=请使用部署环境注入
JEV_MODEL=system-one
JEV_BATCH_SIZE=30
JEV_HIGH_THRESHOLD=0.75
JEV_LOW_THRESHOLD=0.35
```

本地低成本闭环无需配置 JEV：保持 `JEV_ENABLED=false` 即可继续使用本地 embedding、Qdrant、FTS、结构检索、RRF 和启发式 rerank。
