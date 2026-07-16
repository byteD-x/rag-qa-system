# Phase 4 P4.3 合并 kb-worker 进 kb-service — 验证记录

日期:2026-07-16

## 改动
- `worker.py`:新增 `run_worker_loop(stop_event=None, *, enable_metrics=True)`,用 `stop_event.wait(POLL_SECONDS)` 替 `time.sleep` 支持优雅停止;`enable_metrics=False` 时不绑指标端口(避免与 service 冲突)。`run_forever()` 改为委派 `run_worker_loop(stop_event=None, enable_metrics=True)`,独立 kb-worker 进程行为不变。
- `main.py`:新增 `_worker_enabled()` 读 `KB_RUN_WORKER`(默认 false);lifespan 开启时起 daemon 线程跑 `run_worker_loop(stop_event, enable_metrics=False)`,shutdown 时 `worker_stop.set()` + `join(timeout=10)` 再关 scheduler。

## 设计要点(以可运行无 bug 为先)
- **默认关闭**:KB_RUN_WORKER 未设时行为与改动前完全一致(独立 kb-worker 进程),零风险。单机形态才设 true 省一个容器。
- **优雅停止**:原 `while True`+`time.sleep` 无停止信号;改为 stop_event 响应式,shutdown 可干净退出。
- **并发安全**:`_claim_next_job` 用 `FOR UPDATE SKIP LOCKED` + 租约,进程内 worker 与独立 kb-worker 并存也不会重复领取。
- **指标端口**:进程内 enable_metrics=False,不绑 9300。

## 验证
- 编译通过;KB app.main 导入 OK;`_worker_enabled()` 默认 False、KB_RUN_WORKER=true 时 True。
- 分组测试 33/33 全绿。

## 未验证(无 Docker,UNVERIFIED)
- 进程内 worker 线程与查询路径**共享 `_get_vector_store` 的 lru_cache(embedding 模型)**:索引写入与查询读取命中同一 QdrantVectorStore 实例的线程安全,未在活体并发下验证。独立进程模式(默认)不涉及此共享。
- 单机 `KB_RUN_WORKER=true` 下 service 进程内后台索引 → 查询闭环,未活体运行验证。
- 建议:单机启用前在有 Docker 环境跑一次上传→索引→查询闭环确认。
