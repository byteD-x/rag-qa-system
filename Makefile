POWERSHELL ?= powershell
PS_FLAGS ?= -NoProfile -ExecutionPolicy Bypass

.PHONY: help init up down logs logs-follow export-logs ci test build encoding

help:
	@echo Available targets:
	@echo   make up           - 启动企业 RAG 本地环境
	@echo   make down         - 停止本地环境
	@echo   make logs         - 查看最近日志
	@echo   make logs-follow  - 持续跟随日志
	@echo   make export-logs  - 导出日志快照
	@echo   make ci           - 执行基础检查
	@echo   make test         - 执行前端构建和 Python 语法检查
	@echo   make build        - 构建 Docker 镜像
	@echo   make encoding     - 检查文本文件编码

init:
	$(POWERSHELL) $(PS_FLAGS) -File scripts/dev/init.ps1

up:
	$(POWERSHELL) $(PS_FLAGS) -File scripts/dev/up.ps1

down:
	$(POWERSHELL) $(PS_FLAGS) -File scripts/dev/down.ps1 -Force

logs:
	$(POWERSHELL) $(PS_FLAGS) -Command "& .\\logs.bat"

logs-follow:
	$(POWERSHELL) $(PS_FLAGS) -Command "& .\\logs.bat -f"

export-logs:
	$(POWERSHELL) $(PS_FLAGS) -File scripts/observability/aggregate-logs.ps1

ci:
	$(POWERSHELL) $(PS_FLAGS) -File scripts/quality/ci-check.ps1

test:
	python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
	cd apps/web && npm run build

build:
	docker compose build --pull

encoding:
	python scripts/quality/check-encoding.py
