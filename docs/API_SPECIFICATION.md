# API Specification

统一入口由 `gateway` 暴露，前端默认只访问 `gateway` 的 `/api/v1/*`。

## 1. Authentication

### `POST /api/v1/auth/login`

请求：

```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

响应：

```json
{
  "access_token": "<token>",
  "token_type": "bearer",
  "user": {
    "id": "11111111-1111-1111-1111-111111111111",
    "email": "admin@local",
    "role": "admin"
  }
}
```

后续请求头：

```http
Authorization: Bearer <access_token>
X-Trace-Id: <optional-client-trace-id>
```

### `GET /api/v1/auth/me`

返回当前用户信息。

## 2. Unified Chat

### `GET /api/v1/chat/corpora`

返回当前用户可见的统一 corpus 列表。

响应字段：

- `corpus_id`: `kb:<uuid>` 或 `novel:<uuid>`
- `corpus_type`: `kb | novel`
- `name`
- `description`
- `document_count`
- `queryable_document_count`

### `GET /api/v1/chat/corpora/{corpus_id}/documents`

返回某个 corpus 下的文档列表。

响应字段：

- `document_id`
- `corpus_id`
- `corpus_type`
- `display_name`
- `status`
- `query_ready`

### `POST /api/v1/chat/sessions`

请求：

```json
{
  "title": "产品评审",
  "scope": {
    "mode": "multi",
    "corpus_ids": ["kb:uuid-1", "novel:uuid-2"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

### `GET /api/v1/chat/sessions`

返回当前用户的会话列表。

### `GET /api/v1/chat/sessions/{id}`

返回单个会话。

### `GET /api/v1/chat/sessions/{id}/messages`

返回会话消息列表。

### `POST /api/v1/chat/sessions/{id}/messages`

请求：

```json
{
  "question": "请总结审批流程",
  "scope": {
    "mode": "single",
    "corpus_ids": ["kb:uuid-1"],
    "document_ids": ["doc-uuid-1"],
    "allow_common_knowledge": false
  }
}
```

响应固定字段：

- `answer`
- `answer_mode`
- `strategy_used`
- `evidence_status`
- `grounding_score`
- `refusal_reason`
- `citations[]`
- `evidence_path[]`
- `provider`
- `model`
- `usage`
- `scope_snapshot`
- `trace_id`
- `retrieval`
- `latency`
- `cost`

`answer_mode` 可能值：

- `grounded`
- `weak_grounded`
- `refusal`

`evidence_status` 可能值：

- `grounded`
- `partial`
- `insufficient`

### `POST /api/v1/chat/sessions/{id}/messages/stream`

SSE 事件：

- `metadata`
- `citation`
- `answer`
- `done`

说明：

- 网关会在响应头中返回 `X-Trace-Id`
- `retrieval.aggregate` 会汇总各下游服务的 candidate 数与 retrieval 耗时
- `latency` 会返回 `scope_ms / retrieval_ms / generation_ms / total_ms`
- `cost` 会优先依据 `AI_PRICE_TIERS_JSON` 按输入 token 所在档位估算；未配置阶梯时才回退到 `AI_INPUT_PRICE_PER_1K_TOKENS` 与 `AI_OUTPUT_PRICE_PER_1K_TOKENS`
- `cost` 额外包含 `pricing_mode / input_price_per_1k_tokens / output_price_per_1k_tokens / selected_tier / currency`

## 3. Novel Upload and Retrieval

### `POST /api/v1/novel/uploads`

创建 multipart 上传会话。

请求：

```json
{
  "library_id": "uuid",
  "title": "三体",
  "volume_label": "第一卷",
  "spoiler_ack": true,
  "file_name": "three-body.txt",
  "file_type": "txt",
  "size_bytes": 35651584
}
```

### `GET /api/v1/novel/uploads/{upload_id}`

返回上传会话与已上传 part 列表。

### `POST /api/v1/novel/uploads/{upload_id}/parts/presign`

请求：

```json
{
  "part_numbers": [1, 2, 3]
}
```

响应：

- `uploaded_parts[]`
- `presigned_parts[]`
- `chunk_size_bytes`

### `POST /api/v1/novel/uploads/{upload_id}/complete`

请求：

```json
{
  "parts": [
    {
      "part_number": 1,
      "etag": "\"etag-value\"",
      "size_bytes": 5242880
    }
  ],
  "content_hash": ""
}
```

响应：

- `document_id`
- `job_id`
- `document`

### `GET /api/v1/novel/ingest-jobs/{job_id}`

返回小说上传任务状态。

关键字段：

- `status`
- `phase`
- `query_ready`
- `document_status`
- `document_enhancement_status`
- `query_ready_until_chapter`
- `query_ready_at`
- `hybrid_ready_at`
- `ready_at`

### `POST /api/v1/novel/retrieve`

请求：

```json
{
  "library_id": "uuid",
  "question": "主角第一次拿到关键线索是在什么时候？",
  "document_ids": [],
  "limit": 8
}
```

返回统一 evidence block 列表。

新增响应字段：

- `retrieval`
- `trace_id`

## 4. KB Upload and Retrieval

### `POST /api/v1/kb/uploads`

请求：

```json
{
  "base_id": "uuid",
  "file_name": "policy.pdf",
  "file_type": "pdf",
  "size_bytes": 2987771,
  "category": "制度"
}
```

### `GET /api/v1/kb/uploads/{upload_id}`

返回上传会话与已上传 part 列表。

### `POST /api/v1/kb/uploads/{upload_id}/parts/presign`

请求：

```json
{
  "part_numbers": [1, 2, 3]
}
```

### `POST /api/v1/kb/uploads/{upload_id}/complete`

请求结构与 novel 相同。

### `GET /api/v1/kb/ingest-jobs/{job_id}`

返回企业文档上传任务状态。

### `POST /api/v1/kb/retrieve`

请求：

```json
{
  "base_id": "uuid",
  "question": "报销审批需要哪些角色签字？",
  "document_ids": [],
  "limit": 8
}
```

新增响应字段：

- `retrieval`
- `trace_id`

## 5. Legacy Compatibility

以下旧接口仍保留兼容，但前端主流程已切换到 multipart 上传和统一聊天：

- `POST /api/v1/novel/documents/upload`
- `POST /api/v1/novel/query`
- `POST /api/v1/novel/query/stream`
- `POST /api/v1/kb/documents/upload`
- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`
- `POST /api/v1/ai/chat`

## 6. Evidence Block Shape

`citations[]` 的主要字段：

- `unit_id`
- `document_id`
- `document_title`
- `section_title`
- `chapter_title`
- `scene_index`
- `char_range`
- `quote`
- `corpus_id`
- `corpus_type`
- `service_type`
- `evidence_path`

`evidence_path` 的主要字段：

- `structure_hit`
- `fts_rank`
- `vector_rank`
- `final_rank`
- `final_score`

## 7. Error Codes

常见状态码：

- `400`: 参数错误或 scope 越界
- `401`: 未认证或 token 无效
- `404`: 资源不存在
- `502`: 网关调用下游失败
- `503`: AI provider 不可用或未配置
