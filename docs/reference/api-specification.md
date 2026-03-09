# API 规范

当前仓库默认以零数据基线运行，不预置任何知识库文档、评测 fixture 或演示报告。所有上传、检索和问答数据都需要显式提供。

## 1. 错误模型

统一错误响应：

```json
{
  "detail": "request validation failed",
  "code": "validation_error",
  "trace_id": "gateway-xxxx",
  "errors": []
}
```

- `detail`: 人类可读错误信息
- `code`: 稳定错误码
- `trace_id`: 链路追踪 ID
- `errors`: 仅在校验错误时出现

## 2. 健康检查与指标

### `GET /healthz`

仅用于进程存活探针。

### `GET /readyz`

- `gateway` 检查自身数据库、`kb-service` readiness 和 LLM 配置状态
- `kb-service` 检查数据库和对象存储
- 依赖未就绪时返回 `503`

### `GET /metrics`

- `gateway` 与 `kb-service` 都暴露 Prometheus 文本指标
- `kb-worker` 可通过 `KB_WORKER_METRICS_PORT` 暴露独立 metrics 端口

## 3. 认证

### `POST /api/v1/auth/login`

```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

响应：

```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "admin@local",
    "role": "platform_admin",
    "permissions": ["kb.read", "kb.write", "kb.manage", "chat.use", "audit.read"],
    "role_version": 1
  }
}
```

### `GET /api/v1/auth/me`

返回当前登录用户及其 `permissions`。

默认角色映射：

- `admin -> platform_admin`
- `member -> kb_editor`

## 4. 统一聊天

### `POST /api/v1/chat/sessions`

创建会话并持久化 scope。

### `GET /api/v1/chat/sessions/{id}/messages`

按创建时间升序返回消息。

### `POST /api/v1/chat/sessions/{id}/messages`

请求头：

- `Authorization: Bearer <token>`
- `Idempotency-Key: <optional>`

请求体：

```json
{
  "question": "报销审批需要哪些角色签字？",
  "scope": {
    "mode": "single",
    "corpus_ids": ["kb:uuid-1"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

- `allow_common_knowledge`: 默认为 `false`。开启后，当知识库未检索到足够证据时，网关允许回退到通用大模型问答，并在答案中附带风险提示。
- 常识兜底链路可通过环境变量 `LLM_COMMON_KNOWLEDGE_MODEL`、`LLM_COMMON_KNOWLEDGE_MAX_TOKENS`、`LLM_COMMON_KNOWLEDGE_HISTORY_MESSAGES`、`LLM_COMMON_KNOWLEDGE_HISTORY_CHARS` 单独压缩上下文或切到更快模型。
- `answer_mode`: 可能返回 `grounded`、`weak_grounded`、`common_knowledge` 或 `refusal`。

关键响应字段：

- `answer`
- `answer_mode`
- `evidence_status`
- `grounding_score`
- `refusal_reason`
- `citations`
- `evidence_path`
- `trace_id`
- `retrieval`
- `latency`
- `cost`
- `message`

`retrieval.aggregate` 重点字段：

- `empty_scope`
- `document_scope_cache_hit`
- `successful_service_count`
- `failed_service_count`
- `partial_failure`
- `retrieval_ms`
- `sum_service_retrieval_ms`
- `max_service_retrieval_ms`

幂等约束：

- 同 `Idempotency-Key` + 同 payload：返回首次成功结果
- 同 `Idempotency-Key` + 不同 payload：返回 `409 idempotency_conflict`

### `POST /api/v1/chat/sessions/{id}/messages/stream`

- 支持与非流式一致的 `Idempotency-Key`
- SSE 事件顺序：`metadata -> citation -> answer -> message -> done`
- `answer` 为增量期间的累计答案快照；`message` 为最终持久化后的聊天消息对象
- 流式路径会在网关拿到上游 LLM chunk 后立刻向前端转发，不再等待完整回答生成完毕后再切片返回

### `GET /api/v1/audit/events`

由 `gateway` 聚合自身与 `kb-service` 审计事件。

查询参数：

- `service`
- `actor_user_id`
- `resource_type`
- `resource_id`
- `action`
- `outcome`
- `created_from`
- `created_to`
- `limit`
- `offset`

权限要求：

- `audit.read`

## 5. 知识库

### `GET /api/v1/kb/bases`

默认仅返回当前用户创建的知识库；具备 `kb.manage` 的角色可跨用户查看。

### `GET /api/v1/kb/documents/{document_id}`

返回文档详情，并附带：

- `latest_job`
  - `job_id`
  - `status`
  - `attempt_count`
  - `max_attempts`
  - `next_retry_at`
  - `dead_lettered_at`
  - `retryable`

### `GET /api/v1/kb/documents/{document_id}/events`

返回文档处理事件流。

## 6. 分片上传

推荐上传链路：

- `POST /api/v1/kb/uploads`
- `POST /api/v1/kb/uploads/{upload_id}/parts/presign`
- `POST /api/v1/kb/uploads/{upload_id}/complete`
- `GET /api/v1/kb/ingest-jobs/{job_id}`
- `POST /api/v1/kb/ingest-jobs/{job_id}/retry`

### `POST /api/v1/kb/uploads`

请求头：

- `Idempotency-Key: <optional>`

请求体：

```json
{
  "base_id": "uuid",
  "file_name": "policy.pdf",
  "file_type": "pdf",
  "size_bytes": 102400,
  "category": "policy"
}
```

### `POST /api/v1/kb/uploads/{upload_id}/complete`

请求头：

- `Idempotency-Key: <optional>`

响应包含：

- `upload_id`
- `document_id`
- `job_id`
- `document`
- `job`

### `GET /api/v1/kb/ingest-jobs/{job_id}`

关键字段：

- `job_id`
- `status`
- `phase`
- `query_ready`
- `enhancement_status`
- `document_status`
- `query_ready_at`
- `hybrid_ready_at`
- `ready_at`
- `attempt_count`
- `max_attempts`
- `next_retry_at`
- `last_error_code`
- `lease_expires_at`
- `dead_lettered_at`
- `retryable`

常见状态：

- `queued`
- `retry`
- `processing`
- `done`
- `failed`
- `dead_letter`

### `POST /api/v1/kb/ingest-jobs/{job_id}/retry`

权限要求：

- `kb.manage`

行为：

- 仅允许 `failed` 或 `dead_letter` 作业重试
- 会清空 lease、dead-letter 与错误字段并重新入队

### 已弃用：`POST /api/v1/kb/documents/upload`

保留兼容，不再作为默认前端入口。

## 7. 检索与查询

### `POST /api/v1/kb/retrieve`

返回：

- `items`
- `retrieval`
- `trace_id`

当向量检索降级时，`retrieval` 中会包含：

- `degraded_signals`
- `warnings`

### `POST /api/v1/kb/query`

返回字段与统一聊天的证据化结果保持一致。

### `POST /api/v1/kb/query/stream`

流式返回单库问答结果。

## 8. 运行时说明

- 数据库 migration 与对象存储初始化已从服务启动中剥离
- 推荐顺序：

```powershell
make init
make up
```
