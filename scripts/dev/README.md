# Dev Scripts

开发环境相关脚本。

## 文件说明

- `up.ps1`：启动 Docker 服务并托管前端
- `down.ps1`：停止 Docker 服务和托管前端
- `common.ps1`：共享 PowerShell 函数
- `frontend-runner.ps1`：后台启动前端开发服务器

## 环境变量说明

- 启动脚本默认要求根目录存在 [`.env`](/E:/Project/rag-qa-system/.env)。
- [`.env.example`](/E:/Project/rag-qa-system/.env.example) 已包含 `AI_PRICE_CURRENCY` 与 `AI_PRICE_TIERS_JSON`，用于统一聊天的服务端成本估算。
- 如只修改 AI 定价，不需要改前端脚本；重启 `gateway` 即可让新价格生效。
