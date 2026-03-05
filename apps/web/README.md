# Web Console

`apps/web` 是 RAG-QA System 的管理后台与问答前端，技术栈为 Vue 3、TypeScript、Vite 和 Element Plus。

优先使用仓库根目录脚本启动整套开发环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-up.ps1
```

如果只需要单独调试前端：

```powershell
cd apps/web
npm install
npm run dev
npm run build
```

开发服务默认代理 `/v1` 到 `http://localhost:8080`。
