# API 规范

本文档描述当前仓库已经实现并对前端开放的核心后端接口，覆盖：

- 统一聊天与工作流
- 知识库上传、治理、检索与调试
- 多源连接器与定时同步
- Agent 工作台与 Prompt 模板库
- 运营分析看板

## 1. 健康检查

### `GET /healthz`

- 用于存活探针
- 返回：`200 {"status":"ok"}`

### `GET /readyz`

- `gateway` 会检查数据库、`kb-service` 和 LLM 配置
- `kb-service` 会检查数据库、对象存储和 Qdrant / vector store
- 任一关键依赖未就绪时返回 `503`

## 2. 认证

### `POST /api/v1/auth/login`

请求：

```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

响应字段：

- `access_token`
- `token_type`
- `user`

## 3. 统一聊天

### `POST /api/v1/chat/sessions`

创建会话并持久化默认 `scope` 与 `execution_mode`。

请求示例：

```json
{
  "title": "报销问答",
  "execution_mode": "agent",
  "scope": {
    "mode": "multi",
    "corpus_ids": ["kb:uuid-1", "kb:uuid-2"],
    "document_ids": [],
    "allow_common_knowledge": false,
    "agent_profile_id": "profile-uuid",
    "prompt_template_id": "template-uuid"
  }
}
```

新增说明：

- `scope.agent_profile_id`：挂载 Agent 工作台中的 persona / 工具配置
- `scope.prompt_template_id`：挂载 Prompt 模板库中的模板

### `PATCH /api/v1/chat/sessions/{id}`

可更新：

- `title`
- `scope`
- `execution_mode`

### `POST /api/v1/chat/sessions/{id}/messages`

请求头：

- `Authorization: Bearer <token>`
- `Idempotency-Key: <optional>`

响应关键字段：

- `answer`
- `answer_mode`
- `execution_mode`
- `strategy_used`
- `evidence_status`
- `grounding_score`
- `refusal_reason`
- `safety`
- `citations`
- `retrieval`
- `latency`
- `cost`
- `trace_id`
- `llm_trace`
- `message`
- `workflow_run`

### `POST /api/v1/chat/sessions/{id}/messages/stream`

SSE 顺序：

- `metadata -> citation -> answer -> message -> done`

`metadata` 会额外返回：

- `execution_mode`
- `workflow_run`
- `resume`
- `retrieval`
- `safety`

### `GET /api/v1/chat/sessions/{id}/workflow-runs`

列出当前会话下的工作流运行记录。

### `GET /api/v1/chat/workflow-runs/{run_id}`

获取单次聊天工作流快照。

### `POST /api/v1/chat/workflow-runs/{run_id}/retry`

对失败工作流执行重试。

当前约束：

- 仅允许重试 `status=failed`
- 默认复用原 `scope_snapshot`
- 会创建新的 `message` 和新的 `workflow_run`

### `PUT /api/v1/chat/sessions/{id}/messages/{message_id}/feedback`

用户满意度数据入口。

请求：

```json
{
  "verdict": "up",
  "reason_code": "grounded",
  "notes": "引用充分"
}
```

## 4. `execution_mode`

适用接口：

- `POST /api/v1/chat/sessions`
- `PATCH /api/v1/chat/sessions/{id}`
- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`

可选值：

- `grounded`
- `agent`

约束：

- 默认值是 `grounded`
- `agent` 仍然必须在当前 `scope` 内检索
- `agent` 当前支持的工具选择由 Agent Profile 控制，已落地工具：
  - `search_scope`
  - `list_scope_documents`
  - `search_corpus`
  - `calculator`

## 5. 知识库基础管理

### `POST /api/v1/kb/bases`

创建知识库。

### `GET /api/v1/kb/bases`

列出当前用户可见的知识库。

### `GET /api/v1/kb/bases/{base_id}`

获取单个知识库详情。

### `PATCH /api/v1/kb/bases/{base_id}`

更新知识库元数据。

### `DELETE /api/v1/kb/bases/{base_id}`

删除知识库及其下属文档、向量与关联资源。

### `GET /api/v1/kb/bases/{base_id}/documents`

列出知识库文档。

### `GET /api/v1/kb/documents/{document_id}`

获取文档详情，包含 `latest_job`。

### `PATCH /api/v1/kb/documents/{document_id}`

更新文档文件名、分类等元数据。

### `DELETE /api/v1/kb/documents/{document_id}`

