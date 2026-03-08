# Web Console

`apps/web` 是统一前端，基于 `Vue 3 + TypeScript + Vite + Element Plus`。

## 职责

- 登录与权限展示
- AI 对话工作台
- 小说上传、问答、文档详情
- 企业库上传、问答、文档详情

## 路由结构

| 路由 | 说明 |
| --- | --- |
| `/login` | 登录页 |
| `/workspace/entry` | 统一入口页 |
| `/workspace/ai/chat` | AI 对话工作台 |
| `/workspace/novel/upload` | 小说上传页 |
| `/workspace/novel/chat` | 小说问答入口 |
| `/workspace/novel/documents/:id` | 小说文档详情 |
| `/workspace/kb/upload` | 企业库上传页 |
| `/workspace/kb/chat` | 企业库问答入口 |
| `/workspace/kb/documents/:id` | 企业库文档详情 |

## 与后端的边界

- 前端只通过 `gateway` 的 `/api/v1/*` 访问后端
- 不直接访问数据库或本地 blob 存储
- 小说、企业库、AI 对话共用同一前端壳层，但后端链路彼此独立

## 本地开发

```powershell
make up
```

单独调试：

```powershell
cd apps/web
npm install
npm run dev
npm run build
```

## 与成本字段的边界

- 前端不本地计算模型费用，统一读取 `gateway` 返回的 `cost` 字段。
- 如后续在页面展示成本，必须直接使用服务端返回的 `currency` 与 `estimated_cost`，不要在浏览器里硬编码 `USD` 或固定单价。
- AI 定价配置来源于根目录 [`.env`](/E:/Project/rag-qa-system/.env) 和 [`.env.example`](/E:/Project/rag-qa-system/.env.example)。
