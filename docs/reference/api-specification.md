# API 规范

本文档是仓库唯一的 API 文档，覆盖当前项目对前端开放的核心接口，包括：

- 认证、登录态与健康检查
- 统一聊天、工作流与人工接管
- 知识库、文档上传、检索与调试
- 连接器、同步调度与知识治理
- Prompt Template、Agent Profile 与 Tool Workflow
- 运营分析看板、审计与指标接口

静态路由总览见 [../API_ROUTE_INDEX.md](../API_ROUTE_INDEX.md)。该清单由脚本解析当前 FastAPI 路由装饰器生成，只用于快速查找 path、method、handler 与源码位置，不替代本文档中的接口契约说明。

默认本地地址：

- Gateway：`http://localhost:8080`
- KB Service：`http://localhost:8300`

## 1. 通用约定

### 认证

除健康检查外，大多数业务接口都需要：

```http
Authorization: Bearer <ACCESS_TOKEN>
```

登录接口：

- `POST /api/v1/auth/login`

当前用户接口：

- `GET /api/v1/auth/me`

### 内容类型

- 普通接口：`application/json`
- 流式问答：`text/event-stream`

### 常见错误码

| HTTP 状态码 | `code` | 含义 |
|---|---|---|
| `400` | `analytics_view_invalid` / 其他业务错误 | 请求参数合法但业务不成立 |
| `401` | `unauthorized` | 未登录或 token 无效 |
| `403` | `permission_denied` | 权限不足 |
| `404` | `not_found` | 资源不存在 |
| `409` | `conflict` | 状态冲突或重复操作 |
| `422` | `validation_error` | 参数校验失败 |
| `429` | `too_many_inflight_requests` | 高成本接口触发背压保护 |
| `500` | `internal_error` | 服务内部异常 |
| `502` | `upstream_error` | Gateway 访问上游服务失败 |

## 2. 健康检查

### `GET /healthz`

- 用于存活探针
- 返回 `200 {"status":"ok"}`

### `GET /readyz`

- Gateway 会检查数据库、KB Service 与模型配置
- KB Service 会检查数据库、对象存储、Qdrant 连通性与 Qdrant 运行时配置
- `qdrant_runtime_config` 只暴露 endpoint、collection、FastEmbed 参数和 `api_key_configured`，不返回 API key 原文
- 关键依赖未就绪时返回 `503`

### `GET /metrics`

- Gateway 与 KB Service 均暴露 Prometheus 文本格式指标
- 本地默认分别位于 `http://localhost:8080/metrics` 与 `http://localhost:8300/metrics`
- Gateway 运行时治理指标族包括 `rag_gateway_governance_events_total`、`rag_gateway_governance_event_duration_ms` 与 `rag_gateway_governance_failure_reasons_total`
- 运行时治理指标只记录 `prompt_rollback` 与 `tool_workflow` 的聚合结果、耗时和短失败原因，不包含 prompt、payload、工具输出或异常全文

### `GET /api/v1/system/metrics-summary`

- Gateway JSON 指标摘要，适合前端、CI 或本地排障脚本直接读取
- 当前包含 `response_cache_summary` 与 `governance_metrics`
- `response_cache_summary` 描述回答级缓存运行时状态，字段包括 `enabled`、`ttl_seconds`、`size`、`max_entries`、`hits`、`misses`、`writes`、`expired`、`clears`、`hit_rate`、`semantic_enabled`、`semantic_threshold`、`semantic_hits`、`semantic_misses` 与 `semantic_skipped`。L2 相似问法语义命中默认关闭，默认阈值为 `0.92`
- `governance_metrics.events` 只包含 `prompt_rollback` 与 `tool_workflow` 的聚合计数、成功率、总/平均/最近耗时和短失败原因计数，不包含 prompt、payload、工具输出或异常全文。

## 3. 认证

### `POST /api/v1/auth/login`

请求示例：

