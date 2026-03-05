.PHONY: test build up down logs logs-follow export-logs fmt

test:
	cd services/go-api && go test ./...
	cd services/py-rag-service && python -m pytest -q
	cd services/py-worker && python -m pytest -q

build:
	docker compose build

up:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-up.ps1

down:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev-down.ps1 -Force

logs:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\\logs.bat"

logs-follow:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\\logs.bat -f"

export-logs:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/aggregate-logs.ps1

fmt:
	cd services/go-api && go fmt ./...
