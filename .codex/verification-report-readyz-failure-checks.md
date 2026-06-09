# Readyz 失败检查摘要验证记录

日期：2026-06-09

## 范围

- `packages/python/shared/api_errors.py`
  - `json_error_response()` 新增可选 `extra`，用于在统一错误响应中追加诊断字段。
  - `extra` 不允许覆盖 `detail`、`code`、`trace_id`、`errors` 等基础错误字段。
- `apps/services/api-gateway/src/app/gateway_system_routes.py`
  - Gateway `/readyz` 在依赖失败返回 `503` 时保留 `status=not_ready` 与已计算的 `checks`。
  - 路由显式设置 `response_model=None`，避免 FastAPI 对 `dict | Response` 返回注解推导响应模型。
- `apps/services/knowledge-base/src/app/kb_system_routes.py`
  - KB Service `/readyz` 在依赖失败返回 `503` 时保留 `status=not_ready` 与已计算的 `checks`。
- `README.md` 与 `docs/reference/api-specification.md`
  - 同步说明 `/readyz` 失败响应仍携带 `trace_id`、`status=not_ready` 与 `checks` 诊断摘要。
- `tests/test_api_error_payloads.py` 与 `tests/test_backend_infra.py`
  - 覆盖 `extra` 不覆盖基础错误字段，以及 Gateway/KB `/readyz` 失败响应保留检查摘要。

## 已验证

- `.venv\Scripts\python.exe -m pytest tests/test_api_error_payloads.py tests/test_backend_infra.py::test_gateway_readyz_failure_response_includes_checks tests/test_backend_infra.py::test_kb_readyz_failure_response_includes_checks tests/test_backend_infra.py::test_gateway_readiness_checks_degrade_llm_without_failing tests/test_backend_infra.py::test_kb_readiness_checks_require_storage -q`
  - 结果：`7 passed in 21.80s`
- `.venv\Scripts\python.exe -m py_compile packages\python\shared\api_errors.py apps\services\api-gateway\src\app\gateway_system_routes.py apps\services\knowledge-base\src\app\kb_system_routes.py tests\test_api_error_payloads.py tests\test_backend_infra.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 442 files.`
- `.venv\Scripts\python.exe -m compileall packages\python apps\services\api-gateway apps\services\knowledge-base`
  - 结果：通过
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。
- `docker compose config --quiet`
  - 结果：未执行成功，本机缺少 `docker` 命令。
- `.venv\Scripts\python.exe -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('docker-compose.yml').read_text(encoding='utf-8')); print('docker-compose.yml parsed')"`
  - 结果：`docker-compose.yml parsed`

## 风险

- `/readyz` 成功响应保持 `{"status": "ready", "checks": ...}` 不变。
- 失败响应新增 `status` 与 `checks` 字段，原有 `503`、`detail`、`code`、`trace_id` 语义保持不变。
- `checks` 内容来自已有 readiness 检查；Gateway 对 KB 上游错误摘要仍沿用既有截断清洗逻辑。
- 本机缺少 Docker，完整 `docker compose config --quiet` 需在安装 Docker 的环境补跑。