```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

响应关键字段：

- `access_token`
- `token_type`
- `user`

### `GET /api/v1/auth/me`

返回当前 token 对应用户与权限信息。

响应关键字段：

- `user`
- `permissions`
- `role`

## 4. 统一聊天与工作流

### `v2` LangGraph 运行时

新增基于 LangGraph 的 `thread / run / interrupt` 语义：

- `POST /api/v2/chat/threads`
- `GET /api/v2/chat/threads/{thread_id}`
- `GET /api/v2/chat/threads/{thread_id}/messages`
- `POST /api/v2/chat/threads/{thread_id}/runs`
- `GET /api/v2/chat/runs/{run_id}`
- `POST /api/v2/chat/runs/{run_id}/resume`
- `POST /api/v2/chat/interrupts/{interrupt_id}/submit`

`v2` 关键字段：

- `status`
- `run`
- `interrupt`
- `step_events`
- `verification`
- `thread_id`

说明：

- `v2` 的 `run` 由 LangGraph checkpoint 驱动，可在 `interrupted` 状态下继续恢复
- `interrupt` 用于人工澄清和证据不足场景
- `v1` 的 `workflow_run` 仍保留，但实现上已退化为运行投影/审计视图

运行时依赖基线：

- `api-gateway` 当前固定使用 `langgraph==0.5.4` 与 `langgraph-checkpoint-postgres==2.0.25`
- `knowledge-base` 当前固定使用 `langgraph==0.5.4`
- 若部署环境仍使用 `langgraph < 0.5`，`checkpoint-postgres` 会发出兼容性 `DeprecationWarning`

### `POST /api/v1/chat/sessions`

创建聊天会话。

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

### 会话与语料辅助端点

- `GET /api/v1/chat/corpora`
- `GET /api/v1/chat/corpora/{corpus_id}/documents`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{id}`
- `DELETE /api/v1/chat/sessions/{id}`
- `GET /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/handoff/claim-next`

说明：

- `corpora` 端点用于前端构建聊天作用域选择器。
- 会话查询、删除和消息列表端点用于聊天侧边栏、历史消息恢复和会话清理。

### `POST /api/v1/chat/handoff/claim-next`

按租户和技能组认领下一条待人工接管会话。

请求字段：

- `tenant_id`：租户标识，必填。
- `skill_group`：技能组，默认可用 `general`，服务端会去空格、小写并把空格替换为 `_`。
- `operator_id`：坐席或运营人员标识，必填。

请求示例：

```json
{
  "tenant_id": "tenant-a",
  "skill_group": "billing",
  "operator_id": "operator-1"
}
```

响应关键字段：

- `claimed`：是否成功认领到会话。
- `session`：认领到的会话摘要；没有可认领项时为 `null`。
- `backend`：当前后端标识，现阶段为 `local_session_scope`。

本地实现读取 `chat_sessions.scope_json.handoff`，仅认领 `status="pending"` 且匹配 `tenant_id` / `skill_group` 的会话。排序规则为 `priority` 降序、`requested_at` 升序、`session_id` 稳定兜底。当前使用本地进程锁和条件更新防止测试环境重复认领；生产多实例部署建议替换为 Redis sorted set 或数据库 `SELECT ... FOR UPDATE SKIP LOCKED` 后端。

### `PATCH /api/v1/chat/sessions/{id}`

可更新字段：

- `title`
- `scope`
- `execution_mode`

### `POST /api/v1/chat/sessions/{id}/messages`

发送一条消息并等待完整回答。

可选请求头：

- `Idempotency-Key: <value>`

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
- `hallucination`
- `retrieval`
- `latency`
- `cost`
- `trace_id`
- `llm_trace`
- `semantic_cache`
- `message`
- `workflow_run`

`hallucination` 为规则级 RAG 幻觉检测摘要，包含 `hallucination_score`、`passed`、`needs_correction`、`check_dimensions` 与 `items`。当前同步、流式与 LangGraph 回答路径都会在生成最终响应时写入该字段。

`semantic_cache` 为回答级缓存元数据，包含 `enabled`、`hit`、`cache_level`、`similarity_score`、`original_question_hash`、`stored`、`bypass_reason` 与 `cached_usage`。当前同步与 LangGraph 非流式回答路径会在 L1 精确命中或显式开启的 L2 同 scope/corpus key 语义命中时跳过 LLM 生成，在未命中且回答具备 grounded 证据时写入缓存；状态只返回原问题 hash，不返回原问题明文。

### `POST /api/v1/chat/sessions/{id}/messages/stream`

SSE 流式回答，事件顺序：

- `metadata`
- `citation`
- `answer`
- `message`
- `done`

`metadata` 会额外包含：

- `execution_mode`
- `workflow_run`
- `resume`
- `retrieval`
- `safety`

### `GET /api/v1/chat/sessions/{id}/workflow-runs`

列出当前会话下的工作流执行记录。

### `GET /api/v1/chat/workflow-runs/{run_id}`

查询单次工作流执行详情。

### `POST /api/v1/chat/workflow-runs/{run_id}/retry`

重试失败的工作流运行。

当前约束：

- 仅允许重试 `status=failed`
- 默认复用原始 `scope_snapshot`
- 会创建新的 `message` 和新的 `workflow_run`

