# Gateway Readyz Trace 透传验证记录

日期：2026-06-09

## 范围

- `apps/services/api-gateway/src/app/gateway_system_routes.py`
  - Gateway `/readyz` 调用 KB Service `/readyz` 时透传当前 `X-Trace-Id`。
  - 复用 `shared.tracing.trace_headers()`，保持与其他下游请求相同的 trace 上下文来源。
- `tests/test_backend_infra.py`
  - 在 Gateway readiness 定点回归中捕获下游请求 headers，确认当前 trace id 会传给 KB readiness。

## 已验证

- `.venv\Scripts\python.exe -m pytest tests/test_backend_infra.py::test_gateway_readiness_checks_degrade_llm_without_failing tests/test_backend_infra.py::test_gateway_readiness_sanitizes_kb_error_detail tests/test_backend_infra.py::test_downstream_headers_uses_trace_context_and_explicit_override -q`
  - 结果：`3 passed in 2.87s`
- `.venv\Scripts\python.exe -m py_compile apps\services\api-gateway\src\app\gateway_system_routes.py tests\test_backend_infra.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 441 files.`
- `.venv\Scripts\python.exe -m compileall packages\python apps\services\api-gateway apps\services\knowledge-base`
  - 结果：通过
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。
- `docker compose config --quiet`
  - 结果：未执行成功，本机缺少 `docker` 命令。
- `.venv\Scripts\python.exe -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('docker-compose.yml').read_text(encoding='utf-8')); print('docker-compose.yml parsed')"`
  - 结果：`docker-compose.yml parsed`

## 风险

- 本改动只影响 Gateway readiness 到 KB readiness 的内部探活请求 headers，不改变 `/readyz` 响应结构。
- 未新增鉴权 header；KB `/readyz` 仍按原有公开探针语义工作。
- 本机缺少 Docker，完整 `docker compose config --quiet` 需在安装 Docker 的环境补跑。
