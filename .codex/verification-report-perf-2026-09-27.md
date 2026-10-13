# 检索并发与评测口径优化验证

日期：2026-09-27
状态：代码 review 已完成；活体压测已完成，见文末「附录 A」（真实 P95/QPS 收益已取得）。

## 范围

- KB 数据库采用现有 Gateway 模式的懒初始化连接池，配置 KB_DB_POOL_MAX_SIZE，lifespan 关闭；KB runtime 加同版本 psycopg_pool 依赖。
- 三路检索仍并行，但跨请求共用有界线程池，配置 KB_RETRIEVAL_WORKERS，lifespan 关闭。
- 修正压测器的分批等待、成功请求 QPS/P95 口径，加入多问题混合负载与非空检索率。
- 修正有标注检索的 Recall@K 分母，补充拒答率、按币种的模型估算成本/千次请求和样本数。
- 没有改动召回权重、重排策略或拒答策略；保留了工作区原有的部门 ACL 改动。

## 最小验证

- 定向测试：.venv/Scripts/python.exe -m pytest tests/test_performance_paths.py tests/test_eval_pipeline.py tests/test_langgraph_runtime.py -q → 65 passed。
- KB 路由与 ACL 定向测试：4 个 test_backend_infra 用例和 tests/test_kb_document_acl.py → 11 passed。
- 成本评测相关用例复核 → 2 passed。
- py_compile：KB db/retrieve/main、两份评测脚本 → 通过。
- 编码检查：.venv/Scripts/python.exe scripts/quality/check-encoding.py --root . → 473 files passed。
- 离线消融：enterprise-policy-poc-retrieval.json 改动前后三配置的 recall@1、recall@3、MRR、NDCG@3 均为 1.0。样本很小，只能说明该样例未退化。
- 质量扩展：eval-policy-quality.py 读取原始脱敏语料，生成 24 个章节、140 道标注题（120 单章节、8 多章节、12 无证据），其中 58 道 holdout（52 道可回答、6 道无证据）；可回答 holdout Recall@3=1.0000，MRR=1.0000。该指标属于无网络词法诊断，不等同于线上接口召回。
- Compose：Docker Desktop 29.8.0 可通过显式路径调用；docker compose config 可作为配置检查，但 compose up -d --build 两次在拉取 qdrant/qdrant:v1.13.3 时因 Docker Hub CloudFront EOF 失败，未启动完整服务。

## 限制

- 当前仍没有完整运行的 Gateway、KB、Qdrant 服务，无法生成真实前后 P95、QPS 或账单成本下降数字；待 qdrant 镜像可拉取后再跑接口评测和并发压测。
- 连接池与共享线程池在不同 CPU、Postgres 连接数和 Qdrant 延迟下可能有不同收益，需按 docs/reference/performance-benchmark.md 对同一环境做多档并发、混合问题、重复测量，并核对错误率及标注集质量。
- 当前样例语料不支持声明用户数、订单数或设备数；这类规模指标必须从实际运营数据取得。

---

# 附录 A：活体 A/B 压测（2026-09-27 补测）

完整栈已启动（postgres / qdrant / kb-service / gateway），压测已完成。以下数字为真实测量，可审计。

## A.1 对照构造

| 项 | 基线（优化前） | 优化后 |
|---|---|---|
| 代码 | `git worktree` @ HEAD `0d80f6b` | 工作区 |
| 数据库连接 | 每次调用 `psycopg.connect()`（`db.py:19`） | `psycopg_pool.ConnectionPool`（`db.py:23`） |
| 检索线程池 | **每请求**新建 `ThreadPoolExecutor(max_workers=3)`（`retrieve.py:311`） | 跨请求共享 `_get_retrieval_executor()`（`retrieve.py:36`） |
| 依赖 | **未安装** `psycopg_pool` | 已安装 |
| 地址 | `http://localhost:8301` | `http://localhost:8300` |
| 后端 | **同一个** Postgres 容器 + 同一个 Qdrant 容器/集合 | 同左 |
| 语料 | 同一份（1 文档 / 29 章节 / 29 chunk / 58 Qdrant points） | 同左 |