### `PUT /api/v1/chat/sessions/{id}/messages/{message_id}/feedback`

提交用户反馈。

请求示例：

```json
{
  "verdict": "up",
  "reason_code": "grounded",
  "notes": "引用充分"
}
```

## 5. `execution_mode`

适用接口：

- `POST /api/v1/chat/sessions`
- `PATCH /api/v1/chat/sessions/{id}`
- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`

可选值：

- `grounded`
- `agent`

说明：

- 默认值为 `grounded`
- `agent` 仍受当前 `scope` 约束
- `agent` 模式的工具能力由 Agent Profile 控制

当前已落地工具：

- `search_scope`
- `list_scope_documents`
- `search_corpus`
- `calculator`
- `backup_cleanup_dry_run`
- `data_controls_dry_run`

维护类系统工具 `backup_cleanup_dry_run` 与 `data_controls_dry_run` 只允许 dry-run 预览：服务端固定返回 `dry_run=true`、`apply=false`，输出数量、容量、scope 和脱敏摘要，不返回完整路径、原始 targets 或删除候选清单。

## 6. 知识库与文档管理

### 知识库

- `POST /api/v1/kb/bases`
- `GET /api/v1/kb/bases`
- `GET /api/v1/kb/bases/{base_id}`
- `PATCH /api/v1/kb/bases/{base_id}`
- `DELETE /api/v1/kb/bases/{base_id}`

### 文档

- `GET /api/v1/kb/bases/{base_id}/documents`
- `POST /api/v1/kb/documents/batch-update`
- `GET /api/v1/kb/documents/{document_id}`
- `GET /api/v1/kb/documents/{document_id}/versions`
- `GET /api/v1/kb/documents/{document_id}/versions/{version_id}/content`
- `GET /api/v1/kb/documents/{document_id}/versions/{version_id}/diff`
- `PATCH /api/v1/kb/documents/{document_id}`
- `DELETE /api/v1/kb/documents/{document_id}`
- `GET /api/v1/kb/documents/{document_id}/events`
- `GET /api/v1/kb/documents/{document_id}/visual-assets`

### `POST /api/v1/kb/documents/batch-update`

批量更新文档治理字段，适合知识库治理页做多选状态调整。

请求关键字段：

- `document_ids`
- `patch`

响应关键字段：

- `updated`
- `failed`
- `items`

文档对象新增的版本治理字段：

- `version_family_key`：同一份业务文档的版本家族标识。
- `version_label`：面向业务展示的版本标签，例如 `v2`、`2026-Q1`。
- `version_number`：整数版本号，便于排序和治理。
- `version_status`：当前支持 `active | draft | superseded | archived`。
- `is_current_version`：是否作为默认检索候选版本。
- `effective_from` / `effective_to`：版本生效时间窗口。
- `supersedes_document_id`：当前版本替代的是哪一个旧文档。
- `effective_now`：服务端计算字段，表示当前时刻是否处于生效窗口。

### `GET /api/v1/kb/documents/{document_id}/versions`

- 返回当前文档所在版本家族的全部版本。
- 默认按 `is_current_version DESC, version_number DESC, created_at DESC` 排序。
- 适合前端做“当前版本 + 历史版本”面板，也适合运营排查旧版为何还被引用。

### `GET /api/v1/kb/documents/{document_id}/versions/{version_id}/content`

- 返回指定历史版本或当前版本的正文内容。
- 输出里包含 `sections[*].text_content` 和拼接后的 `full_text`，方便前端做“查看历史版本原文”。
- `include_disabled=true` 时也会返回被人工禁用的切片，适合治理排查。

### `GET /api/v1/kb/documents/{document_id}/versions/{version_id}/diff`

- 默认把 `version_id` 指向的版本和当前页面文档做差异对比。
- 也支持通过 `compare_to_document_id` 指定另一个同家族版本做对比。
- 返回：
  - `source`
  - `target`
  - `diff.summary`
  - `diff.diff_text`
- `diff.summary` 当前包含 `added_chunks`、`removed_chunks`、`modified_chunks`、`changed_sections`，便于直接向业务方解释“新版具体改了哪些地方”。

### `PATCH /api/v1/kb/documents/{document_id}`

除 `file_name`、`category` 外，还支持以下版本治理字段：

```json
{
  "version_family_key": "expense-policy",
  "version_label": "2026-Q1",
  "version_number": 3,
  "version_status": "active",
  "is_current_version": true,
  "effective_from": "2026-03-11T00:00:00Z",
  "effective_to": null,
  "supersedes_document_id": "old-doc-uuid"
}
```

规则说明：

- `is_current_version=true` 时，`version_status` 必须是 `active`。
- 如果 `effective_from` 在未来，文档暂时不能标记为 current；建议先保持 `active + is_current_version=false`，等正式切换时再升 current。
- 同一 `base_id + version_family_key` 下切换 current 版本时，服务端会自动取消同家族其他 current 标记，并把仍是 `active` 的旧版本降为 `superseded`。
- `supersedes_document_id` 必须和当前文档属于同一个知识库。

常见文档状态：

- `uploaded`
- `parsing_fast`
- `fast_index_ready`
- `hybrid_ready`
- `ready`

### 视觉资产

- `GET /api/v1/kb/documents/{document_id}/visual-assets`
- `GET /api/v1/kb/visual-assets/{asset_id}/thumbnail`
- `GET /api/v1/kb/visual-assets/{asset_id}/regions`

说明：

- `visual-assets` 用于列出文档解析阶段提取的图片、页面截图或区域资产。
- `thumbnail` 返回缩略图二进制内容。
- `regions` 返回 OCR / layout 解析出的区域列表，用于截图区域问答和治理工作台。

## 7. 上传与 Ingest

推荐上传链路：

- `POST /api/v1/kb/uploads`
- `GET /api/v1/kb/uploads/{upload_id}`
- `POST /api/v1/kb/uploads/{upload_id}/parts/presign`
- `POST /api/v1/kb/uploads/{upload_id}/complete`
- `GET /api/v1/kb/ingest-jobs/{job_id}`
- `POST /api/v1/kb/ingest-jobs/{job_id}/retry`

### `POST /api/v1/kb/uploads`

除了基础上传字段，也支持在导入时直接声明版本治理信息：

```json
{
  "base_id": "base-uuid",
  "file_name": "expense-policy-2026.pdf",
  "file_type": "pdf",
  "size_bytes": 204800,
  "category": "finance",
  "version_family_key": "expense-policy",
  "version_label": "2026-Q1",
  "version_number": 3,
  "version_status": "active",
  "is_current_version": true,
  "effective_from": "2026-03-11T00:00:00Z",
  "effective_to": null,
  "supersedes_document_id": "doc-previous-version"
}
```

导入时的默认行为：

- 如果没有提供任何版本字段，系统会把该文档当作一个独立版本家族，默认生成 `v1`、`version_number=1`、`is_current_version=true`。
- 如果提供了 `supersedes_document_id`，但没有显式传 `version_family_key` / `version_number` / `version_label`，服务端会继承旧文档的版本家族，并自动把版本号递增、版本标签补成 `vN`。

说明：

- 旧的 legacy 上传接口已移除
- 新链路统一走 upload session + multipart / complete 模型

## 8. 检索、问答与调试

### 检索

### `POST /api/v1/kb/retrieve`

纯检索接口，不触发 LLM 生成。

响应关键字段：

- `items`
- `retrieval`
- `trace_id`

### `POST /api/v2/kb/retrieve`

LangGraph 编排版检索接口。

除 `v1` 字段外，额外返回：

- `graph.engine`
- `graph.entrypoint`
- `graph.final_node`
- `graph.trace_id`

说明：

- 运行时依赖基线与 Gateway `v2` 一致，当前要求 `langgraph==0.5.4`

### `POST /api/v1/kb/retrieve/debug`

检索调试工作台接口。

用途：

- 查看 Top-K 召回结果
- 查看 rerank 分数与信号分数
- 排查 zero-hit、低质量召回和排序问题

请求关键字段：

- `base_id`：必填，知识库 ID
- `question`：必填，调试问题
- `document_ids`：可选，限定检索文档范围
- `limit`：可选，召回数量上限

响应关键字段：

- `query`
- `items[*].document_title`
- `items[*].section_title`
- `items[*].unit_id`
- `items[*].quote`
- `items[*].raw_text`
- `items[*].signal_scores`
- `items[*].evidence_path`
- `items[*].debug.rank`
- `items[*].debug.score`
- `items[*].debug.signal_scores`
- `items[*].debug.rerank_score`
- `retrieval`
- `trace_id`

### 知识库问答

### `POST /api/v2/kb/query`

LangGraph 编排版知识库问答接口。

除 `v1` 字段外，额外返回：

- `graph.engine`
- `graph.entrypoint`
- `graph.final_node`
- `graph.trace_id`

说明：

- 运行时依赖基线与 Gateway `v2` 一致，当前要求 `langgraph==0.5.4`

- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`

