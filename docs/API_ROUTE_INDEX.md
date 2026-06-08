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
- `apps/services/api-gateway/src/app/gateway_mcp_routes.py`
- `apps/services/api-gateway/src/app/gateway_platform_routes.py`
- `apps/services/api-gateway/src/app/gateway_system_routes.py`
- `apps/services/api-gateway/src/app/main.py`
- `apps/services/knowledge-base/src/app/kb_analytics_routes.py`
- `apps/services/knowledge-base/src/app/kb_base_routes.py`
- `apps/services/knowledge-base/src/app/kb_batch_dry_run_routes.py`
- `apps/services/knowledge-base/src/app/kb_chunk_routes.py`
- `apps/services/knowledge-base/src/app/kb_connector_routes.py`
- `apps/services/knowledge-base/src/app/kb_ingest_routes.py`
- `apps/services/knowledge-base/src/app/kb_query_routes.py`
- `apps/services/knowledge-base/src/app/kb_sync_routes.py`
- `apps/services/knowledge-base/src/app/kb_system_routes.py`
- `apps/services/knowledge-base/src/app/kb_upload_routes.py`
- `apps/services/knowledge-base/src/app/kb_visual_routes.py`
- `apps/services/knowledge-base/src/app/main.py`

## 路由总览（98 条）

