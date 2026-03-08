# Gateway Service

统一网关负责三类能力：

- 本地认证与 JWT 签发
- `novel-service`、`kb-service` 的统一代理与聚合
- 统一聊天链路中的 AI 调用、证据融合、成本估算和元数据回传

## 目录说明

- `app/main.py`：FastAPI 入口，暴露认证、统一聊天、AI 对话和代理路由
- `app/ai_client.py`：OpenAI-compatible 模型客户端
- `app/db.py`：网关数据库连接和 schema 初始化
- `migrations/`：`gateway_app` 初始化 SQL
- `requirements.runtime.txt`：运行依赖

## 关键环境变量

- `NOVEL_SERVICE_URL`
- `KB_SERVICE_URL`
- `GATEWAY_TIMEOUT_SECONDS`
- `AI_CHAT_ENABLED`
- `AI_PROVIDER`
- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`
- `AI_CHAT_TIMEOUT_SECONDS`
- `AI_DEFAULT_TEMPERATURE`
- `AI_DEFAULT_MAX_TOKENS`
- `AI_SYSTEM_PROMPT`
- `AI_EXTRA_BODY_JSON`
- `AI_PRICE_CURRENCY`
- `AI_PRICE_TIERS_JSON`
- `AI_INPUT_PRICE_PER_1K_TOKENS`
- `AI_OUTPUT_PRICE_PER_1K_TOKENS`

## AI 定价与成本估算

- 统一聊天接口里的 `cost` 字段由服务端生成，不依赖前端本地计算。
- 默认币种由 `AI_PRICE_CURRENCY` 控制，当前示例值为 `CNY`。
- 优先读取 `AI_PRICE_TIERS_JSON` 做阶梯计费。
- 当 `AI_PRICE_TIERS_JSON` 为空或非法时，回退到 `AI_INPUT_PRICE_PER_1K_TOKENS` 与 `AI_OUTPUT_PRICE_PER_1K_TOKENS`。
- 当前 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 预置了 DashScope `qwen3.5-plus` 的三档价格：`<=128K`、`<=256K`、`<=1M`。

## 对外接口

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/ai/config`
- `POST /api/v1/ai/chat`
- `GET /api/v1/chat/corpora`
- `POST /api/v1/chat/sessions`
- `POST /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages/stream`
- `/api/v1/novel/*`
- `/api/v1/kb/*`

说明：

- `POST /api/v1/ai/chat` 返回模型原始对话结果和 `usage`，不附带统一聊天的 `cost` 聚合字段。
- `cost`、`retrieval`、`latency`、`trace_id` 属于统一聊天接口的增强元数据。