版本选择规则：

- 当请求显式传入 `document_ids` 时，系统会严格按这些文档 ID 检索。企业用户可以手动指定旧制度、旧合同、旧手册做追溯查询。
- 当请求不传 `document_ids` 时，系统默认只在“当前生效版本”中检索，也就是同时满足：
  - `query_ready = true`
  - `source_deleted_at IS NULL`
  - `version_status = active`
  - `is_current_version = true`
  - 当前时间落在 `effective_from / effective_to` 生效窗口内
- 这条规则用于解决“旧版本和新版本同时存在时，系统默认应该选谁”的企业场景问题。

流式接口事件顺序：

- `metadata`
- `citation`
- `answer`
- `done`

## 9. Chunk 治理

### `GET /api/v1/kb/documents/{document_id}/chunks`

查看文档切片详情。

查询参数：

- `include_disabled=true|false`

### `PATCH /api/v1/kb/chunks/{chunk_id}`

人工修改切片文本，或启用 / 禁用切片。

请求示例：

```json
{
  "text_content": "更新后的切片正文",
  "disabled": false,
  "disabled_reason": "",
  "manual_note": "修正 OCR 噪音"
}
```

### `POST /api/v1/kb/chunks/{chunk_id}/split`

手动拆分单个切片。

### `POST /api/v1/kb/chunks/merge`

