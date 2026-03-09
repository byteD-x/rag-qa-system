# 运维手册

本文档聚焦企业知识库 RAG 的本地运行与排障。

## 1. 基础检查

确认以下服务都在运行：

- `postgres`
- `minio`
- `gateway`
- `kb-service`
- `kb-worker`

```powershell
docker compose ps
.\logs.bat -l ERROR -s gateway kb-service kb-worker
```

## 2. 初始化缺失

如果接口报表不存在、对象存储桶不存在，或应用启动后立即出现数据库错误，优先检查是否执行了显式初始化：

```powershell
make init
```

等价命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/init.ps1
```

## 3. 上传后长期停留在处理中

优先检查：

- `KB_DATABASE_DSN` 是否正确
- `kb-worker` 是否在运行
- `minio` 是否健康
- 是否已经执行过 `make init`

```powershell
.\logs.bat -f -s kb-service
.\logs.bat -f -s kb-worker
```

重点关注：

- `attempt_count / max_attempts`
- `next_retry_at`
- `lease_expires_at`
- `dead_lettered_at`

如果 job 进入 `dead_letter`，可由具备 `kb.manage` 权限的用户调用：

```text
POST /api/v1/kb/ingest-jobs/{job_id}/retry
```

## 4. 检索结果为空或证据不足

先确认：

- 文档状态已达到 `fast_index_ready` 或更高
- scope 选中了正确知识库
- 问题没有超出文档边界

再看网关与 KB 服务日志：

```powershell
.\logs.bat -f -s gateway kb-service
```

重点关注：

- `trace_id`
- `retrieval_ms`
- `selected_candidates`
- `rewrite_tags`
- `expansion_terms`
- `degraded_signals`
- `partial_failure`

## 5. 分片上传或断点续传异常

优先检查：

- `minio` 与 `kb-service` 是否正常启动
- 预签名 URL 是否可访问
- 上传会话与分片记录是否已落库
- 前端是否发送了稳定的 `Idempotency-Key`

同一个幂等键如果配合不同 payload 重放，会返回：

- `409 idempotency_conflict`

## 6. Metrics / Audit 排障顺序

推荐顺序：

1. 用 `trace_id` 锁定单次请求
2. 到 `GET /api/v1/audit/events` 查操作结果
3. 抓取 `/metrics` 看错误率、降级率、死信量
4. 最后回看 `kb-worker` 日志和文档事件流

常用指标入口：

- `http://localhost:8080/metrics`
- `http://localhost:8300/metrics`

## 7. 本地验证清单

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
docker compose config --quiet
```
