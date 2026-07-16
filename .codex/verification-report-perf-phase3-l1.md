# Phase 3(L1)默认热路径提速 — 验证记录

日期:2026-07-16
环境约束:本机无 Docker,无法测活体延迟/吞吐。验证口径 = 结构分析 + 分组测试全绿 + 离线检索质量非劣化 + import 冒烟。

## 已完成(均已核实断言、编译、测试)

- **P3.1 集合索引移出查询路径**:qdrant_store.ensure_qdrant_collection 的 8 个 create_payload_index 移进 `if not collection_exists` 块内;vector_store.build_vector_retriever 去掉每查 ensure_qdrant_collection。集合由 stack_init 启动与索引写入时保证;缺失时 search_vector_documents 已有 try/except 降级。省每查约 9 次 Qdrant 往返。
- **P3.3 三路检索并发**:retrieve._run_signal_retrievers 用 ThreadPoolExecutor(max_workers=3) 并发 structure/fts/vector。各检索器内部独立开连接,线程安全;异常语义保留(structure/fts 传播,vector 内部降级)。总耗时约等最慢一路。
- **P3.5 检索包线程池**:kb_query_helpers.build_query_response、kb_query_routes.stream_query_kb 的同步阻塞检索包进 run_in_threadpool,不阻塞事件循环。
- **P3.2 Gateway 连接池**:db.GatewayDatabase 引入 psycopg_pool.ConnectionPool(懒创建、线程安全、min_size=1/max_size 可配),替代每请求新建连接;main lifespan 关闭池;requirements 增 psycopg_pool==3.3.1。测试全部 monkeypatch gateway_db.connect,对改动透明。
- **P3.8 语义缓存诚实化**:确认 GATEWAY_RESPONSE_CACHE_SEMANTIC_ENABLED **默认 False**(L2 本就默认关闭,计划核心诉求已满足)。embed_query_text 本地后端是哈希桶嵌入(词法非语义),仅配 EMBEDDING_API_URL 外部服务才语义。改 docstring 诚实说明,不再无条件宣称"语义"。未改成纯精确 key——那会删掉配外部嵌入时合法可用的功能。

验证:分组测试 33/33 全绿;离线检索质量 recall@1/@3/mrr/ndcg 保持全 1.0(未劣化);API_ROUTE_INDEX 因行号漂移刷新;compileall 通过。

## 有依据暂缓(非"失败",是无法在本环境负责任地验证/或计划与代码不符)

- **P3.7 消除同文档双份嵌入**:section(粗粒度带标题/摘要)与 chunk(细粒度窗口)是不同检索粒度,都进同 collection、检索混用。删任一路改变召回,而无 Docker + 离线 fixture 合成满分 → 无法验证非劣化。且它在摄入/索引时发生,非查询热路径。计划本身留了"或取舍其一"余地。**待用户决策**或在可跑真实评测的环境处理。
- **P3.4 共享 httpx.AsyncClient**:真瓶颈,但触及 ~11 处入口/8 文件;ai_client 处测试直接 monkeypatch httpx.AsyncClient(改则需重做测试);keepalive/连接复用收益在无 Docker 下无法测量。行为等价的纯优化,最适合在有 Docker、能集成测量的环境整体重构。**暂缓**。
- **P3.6 workflow 写合并 / 审计后台化 / session 去重**:
  - workflow 中间那次 update(stage=generation_completed,RESUME_TARGET_PERSISTENCE)经查是**恢复检查点**(LLM 生成后、持久化前落状态,崩溃可从此恢复不重跑 LLM;test_chat_workflow_resume 覆盖),**非纯追踪**——计划为旧审阅误判,合并会破坏恢复能力,不做。
  - 审计改 fire-and-forget:审计是安全合规日志,后台化在崩溃时可能丢事件,无 Docker 无法验证运行时行为,风险高,**暂缓**。
  - session 去重 SELECT:需改 session_cost_summary 签名接收预载 session,波及测试打桩;收益小,**暂缓**。

## 结论

Phase 3 收益最高、可验证的三项(连接池 P3.2、集合索引 P3.1、三路并发 P3.3)+ 线程池 P3.5 + 缓存诚实化 P3.8 已落地并验证。其余三项因无 Docker 不可验证或与代码事实冲突而暂缓,均记录理由,待用户决策或移至可测环境。