手动合并连续切片。

## 10. 连接器与同步

### 直接执行型接口

- `POST /api/v1/kb/connectors/local-directory/sync`
- `POST /api/v1/kb/connectors/notion/sync`

### 连接器注册表

- `GET /api/v1/kb/connectors`
- `POST /api/v1/kb/connectors`
- `GET /api/v1/kb/connectors/{connector_id}`
- `PATCH /api/v1/kb/connectors/{connector_id}`
- `DELETE /api/v1/kb/connectors/{connector_id}`
- `GET /api/v1/kb/connectors/{connector_id}/runs`
- `POST /api/v1/kb/connectors/{connector_id}/sync`
- `POST /api/v1/kb/connectors/run-due`

连接器同步的版本行为：

- 同一 `source_type + source_uri` 在 current 视角下只保留一个当前版本。
- 当连接器检测到内容哈希变化时，不再原地覆盖旧文档，而是创建一个新的文档版本，并把旧 current 版本自动降为 `superseded`。
- 当只是文件名变化或来源恢复时，仍沿用原文档更新，避免无意义地制造新版本。
- KB Service 内部的定时同步 runner 只有在存在 `schedule_enabled=true` 的连接器时才会启动；当没有任何已启用调度的连接器时，runner 会自动停掉，避免空转占用资源。

当前支持的连接器类型：

- `local_directory`
- `notion`
- `web_crawler`
- `feishu_document`
- `dingtalk_document`
- `sql_query`

说明：

- `sql_query` 通过 `dsn_env` 引用后端环境变量中的 DSN，避免在请求体中直接传递敏感连接串
- `run-due` 适合配合外部 cron / worker 做定时执行

## 11. Prompt Template 与 Agent Profile

### Prompt Template

- `GET /api/v1/platform/prompt-templates`
- `POST /api/v1/platform/prompt-templates`
- `GET /api/v1/platform/prompt-templates/{template_id}`
- `PATCH /api/v1/platform/prompt-templates/{template_id}`
- `DELETE /api/v1/platform/prompt-templates/{template_id}`

请求示例：

```json
{
  "name": "财务规范回答",
  "content": "先给结论，再列引用和风险。",
  "visibility": "public",
  "tags": ["finance", "grounded"],
  "favorite": true
}
```

### Agent Profile

- `GET /api/v1/platform/agent-profiles`
- `POST /api/v1/platform/agent-profiles`
- `GET /api/v1/platform/agent-profiles/{profile_id}`
- `PATCH /api/v1/platform/agent-profiles/{profile_id}`
- `DELETE /api/v1/platform/agent-profiles/{profile_id}`

请求示例：

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

### Tool Workflow

- `POST /api/v1/agents/tool-workflow`

权限：
- 需要 `chat.use`

请求体：
```json
{
  "tool_name": "data_controls_dry_run",
  "workflow_mode": "plan_reflect_repair",
  "payload": {
    "scopes": [],
    "action": "audit"
  }
}
```

字段说明：
- `tool_name`：必填，受控只读业务工具名，服务端会去除首尾空白并拒绝空白名称。
- `payload`：可选对象，传给工具的参数；非对象请求会被参数校验拒绝。
- `workflow_mode`：可选，取值为 `direct` 或 `plan_reflect_repair`，默认 `direct`。