删除文档及关联向量、上传会话、视觉资源。

### `GET /api/v1/kb/documents/{document_id}/events`

查看文档处理事件流。

### `GET /api/v1/kb/documents/{document_id}/visual-assets`

列出文档视觉资源。

## 6. 文档上传与 Ingest

推荐路径：

- `POST /api/v1/kb/uploads`
- `GET /api/v1/kb/uploads/{upload_id}`
- `POST /api/v1/kb/uploads/{upload_id}/parts/presign`
- `POST /api/v1/kb/uploads/{upload_id}/complete`
- `GET /api/v1/kb/ingest-jobs/{job_id}`
- `POST /api/v1/kb/ingest-jobs/{job_id}/retry`

兼容路径仍保留：

- `POST /api/v1/kb/documents/upload`

## 7. Chunk 治理与 Retrieval Debugger

### `GET /api/v1/kb/documents/{document_id}/chunks`

查看文档切片详情页数据。

查询参数：

- `include_disabled=true|false`

响应字段：

- `document_id`
- `base_id`
- `counts.total`
- `counts.active`
- `counts.disabled`
- `items[*].chunk_id`
- `items[*].section_title`
- `items[*].text_content`
- `items[*].disabled`
- `items[*].disabled_reason`
- `items[*].manual_note`
- `items[*].source_kind`

### `PATCH /api/v1/kb/chunks/{chunk_id}`

人工修改切片文本或启用/禁用切片。

请求示例：

```json
{
  "text_content": "更新后的切片正文",
  "disabled": false,
  "disabled_reason": "",
  "manual_note": "修正 OCR 噪音"
}
```

说明：

- 会同步刷新 FTS 字段
- 会重建该文档的 section/chunk 向量

### `POST /api/v1/kb/chunks/{chunk_id}/split`

手动拆分单个切片。

请求示例：

```json
{
  "parts": [
    "第一段",
    "第二段",
    "第三段"
  ]
}
```

### `POST /api/v1/kb/chunks/merge`

手动合并同一 section 内连续切片。

请求示例：

```json
{
  "chunk_ids": ["chunk-1", "chunk-2"],
  "separator": "\n\n"
}
```

### `POST /api/v1/kb/retrieve`

纯检索接口，不触发 LLM 生成。

响应字段：

- `items`
- `retrieval`
- `trace_id`

### `POST /api/v1/kb/retrieve/debug`

检索调试工作台接口。

用途：

- 输入 Query 后仅返回 Top-K 召回结果
- 暴露最终排序分数、信号分数和 rerank 分数
- 不触发 LLM 生成

响应字段：

- `query`
- `items[*].debug.rank`
- `items[*].debug.score`
- `items[*].debug.signal_scores`
- `items[*].debug.rerank_score`
- `retrieval`
- `trace_id`

### `POST /api/v1/kb/query`

严格 grounded 的 KB 问答接口。

### `POST /api/v1/kb/query/stream`

SSE 顺序保持：

- `metadata -> citation -> answer -> done`

## 8. 多源连接器与定时同步

### 8.1 直接执行型连接器

保留的老接口：

- `POST /api/v1/kb/connectors/local-directory/sync`
- `POST /api/v1/kb/connectors/notion/sync`

### 8.2 连接器注册表

新增统一连接器配置接口，支持：

- `local_directory`
- `notion`
- `web_crawler`
- `feishu_document`
- `dingtalk_document`
- `sql_query`

### `GET /api/v1/kb/connectors?base_id=<optional>`

列出当前用户可见的连接器。

### `POST /api/v1/kb/connectors`

创建连接器配置。

请求示例：

```json
{
  "base_id": "base-uuid",
  "name": "飞书制度同步",
  "connector_type": "feishu_document",
  "config": {
    "urls": ["https://open.feishu.cn/docx/xxx"],
    "category": "policy",
    "delete_missing": true,
    "header_name": "Authorization",
    "header_value_env": "KB_FEISHU_AUTH_HEADER"
  },
  "schedule": {
    "enabled": true,
    "interval_minutes": 60
  }
}
```

说明：

- `web_crawler` / `feishu_document` / `dingtalk_document` 当前以 URL 抓取模式落地
- `sql_query` 当前以安全的 SQL 模板同步落地，要求 `dsn_env` 指向后端环境变量中的 DSN
- 调度采用“注册表 + run-due 执行入口”模式，便于后续接外部 cron / worker

