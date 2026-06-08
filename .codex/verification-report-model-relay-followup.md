# 模型中转站接入收尾验证记录

日期：2026-06-08

## 范围

- 继续复核模型中转站接入后的剩余风险。
- 修复 `api-gateway` 本地 `LLM_MODEL_ROUTING_JSON` 解析丢失 `fallback_route_key` 的问题。
- 补齐 OpenAI-compatible 非流式 completion 与流式非 SSE JSON 降级契约测试。
- 补齐前端模型接入页组件测试，覆盖“发现模型后默认选中第一项并生成部署配置片段”。

## 子代理结论与采用情况

- Helmholtz：确认后端模型发现、路由 fallback 和流式 happy path 已有覆盖；指出 `app.ai_client` 未保留 `fallback_route_key`，并建议补直接 completion 契约测试。已采用。
- Dirac：确认本仓库没有等价替代 `docker compose config --quiet` 的静态校验；建议只记录 Docker CLI 缺失并依赖 CI 或有 Docker 的环境补跑。已采用。
- Locke：确认前端 `/api/v1` platform 与 `/api/v2` chat 链路低风险；建议补 `ModelProviderView` 组件级组合测试。已采用。
- Kepler：新增前端组件级单测，仅修改测试文件；已复核并纳入最终验证。
- Gibbs：只读复核本轮 staged 改动，确认 `fallback_route_key` 链路、OpenAI-compatible 契约测试与前端测试边界无阻断问题。已关闭。

## 验证命令与结果

```powershell
.venv\Scripts\python.exe -m pytest tests\test_ai_platform_capabilities.py::test_gateway_llm_settings_parses_fallback_route_key_from_env tests\test_backend_infra.py::test_create_llm_completion_maps_openai_response_contract tests\test_backend_infra.py::test_create_llm_completion_stream_handles_non_sse_json_response tests\test_backend_infra.py::test_create_llm_completion_stream_yields_live_deltas -q
```

结果：4 passed。

```powershell
.venv\Scripts\python.exe -m pytest tests\test_ai_platform_capabilities.py -q
```

结果：16 passed。

```powershell
.venv\Scripts\python.exe -m pytest tests\test_backend_infra.py::test_generate_grounded_answer_retries_with_fallback_route tests\test_backend_infra.py::test_create_llm_completion_maps_openai_response_contract tests\test_backend_infra.py::test_create_llm_completion_stream_handles_non_sse_json_response tests\test_backend_infra.py::test_create_llm_completion_stream_yields_live_deltas -q
```

结果：4 passed。

```powershell
cd apps\web
npm run test:unit -- src/views/platform/ModelProviderView.test.ts
npm run test:unit
npm run build
```

结果：组件单测 1 passed；前端全量单测 15 files / 35 tests passed；前端构建通过。

```powershell
.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .
.venv\Scripts\python.exe -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
git diff --check
```

结果：编码检查通过；compileall 通过；`git diff --check` 通过，仅有 Windows 行尾提示。

```powershell
docker compose config --quiet
```

结果：未通过，当前环境没有 `docker` 命令。

## 未完成验证

- `docker compose config --quiet` 仍需在安装 Docker CLI / Docker Desktop 的本机或 CI runner 中补跑。
- 本轮未新增静态 Compose 替代校验，因为仓库现有脚本与 CI 均以 Docker Compose CLI 为准，PyYAML 解析不能等价覆盖 Compose schema、变量插值、扩展字段和 merge 行为。

## 风险

- 生产环境若不配置 `LLM_MODEL_DISCOVERY_ALLOWED_HOSTS` / `AI_MODEL_DISCOVERY_ALLOWED_HOSTS`，模型发现接口仍会兼容访问任意 OpenAI-compatible 中转站 Host；建议生产环境配置 allowlist。
- 本轮新增的 completion 契约测试覆盖非流式响应映射和非 SSE JSON 降级，未新增真实中转站集成测试；真实 newapi/sub2api 仍建议在可控环境用 mock server 或测试中转站补充端到端验证。
