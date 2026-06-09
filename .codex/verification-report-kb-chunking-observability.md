# KB Chunking Observability 验证记录

日期：2026-06-09

## 范围

- `apps/services/knowledge-base/src/app/runtime.py`
  - `KBChunkingSettings` 增加 `enabled` 与 `summary()`，统一输出当前分块模式摘要。
  - `load_chunking_summary()` 供 readiness 诊断复用，避免重复解析逻辑。
- `apps/services/knowledge-base/src/app/kb_support.py`
  - `kb_readiness_checks()` 接收可选 `chunking_config_checker`。
  - 配置合法时返回 `chunking_config.status=ok`，配置非法时返回 `status=failed` 与错误摘要。
- `apps/services/knowledge-base/src/app/kb_api_support.py`
  - KB Service `/readyz` 注入 `load_chunking_summary()`，让 `KB_CHUNK_*` 配置错误可诊断。
- `apps/services/knowledge-base/src/app/worker.py`
  - 每个 ingest job 开始时读取一份 `KBChunkingSettings`，同一份配置透传给文本、二进制与视觉分块路径。
  - job checkpoint 与 stats 增加 `chunking` 摘要。
- `apps/services/knowledge-base/src/app/kb_batch_dry_run.py`
  - 每次 dry-run 请求读取一份分块配置，响应顶层增加 `chunking` 摘要。
- `apps/services/knowledge-base/src/app/kb_batch_ingest.py`
  - 每次 batch ingest 请求读取一份分块配置，响应顶层与文档 `stats_json` 增加同一份 `chunking` 摘要。
- `apps/services/knowledge-base/src/app/kb_auto_index.py`
  - fixed inbox preview 响应在正常、缺失 inbox、inbox 非目录三类路径下均增加 `chunking` 摘要。
- `README.md` 与 `docs/reference/*`
  - 同步说明 readiness、batch dry-run、batch ingest 与 auto-index preview 新增的分块策略摘要字段。

## 已验证

- `.venv\Scripts\python.exe -m pytest tests/test_ai_platform_capabilities.py::test_kb_chunking_settings_parse_env_defaults_and_validation tests/test_backend_infra.py::test_kb_readiness_checks_require_storage tests/test_backend_infra.py::test_knowledge_batch_dry_run_builds_sanitized_summary tests/test_backend_infra.py::test_knowledge_auto_index_preview_summarizes_fixed_inbox_without_raw_content tests/test_backend_infra.py::test_knowledge_auto_index_preview_reports_missing_inbox_without_path_leak tests/test_backend_infra.py::test_knowledge_batch_ingest_route_writes_inline_documents_without_raw_content -q`
  - 结果：`6 passed in 57.73s`
- `.venv\Scripts\python.exe -m py_compile apps/services/knowledge-base/src/app/runtime.py apps/services/knowledge-base/src/app/kb_api_support.py apps/services/knowledge-base/src/app/kb_support.py apps/services/knowledge-base/src/app/worker.py apps/services/knowledge-base/src/app/kb_batch_ingest.py apps/services/knowledge-base/src/app/kb_batch_dry_run.py apps/services/knowledge-base/src/app/kb_auto_index.py tests/test_ai_platform_capabilities.py tests/test_backend_infra.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts/quality/check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 439 files.`
- `.venv\Scripts\python.exe -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base`
  - 结果：通过
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。
- `docker compose config --quiet`
  - 结果：未执行成功，本机缺少 `docker` 命令。
- `.venv\Scripts\python.exe -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('docker-compose.yml').read_text(encoding='utf-8')); print('docker-compose.yml parsed')"`
  - 结果：`docker-compose.yml parsed`

## 风险

- 默认未配置 `KB_CHUNK_MAX_TOKENS` 时仍使用字符滑窗，现有 ingestion 行为不变。
- `chunking` 字段只暴露策略摘要，不返回正文、chunk text、embedding 或本机路径。
- token 预算仍基于本地估算，不是 semantic chunking，也不是模型 tokenizer 的精确计数。
- 本机缺少 Docker，已用 YAML 解析作为配置语法补偿检查；完整 `docker compose config --quiet` 需在安装 Docker 的环境补跑。