响应顶层字段：
- `workflow_mode`
- `tool_name`
- `success`
- `data`
- `error`
- `metadata`

`plan_reflect_repair` 模式可能额外返回：
- `planning`：单工具规划元数据。
- `reflection`：失败原因与是否可修复。
- `repair`：一次受控修复的执行摘要。

说明：
- HTTP `200` 只表示工具工作流请求已被服务端处理，工具本身是否成功以响应体 `success` 为准。
- `direct` 是默认模式，只执行受控只读业务工具白名单，不返回 `planning`、`reflection` 或 `repair`。
- `plan_reflect_repair` 需要显式传入；当前自动修复只覆盖 `data_controls_dry_run` 的空 `scopes` dry-run 场景，会修复为 `memory`、`usage`、`export_rag`，且最多尝试一次。
- 该入口不会绕过 `requires_confirmation`，需要确认的工具不会被自动修复执行。
- 该入口不开放 shell、文件写入、任意 HTTP、动态插件或非 dry-run 写操作，也不暴露 `prompt_preview`、配置审计明细、密钥、连接串或原始目标列表。

### MCP JSON-RPC Adapter

- `POST /api/v1/mcp`

权限：
- 需要 `chat.use`

支持的 JSON-RPC methods：
- `initialize`
- `tools/list`
- `tools/call`

`initialize` 请求示例：
```json
{
  "jsonrpc": "2.0",
  "id": "init-1",
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05"
  }
}
```

`tools/list` 响应只返回本机只读摘要工具：
- `kb_scope_summary`
- `workflow_trace_summary`
- `tool_registry_stats`

`tools/call` 请求示例：
```json
{
  "jsonrpc": "2.0",
  "id": "call-1",
  "method": "tools/call",
  "params": {
    "name": "tool_registry_stats",
    "arguments": {}
  }
}
```

说明：
- 该端点是本机只读 JSON-RPC adapter，不是动态插件市场，也不负责注册远程 MCP server。
- 成功响应使用 `result`，协议级或参数错误使用 JSON-RPC `error`；HTTP `200` 只表示 adapter 已处理请求。
- `tools/call` 只接受单个工具名和对象类型 `arguments`，内部复用 Tool Workflow 的 `direct` 模式执行。
- 不暴露 `backup_cleanup_dry_run`、`data_controls_dry_run`、`prompt_preview`、配置审计明细、连接串、密钥、原始目标列表、shell、文件写入、任意 HTTP 或动态插件能力。

## 12. 运营分析看板

项目只保留这一份看板 API 说明，不再拆出单独文档。

### Gateway 看板

#### `GET /api/v1/analytics/dashboard`

用途：

- 聚合知识库创建、文档 ready 漏斗、问答质量、反馈趋势、成本趋势
- 供前端运营看板直接渲染

权限：

- `view=personal` 需要 `chat.use`
- `view=admin` 额外需要 `platform_admin`

Query 参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `view` | `personal \| admin` | `personal` | 聚合范围 |
| `days` | `int` | `14` | 滚动时间窗口，范围 `1-90` |

响应顶层字段：

- `view`
- `days`
- `hot_terms`
- `zero_hit`
- `satisfaction`
- `usage`
- `funnel`
- `ingest_health`
- `qa_quality`
- `data_quality`

`usage` 关键字段：

- `summary.assistant_turns`
- `summary.prompt_tokens`
- `summary.completion_tokens`
- `summary.estimated_cost`
- `summary.provider_billing_records`
- `summary.provider_billed_cost_cents`
- `summary.provider_billed_cost`
- `summary.provider_input_tokens`
- `summary.provider_output_tokens`
- `summary.cost_source_counts`
- `provider_billing.by_currency`
- `provider_billing.by_provider`
- `provider_billing.by_route`
- `provider_billing.trend`

成本口径：

- `estimated_cost` 是基于聊天消息 usage 与本地模型定价的估算成本。
- `provider_billed_cost_cents` 与 `provider_billing.*` 聚合平台管理员导入的 provider billing 记录。
- `usage_reconciliation` 指这组 usage 诊断对账口径，不是额外响应字段；它用 `summary.cost_source_counts` 标出本地估算轮次与 provider billing 记录数，并通过 `provider_billing.by_currency`、`by_provider`、`by_route`、`trend` 展示导入账单的聚合结果。
- 当前接口不自动拉取供应商账单；生产对账应由外部结算任务或后台系统调用导入接口。