### `GET /api/v1/kb/connectors/{connector_id}`

获取单个连接器配置。

### `PATCH /api/v1/kb/connectors/{connector_id}`

更新配置、状态与调度信息。

### `DELETE /api/v1/kb/connectors/{connector_id}`

删除连接器配置。

### `GET /api/v1/kb/connectors/{connector_id}/runs`

查看连接器历史运行记录。

### `POST /api/v1/kb/connectors/{connector_id}/sync`

立即执行一次连接器同步。

请求：

```json
{
  "dry_run": false
}
```

### `POST /api/v1/kb/connectors/run-due`

执行所有到期的定时连接器。

请求：

```json
{
  "dry_run": false,
  "limit": 10
}
```

## 9. Agent 工作台与 Prompt 模板库

### 9.1 Prompt 模板库

#### `GET /api/v1/platform/prompt-templates`

列出个人模板和公共模板。

#### `POST /api/v1/platform/prompt-templates`

创建模板。

请求：

```json
{
  "name": "财务规范回答",
  "content": "先给结论，再列引用和风险。",
  "visibility": "public",
  "tags": ["finance", "grounded"],
  "favorite": true
}
```

#### `GET /api/v1/platform/prompt-templates/{template_id}`

获取模板详情。

#### `PATCH /api/v1/platform/prompt-templates/{template_id}`

更新模板。

#### `DELETE /api/v1/platform/prompt-templates/{template_id}`

删除模板。

### 9.2 Agent Profile

#### `GET /api/v1/platform/agent-profiles`

列出 Agent Profile。

#### `POST /api/v1/platform/agent-profiles`

创建 Agent Profile。

请求：

```json
{
  "name": "报销制度审阅员",
  "description": "面向企业报销流程问答",
  "persona_prompt": "你是财务制度分析师，优先给出审批链和风险提示。",
  "enabled_tools": ["search_scope", "search_corpus", "calculator"],
  "default_corpus_ids": ["kb:uuid-1"],
  "prompt_template_id": "template-uuid"
}
```

#### `GET /api/v1/platform/agent-profiles/{profile_id}`

获取单个 Agent Profile。

#### `PATCH /api/v1/platform/agent-profiles/{profile_id}`

更新 Agent Profile。

#### `DELETE /api/v1/platform/agent-profiles/{profile_id}`

删除 Agent Profile。

## 10. 运营与数据看板

### `GET /api/v1/analytics/dashboard?view=personal|admin&days=14`

返回 EntryView 可直接消费的运营看板数据。

权限：

- `view=personal`：普通用户可访问
- `view=admin`：需要 `platform_admin`

响应结构：

```json
{
  "view": "admin",
  "days": 14,
  "hot_terms": [
    {"term": "报销", "count": 18}
  ],
  "zero_hit": {
    "trend": [{"date": "2026-03-10", "count": 3}],
    "top_queries": [{"query": "海外差旅餐补", "count": 2}]
  },
  "satisfaction": {
    "trend": [
      {"date": "2026-03-10", "up_count": 12, "down_count": 2, "flag_count": 1}
    ]
  },
  "usage": {
    "currency": "CNY",
    "summary": {
      "assistant_turns": 64,
      "prompt_tokens": 12034,
      "completion_tokens": 5088,
      "estimated_cost": 23.42
    },
    "trend": [
      {"date": "2026-03-10", "prompt_tokens": 900, "completion_tokens": 420, "estimated_cost": 1.82}
    ]
  }
}
```

## 11. 安全与背压补充

以下高成本接口具备 in-flight 背压保护：

- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`
- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`

超限返回：

- `429`
- `code=too_many_inflight_requests`

以下接口会返回 `safety` 字段或在 SSE `metadata` 中返回：

- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`
- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`

字段结构：

```json
{
  "risk_level": "low | medium | high",
  "blocked": false,
  "action": "allow | warn | fallback | refuse",
  "reason_codes": ["prompt_injection_user"],
  "source_types": ["user"],
  "matched_signals": ["instruction_override"]
}
```

## 12. 基线验证

在仓库根目录执行：

```powershell
python scripts/quality/check-encoding.py
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
docker compose config --quiet
pytest tests/test_platform_and_connector_extensions.py tests/test_kb_local_sync.py tests/test_kb_notion_sync.py tests/test_chat_workflow_resume_and_budget.py
```
