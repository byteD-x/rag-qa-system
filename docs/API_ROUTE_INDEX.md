# API 路由清单

> 本文件由 `scripts/generate_api_route_index.py` 静态解析 FastAPI 路由装饰器生成。
> 它只列出路由、方法、处理函数和源码位置，不包含请求/响应示例、密钥、Prompt 或运行时数据。

## 生成方式

```powershell
.venv\Scripts\python.exe scripts/generate_api_route_index.py --output docs/API_ROUTE_INDEX.md
```

## 源码范围

- `apps/services/api-gateway/src/app/gateway_admin_routes.py`
- `apps/services/api-gateway/src/app/gateway_analytics_routes.py`
- `apps/services/api-gateway/src/app/gateway_auth_routes.py`
- `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py`
- `apps/services/api-gateway/src/app/gateway_chat_routes.py`
- `apps/services/api-gateway/src/app/gateway_interview_routes.py`
- `apps/services/api-gateway/src/app/gateway_mcp_routes.py`
- `apps/services/api-gateway/src/app/gateway_platform_routes.py`
- `apps/services/api-gateway/src/app/gateway_system_routes.py`
- `apps/services/api-gateway/src/app/main.py`
- `apps/services/knowledge-base/src/app/kb_analytics_routes.py`
- `apps/services/knowledge-base/src/app/kb_auto_index_routes.py`
- `apps/services/knowledge-base/src/app/kb_base_routes.py`
- `apps/services/knowledge-base/src/app/kb_batch_dry_run_routes.py`
- `apps/services/knowledge-base/src/app/kb_batch_ingest_routes.py`
- `apps/services/knowledge-base/src/app/kb_chunk_routes.py`
- `apps/services/knowledge-base/src/app/kb_connector_routes.py`
- `apps/services/knowledge-base/src/app/kb_generic_routes.py`
- `apps/services/knowledge-base/src/app/kb_index_routes.py`
- `apps/services/knowledge-base/src/app/kb_ingest_routes.py`
- `apps/services/knowledge-base/src/app/kb_job_queue_routes.py`
- `apps/services/knowledge-base/src/app/kb_object_store_routes.py`
- `apps/services/knowledge-base/src/app/kb_query_routes.py`
- `apps/services/knowledge-base/src/app/kb_rebuild_routes.py`
- `apps/services/knowledge-base/src/app/kb_sync_routes.py`
- `apps/services/knowledge-base/src/app/kb_system_routes.py`
- `apps/services/knowledge-base/src/app/kb_upload_routes.py`
- `apps/services/knowledge-base/src/app/kb_visual_routes.py`
- `apps/services/knowledge-base/src/app/main.py`

## 路由总览（152 条）