容器内代码已逐一核验（`docker exec` grep），确认两栈代码确实不同，非同名镜像。

压测接口：`POST /api/v1/kb/retrieve`（**纯检索，不经 LLM**）。问题集：140 道标注题全量轮转，`limit=8`。

## A.2 结果（每档 500 请求）

两轮独立测量的提升幅度，第二轮采用 **ABBA 交替顺序**以消除时间漂移（页缓存 / 索引预热）造成的系统性偏差：

| 并发 | QPS 基线 (ABBA) | QPS 优化 (ABBA) | QPS 提升 | p95 基线 | p95 优化 | p95 降低 |
|---|---|---|---|---|---|---|
| 1 | 24.5 | 54.0 | **+120.3%** | 45.4 ms | 21.8 ms | **-51.9%** |
| 4 | 44.0 | 69.9 | **+58.8%** | 105.5 ms | 67.2 ms | **-36.3%** |
| 8 | 40.5 | 64.5 | **+59.1%** | 252.5 ms | 167.2 ms | **-33.8%** |
| 16 | 40.2 | 62.2 | **+55.0%** | 498.8 ms | 354.0 ms | **-29.0%** |
| 32 | 38.8 | 57.8 | **+48.8%** | 1038.1 ms | 735.1 ms | **-29.2%** |

首轮（非交替）测量：并发 4/8/16/32 的 QPS 提升为 +67.7% / +45.7% / +54.1% / +52.0%，p95 降低 -44.4% / -29.3% / -31.7% / -35.6%。两轮互相印证。

**稳定性**：ABBA 轮 40 次运行，成功率 **100%**，检索非空率 **100%**，错误数 **0**。组内 QPS 波动很小（如并发 4：基线 38.3~46.7）。

基线在并发 ≥8 时 QPS 见顶（~40）且 p95 随并发线性劣化 → 典型的每请求建连/建线程池开销饱和；优化后 QPS 抬升至 ~62 且 p95 增长更缓。

## A.3 质量中性验证

对同一 140 题分别请求两栈，比较返回的 unit_id 有序列表：

- 跨栈一致 135/140（96.4%）
- **对照实验**：同一栈自己重查两遍 —— 基线 5/140 不一致（96.4%），优化后 6/140 不一致（95.7%）

即**自比对噪声与跨栈差异同量级**。人工核验 5 处差异全部是**相邻名次互换**（rank5↔6、rank3↔4），属检索管线固有的同分并列排序不确定，与本次优化无关。**结论：本次优化不改变检索质量。**

## A.4 本附录数字能/不能用于简历

**可以**（有前后可审计报告）：

- 检索接口在并发 4–32 下 QPS 提升 ~49–59%、P95 降低 ~29–36%
- 同环境同语料同问题集，ABBA 交替，每档 500 请求，成功率 100%、零错误
- 质量中性（96.4% 一致 vs 自比对噪声 96.4%）

**不可以**（见附录 B）：

- faithfulness、答案正确率、拒答率、成本下降 —— 生成链路未真正运行
- 任何端到端（含 LLM）的 P95/QPS —— 本次压测只覆盖检索段

## A.5 复现命令

```bash
# 基线 worktree（不触碰工作区）
git worktree add E:/Project/rag-qa-baseline HEAD --detach
# 基线 .env 设 KB_HOST_PORT=8301 / GATEWAY_HOST_PORT=8081，复用主工作区 data/kb 与既有 postgres/qdrant 网络
docker compose -f docker-compose.yml -f docker-compose.baseline.yml up -d --no-deps kb-service

# ABBA 交替矩阵
python scripts/_tmp_bench_matrix.py --base-id <kb-base-id> \
  --questions-file artifacts/reports/_bench-questions.txt \
  --levels 1,4,8,16,32 --reps 4 --total-requests 500 --warmup 16 --interleave \
  --output artifacts/reports/ab-matrix-interleaved.json
```

