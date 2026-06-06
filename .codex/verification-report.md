# 验证记录

> Last updated: 2026-06-06

## Agent 平台增强、人工接管队列与文档同步

完成内容：

- 新增 `apps/services/api-gateway/src/app/gateway_handoff.py`，提供 `HandoffQueueBackend` 协议与 `LocalSessionHandoffQueueBackend` 本地实现。
- 新增 `POST /api/v1/chat/handoff/claim-next`，按 `tenant_id`、`skill_group`、`operator_id` 认领下一条待人工接管会话。
- 将语义缓存元数据与规则级幻觉检测接入聊天响应和 LangGraph 生成路径。
- 修复请求合并 follower 读取 leader 响应、场景模板自定义模板读取、测试模块隔离与若干 UTF-8 BOM / 前端构建问题。
- 更新 `README.md`、`docs/reference/api-specification.md`、`docs/README.md`、`AGENTS.md`、`AI_HIGHLIGHTS.md`、STAR 与面试材料，明确本地实现、验证范围与生产 Redis / DB 后端边界。

已执行验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backend_infra.py -q -k "handoff"
.\.venv\Scripts\python.exe -m pytest tests/test_chat_workflow_resume_and_budget.py -q -k "semantic_cache or hallucination"
.\.venv\Scripts\python.exe -m pytest tests/test_inference_optimization.py tests/test_platform_ecosystem.py tests/test_agent_capabilities.py -q
.\.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .
.\.venv\Scripts\python.exe -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
cd apps\web; npm run test:unit
cd apps\web; npm run build
git diff --check -- .
```

结果：

- 人工接管队列定向测试通过：`3 passed, 74 deselected`。
- 语义缓存与幻觉检测定向测试通过：`3 passed, 12 deselected`。
- Agent / 推理优化 / 平台生态回归通过：`91 passed`。
- 编码检查通过：`Encoding check passed. Checked 368 files.`。
- Python 后端 `compileall` 通过。
- 前端 Vitest 通过：`9 passed` test files，`20 passed` tests。
- 前端生产构建通过：`vue-tsc -b && vite build` 完成。
- `git diff --check -- .` 通过；仅出现 Git 换行符转换 warning。

未完成的环境验证：

- `docker compose config --quiet` 未执行成功：当前环境没有 `docker` 命令，`where.exe docker` 返回 `INFO: Could not find files for the given pattern(s).`

边界与风险：

- 当前人工接管队列数据仍来自 `chat_sessions.scope_json.handoff`，适合本地测试和接口契约验证。
- 跨实例生产队列应替换为 Redis sorted set 或数据库 `SELECT ... FOR UPDATE SKIP LOCKED` 后端。
- 前端平台页本次补齐 `platformApi` 兼容导出以恢复构建；部分展示型平台端点仍需后续与 Gateway 真实路由逐项联调。

## AI 应用工程 P0 闭环改造

完成内容：

- 将 Agent 主链路改为可配置运行时：`GATEWAY_AGENT_RUNTIME=simple|enhanced`，默认保持 simple；开启 enhanced 时调用增强 Agent，失败自动回退 simple 并写入 retrieval metadata。
- 将生成后幻觉深检做成可配置门禁：`GATEWAY_HALLUCINATION_DEEP_CHECK_ENABLED=false` 默认关闭；开启后在规则检测后追加 LLM 深度一致性检查和 gate 元数据。
- smoke eval 的 CI artifact 上传范围补充 `agent_smoke_regression_gate.*`，便于审计 golden evaluation gate 的阈值结果。
- 同步 `.env.example` 与 `README.md`，记录新增运行时开关和默认行为。

已执行验证：

```powershell
.\.venv\Scripts\python.exe -m compileall apps/services/api-gateway/src/app/gateway_chat_service.py apps/services/api-gateway/src/app/gateway_config.py tests/test_backend_infra.py tests/test_chat_workflow_resume_and_budget.py
.\.venv\Scripts\python.exe -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
git diff --check -- .
where.exe docker
```

结果：

- 定向 `compileall` 通过，覆盖本次修改的 Gateway 配置、聊天服务与新增测试文件。
- Python 后端全仓 `compileall` 顺序重跑通过。并发验证时曾出现 Windows `__pycache__` 文件锁，顺序重跑后消失。
- `git diff --check -- .` 通过；仅出现 Git 换行符转换 warning。
- 当前环境没有 `docker` 命令，`where.exe docker` 返回 `INFO: Could not find files for the given pattern(s).`

未完成验证与限制：

- 新增后端 pytest 定向命令在 60 秒内无输出超时，已停止 job 且确认没有本仓库残留 Python 进程：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backend_infra.py tests/test_chat_workflow_resume_and_budget.py -q -k "agent_retrieval or hallucination_deep_gate"
```

- 编码检查在 60 秒内无输出超时，已停止 job 且确认没有本仓库残留 Python 进程：

```powershell
.\.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .
```

风险与后续补偿：

- `GATEWAY_AGENT_RUNTIME=enhanced` 会增加 Agent 编排成本与延迟，当前默认仍为 `simple`，增强运行时失败会回退 simple。
- `GATEWAY_HALLUCINATION_DEEP_CHECK_ENABLED=true` 会增加一次 LLM 深检调用，当前默认关闭；低置信回答只写入 gate metadata，未自动改写用户答案。
- 需要在 pytest 不再卡住的环境补跑新增定向测试、编码检查与 `docker compose config --quiet`。