| service | methods | path | handler | source |
|---|---|---|---|---|
| api-gateway | `GET` | `/api/knowledge_base/auto-index/preview` | `proxy_knowledge_auto_index_preview` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:109` |
| knowledge-base | `GET` | `/api/knowledge_base/auto-index/preview` | `get_knowledge_auto_index_preview` | `apps/services/knowledge-base/src/app/kb_auto_index_routes.py:17` |
| api-gateway | `POST` | `/api/knowledge_base/batch-dry-run` | `proxy_knowledge_batch_dry_run` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:100` |
| knowledge-base | `POST` | `/api/knowledge_base/batch-dry-run` | `post_knowledge_batch_dry_run` | `apps/services/knowledge-base/src/app/kb_batch_dry_run_routes.py:18` |
| api-gateway | `POST` | `/api/knowledge_base/batch-ingest` | `proxy_knowledge_batch_ingest` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:127` |
| knowledge-base | `POST` | `/api/knowledge_base/batch-ingest` | `post_knowledge_batch_ingest` | `apps/services/knowledge-base/src/app/kb_batch_ingest_routes.py:20` |
| api-gateway | `GET` | `/api/knowledge_base/index` | `proxy_knowledge_index` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:136` |
| knowledge-base | `GET` | `/api/knowledge_base/index` | `get_knowledge_index` | `apps/services/knowledge-base/src/app/kb_index_routes.py:17` |
| api-gateway | `POST` | `/api/knowledge_base/jobs` | `proxy_knowledge_job_create` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:145` |
| knowledge-base | `POST` | `/api/knowledge_base/jobs` | `post_knowledge_job` | `apps/services/knowledge-base/src/app/kb_job_queue_routes.py:22` |
| api-gateway | `GET` | `/api/knowledge_base/jobs/{job_id}` | `proxy_knowledge_job_get` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:154` |
| knowledge-base | `GET` | `/api/knowledge_base/jobs/{job_id}` | `get_knowledge_job` | `apps/services/knowledge-base/src/app/kb_job_queue_routes.py:40` |
| api-gateway | `POST` | `/api/knowledge_base/rebuild` | `proxy_knowledge_rebuild` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:118` |
| knowledge-base | `POST` | `/api/knowledge_base/rebuild` | `post_knowledge_rebuild` | `apps/services/knowledge-base/src/app/kb_rebuild_routes.py:18` |
| api-gateway | `GET` | `/api/knowledge_base/status` | `proxy_knowledge_status` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:163` |
| knowledge-base | `GET` | `/api/knowledge_base/status` | `get_knowledge_status` | `apps/services/knowledge-base/src/app/kb_job_queue_routes.py:53` |
| api-gateway | `POST` | `/api/v1/admin/costs/provider-billing-records` | `import_provider_billing` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:81` |
| api-gateway | `POST` | `/api/v1/agents/tool-workflow` | `post_tool_workflow` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:107` |
| api-gateway | `GET` | `/api/v1/analytics/dashboard` | `get_dashboard` | `apps/services/api-gateway/src/app/gateway_analytics_routes.py:645` |
| api-gateway | `GET` | `/api/v1/audit/events` | `list_audit_events` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:34` |
| api-gateway | `POST` | `/api/v1/auth/login` | `login` | `apps/services/api-gateway/src/app/gateway_auth_routes.py:15` |
| api-gateway | `GET` | `/api/v1/auth/me` | `me` | `apps/services/api-gateway/src/app/gateway_auth_routes.py:33` |
| api-gateway | `POST` | `/api/v1/auth/register` | `register` | `apps/services/api-gateway/src/app/gateway_auth_routes.py` |
| api-gateway | `POST` | `/api/v1/auth/password-reset/request` | `password_reset_request` | `apps/services/api-gateway/src/app/gateway_auth_routes.py` |
| api-gateway | `POST` | `/api/v1/auth/password-reset/confirm` | `password_reset_confirm` | `apps/services/api-gateway/src/app/gateway_auth_routes.py` |
| api-gateway | `GET` | `/api/v1/chat/corpora` | `list_chat_corpora` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:148` |
| api-gateway | `GET` | `/api/v1/chat/corpora/{corpus_id}/documents` | `list_chat_corpus_documents` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:154` |
| api-gateway | `POST` | `/api/v1/chat/handoff/claim-next` | `claim_next_handoff_session` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:187` |
| api-gateway | `GET` | `/api/v1/chat/sessions` | `list_chat_sessions` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:177` |
| api-gateway | `POST` | `/api/v1/chat/sessions` | `create_chat_session` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:163` |
| api-gateway | `DELETE` | `/api/v1/chat/sessions/{session_id}` | `delete_chat_session` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:244` |
| api-gateway | `GET` | `/api/v1/chat/sessions/{session_id}` | `get_chat_session` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:218` |
| api-gateway | `PATCH` | `/api/v1/chat/sessions/{session_id}` | `update_chat_session` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:224` |
| api-gateway | `GET` | `/api/v1/chat/sessions/{session_id}/messages` | `list_chat_messages` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:256` |
| api-gateway | `POST` | `/api/v1/chat/sessions/{session_id}/messages` | `send_chat_message` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:428` |
| api-gateway | `POST` | `/api/v1/chat/sessions/{session_id}/messages/stream` | `stream_chat_message` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:478` |
| api-gateway | `PUT` | `/api/v1/chat/sessions/{session_id}/messages/{message_id}/feedback` | `put_chat_message_feedback` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:262` |
| api-gateway | `GET` | `/api/v1/chat/sessions/{session_id}/workflow-runs` | `list_chat_workflow_runs` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:297` |
| api-gateway | `GET` | `/api/v1/chat/workflow-runs/{run_id}` | `get_chat_workflow_run` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:309` |
| api-gateway | `POST` | `/api/v1/chat/workflow-runs/{run_id}/retry` | `retry_chat_workflow_run` | `apps/services/api-gateway/src/app/gateway_chat_routes.py:315` |
| api-gateway | `POST` | `/api/v1/interviews/sessions` | `start_interview` | `apps/services/api-gateway/src/app/gateway_interview_routes.py:173` |
| api-gateway | `POST` | `/api/v1/interviews/sessions/{session_id}/questions/{session_question_id}/answer` | `answer_interview_question` | `apps/services/api-gateway/src/app/gateway_interview_routes.py:207` |
| api-gateway | `GET` | `/api/v1/interviews/sessions/{session_id}/report` | `interview_report` | `apps/services/api-gateway/src/app/gateway_interview_routes.py:258` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/dashboard` | `get_kb_dashboard` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1148` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance` | `get_kb_governance` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1206` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance/batch-events` | `get_kb_governance_batch_events` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1235` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance/batch-events/{task_id}` | `get_kb_governance_batch_event_detail` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1263` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/operations` | `get_kb_operations` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1177` |
| knowledge-base | `GET` | `/api/v1/kb/audit/events` | `list_kb_audit_events` | `apps/services/knowledge-base/src/app/kb_system_routes.py:43` |
| knowledge-base | `GET` | `/api/v1/kb/bases` | `list_bases` | `apps/services/knowledge-base/src/app/kb_base_routes.py:528` |
| knowledge-base | `POST` | `/api/v1/kb/bases` | `create_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:479` |
| knowledge-base | `DELETE` | `/api/v1/kb/bases/{base_id}` | `delete_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:616` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}` | `get_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:560` |
| knowledge-base | `PATCH` | `/api/v1/kb/bases/{base_id}` | `update_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:566` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}/documents` | `list_base_documents` | `apps/services/knowledge-base/src/app/kb_base_routes.py:645` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}/question-pool` | `question_pool` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:426` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}/questions` | `list_questions` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:271` |
| knowledge-base | `POST` | `/api/v1/kb/chunks/merge` | `merge_document_chunks` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:59` |
| knowledge-base | `PATCH` | `/api/v1/kb/chunks/{chunk_id}` | `patch_chunk` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:39` |
| knowledge-base | `POST` | `/api/v1/kb/chunks/{chunk_id}/split` | `split_document_chunk` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:53` |
| knowledge-base | `GET` | `/api/v1/kb/connectors` | `list_connectors` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:245` |
| knowledge-base | `POST` | `/api/v1/kb/connectors` | `create_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:277` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/local-directory/sync` | `sync_local_directory` | `apps/services/knowledge-base/src/app/kb_sync_routes.py:20` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/notion/sync` | `sync_notion_pages` | `apps/services/knowledge-base/src/app/kb_sync_routes.py:62` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/run-due` | `run_due_connectors` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:464` |
| knowledge-base | `DELETE` | `/api/v1/kb/connectors/{connector_id}` | `delete_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:385` |
| knowledge-base | `GET` | `/api/v1/kb/connectors/{connector_id}` | `get_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:328` |
| knowledge-base | `PATCH` | `/api/v1/kb/connectors/{connector_id}` | `update_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:334` |
| knowledge-base | `GET` | `/api/v1/kb/connectors/{connector_id}/runs` | `list_connector_runs` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:406` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/{connector_id}/sync` | `run_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:426` |
| knowledge-base | `POST` | `/api/v1/kb/documents/batch-update` | `batch_update_documents` | `apps/services/knowledge-base/src/app/kb_base_routes.py:652` |
| knowledge-base | `DELETE` | `/api/v1/kb/documents/{document_id}` | `delete_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:779` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}` | `get_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:717` |
| knowledge-base | `PATCH` | `/api/v1/kb/documents/{document_id}` | `update_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:773` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/chunks` | `get_document_chunks` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:17` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/events` | `get_document_events` | `apps/services/knowledge-base/src/app/kb_base_routes.py:808` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions` | `get_document_versions` | `apps/services/knowledge-base/src/app/kb_base_routes.py:723` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions/{version_id}/content` | `get_document_version_content` | `apps/services/knowledge-base/src/app/kb_base_routes.py:729` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions/{version_id}/diff` | `get_document_version_diff` | `apps/services/knowledge-base/src/app/kb_base_routes.py:745` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/visual-assets` | `get_document_visual_assets` | `apps/services/knowledge-base/src/app/kb_base_routes.py:827` |
| knowledge-base | `GET` | `/api/v1/kb/ingest-jobs/{job_id}` | `get_ingest_job` | `apps/services/knowledge-base/src/app/kb_ingest_routes.py:17` |
| knowledge-base | `POST` | `/api/v1/kb/ingest-jobs/{job_id}/retry` | `retry_ingest_job` | `apps/services/knowledge-base/src/app/kb_ingest_routes.py:26` |
| knowledge-base | `GET` | `/api/v1/kb/job-positions` | `list_job_positions` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:205` |
| knowledge-base | `POST` | `/api/v1/kb/job-positions` | `create_job_position` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:218` |
| knowledge-base | `PATCH` | `/api/v1/kb/job-positions/{position_id}` | `update_job_position` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:240` |
| knowledge-base | `GET` | `/api/v1/kb/object-store/object` | `read_object` | `apps/services/knowledge-base/src/app/kb_object_store_routes.py:52` |
| knowledge-base | `PUT` | `/api/v1/kb/object-store/parts` | `upload_object_part` | `apps/services/knowledge-base/src/app/kb_object_store_routes.py:32` |
| knowledge-base | `POST` | `/api/v1/kb/query` | `query_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:181` |
| knowledge-base | `POST` | `/api/v1/kb/query/stream` | `stream_query_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:236` |
| knowledge-base | `POST` | `/api/v1/kb/questions` | `create_question` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:309` |
| knowledge-base | `DELETE` | `/api/v1/kb/questions/{question_id}` | `delete_question` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:414` |
| knowledge-base | `GET` | `/api/v1/kb/questions/{question_id}` | `get_question` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:345` |
| knowledge-base | `PATCH` | `/api/v1/kb/questions/{question_id}` | `update_question` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:353` |
| knowledge-base | `POST` | `/api/v1/kb/questions/{question_id}/publish` | `publish_question` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:397` |
| knowledge-base | `POST` | `/api/v1/kb/retrieve` | `retrieve_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:92` |
| knowledge-base | `POST` | `/api/v1/kb/retrieve/debug` | `retrieve_kb_debug` | `apps/services/knowledge-base/src/app/kb_query_routes.py:141` |
| knowledge-base | `GET` | `/api/v1/kb/types` | `list_kb_types` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:137` |
| knowledge-base | `POST` | `/api/v1/kb/types` | `create_kb_type` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:150` |
| knowledge-base | `PATCH` | `/api/v1/kb/types/{type_key}` | `update_kb_type` | `apps/services/knowledge-base/src/app/kb_generic_routes.py:173` |
| knowledge-base | `POST` | `/api/v1/kb/uploads` | `create_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:37` |
| knowledge-base | `GET` | `/api/v1/kb/uploads/{upload_id}` | `get_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:147` |
| knowledge-base | `POST` | `/api/v1/kb/uploads/{upload_id}/complete` | `complete_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:179` |
| knowledge-base | `POST` | `/api/v1/kb/uploads/{upload_id}/parts/presign` | `presign_upload_parts` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:154` |
| knowledge-base | `GET` | `/api/v1/kb/visual-assets/{asset_id}/regions` | `get_visual_asset_regions` | `apps/services/knowledge-base/src/app/kb_visual_routes.py:24` |
| knowledge-base | `GET` | `/api/v1/kb/visual-assets/{asset_id}/thumbnail` | `get_visual_asset_thumbnail` | `apps/services/knowledge-base/src/app/kb_visual_routes.py:15` |
| api-gateway | `DELETE, GET, OPTIONS, PATCH, POST, PUT` | `/api/v1/kb/{path:path}` | `proxy_kb` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:172` |
| api-gateway | `POST` | `/api/v1/mcp` | `post_mcp` | `apps/services/api-gateway/src/app/gateway_mcp_routes.py:17` |
| api-gateway | `GET` | `/api/v1/platform/agent-profiles` | `get_agent_profiles` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:472` |
| api-gateway | `POST` | `/api/v1/platform/agent-profiles` | `post_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:478` |
| api-gateway | `DELETE` | `/api/v1/platform/agent-profiles/{profile_id}` | `remove_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:518` |
| api-gateway | `GET` | `/api/v1/platform/agent-profiles/{profile_id}` | `get_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:494` |
| api-gateway | `PATCH` | `/api/v1/platform/agent-profiles/{profile_id}` | `patch_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:501` |
| api-gateway | `GET` | `/api/v1/platform/agent/registry/summary` | `get_platform_tool_summary` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:250` |
| api-gateway | `GET` | `/api/v1/platform/agent/runs` | `list_platform_agent_runs` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:183` |
| api-gateway | `GET` | `/api/v1/platform/agent/runs/{run_id}` | `get_platform_agent_run` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:206` |
| api-gateway | `GET` | `/api/v1/platform/agent/tools` | `list_platform_tools` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:257` |
| api-gateway | `POST` | `/api/v1/platform/agent/tools/{tool_name}/toggle` | `toggle_platform_tool` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:265` |
| api-gateway | `GET` | `/api/v1/platform/cache/config` | `get_platform_cache_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:370` |
| api-gateway | `PATCH` | `/api/v1/platform/cache/config` | `patch_platform_cache_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:376` |
| api-gateway | `POST` | `/api/v1/platform/cache/invalidate` | `invalidate_platform_cache` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:382` |
| api-gateway | `GET` | `/api/v1/platform/cache/stats` | `get_platform_cache_stats` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:364` |
| api-gateway | `GET` | `/api/v1/platform/cost/breakdown` | `get_platform_cost_breakdown` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:339` |
| api-gateway | `GET` | `/api/v1/platform/cost/model-health` | `get_platform_model_health` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:358` |
| api-gateway | `GET` | `/api/v1/platform/llm/config` | `get_llm_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:389` |
| api-gateway | `POST` | `/api/v1/platform/llm/models/discover` | `post_discover_llm_models` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:395` |
| api-gateway | `GET` | `/api/v1/platform/memory/entries` | `list_memory_entries` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:274` |
| api-gateway | `DELETE` | `/api/v1/platform/memory/entries/{memory_id}` | `deactivate_memory_entry` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:312` |
| api-gateway | `GET` | `/api/v1/platform/memory/search` | `search_memory_entries` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:296` |
| api-gateway | `GET` | `/api/v1/platform/memory/stats` | `get_memory_stats` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:325` |
| api-gateway | `GET` | `/api/v1/platform/model-configs` | `get_model_configs` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:63` |
| api-gateway | `POST` | `/api/v1/platform/model-configs` | `post_model_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:69` |
| api-gateway | `DELETE` | `/api/v1/platform/model-configs/{config_id}` | `remove_model_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:85` |
| api-gateway | `PATCH` | `/api/v1/platform/model-configs/{config_id}` | `patch_model_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:77` |
| api-gateway | `POST` | `/api/v1/platform/model-configs/{config_id}/test` | `test_model_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:93` |
| api-gateway | `GET` | `/api/v1/platform/prompt-templates` | `get_prompt_templates` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:421` |
| api-gateway | `POST` | `/api/v1/platform/prompt-templates` | `post_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:427` |
| api-gateway | `DELETE` | `/api/v1/platform/prompt-templates/{template_id}` | `remove_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:464` |
| api-gateway | `GET` | `/api/v1/platform/prompt-templates/{template_id}` | `get_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:442` |
| api-gateway | `PATCH` | `/api/v1/platform/prompt-templates/{template_id}` | `patch_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:448` |
| api-gateway | `GET` | `/api/v1/platform/api-keys` | `list_platform_api_keys` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/api-keys` | `create_platform_api_key` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/api-keys/{key_id}/rotate` | `rotate_platform_api_key` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/api-keys/{key_id}/revoke` | `revoke_platform_api_key` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/webhooks` | `list_platform_webhooks` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/webhooks` | `register_platform_webhook` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `PATCH` | `/api/v1/platform/webhooks/{webhook_id}` | `update_platform_webhook` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `DELETE` | `/api/v1/platform/webhooks/{webhook_id}` | `delete_platform_webhook` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/webhooks/{webhook_id}/test` | `test_platform_webhook` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/webhooks/deliveries` | `list_platform_webhook_deliveries` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/pii/config` | `get_platform_pii_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `PATCH` | `/api/v1/platform/pii/config` | `save_platform_pii_config` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/pii/test` | `test_platform_pii` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/experiments` | `list_platform_experiments` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/experiments` | `start_platform_experiment` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `POST` | `/api/v1/platform/experiments/{experiment_id}/stop` | `stop_platform_experiment` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/experiments/{experiment_id}/report` | `get_platform_experiment_report` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/platform/orchestration/runs` | `list_platform_orchestration_runs` | `apps/services/api-gateway/src/app/gateway_platform_routes.py` |
| api-gateway | `GET` | `/api/v1/system/metrics-summary` | `metrics_summary` | `apps/services/api-gateway/src/app/gateway_system_routes.py:117` |
| api-gateway | `POST` | `/api/v2/chat/interrupts/{interrupt_id}/submit` | `submit_chat_interrupt` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:260` |
| api-gateway | `GET` | `/api/v2/chat/runs/{run_id}` | `get_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:219` |
| api-gateway | `POST` | `/api/v2/chat/runs/{run_id}/resume` | `resume_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:227` |
| api-gateway | `POST` | `/api/v2/chat/threads` | `create_chat_thread` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:121` |
| api-gateway | `GET` | `/api/v2/chat/threads/{thread_id}` | `get_chat_thread` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:161` |
| api-gateway | `GET` | `/api/v2/chat/threads/{thread_id}/messages` | `list_chat_thread_messages` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:167` |
| api-gateway | `POST` | `/api/v2/chat/threads/{thread_id}/runs` | `create_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:179` |
| knowledge-base | `POST` | `/api/v2/kb/query` | `query_kb_v2` | `apps/services/knowledge-base/src/app/kb_query_routes.py:229` |
| knowledge-base | `POST` | `/api/v2/kb/retrieve` | `retrieve_kb_v2` | `apps/services/knowledge-base/src/app/kb_query_routes.py:116` |
| api-gateway | `GET` | `/healthz` | `healthz` | `apps/services/api-gateway/src/app/gateway_system_routes.py:22` |
| knowledge-base | `GET` | `/healthz` | `healthz` | `apps/services/knowledge-base/src/app/kb_system_routes.py:18` |
| api-gateway | `GET` | `/metrics` | `metrics` | `apps/services/api-gateway/src/app/gateway_system_routes.py:122` |
| knowledge-base | `GET` | `/metrics` | `metrics` | `apps/services/knowledge-base/src/app/kb_system_routes.py:37` |
| api-gateway | `GET` | `/readyz` | `readyz` | `apps/services/api-gateway/src/app/gateway_system_routes.py:96` |
| knowledge-base | `GET` | `/readyz` | `readyz` | `apps/services/knowledge-base/src/app/kb_system_routes.py:23` |