`funnel` 关键字段：

- `knowledge_bases_created`
- `documents_uploaded`
- `documents_ready`
- `chat_sessions_with_questions`
- `questions_asked`
- `answer_outcomes`
- `feedback`

`qa_quality` 关键字段：

- `summary`
- `answer_mode_distribution`
- `evidence_status_distribution`
- `zero_hit`
- `low_quality`

`data_quality` 关键字段：

- `unsupported_fields`
- `degraded_sections`

#### 请求示例

```bash
curl -X GET "http://localhost:8080/api/v1/analytics/dashboard?view=admin&days=30" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### KB Service 看板

#### `GET /api/v1/kb/analytics/dashboard`

用途：

- 为 Gateway 提供知识库创建、文档上传、`ready` 漏斗与 ingest 健康度聚合
- 也可供前端在需要时直接消费

权限：

- `view=personal` 需要 `kb.read`
- `view=admin` 需要 `kb.manage` 或平台管理员权限

Query 参数与 Gateway 保持一致：

- `view=personal|admin`
- `days=1..90`

#### 请求示例

```bash
curl -X GET "http://localhost:8300/api/v1/kb/analytics/dashboard?view=personal&days=14" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

#### `GET /api/v1/kb/analytics/operations`

用途：

- 为 `/workspace/kb/operations` 知识库运维总览页提供聚合读模型
- 聚合 KB 依赖健康、ingest 风险队列、connector 运行看板与近期运维事故流

权限：

- 页面与接口默认需要 `kb.manage`
- `view=admin` 仅允许 `kb.manage` 或平台管理员查看团队范围
- `view=personal` 返回当前用户范围内可见知识库的数据

Query 参数：

- `view=personal|admin`
- `days=1..90`

返回顶层字段：

- `view`
- `days`
- `generated_at`
- `service_health`
- `ingest_ops`
- `connector_ops`
- `incident_feed`
- `data_quality`

字段说明：

- `service_health.status`：聚合状态，取值 `ok | degraded | failed`
- `service_health.checks`：透传 `readyz` 依赖检查项，包含 `database`、`object_storage`、`vector_store`、`qdrant_runtime_config` 等
- `ingest_ops.retryable_jobs`：仅包含当前可人工重试的 `failed | dead_letter` ingest job
- `ingest_ops.stalled_documents`：超过阈值仍未推进的文档及其最近 job 状态
- `connector_ops.items`：连接器当前运行视图，包含 `next_run_at`、`last_run_outcome`、`last_error`
- `incident_feed.items`：失败、重试、降级相关审计事件，包含 `trace_id`
- `data_quality.degraded_sections`：当某个区块上游暂时不可用时记录降级原因

#### 请求示例

