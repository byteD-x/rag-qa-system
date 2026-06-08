# 模型中转站接入验证报告

日期：2026-06-08

## 范围

- 新增 OpenAI-compatible `/models` 模型发现能力。
- 新增前端“模型接入”平台页，用于发现中转站模型并生成配置片段。
- 修复前端 `/api/v2/chat/*` 请求被 `/api/v1` baseURL 误拼接的问题。
- 同步 `LLM_MODEL_ROUTING_JSON` compose 传递、README 与 API 路由索引。
- 增加可选 `LLM_MODEL_DISCOVERY_ALLOWED_HOSTS` / `AI_MODEL_DISCOVERY_ALLOWED_HOSTS`，用于生产环境限制可被模型发现请求访问的中转站 Host。
- 补充后端 URL 规范化、非法协议、Host 白名单拒绝、路由审计脱敏测试，以及前端 `/api/v2` proxy 回归测试。

## 子代理结论采用情况

- Euler：确认现有 `LLM_BASE_URL`、`LLM_MODEL_ROUTING_JSON` 已能覆盖 newapi/sub2api 主接入点；采用其建议补模型发现 API 与 compose 环境变量。
- Raman：确认前端没有 provider/model 选择入口，并发现 `/api/v2` 请求路径与 Vite proxy 脱节；采用其建议新增平台页并修复 v2 请求/proxy。
- Tesla：确认后端主链路成熟度风险集中在 LLM 双配置实现、LangChain 主链路契约测试不足、readyz 对 LLM 过宽松、流式错误契约不足；本次记录为后续高优先级治理项。
- Meitner：复核后端模型发现满足 OpenAI-compatible 中转站 `/models` 获取，建议补 URL 边界与审计脱敏测试；已采用。
- Carver：复核前端 `/api/v1` platform 与 `/api/v2` chat 链路正确，建议补 `/api/v2` Vite proxy 断言；已采用。
- Hilbert：复核文档与验证记录，指出 README 中 compose 传递范围应为 Gateway 服务，并建议记录 Docker 补跑计划；已采用。

## 验证命令

```powershell
.venv\Scripts\python.exe -m pytest tests\test_ai_platform_capabilities.py -q
npm run test:unit
npx vitest run vite.config.test.ts
npx vitest run src\router\operationsRoute.test.ts
npm run build
.venv\Scripts\python.exe -m compileall packages\python apps\services\api-gateway apps\services\knowledge-base
.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .
git diff --check
docker compose config --quiet
```

## 结果

- `tests/test_ai_platform_capabilities.py`：15 passed。
- `apps/web npm run test:unit`：14 files / 34 tests passed。首次全量运行中 `operationsRoute.test.ts` 出现一次超时；单跑该测试通过，随后重跑全量通过。
- `apps/web npx vitest run vite.config.test.ts`：1 file / 4 tests passed。
- `apps/web npx vitest run src\router\operationsRoute.test.ts`：1 file / 2 tests passed。
- `apps/web npm run build`：通过。
- `compileall`：通过。
- 编码检查：通过，检查 428 个文件。
- `git diff --check`：通过，仅输出 Windows 行尾提示。

## 未完成验证

- `docker compose config --quiet` 未执行成功：当前环境没有 `docker` 命令。
- 补偿计划：需要在安装 Docker CLI / Docker Desktop 的本机或 CI runner 中补跑 `docker compose config --quiet`；通过后更新本报告。

## 残余风险

- 模型发现会让后端请求用户输入的 `base_url`，当前通过 `chat.use` 权限、`http/https` URL 校验、不保存密钥、路由审计脱敏测试和可选 Host 白名单降低风险。若生产环境不配置 `LLM_MODEL_DISCOVERY_ALLOWED_HOSTS`，仍会保持对任意 OpenAI-compatible 中转站的兼容，也保留相应 SSRF 风险面。
- 中转站兼容性仍需补 mock OpenAI-compatible server 契约测试，覆盖 usage 缺失、流式、tool_calls、错误体和超时。
