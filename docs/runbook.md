# 运行手册

本手册面向本地开发、演示环境维护和日常排障。

## 统一排障原则

1. 先确认是 `novel` 线路、`kb` 线路还是 `gateway` 汇总链路的问题。
2. 先看状态和健康检查，再看日志。
3. 优先执行可回滚的恢复动作，不直接删库或清理数据目录。

## 第一响应检查

```powershell
docker compose ps
.\logs.bat -l ERROR -s gateway novel-service kb-service
```

确认：

- `postgres`、`minio`、`gateway`、`novel-service`、`kb-service` 都在运行
- `http://localhost:8080/healthz`、`http://localhost:8100/healthz`、`http://localhost:8300/healthz` 能正常返回
- 前端仍可访问 `http://localhost:5173`

## 场景 1：小说上传后一直停留在处理中

现象：

- 文档状态长时间停留在 `uploaded`、`parsing_fast` 或 `fast_index_ready`
- 事件时间线不再推进

排查：

```powershell
.\logs.bat -f -s gateway novel-service
```

重点确认：

- `data/novel/<document_id>/` 下是否已落盘源文件
- `NOVEL_DATABASE_DSN` 是否正确
- `novel-worker` 是否在运行

## 场景 2：企业库上传后解析失败

现象：

- 文档进入 `failed`
- 事件里只有 `uploaded`

排查：

```powershell
.\logs.bat -f -s gateway kb-service
```

重点确认：

- 文件类型是否在 `txt / pdf / docx` 范围内
- `data/kb/<document_id>/source.*` 是否存在
- `kb-worker` 和 `kb_app` 数据库是否正常

## 场景 3：登录返回 401

排查顺序：

1. 确认请求走的是 `POST /api/v1/auth/login`
2. 核对 [`.env`](/E:/Project/rag-qa-system/.env) 中本地账号字段
3. 查看 `gateway` 日志

```powershell
.\logs.bat -f -s gateway -k auth
```

## 场景 4：统一聊天返回拒答或无证据

排查顺序：

1. 文档是否已进入 `fast_index_ready`、`hybrid_ready` 或 `ready`
2. 作用域里的 `corpus_id`、`document_id` 是否正确
3. 检查 `novel-service` 或 `kb-service` 的检索日志

```powershell
.\logs.bat -f -s novel-service
.\logs.bat -f -s kb-service
```

## 场景 5：网关返回 502 或 503

排查：

```powershell
docker compose ps
.\logs.bat -f -s gateway novel-service kb-service
```

重点确认：

- `NOVEL_SERVICE_URL`、`KB_SERVICE_URL` 是否和 compose 服务名一致
- 下游服务是否通过健康检查
- 宿主机端口是否被 [`.env`](/E:/Project/rag-qa-system/.env) 中的端口配置覆盖

## 场景 6：数据库初始化异常

排查：

```powershell
docker compose logs postgres --tail 200
docker compose config --quiet
```

当前 `db-bootstrap` 会创建三个数据库：

- `novel_app`
- `kb_app`
- `gateway_app`

## 场景 7：成本币种或价格档位异常

排查顺序：

1. 检查 [`.env`](/E:/Project/rag-qa-system/.env) 中的 `AI_PRICE_CURRENCY`
2. 检查 `AI_PRICE_TIERS_JSON` 是否是合法 JSON，且档位上限与价格没有写反
3. 发起一次统一聊天请求，确认返回的 `cost.pricing_mode` 是 `tiered` 还是 `flat`
4. 修改后重启 `gateway`，再次验证 `cost.currency` 与 `cost.selected_tier`

说明：

- `cost` 由 `gateway` 服务端计算，前端不本地计算币种或单价
- `AI_INPUT_PRICE_PER_1K_TOKENS` 与 `AI_OUTPUT_PRICE_PER_1K_TOKENS` 仅在未配置阶梯时回退使用

## 日志导出

```powershell
.\scripts\observability\aggregate-logs.ps1
.\scripts\observability\aggregate-logs.ps1 -Service gateway,novel-service,kb-service,frontend
```

## 安全恢复建议

可以安全尝试的动作：

- 重启单个容器
- 重新登录
- 重新上传单个文档
- 导出日志快照
- 重跑前端构建和 compose 配置检查

需要谨慎的动作：

- 手动修改数据库记录
- 直接删除数据卷
- 手动改写 `data/novel` 或 `data/kb` 下的文件
