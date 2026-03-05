# Development Scripts

本仓库的本地开发脚本现在统一围绕三件事设计：

- 一键启动项目
- 一键停止项目
- 在项目运行后稳定查看实时日志

## 脚本清单

- `scripts/dev-up.ps1`
  负责启动 Docker Compose 服务，并托管前端 `vite` 开发服务
- `scripts/dev-down.ps1`
  负责停止 Docker Compose 服务，并停止脚本托管的前端进程
- `logs.bat`
  负责查看实时日志，默认同时显示 Docker 日志和托管前端日志
- `scripts/aggregate-logs.ps1`
  负责导出当前日志快照，便于排障和归档
- `scripts/check_encoding.py`
  负责检查仓库文本文件是否为 UTF-8 且无 BOM

## 启动项目

在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-up.ps1
```

默认行为：

- 执行 `docker compose up -d --remove-orphans --build`
- 等待 `go-api` 和 `py-rag-service` 的基础健康检查通过
- 如果 `apps/web/node_modules` 不存在，则自动安装前端依赖
- 启动受脚本托管的前端开发服务
- 将前端 PID 和日志写入 `logs/dev/`

常用参数：

```powershell
.\scripts\dev-up.ps1 -NoBuild
.\scripts\dev-up.ps1 -SkipFrontend
.\scripts\dev-up.ps1 -SkipHealthCheck
.\scripts\dev-up.ps1 -AttachLogs
```

说明：

- `-NoBuild`：跳过镜像构建，适合依赖和 Dockerfile 未变化时重复启动
- `-SkipFrontend`：只启动 Docker Compose，不启动前端开发服务
- `-SkipHealthCheck`：不等待 HTTP 健康检查完成
- `-AttachLogs`：启动完成后直接进入实时日志跟随模式

## 停止项目

在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-down.ps1
```

默认行为：

- 停止脚本托管的前端开发服务
- 执行 `docker compose down --remove-orphans`

常用参数：

```powershell
.\scripts\dev-down.ps1 -Force
.\scripts\dev-down.ps1 -RemoveVolumes
.\scripts\dev-down.ps1 -RemoveImages
```

说明：

- `-Force`：不再二次确认
- `-RemoveVolumes`：同时删除 Compose 命名卷
- `-RemoveImages`：同时删除当前项目构建出来的镜像

## 查看实时日志

在仓库根目录执行：

```powershell
.\logs.bat -f
```

默认会同时跟随：

- `docker compose logs --follow`
- `logs/dev/frontend.log`

常用命令：

```powershell
.\logs.bat
.\logs.bat -f
.\logs.bat -s go-api py-rag-service
.\logs.bat -s frontend -f
.\logs.bat -l ERROR
.\logs.bat -k timeout
.\logs.bat --stats
.\logs.bat --no-frontend
```

说明：

- `-s frontend` 表示只看脚本托管的前端日志
- `--no-frontend` 表示只看 Docker Compose 日志
- `--stats` 会输出最近日志的服务分布和级别分布

## 导出日志快照

```powershell
.\scripts\aggregate-logs.ps1
.\scripts\aggregate-logs.ps1 -Tail 2000
.\scripts\aggregate-logs.ps1 -Service go-api,py-rag-service,frontend
```

输出目录默认是 `logs/export/`，会生成：

- `ALL/<service>.log`
- `ERROR/errors_<timestamp>.log`
- `WARNING/warnings_<timestamp>.log`
- `summary_<timestamp>.txt`

## 运行状态文件

脚本托管的运行状态写入：

- `logs/dev/frontend.pid`
- `logs/dev/frontend.log`

这些文件仅用于本地开发流程控制，不应提交到仓库。
