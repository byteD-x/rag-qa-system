# 运维手册

## 1. 启动顺序

推荐固定按下面顺序执行：

```powershell
make preflight
make init
make up
make smoke-eval
```

说明：

- `make preflight` 先确认代码和 compose 配置可运行
- `make init` 会先拉起 `postgres`、`minio`、`qdrant`，再执行 `stack-init`
- `make up` 会启动应用服务并等待核心健康检查
- `make smoke-eval` 用运行态链路验证 grounded 与 agent 模式

## 2. 关键服务

本地完整链路至少包含：

- `postgres`
- `minio`
- `qdrant`
- `kb-service`
- `kb-worker`
- `gateway`

检查命令：

```powershell
docker compose ps
.\logs.bat -l ERROR -s gateway kb-service kb-worker
```

## 3. `readyz` 排障

### `gateway /readyz`

重点检查：

- 数据库连接
- `kb-service` 可达性
- LLM 配置状态

### `kb-service /readyz`

重点检查：

- 数据库连接
- 对象存储访问
- `vector_store` 状态

如果 `vector_store` 失败，优先检查：

- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `FASTEMBED_MODEL_NAME`
- `FASTEMBED_SPARSE_MODEL_NAME`

## 4. Qdrant / FastEmbed

当前主链路已经切到 `langchain-qdrant`。

排障建议：

- 先确认 `qdrant` 容器已启动
- 再检查 collection 是否已由 `stack-init` 创建
- 如果历史索引 payload 和当前 metadata 结构不一致，执行：

```powershell
python scripts/dev/reindex-qdrant.py
```

## 5. smoke-eval 失败时看哪里

先确认：

- `.env` 中 `ADMIN_EMAIL`、`ADMIN_PASSWORD` 正确
- `http://localhost:8080/readyz` 可达并返回 `200`
- `http://localhost:8300/readyz` 可达并返回 `200`
- 如在 CI 或容器网络里跑 smoke，可优先使用 `python scripts/dev/smoke_eval.py --wait-for-ready`

再看：

- `artifacts/reports/agent_smoke_report.json`
- `artifacts/reports/agent_smoke_report.md`
- `gateway` 日志
- `kb-service` / `kb-worker` 日志

重点关注报告里的以下字段：

- `suite_version`
- `dataset_version`
- `execution_modes`
- `prompt_versions`
- `model_versions`
- `correctness`
- `faithfulness`
- `citation_alignment`

## 6. 常用验证命令

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
docker compose config --quiet
docker compose ps
```

## 7. AI 平台扩展点排障

### 7.1 Prompt Registry / Model Routing

如果回答链路使用了错误的 prompt 版本或错误模型，优先检查：

- `PROMPT_REGISTRY_JSON` / `PROMPT_REGISTRY_PATH`
- `LLM_MODEL_ROUTING_JSON`
- 响应中的 `llm_trace.prompt_key`
- 响应中的 `llm_trace.prompt_version`
- 响应中的 `llm_trace.route_key`

说明：

- `route_key` 为空，说明当前请求走的是默认模型配置
- `prompt_version` 不符合预期，优先排查 prompt registry 覆盖是否生效
- `model_resolved` 不符合预期，优先排查 model routing 与上游 provider 的模型别名

### 7.2 Cross-Encoder Rerank

当 FTS / vector 命中正常，但最终排序异常时，检查：

- `retrieval.rerank_provider`
- `RERANK_PROVIDER`
- `RERANK_API_BASE_URL`
- `RERANK_MODEL`

说明：

- `rerank_provider=heuristic` 表示当前没有启用外部 rerank，或外部 rerank 失败后已自动回退
- 如果预期使用 cross-encoder，但结果始终是 `heuristic`，优先检查 `/rerank` provider 的网络连通性和返回结构

### 7.3 Layout-Aware Visual Retrieval

当图片或扫描件已经 OCR，但 region 级命中始终不出现时，检查：

- 外部视觉 provider 是否返回了 `layout_hints`
- 外部视觉 provider 是否返回了 `regions`
- ingest 后文档统计里是否出现 `visual_layout_section_count`
- citation 的 `source_kind` 是否出现 `visual_region`

说明：

- 仅本地 OCR 时，系统仍可工作，但通常只会产生 `visual_ocr`
- 要获得表格/区域级检索，需要外部视觉 provider 返回结构化 region 信息
