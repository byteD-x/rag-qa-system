# Gateway KB Readiness 透传验证记录

日期：2026-06-09

## 范围

- `apps/services/api-gateway/src/app/gateway_system_routes.py`
  - Gateway `/readyz` 在 `checks.kb_service` 中保留 KB Service `/readyz` 的 `upstream_status` 与字典型 `checks` 摘要。
  - 对上游错误 `detail` 做换行清理和长度截断，避免 Gateway 健康检查返回大段异常全文。
- `apps/services/api-gateway/src/app/main.py`
  - `_gateway_readiness_checks` 改为复用 `gateway_system_routes.gateway_readiness_checks`，避免 app 入口与真实路由各维护一份 readiness 逻辑。
- `README.md` 与 `docs/reference/api-specification.md`
  - 同步说明 Gateway `/readyz` 会透传 KB readiness 摘要。

## 已验证

- `.venv\Scripts\python.exe -m pytest tests/test_backend_infra.py::test_gateway_readiness_checks_degrade_llm_without_failing tests/test_backend_infra.py::test_gateway_readiness_sanitizes_kb_error_detail -q`
  - 结果：`2 passed in 2.59s`
- `.venv\Scripts\python.exe -m py_compile apps\services\api-gateway\src\app\gateway_system_routes.py apps\services\api-gateway\src\app\main.py tests\test_backend_infra.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 440 files.`
- `.venv\Scripts\python.exe -m compileall packages\python apps\services\api-gateway apps\services\knowledge-base`
  - 结果：通过
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。
- `docker compose config --quiet`
  - 结果：未执行成功，本机缺少 `docker` 命令。
- `.venv\Scripts\python.exe -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('docker-compose.yml').read_text(encoding='utf-8')); print('docker-compose.yml parsed')"`
  - 结果：`docker-compose.yml parsed`

## 风险

- Gateway 只透传 KB `/readyz` 已返回的检查摘要，不额外查询 KB 内部依赖。
- `checks.kb_service.checks` 仅保留字典型检查项；非字典 payload 会被忽略，以维持健康检查响应结构稳定。
- 上游错误摘要会截断，排障时如需完整错误仍应查看 KB Service 日志。
- 本机缺少 Docker，完整 `docker compose config --quiet` 需在安装 Docker 的环境补跑。
