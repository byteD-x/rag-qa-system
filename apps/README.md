# Apps

`apps/` 存放所有可运行应用。

## 目录说明

- `backend/`：后端服务集合
- `web/`：统一前端应用

## 约定

- 后端服务目录内只放该服务自己的应用代码、迁移和运行依赖
- 前端目录内只放前端源码、构建配置和静态资源
- 跨服务共享逻辑不放在 `apps/`，统一放到 `packages/`

## 与成本估算相关的边界

- AI 成本估算由 `apps/backend/gateway` 统一负责。
- `apps/web` 只消费 `gateway` 返回的 `cost` 字段，不自行推导币种或单价。
- 价格配置来源于根目录 [`.env`](/E:/Project/rag-qa-system/.env) 和 [`.env.example`](/E:/Project/rag-qa-system/.env.example)。
