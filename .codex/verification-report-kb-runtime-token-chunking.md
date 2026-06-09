# KB Runtime Token Chunking 验证记录

日期：2026-06-09

## 范围

- `apps/services/knowledge-base/src/app/parsing.py`
  - `parse_document()` 与 `parse_text_content()` 支持可选 `max_tokens` / `token_overlap` 参数。
- `apps/services/knowledge-base/src/app/runtime.py`
  - 新增 `KB_CHUNK_MAX_TOKENS` / `KB_CHUNK_TOKEN_OVERLAP` 运行配置解析，默认关闭。
- `apps/services/knowledge-base/src/app/worker.py`
  - worker 文本、PDF/DOCX 与视觉 OCR/region 入库路径透传 chunking 配置。
- `apps/services/knowledge-base/src/app/kb_batch_ingest.py`
  - inline batch ingest 使用相同 chunking 配置。
- `apps/services/knowledge-base/src/app/kb_batch_dry_run.py`
  - dry-run 摘要按相同配置预览 chunk 数。
- `apps/services/knowledge-base/src/app/kb_auto_index.py`
  - fixed inbox preview 按相同配置预览 chunk 数。
- `.env.example`、`docker-compose.yml`、`README.md`
  - 记录并透传可选配置入口；默认留空，不改变字符滑窗行为。

## 已验证

- `.venv\Scripts\python.exe -m pytest tests/test_ai_platform_capabilities.py::test_kb_parse_text_content_can_apply_token_chunking_options tests/test_ai_platform_capabilities.py::test_kb_chunking_settings_parse_env_defaults_and_validation tests/test_ai_platform_capabilities.py::test_kb_worker_can_forward_token_chunking_options -q`
  - 结果：`3 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_ai_platform_capabilities.py::test_kb_parse_text_content_can_apply_token_chunking_options tests/test_ai_platform_capabilities.py::test_kb_chunking_settings_parse_env_defaults_and_validation tests/test_ai_platform_capabilities.py::test_kb_worker_can_forward_token_chunking_options tests/test_backend_infra.py::test_knowledge_batch_dry_run_builds_sanitized_summary tests/test_backend_infra.py::test_knowledge_auto_index_preview_summarizes_fixed_inbox_without_raw_content tests/test_backend_infra.py::test_knowledge_batch_ingest_route_writes_inline_documents_without_raw_content -q`
  - 结果：`6 passed`
- `.venv\Scripts\python.exe -m py_compile apps\services\knowledge-base\src\app\parsing.py apps\services\knowledge-base\src\app\runtime.py apps\services\knowledge-base\src\app\worker.py apps\services\knowledge-base\src\app\kb_batch_ingest.py apps\services\knowledge-base\src\app\kb_batch_dry_run.py apps\services\knowledge-base\src\app\kb_auto_index.py tests\test_ai_platform_capabilities.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 438 files.`
- `.venv\Scripts\python.exe -m compileall packages\python apps\services\api-gateway apps\services\knowledge-base`
  - 结果：通过
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。
- `docker compose config --quiet`
  - 结果：未执行成功，本机缺少 `docker` 命令。
- Python YAML 补偿检查 `docker-compose.yml`
  - 结果：解析通过，`kb-service` 与 `kb-worker` 均包含 `KB_CHUNK_MAX_TOKENS` / `KB_CHUNK_TOKEN_OVERLAP`。

## 风险

- 默认配置为空时，`load_chunking_settings().as_kwargs()` 返回空字典，旧分块行为保持不变。
- `KB_CHUNK_TOKEN_OVERLAP` 必须与 `KB_CHUNK_MAX_TOKENS` 一起设置；单独设置会失败，避免误以为已经启用 token-aware 分块。
- token 数基于本地估算，仍不是 semantic chunking，也不是模型 tokenizer 的精确账单口径。
