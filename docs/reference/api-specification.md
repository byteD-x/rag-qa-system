# API Specification

本文档描述当前默认启用的企业知识库 RAG API。

## 1. Auth

### `POST /api/v1/auth/login`

请求体：

```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

返回：

```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "admin@local",
    "role": "admin"
  }
}
```

## 2. Unified Chat

### `GET /api/v1/chat/corpora`

返回当前可选知识库列表，`corpus_id` 统一使用 `kb:<uuid>`。

### `GET /api/v1/chat/corpora/{corpus_id}/documents`

返回指定知识库下的文档列表。

### `POST /api/v1/chat/sessions`

```json
{
  "title": "费用制度问答",
  "scope": {
    "mode": "single",
    "corpus_ids": ["kb:uuid-1"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

### `POST /api/v1/chat/sessions/{id}/messages`

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

关键返回字段：

- `answer`
- `answer_mode`
- `evidence_status`
- `grounding_score`
- `citations`
- `evidence_path`
- `trace_id`
- `retrieval`
- `latency`
- `cost`

## 3. KB Upload and Retrieval

### `POST /api/v1/kb/uploads`

```json
{
  "base_id": "uuid",
  "file_name": "policy.pdf",
  "file_type": "pdf",
  "size_bytes": 102400,
  "category": "policy"
}
```

### `GET /api/v1/kb/uploads/{upload_id}`

返回上传 session 与已上传 part 信息。

### `POST /api/v1/kb/uploads/{upload_id}/parts/presign`

```json
{
  "part_numbers": [1, 2, 3]
}
```

### `POST /api/v1/kb/uploads/{upload_id}/complete`

```json
{
  "parts": [
    {"part_number": 1, "etag": "\"etag-1\"", "size_bytes": 5242880}
  ],
  "content_hash": ""
}
```

### `GET /api/v1/kb/ingest-jobs/{job_id}`

常见状态：

- `uploaded`
- `fast_index_ready`
- `hybrid_ready`
- `ready`
- `failed`

### `POST /api/v1/kb/retrieve`

```json
{
  "base_id": "uuid",
  "question": "试用期请假怎么走流程？",
  "document_ids": [],
  "limit": 8
}
```

## 4. LLM 配置

统一问答链路的答案生成默认读取 `LLM_*` 环境变量：

- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_TEMPERATURE`
- `LLM_MAX_TOKENS`
- `LLM_SYSTEM_PROMPT`
- `LLM_EXTRA_BODY_JSON`
- `LLM_PRICE_CURRENCY`
- `LLM_PRICE_TIERS_JSON`
- `LLM_INPUT_PRICE_PER_1K_TOKENS`
- `LLM_OUTPUT_PRICE_PER_1K_TOKENS`

历史 `AI_*` 变量仍可作为兼容别名读取，但不再建议用于新配置。
