# RAG-QA 全栈性能重设计 — 实施计划

> 范围:全套 L0-L3 + 物理删除死代码 + 单机低门槛演示形态(用户 2026-07-16 确认)
> 原则:外科式修改,不推倒重写。每阶段绑定验证,失败即停并回报。

## 诊断结论(经三路子代理 + 精读交叉验证)

系统"外表重、运行时轻":默认问答热路径 = 一次检索 + 一次 LLM。大量"重"是死代码与未启用的展示功能。真正瓶颈少而明确。

---

## Phase 0 — 基线与安全网(动手前)

- 新建工作分支 `perf/redesign`。
- 跑现有测试记录基线通过数;`docker compose config --quiet` 通过。
- 记录一次检索延迟基线(现有 eval/retrieve 脚本)。
- 验证:基线可复现,后续每阶段与之对比。

## Phase 1(L0)— 零风险清理

1. 删 `rapidocr-onnxruntime`(KB requirements.runtime.txt:18)→ 省 ~130MB(含 cv2)。
2. 删 `qdrant_store.py:205-228` 死代码嵌入(embed_passages/embed_query/_get_fastembed_model),同步更新仅有的 tests/scripts 引用。
3. 删 docker-compose `AI_*` 冗余透传(48-80 行,代码已 LLM_→AI_ fallback,保留 LLM_ 一套)。
4. 新建 `.env.minimal`(约 12 项必填:JWT_SECRET/POSTGRES_*/两 DSN/QDRANT_URL/LLM_*)。
- 验证:构建镜像对比体积;`docker compose config`;启动冒烟 + healthz。

## Phase 2(L2)— 物理删除死代码(13 模块 + 关联测试)

- 删模块文件:agent_orchestrator/metacognition/error_recovery/guardrails、context_compressor、memory_extractor/injection/integrator、complexity_classifier、instruction_merger、ttft_optimizer、scene_templates、request_coalescer + instruction_hotreload。
- 整删专测死码的测试:test_agent_metacognition、test_agent_orchestration、test_memory_enhancement 等。
- 外科式编辑混测文件(保留活码用例):test_agent_capabilities(tool_registry)、test_context_optimization(context_window)、test_inference_optimization(semantic_cache)、test_platform_ecosystem*、test_eval_pipeline。
- 验证:全量 import 无断裂(`python -c import app.main`);测试全绿;gateway 启动冒烟。

## Phase 3(L1)— 默认热路径提速【收益最高】

- P3.1 KB:`ensure_qdrant_collection` 移出查询路径,集合/索引在启动或 stack_init 一次性建;create_payload_index 仅集合不存在时建(qdrant_store.py:152-179)。省每查约 9 次 Qdrant 往返。
- P3.2 Gateway:引入 `psycopg_pool.ConnectionPool` 替代 db.py:28 每次新建连接。
- P3.3 KB:三路检索信号 structure/fts/vector 并发(asyncio.gather/线程池,retrieve.py:285-300)。
- P3.4 Gateway:模块级共享 `httpx.AsyncClient`(keepalive + limits,挂 lifespan),替换各处每请求新建。
- P3.5 KB:async 路由检索包进 `run_in_threadpool`(kb_query_helpers.py:79、kb_query_routes.py:204)。
- P3.6 Gateway:workflow_run 三写合并为终态一次;审计改后台 fire-and-forget;去重 session SELECT。
- P3.7 KB:消除同文档双份嵌入(worker.py:182 section + :190 chunk)——按 unit_type 打标+检索过滤,或明确取舍其一。
- P3.8 语义缓存:因用伪嵌入(semantic_cache.py:31),默认关闭或改为精确 key 缓存(不宣称"语义")。
- 验证:每项前后延迟/往返数对比;eval pipeline 不劣化;并发压测吞吐提升。

## Phase 4(L3)— 单机低门槛形态

- P4.1 新增文件系统存储后端(实现 ObjectStorageClient 接口,文件落 KB_BLOB_ROOT,上传改服务端中转、下载经 KB 服务),`OBJECT_STORAGE_PROVIDER=filesystem` 可去 minio 容器。**权衡:放弃 S3 预签名直传。**
- P4.2 pgvector→postgres:16:改 gateway 001 / KB 002 迁移,去 `CREATE EXTENSION vector`、VECTOR(512) 列、HNSW 索引、kb_embedding_cache 表(仅影响全新安装);去掉自定义 postgres 镜像。
- P4.3 合并 kb-worker 进 kb-service:worker 轮询循环在 lifespan 后台线程运行(可 KB_RUN_WORKER 开关),单机减一容器。
- P4.4 重写 docker-compose 为单机最小 profile;健康检查 `/healthz`→`/readyz` 深检依赖。
- P4.5 精简 langchain-community:FastEmbedEmbeddings 换 langchain_qdrant 原生/直连 fastembed,省 ~38MB。
- 验证:全新 `docker compose up` 最小组件跑通上传→索引→问答闭环;/readyz 通过;镜像体积对比。

---

## 两个必须知晓的权衡

1. **去 minio** 需新增文件系统存储后端并改上传流(非纯配置),是 L3 最大工作项;完成后上传走服务端中转而非浏览器直传 S3。
2. **pgvector 迁移编辑仅对全新安装生效**;已有数据库需单独降级迁移。演示形态默认全新安装,可接受。

## 交付标准
- 每阶段独立可验证、可回滚;测试全绿;README/docs 同步更新变化点;.codex 留验证记录。
