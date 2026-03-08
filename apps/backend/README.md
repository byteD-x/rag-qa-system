# Backend Apps

`apps/backend/` 存放三个后端服务。

## 服务说明

- `gateway/`：统一认证、路由聚合、统一聊天、AI 代理和成本估算
- `novel-service/`：小说上传、解析、检索、问答
- `kb-service/`：企业知识库上传、解析、检索、问答

## 服务内公共结构

- `app/`：运行时代码
- `migrations/`：数据库初始化或迁移脚本
- `Dockerfile`：镜像构建入口
- `requirements.runtime.txt`：运行依赖

## 统一成本估算归属

- `gateway/` 负责统一聊天链路中的 `cost` 字段计算和币种标记。
- `novel-service/` 与 `kb-service/` 不直接做模型费用估算，只返回检索与证据结果。
- 如需调整 AI 成本估算逻辑，优先查看 [gateway README](/E:/Project/rag-qa-system/apps/backend/gateway/README.md) 和 [API 说明](/E:/Project/rag-qa-system/docs/API_SPECIFICATION.md)。