| service | methods | path | handler | source |
|---|---|---|---|---|
| api-gateway | `POST` | `/api/knowledge_base/batch-dry-run` | `proxy_knowledge_batch_dry_run` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:100` |
| knowledge-base | `POST` | `/api/knowledge_base/batch-dry-run` | `post_knowledge_batch_dry_run` | `apps/services/knowledge-base/src/app/kb_batch_dry_run_routes.py:18` |
| api-gateway | `POST` | `/api/v1/admin/costs/provider-billing-records` | `import_provider_billing` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:81` |
| api-gateway | `POST` | `/api/v1/agents/tool-workflow` | `post_tool_workflow` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:39` |
| api-gateway | `GET` | `/api/v1/analytics/dashboard` | `get_dashboard` | `apps/services/api-gateway/src/app/gateway_analytics_routes.py:645` |
| api-gateway | `GET` | `/api/v1/audit/events` | `list_audit_events` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:34` |
| api-gateway | `POST` | `/api/v1/auth/login` | `login` | `apps/services/api-gateway/src/app/gateway_auth_routes.py:15` |
| api-gateway | `GET` | `/api/v1/auth/me` | `me` | `apps/services/api-gateway/src/app/gateway_auth_routes.py:33` |
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
| knowledge-base | `GET` | `/api/v1/kb/analytics/dashboard` | `get_kb_dashboard` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1148` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance` | `get_kb_governance` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1206` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance/batch-events` | `get_kb_governance_batch_events` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1235` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/governance/batch-events/{task_id}` | `get_kb_governance_batch_event_detail` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1263` |
| knowledge-base | `GET` | `/api/v1/kb/analytics/operations` | `get_kb_operations` | `apps/services/knowledge-base/src/app/kb_analytics_routes.py:1177` |
| knowledge-base | `GET` | `/api/v1/kb/audit/events` | `list_kb_audit_events` | `apps/services/knowledge-base/src/app/kb_system_routes.py:39` |
| knowledge-base | `GET` | `/api/v1/kb/bases` | `list_bases` | `apps/services/knowledge-base/src/app/kb_base_routes.py:380` |
| knowledge-base | `POST` | `/api/v1/kb/bases` | `create_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:354` |
| knowledge-base | `DELETE` | `/api/v1/kb/bases/{base_id}` | `delete_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:441` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}` | `get_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:403` |
| knowledge-base | `PATCH` | `/api/v1/kb/bases/{base_id}` | `update_base` | `apps/services/knowledge-base/src/app/kb_base_routes.py:409` |
| knowledge-base | `GET` | `/api/v1/kb/bases/{base_id}/documents` | `list_base_documents` | `apps/services/knowledge-base/src/app/kb_base_routes.py:470` |
| knowledge-base | `POST` | `/api/v1/kb/chunks/merge` | `merge_document_chunks` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:59` |
| knowledge-base | `PATCH` | `/api/v1/kb/chunks/{chunk_id}` | `patch_chunk` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:39` |
| knowledge-base | `POST` | `/api/v1/kb/chunks/{chunk_id}/split` | `split_document_chunk` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:53` |
| knowledge-base | `GET` | `/api/v1/kb/connectors` | `list_connectors` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:244` |
| knowledge-base | `POST` | `/api/v1/kb/connectors` | `create_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:276` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/local-directory/sync` | `sync_local_directory` | `apps/services/knowledge-base/src/app/kb_sync_routes.py:20` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/notion/sync` | `sync_notion_pages` | `apps/services/knowledge-base/src/app/kb_sync_routes.py:61` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/run-due` | `run_due_connectors` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:463` |
| knowledge-base | `DELETE` | `/api/v1/kb/connectors/{connector_id}` | `delete_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:384` |
| knowledge-base | `GET` | `/api/v1/kb/connectors/{connector_id}` | `get_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:327` |
| knowledge-base | `PATCH` | `/api/v1/kb/connectors/{connector_id}` | `update_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:333` |
| knowledge-base | `GET` | `/api/v1/kb/connectors/{connector_id}/runs` | `list_connector_runs` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:405` |
| knowledge-base | `POST` | `/api/v1/kb/connectors/{connector_id}/sync` | `run_connector` | `apps/services/knowledge-base/src/app/kb_connector_routes.py:425` |
| knowledge-base | `POST` | `/api/v1/kb/documents/batch-update` | `batch_update_documents` | `apps/services/knowledge-base/src/app/kb_base_routes.py:477` |
| knowledge-base | `DELETE` | `/api/v1/kb/documents/{document_id}` | `delete_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:604` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}` | `get_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:542` |
| knowledge-base | `PATCH` | `/api/v1/kb/documents/{document_id}` | `update_document` | `apps/services/knowledge-base/src/app/kb_base_routes.py:598` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/chunks` | `get_document_chunks` | `apps/services/knowledge-base/src/app/kb_chunk_routes.py:17` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/events` | `get_document_events` | `apps/services/knowledge-base/src/app/kb_base_routes.py:633` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions` | `get_document_versions` | `apps/services/knowledge-base/src/app/kb_base_routes.py:548` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions/{version_id}/content` | `get_document_version_content` | `apps/services/knowledge-base/src/app/kb_base_routes.py:554` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/versions/{version_id}/diff` | `get_document_version_diff` | `apps/services/knowledge-base/src/app/kb_base_routes.py:570` |
| knowledge-base | `GET` | `/api/v1/kb/documents/{document_id}/visual-assets` | `get_document_visual_assets` | `apps/services/knowledge-base/src/app/kb_base_routes.py:652` |
| knowledge-base | `GET` | `/api/v1/kb/ingest-jobs/{job_id}` | `get_ingest_job` | `apps/services/knowledge-base/src/app/kb_ingest_routes.py:17` |
| knowledge-base | `POST` | `/api/v1/kb/ingest-jobs/{job_id}/retry` | `retry_ingest_job` | `apps/services/knowledge-base/src/app/kb_ingest_routes.py:26` |
| knowledge-base | `POST` | `/api/v1/kb/query` | `query_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:145` |
| knowledge-base | `POST` | `/api/v1/kb/query/stream` | `stream_query_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:192` |
| knowledge-base | `POST` | `/api/v1/kb/retrieve` | `retrieve_kb` | `apps/services/knowledge-base/src/app/kb_query_routes.py:63` |
| knowledge-base | `POST` | `/api/v1/kb/retrieve/debug` | `retrieve_kb_debug` | `apps/services/knowledge-base/src/app/kb_query_routes.py:107` |
| knowledge-base | `POST` | `/api/v1/kb/uploads` | `create_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:37` |
| knowledge-base | `GET` | `/api/v1/kb/uploads/{upload_id}` | `get_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:136` |
| knowledge-base | `POST` | `/api/v1/kb/uploads/{upload_id}/complete` | `complete_upload` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:168` |
| knowledge-base | `POST` | `/api/v1/kb/uploads/{upload_id}/parts/presign` | `presign_upload_parts` | `apps/services/knowledge-base/src/app/kb_upload_routes.py:143` |
| knowledge-base | `GET` | `/api/v1/kb/visual-assets/{asset_id}/regions` | `get_visual_asset_regions` | `apps/services/knowledge-base/src/app/kb_visual_routes.py:24` |
| knowledge-base | `GET` | `/api/v1/kb/visual-assets/{asset_id}/thumbnail` | `get_visual_asset_thumbnail` | `apps/services/knowledge-base/src/app/kb_visual_routes.py:15` |
| api-gateway | `DELETE, GET, OPTIONS, PATCH, POST, PUT` | `/api/v1/kb/{path:path}` | `proxy_kb` | `apps/services/api-gateway/src/app/gateway_admin_routes.py:109` |
| api-gateway | `POST` | `/api/v1/mcp` | `post_mcp` | `apps/services/api-gateway/src/app/gateway_mcp_routes.py:17` |
| api-gateway | `GET` | `/api/v1/platform/agent-profiles` | `get_agent_profiles` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:132` |
| api-gateway | `POST` | `/api/v1/platform/agent-profiles` | `post_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:138` |
| api-gateway | `DELETE` | `/api/v1/platform/agent-profiles/{profile_id}` | `remove_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:178` |
| api-gateway | `GET` | `/api/v1/platform/agent-profiles/{profile_id}` | `get_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:154` |
| api-gateway | `PATCH` | `/api/v1/platform/agent-profiles/{profile_id}` | `patch_agent_profile` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:161` |
| api-gateway | `GET` | `/api/v1/platform/prompt-templates` | `get_prompt_templates` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:81` |
| api-gateway | `POST` | `/api/v1/platform/prompt-templates` | `post_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:87` |
| api-gateway | `DELETE` | `/api/v1/platform/prompt-templates/{template_id}` | `remove_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:124` |
| api-gateway | `GET` | `/api/v1/platform/prompt-templates/{template_id}` | `get_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:102` |
| api-gateway | `PATCH` | `/api/v1/platform/prompt-templates/{template_id}` | `patch_prompt_template` | `apps/services/api-gateway/src/app/gateway_platform_routes.py:108` |
| api-gateway | `GET` | `/api/v1/system/metrics-summary` | `metrics_summary` | `apps/services/api-gateway/src/app/gateway_system_routes.py:63` |
| api-gateway | `POST` | `/api/v2/chat/interrupts/{interrupt_id}/submit` | `submit_chat_interrupt` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:259` |
| api-gateway | `GET` | `/api/v2/chat/runs/{run_id}` | `get_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:218` |
| api-gateway | `POST` | `/api/v2/chat/runs/{run_id}/resume` | `resume_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:226` |
| api-gateway | `POST` | `/api/v2/chat/threads` | `create_chat_thread` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:120` |
| api-gateway | `GET` | `/api/v2/chat/threads/{thread_id}` | `get_chat_thread` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:160` |
| api-gateway | `GET` | `/api/v2/chat/threads/{thread_id}/messages` | `list_chat_thread_messages` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:166` |
| api-gateway | `POST` | `/api/v2/chat/threads/{thread_id}/runs` | `create_chat_run` | `apps/services/api-gateway/src/app/gateway_chat_graph_routes.py:178` |
| knowledge-base | `POST` | `/api/v2/kb/query` | `query_kb_v2` | `apps/services/knowledge-base/src/app/kb_query_routes.py:185` |
| knowledge-base | `POST` | `/api/v2/kb/retrieve` | `retrieve_kb_v2` | `apps/services/knowledge-base/src/app/kb_query_routes.py:83` |
| api-gateway | `GET` | `/healthz` | `healthz` | `apps/services/api-gateway/src/app/gateway_system_routes.py:20` |
| knowledge-base | `GET` | `/healthz` | `healthz` | `apps/services/knowledge-base/src/app/kb_system_routes.py:17` |
| api-gateway | `GET` | `/metrics` | `metrics` | `apps/services/api-gateway/src/app/gateway_system_routes.py:68` |
| knowledge-base | `GET` | `/metrics` | `metrics` | `apps/services/knowledge-base/src/app/kb_system_routes.py:33` |
| api-gateway | `GET` | `/readyz` | `readyz` | `apps/services/api-gateway/src/app/gateway_system_routes.py:47` |
| knowledge-base | `GET` | `/readyz` | `readyz` | `apps/services/knowledge-base/src/app/kb_system_routes.py:22` |