```bash
curl -X GET "http://localhost:8300/api/v1/kb/analytics/operations?view=admin&days=14" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

#### `GET /api/v1/kb/analytics/governance`

用途：

- 为知识治理工作台提供低置信 OCR 区域、待处理切片、批处理事件等聚合读模型。
- 支持个人视角与管理员视角。
- 前端治理页的单文档 rebuild 动作固定调用 `POST /api/knowledge_base/rebuild`，执行前必须先 dry-run 并校验 payload signature；该入口只传已选文档 ID 与签名，不开放文件上传、目录扫描、任意路径读取或手工 `source_path`。

相关事件端点：

- `GET /api/v1/kb/analytics/governance/batch-events`
- `GET /api/v1/kb/analytics/governance/batch-events/{task_id}`

说明：

- 批处理事件详情包含重试时间线、过滤条件和分页结果。
- 低置信视觉区域仍复用 `visual-assets/{asset_id}/regions`，不新增独立批量区域接口。

### 指标说明

- `knowledge_bases_created`：按知识库创建时间统计
- `documents_uploaded`：按文档上传时间统计
- `documents_ready`：按文档进入 `ready` 的时间统计
- `zero_hit.selected_candidates_zero`：严格以 `selected_candidates = 0` 为准
- 顶层 `zero_hit`：兼容旧口径，命中条件是“无引用”或 `selected_candidates = 0`
- `stalled_documents`：当前非 `ready/failed` 且超过阈值未更新的文档数

### 降级行为

当 KB analytics 上游暂时不可用时，Gateway 仍可能返回 `200`，但：

- `ingest_health = null`
- `funnel` 中部分 KB 字段为 `null`
- 具体原因写入 `data_quality.degraded_sections`

## 13. 审计与运维接口

- `GET /api/v1/audit/events`
- `GET /api/v1/kb/audit/events`
- `POST /api/v1/admin/costs/provider-billing-records`
- `GET /metrics`

说明：

- Gateway 审计接口聚合网关侧会话、反馈、重试和平台操作事件。
- KB 审计接口记录知识库、上传、连接器、ingest 与治理相关事件。
- Provider billing 导入接口仅允许 `platform_admin` 调用，成功或拒绝都会写入 `admin.cost.provider_billing.import` 审计事件。

### `POST /api/v1/admin/costs/provider-billing-records`

用途：

- 导入供应商账单样本或外部结算系统回填记录。
- 让 `GET /api/v1/analytics/dashboard` 同时展示本地估算成本与 provider billed cost。

请求体：

```json
{
  "records": [
    {
      "external_id": "bill-202606-openai-001",
      "tenant_id": "tenant-a",
      "user_id": "user-1",
      "provider": "openai",
      "model": "gpt-4.1-mini",
      "route_key": "grounded",
      "prompt_key": "chat_grounded_answer",
      "currency": "USD",
      "billed_cost_cents": 987,
      "input_tokens": 2200,
      "output_tokens": 500,
      "billed_at": "2026-06-07T10:00:00Z",
      "metadata": {
        "invoice": "inv-001"
      }
    }
  ]
}
```

字段说明：

- `records` 最多 500 条。
- `id` 可选；未传时由服务端生成 UUID。
- `external_id` 可选；非空时按 `(provider, external_id)` 幂等 upsert。
- `billed_cost_cents`、`input_tokens`、`output_tokens` 必须为非负整数。
- `currency` 会统一转为大写，默认 `CNY`。
- `user_id` 未传时默认归属导入管理员。
- 导入记录按 `provider`、`external_id`、`route_key`、`currency`、`billed_at` 等字段参与看板聚合；`usage_reconciliation` 只用于运营诊断，不声明自动供应商账单拉取或财务级结算完成。

响应示例：

```json
{
  "imported": 1,
  "record_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
}
```

## 14. 背压与安全

以下高成本接口有 in-flight 背压保护：

- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`
- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`

超限时返回：

- HTTP `429`
- `code=too_many_inflight_requests`

以下接口会返回 `safety` 字段，或在 SSE `metadata` 中返回：

- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`
- `POST /api/v1/kb/query`
- `POST /api/v1/kb/query/stream`

## 15. 基线验证

在仓库根目录执行：

```powershell
python scripts/quality/check-encoding.py --root .
cd apps/web && npm run test:unit
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
docker compose config --quiet
```
## 企业聊天 v2 补充字段

这一节汇总了在原始 API 结构之外新增的第一阶段企业级澄清字段。

### 聊天补问字段

- `interrupt.payload.subject`
  - `type`: `version_family | visual_region_group`
  - `id`
  - `summary`
- `interrupt.payload.options[*].badges`
  - 用于展示的扁平标签，例如 `current`、`effective`、`v2`、`p.3`、`72.0%`
- `interrupt.payload.options[*].meta`
  - 结构化展示元数据，例如 `version_label`、`page_number`、`region_id`、`confidence`
- `resume` 与中断提交接口现在支持可选的 `focus_hint`
  - `focus_hint.kind`: `single_version | compare_versions | visual_region`

### 聊天回答字段

- 同步聊天响应现在包含 `answer_basis`
- 持久化后的助手消息也会暴露 `answer_basis`
- 版本比较模式下可能包含：
  - `answer_basis.kind = compare_versions`
  - `answer_basis.version_labels`
  - `answer_basis.compare_summary`
- 截图区域澄清后的回答可能包含：
  - `answer_basis.kind = visual_region`
  - `answer_basis.asset_id`
  - `answer_basis.region_id`

### 分析看板中的补问字段

- `GET /api/v1/analytics/dashboard` 现在包含 `qa_quality.clarification`
- `qa_quality.clarification` 包含：
  - `triggered_runs`
  - `completed_runs`
  - `pending_runs`
  - `completion_rate`
  - `free_text_runs`
  - `selection_runs`
  - `kind_distribution`

### 上传与连接器字段

- 上传完成响应可能包含 `version_assist`
- 连接器同步结果项可能包含 `version_assist`
- `version_assist` 包含：
  - `suggested_version_family_key`
  - `suggested_version_label`
  - `suggested_supersedes_document_id`
  - `confidence`
  - `reasons[]`
  - `auto_apply`

更完整的交互说明见 [enterprise-chat-v2.md](enterprise-chat-v2.md)。
