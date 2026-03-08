# Runbook

本文档聚焦企业知识库 RAG 的本地排障。

## 1. 基础检查

先确认以下服务都在运行：

- `postgres`
- `minio`
- `gateway`
- `kb-service`
- `kb-worker`

```powershell
docker compose ps
.\logs.bat -l ERROR -s gateway kb-service
```

## 2. 上传后长期停留处理中

优先检查：

- `KB_DATABASE_DSN` 是否正确
- `kb-worker` 是否在运行
- `minio` 是否健康
- `kb-service` 日志是否有解析或对象存储错误

```powershell
.\logs.bat -f -s kb-service
.\logs.bat -f -s kb-worker
```

## 3. 检索结果为空或证据不足

先确认：

- 文档状态是否已达到 `fast_index_ready` 或更高
- scope 是否选中了正确知识库
- 问题是否超出文档边界

再看网关和 KB 检索日志：

```powershell
.\logs.bat -f -s gateway kb-service
```

重点关注：

- `trace_id`
- `retrieval_ms`
- `selected_candidates`
- `rewrite_tags`

## 4. 上传慢或断点续传异常

先确认：

- `minio` 和 `gateway` 已正常启动
- 浏览器与 MinIO 直传 URL 可访问
- `upload_sessions / upload_parts` 已持久化

验证脚本：

```powershell
python scripts/evaluation/verify-multipart-resume.py --corpus-id <base-id> --file <path> --password <pwd>
```

默认输出会写入 `artifacts/reports/multipart_resume_report.json`。如需与仓库内留档快照对比，可再查看 `docs/reports/`。

## 5. 本地验证清单

```powershell
python scripts/quality/check-encoding.py
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
python scripts/evaluation/run-retrieval-ablation.py
python scripts/evaluation/benchmark-local-ingest.py
docker compose config --quiet
```