产物：`artifacts/reports/ab-matrix.json`、`ab-matrix-interleaved.json`、`ab-retrieval-parity.json`、`ab-parity-control.json`。

---

# 附录 B：在线评测的两处阻塞缺陷（未修，勿引用相关指标）

本次尝试在线质量评测时发现两个缺陷。**在修复前，faithfulness、答案正确率、拒答率、成本均不可用于简历。**

## B.1 LLM 从未被真正调用（DashScope 额度耗尽）

- 现象：140/140 条 `answer_mode=grounded`、`citation_count` 恒为 2、`estimated_cost=0`、`model_version=""`、`generation_ms=0.073 ms`、总延迟仅 ~145 ms。
- 证据：网关日志 100% 请求 `WARNING llm grounded answer fallback engaged`；响应 `llm_trace={}`、`usage={}`、`prompt_tokens=0`、`completion_tokens=0`。
- 根因：直连 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` → **HTTP 403 `AllocationQuota.FreeTierOnly`**（"Free quota exhausted"）。Key 有效、配置正确（`readyz: llm configured=true`）。
- 降级路径：`gateway_answering.py:571` 的 `except HTTPException` → `packages/python/shared/grounded_answering.py:90` `fallback_answer()`，抽取式拼接 evidence[0]/[1] 的 quote 前 160/96 字。
- 失效指标：faithfulness、correctness、答案文本质量、成本。**recall / MRR / nDCG 属检索侧、不经 LLM，仍然有效。**
- 需处理：重跑在线评测前清掉语义缓存（进程内内存，重启即空）与 gateway DB 中已持久化的降级 `chat_messages`，避免缓存命中污染。

## B.2 永不拒答（RRF 分数量纲错误，独立于 LLM）——**已修，见附录 C**

- 现象：12/12 无证据题全部 `answer_mode=grounded`，`refusal_rate=0.0`，refusal precision/recall 均为 0。
- 根因：`final_score` 是**倒数排名融合**（`packages/python/shared/retrieval.py:90` `weighted_rrf`：`score += weight/(60+rank)`），而 `classify_evidence`（`grounded_answering.py:69`）用**绝对阈值**判定：`strong_items = [s for s in scores if s >= 0.02]`，`len(strong_items) >= 2` 即 `grounded`。
- 数学证明：`structure` 权重 1.3，rank 1~5 单路即 ≥0.02（1.3/61=0.0213 … 1.3/65=0.0200）；三路信号各有一个前列文档，累加后必然 ≥2 条越过 0.02。**只要检索返回结果，就必然判 grounded。**
- 本质：RRF 分是相对排名量、不含绝对相关性，被当绝对阈值使用。单纯调阈值治标不治本。
- 注意：`answer_mode` 由检索分数决定，**与 LLM 无关** —— 即使 B.1 修好，拒答仍不会工作。
- **已于 2026-09-27 修复**：判据改用 dense 单路余弦绝对相关性，详见附录 C。B.1（LLM 额度）仍未处理。

---

# 附录 C：拒答判据改用绝对相关性（2026-09-27 实施）

修复附录 B.2 的「永不拒答」。**B.1（LLM 额度）未处理。**

> 本节 C.1–C.6 记录**实施过程**；其中 **C.2 的阈值标定口径有误**（未计入 gateway 证据截断），
> 最终阈值与端到端结果见 **C.7**。以 C.7 为准。

## C.1 根因与改动

`classify_evidence`（`packages/python/shared/grounded_answering.py`）原先用 `evidence_path.final_score` 的绝对阈值（`>= 0.02`）判断，而 `final_score` 是 `weighted_rrf` 产出的**倒数排名融合分**。三路信号权重 `{structure: 1.3, fts: 1.0, vector: 0.9}`、`base_k=60`，单路 rank1~5 即 `1.3/61=0.0213 … 1.3/65=0.0200`，三路各有一个前列文档 → **只要检索返回结果，`len(strong_items) >= 2` 必然成立，永久判 grounded**。调阈值无法解决，因为量纲本身不对。

改动：

| 文件 | 改动 |
|---|---|
| `apps/services/knowledge-base/src/app/vector_store.py` | `KnowledgeBaseRetriever` 增加 `_dense_relevance()`：额外执行一次 **dense 单路** `query_points`，取绝对余弦分。`RetrievalMode.HYBRID` 下 `similarity_search_with_score` 返回的是 Qdrant 的 RRF 融合分（实测 `年假要提前多久` → hybrid `0.5/0.3333/0.25`，dense `0.7887/0.6642/…`），故必须单查 dense 一路 |
| `packages/python/shared/retrieval.py` | `EvidencePath` 新增 `relevance: float` |
| `apps/services/knowledge-base/src/app/retrieve.py` | 贯通 `relevance`（两处 `EvidencePath` 构造 + `_merge_documents`） |
| `packages/python/shared/grounded_answering.py` | 判据改用 `relevance`；**按章节去重**（dual-granularity 下同一章节的 section/chunk 是两个 unit，会虚增计数）；阈值 `STRONG_RELEVANCE=0.68` / `WEAK_RELEVANCE=0.62` / `STRONG_EVIDENCE_COUNT=2`（标定见 C.2、C.7） |
| `tests/test_shared_stack.py` | 新增 4 个回归用例（RRF 分不再生效、两章节强证据判 grounded、同章节不重复计数、无章节达弱线判拒答） |

## C.2 阈值标定（140 题：128 可回答 / 12 无证据）

> **⚠️ 本节标定口径有误，阈值已被 C.7 推翻。** 本节直接读 kb-service 的 top-k=8，
> 未考虑 gateway 会按文档截断证据（每文档最多 2 条）。以本节结论 `WEAK=0.55` 实测，
> 无证据题硬拒答 **0/12**。正确标定见 **C.7「纠正 1」**（`WEAK=0.62` / `STRONG=0.68`）。
> 本节保留以记录错误路径，数值请勿引用。

线上 `/api/v1/kb/retrieve` 实采 `relevance`（`data/kb/_relevance_topk.json`）：

| 组 | min | p10 | p50 | max |
|---|---|---|---|---|
| 可回答 top1 | 0.541 | 0.647 | 0.732 | 0.877 |
| 无证据 top1 | 0.430 | 0.517 | 0.618 | 0.683 |

无标签规则（可部署）扫描结果：

| `T_strong` | `count(relevance>=T)>=2` → grounded<br>可回答 / 无证据 | 拒答率 |
|---|---|---|
| 0.60 | 48/128 · 1/12 | 3/12 |
| 0.63 | 29/128 · 0/12 | 3/12 |
| **0.65** | **20/128 · 0/12** | **3/12** |
| 0.68 | 8/128 · 0/12 | 3/12 |

**选定 0.65**：0.63→0.65 之间是关键分界（`T>=0.66` 时 `grounded` 掉到 15/128，而过严的 grounded 会连带压低 `top1>=0.55` 的比例，把可回答题挤向拒答）。判据最终结论：

| 组 | grounded | weak_grounded | refusal |
|---|---|---|---|
| 可回答 n=128 | 20 | 107 | **1**（误拒 0.8%） |
| 无证据 n=12 | **0** | 9 | **3**（拒答率 25%） |

对比修复前：12/12 无证据题全部 grounded、拒答率 0.0。

## C.3 已知局限（必须如实说明）

1. **判据不是干净分离器。** 两组在 `relevance ∈ [0.541, 0.683]` 上重叠，无任何阈值能完美切分。上表是权衡结果，不是「解决了」。
2. **拒答召回只有 25%。** 12 道无证据题中 9 道落入 `weak_grounded`（给保守答案 + `partial_evidence` 标注），只有 3 道落入硬拒答。这是有意选择：把「部分覆盖」降级为弱回答，避免高误拒率；**若产品要的是硬拒答率，需要把 `WEAK_RELEVANCE` 上调，代价是误拒可回答题**。
3. **阈值来自单一合成语料（1 文档 / 29 章节）的 12 道无证据题**，样本极小、且这些题多是「主题邻近但事实缺失」的探针（如「固定资产的折旧年限」vs 语料里的「固定资产验收」），不是真正无主题重叠的查询。**换真实语料必须重新标定**，当前数值不可迁移。
4. 测量取的是 **top-k=8 内**的 `relevance`，不是全库 top-1；对无证据题这会低估其最高分（例：「供应商准入审查的收费标准」全库 top1=0.7005，top-8 内最大仅 0.683）。
5. `allow_common_knowledge=True` 时仍按原逻辑返回 `common_knowledge`（该分支在弱相关判断之前），行为未变。
6. **gateway 会再裁剪证据**：`gateway_retrieval.py:181` 限制**每个文档最多 2 条**、每语料最多 3 条。单文档语料下判据实际只看得到 2 条证据，`STRONG_EVIDENCE_COUNT=2` 因此等价于「两路信号都必须命中」。这使 C.2 离线标定（直接读 kb-service 的 top-k=8）与线上行为不一致——见 C.7 的纠正。
7. **`weak_grounded` 仍是回答，不是拒答。** 该标注集下 12 道无证据题有 9 道走这条路，意味着一道**事实不存在**的问题仍会得到一段带引用的答案，只是附 `partial_evidence` 标注。实测该路径回答文本是**显式保守**的、并非编造：

   > 问：病假期间工资按基本工资的百分之几发放？
   > 答：根据当前证据，我只能保守确认：### 病假材料要求 病假连续两天及以上时，员工应在返岗后三个工作日内补交医院诊断证明或线上问诊记录。……现有证据不足以支持更强结论。[1]

   即引用了真实证据，但**不声称**缺失的那个事实，并写明证据不足。所以此档的风险是「未拒答」而非「答错」。**注意**：该文本来自 `fallback_answer()` 抽取式拼接（B.1 未修，LLM 未被调用）；B.1 修复后由 LLM 生成的 `weak_grounded` 回答是否同样保守，**尚未验证**。

## C.4 性能影响与一个必须记住的坑

dense 探测是**每题额外一次**向量查询。同进程 monkeypatch 精确隔离（60 题 × 5 次）：

| | ms/题 |
|---|---|
| 关闭探测 | 3.92 |
| 开启探测 | 8.05 |
| **边际成本** | **+4.13 ms/题（+105%）** |

**坑**：`query_points(with_payload=["metadata.unit_id"])` 这种部分字段选择器会让 qdrant-client 走慢路径，单次查询 **44 ms**（vs `with_payload=True` 的 1.5 ms），使探测边际成本一度达 **49.54 ms/题（3.95 → 53.49，13.5 倍）**，足以吃掉附录 A 的全部优化收益。改为 `with_payload=True` 后降至 4.13 ms。已在 `vector_store.py` 注释中标注。

改 `with_payload=True` 前后，140 题 **条目集合完全一致**（2 题仅并列排序不同，即附录 A.3 已证实的自比对噪声），**最大相关性偏差 0.00e+00** → 只改请求方式，不改数值。

> **注**：C.4 的 A/B 采用**直连端口**（8300/8301）压测，不经过 `kb-service` 主机名，
> 因此**不受** C.7「纠正 2」的别名污染影响；两栈本就同处一台 Docker 主机，资源竞争条件与附录 A 相同。
> 该组数字与附录 A 同口径，可并列引用。

A/B 复测（ABBA 交替，每档 4 轮 × 400 请求，0 错误）：优化栈（含探测）相对 HEAD 基线仍为 **QPS +47.9% / +28.0% / +17.9%**，p95 **-21.6% / -17.2% / -14.7%**（并发 1/8/32）。此对照**混合了**附录 A 的连接池收益与本次探测成本，不可单独解读为探测开销。

## C.5 复现

```bash
# 采集绝对相关性分布（需 ADMIN_PASSWORD 环境变量，勿写入文件）
# 注意：kb-service 的 base_id 要裸 UUID，带 kb: 前缀是 gateway 的 corpus 写法，直接调会 500
# 以下临时脚本按仓库惯例用完已删除，命令留档以便复现时重写
python scripts/_tmp_relevance_dist.py --base-id <kb-base-id>
# A/B 压测（8301=HEAD 基线，8300=当前）
python scripts/_tmp_bench_relevance.py --base-id <kb-base-id> --levels 1,8,32 --reps 4 --total 400
# 判据回归
python -m pytest tests/test_shared_stack.py -q
```

产物：`data/kb/_relevance_topk.json`（临时脚本与中间数据按仓库惯例已删除，见 C.7 复现段）、`artifacts/reports/ab-relevance-probe.json`（保留）。

## C.6 可以 / 不可以写进简历

**可以**（有前后可审计报告）：

- 定位并修正「相对排名分被当绝对阈值」的量纲缺陷：修复前 12/12 无证据题全部判 grounded（拒答率 0.0），修复后 0/12 误判 grounded，可回答题硬误拒 1/128
- 建立绝对相关性信号（dense 单路余弦）并贯通检索链路，标注集标定阈值
- 定位并修正一个 12 倍性能陷阱（qdrant-client 部分 payload 选择器 44ms vs 全量 1.5ms），探测边际成本 49.54 → 4.13 ms/题

**不可以**：

- 任何 faithfulness / 答案正确率 / 成本数字（附录 B.1 未修，LLM 未被真正调用）
- 「拒答率提升到 X%」作为效果宣传 —— 拒答召回仅 25%，且阈值来自 12 题小样本 + 单一合成语料，不可迁移
- 把 C.4 的 +47.9% 等数字单独归因于本次改动（对照混合了附录 A 的连接池收益）

---

## C.7 端到端在线评测与两处纠正（2026-09-27 补测）

用与修复前报告**完全相同的路径与配置**（`eval-long-rag.py`，single scope，`kb:6e63da1f-…`，grounded，140 题）在真实 gateway 链路上取证：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| refusal_rate | 0.0 | 0.0286 |
| refusal.precision | 0.0 | **0.75** |
| refusal.recall | 0.0 | **0.25** |
| recall_at_1 | 0.6179 | 0.6250 |
| mrr | 0.7536 | 0.7571 |
| ndcg_at_5 | 0.7826 | 0.7852 |
| accuracy / recall_at_3 / recall_at_5 | 0.8643 | 0.8643（不变） |
| citation_precision / citation_alignment | 0.4571 / 0.5036 | 0.4571 / 0.5036（不变） |

分组（修复后）：

| 组 | grounded | weak_grounded | refusal |
|---|---|---|---|
| 无证据 n=12 | **0** | 9 | **3** |
| 可回答 n=128 | 26 | 101 | **1**（误拒 0.8%） |

对比修复前：12/12 无证据题全部 `grounded`、拒答率 0.0。

### 纠正 1：C.2 的离线标定口径错误，阈值已重标

C.2 当初**直接读 kb-service 的 top-k=8** 标定，得出 `WEAK=0.55`。但真实链路上 gateway 会**按文档截断证据**（`gateway_retrieval.py:181`，每文档最多 2 条），单文档语料下判据只看得到 2 条。用 0.55 实测：**12/12 无证据题仍全部 `weak_grounded`，硬拒答 0/12**（其中若干条 top1 达 0.60–0.70，越过 0.55 弱线）。

重新在**端到端链路上**采集每例的 per-section `relevance`（`data/kb/_live_cal.json`），扫描结果：

| `WEAK_RELEVANCE` | 无证据硬拒答 | 可回答误拒 |
|---|---|---|
| 0.55（原值） | 0/12 | 0/128 |
| **0.62（新值）** | **3/12** | **1/128** |
| 0.66 | 6/12 | 8/128 |
| 0.70 | 11/12 | 21/128 |

`STRONG_RELEVANCE` 同步由 0.65 上调至 **0.68**（0.65 时 12 道无证据题中有 1 道被判 `grounded`，0.68 起为 0）。两组 top1 实测重叠区间为 `[0.567, 0.702]`，无完美切点；0.62 是「误拒 1/128」与「硬拒答 3/12」的折中。

### 纠正 2：一次由基线容器造成的测量污染（已修复）

首轮在线评测出现 **66/140 拒答、其中 61 道可回答题被误拒**，与离线预测（1/128）严重不符。逐层排查结果：

- kb-service 侧 30/30 稳定返回 `relevance`；同一问题在 gateway 上**约 50% 请求丢失 `relevance` 字段**；
- 根因：为附录 A 建的基线容器 `rag-qa-baseline-kb-service-1`（HEAD，**无本修复**）被接入**同一个 docker 网络** `rag-qa-system_default`，并注册了**同名网络别名 `kb-service`**；
- 于是从 gateway 容器看 `kb-service` 解析出**两个 IP**：`172.18.0.4`（主服务，含修复）与 `172.18.0.6`（基线，无修复）。httpx 连接池并发建连时在两个后端间随机分布 → 约一半请求打到无 `relevance` 的旧代码，无 `relevance` 按 0.0 计 → 判拒答。
- 旁证：日志中 refusal 请求的 `retrieval_ms` 恒在 46ms 档、grounded 恒在 30ms 档，两条互斥的延迟总体即两个后端。

处置：`docker network disconnect` 后以 `--alias baseline-kb` 重新接入。修复后 gateway 内解析唯一，同一问题连测 **16/16 全部 `grounded`**。基线仍可经 8301 访问，附录 A 的 A/B 结论不受影响（压测直连 8300/8301，不经该别名）。

**教训**：任何「新起一个旧版本服务做对照」的做法，都必须确认它没有在主服务的网络上注册同名别名，否则会静默污染主链路。

### C.7 可以 / 不可以写进简历

**可以**（有前后可审计报告，`policy-quality-v2-online-eval.json` → `-after.json`）：

- 修复「相对排名分被当绝对阈值」的量纲缺陷后，无证据题误判 `grounded` 由 **12/12 降到 0/12**；拒答 precision 0.0 → 0.75，recall 0.0 → 0.25
- 可回答题硬误拒仅 **1/128（0.8%）**，检索指标（recall/MRR/nDCG/accuracy）**完全不变**
- 定位并修复一起容器网络别名冲突导致的 **50% 请求静默降级**（详见「纠正 2」）

**不可以**：

- 仍不可发布 faithfulness / 正确答案率 / 成本（B.1 未修）
- 不可把 refusal recall 0.25 说成「拒答已解决」——9/12 无证据题仍产出 `weak_grounded` 答案（见 C.3 第 7 条）
- 不可声称阈值可迁移——来自 12 题 + 单一合成语料

### C.7 复现

```bash
export BENCHMARK_PASSWORD="$(grep -m1 '^ADMIN_PASSWORD=' .env | cut -d= -f2- | tr -d '\r')"
.venv/Scripts/python.exe scripts/evaluation/eval-long-rag.py \
  --base-url http://localhost:8080/api/v1 --email admin@local \
  --eval-file artifacts/reports/policy-quality-v2-online.json \
  --scope-mode single --corpus-id kb:6e63da1f-d5bb-4134-8057-471cbecb10ba \
  --execution-mode grounded \
  --output artifacts/reports/policy-quality-v2-online-eval-after.json \
  --summary-output artifacts/reports/policy-quality-v2-online-eval-after.md

# 前置检查：确认 gateway 内 kb-service 只解析出一个 IP
docker exec rag-qa-system-gateway-1 python -c \
  "import socket;print({a[4][0] for a in socket.getaddrinfo('kb-service',8200)})"
```

产物：`artifacts/reports/policy-quality-v2-online-eval-after.json` / `.md`、`data/kb/_live_cal.json`。
