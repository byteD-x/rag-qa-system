# Logging

实时日志入口已经统一成两条：

- `logs.bat`
- `python infra/logging/logs.py`

日志查看器会同时读取：

- `docker compose logs`
- `logs/dev/frontend.log`（由 `scripts/dev-up.ps1` 托管的前端开发服务）

常用命令：

```powershell
.\logs.bat
.\logs.bat -f
.\logs.bat -s go-api py-rag-service
.\logs.bat -s frontend -f
.\logs.bat -l ERROR
.\logs.bat --stats
```

日志快照导出：

```powershell
.\scripts\aggregate-logs.ps1
.\scripts\aggregate-logs.ps1 -Tail 2000
.\scripts\aggregate-logs.ps1 -Service go-api,frontend
```

完整的启动、停止、日志说明见 [docs/dev-scripts.md](../../docs/dev-scripts.md)。
