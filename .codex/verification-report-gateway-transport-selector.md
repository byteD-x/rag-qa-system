# Gateway Transport Selector 验证记录

日期：2026-06-09

## 范围

- `tests/test_backend_infra.py`
  - 增加 `downstream_headers()` trace 边界回归，覆盖当前 trace context 透传与显式 `trace_id` 覆盖。
- `scripts/quality/select_fast_tests.py`
  - 为 `apps/services/api-gateway/src/app/gateway_transport.py` 增加精确 fast test 映射。
- `tests/test_eval_pipeline.py`
  - 增加 selector 回归，确认不会回退到整份 `tests/test_backend_infra.py`。
- `docs/reference/rag-ai-engineer-interview-spoken.md`
  - 校准 chunking “不要说”示例，避免声称已默认启用 semantic chunking、parent-child retrieval 或 token-aware 入库主路径。

## 验证

- `.venv\Scripts\python.exe -m pytest tests/test_backend_infra.py::test_downstream_headers_uses_trace_context_and_explicit_override -q`
  - 结果：`1 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_eval_pipeline.py::test_fast_test_selector_routes_gateway_transport_to_focused_tests tests/test_backend_infra.py::test_downstream_headers_uses_trace_context_and_explicit_override tests/test_backend_infra.py::test_request_service_json_preserves_upstream_4xx tests/test_backend_infra.py::test_request_service_json_wraps_upstream_5xx_as_502 -q`
  - 结果：`4 passed`
- `.venv\Scripts\python.exe -m py_compile scripts\quality\select_fast_tests.py tests\test_backend_infra.py tests\test_eval_pipeline.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 437 files.`
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。

## 风险

- 本批不修改生产代码，不新增配置入口，不改变 KB 默认字符滑窗分块策略。
- selector 新增的是精确 nodeid 映射；若未来重命名测试函数，需要同步更新该映射。
