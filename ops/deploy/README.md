# 低配 Linux 部署

`docker-compose.lowmem.yml` 用于 2 核、约 2 GB 内存的小规格 Linux 主机。它复用宿主机 PostgreSQL，不启动额外数据库容器；容器只运行 Qdrant、KB Service 和 Gateway。`nginx-kb.byted.online.conf` 将静态前端和 `/api/` 接入同一 HTTPS 域名。

## 资源与持久化

- Qdrant、KB Service、Gateway 的内存上限分别为 384 MiB、560 MiB、420 MiB；CPU 上限分别为 0.60、0.85、0.75 核。
- FastEmbed 限为单线程，索引批次为 16；KB ingest worker 在 KB Service 内运行，避免额外常驻容器。
- Qdrant 与文件对象存储分别持久化到 `ops/deploy/qdrant-data`、`ops/deploy/kb-data`。不要在升级时删除这两个目录。
- Qdrant、KB、Gateway 只绑定 `127.0.0.1`；公网入口由 Nginx 负责。

## 部署步骤

在服务器仓库根目录准备 `.env`，配置 PostgreSQL DSN、LLM 接入和生产认证信息；不要把真实密钥提交到仓库，文件权限建议设为 `600`。`.env` 中的管理员和成员密码应使用非默认随机值。

构建后端镜像并初始化数据库、文件存储和 Qdrant：

```bash
docker compose -f ops/deploy/docker-compose.lowmem.yml build kb-service gateway
docker compose -f ops/deploy/docker-compose.lowmem.yml run --rm stack-init python -m shared.stack_init
```

启动服务：

```bash
docker compose -f ops/deploy/docker-compose.lowmem.yml up -d --no-build kb-service gateway
docker compose -f ops/deploy/docker-compose.lowmem.yml ps
```

在服务器构建前端后，确保产物位于 `apps/web/dist`。Nginx 配置从该目录提供静态文件；HTTPS 配置要求证书已存在于 `/etc/letsencrypt/live/kb.byted.online/`。

```bash
cd apps/web && npm ci && npm run build
cd ../..
sudo cp ops/deploy/nginx-kb.byted.online.conf /etc/nginx/sites-enabled/kb.byted.online
sudo nginx -t && sudo systemctl reload nginx
```

## 验证与维护

```bash
curl -fsS http://127.0.0.1:8300/readyz
curl -fsS http://127.0.0.1:8080/readyz
curl -fsSI https://kb.byted.online/
docker stats --no-stream
```

低配配置会关闭自动向量重建（`KB_AUTO_REINDEX_AFTER_MIGRATION=false`），避免升级时在有限内存下意外重建大规模索引。若后续迁移明确要求重建已有向量，在维护窗口评估数据量与资源后，显式运行：

```bash
docker compose -f ops/deploy/docker-compose.lowmem.yml run --rm \
  -e KB_AUTO_REINDEX_AFTER_MIGRATION=true stack-init python -m shared.stack_init
```

执行前先备份 PostgreSQL 与 Qdrant 数据；重建完成后检查两项 `/readyz`。查看管理员或成员账号密码时仅在受控 SSH 会话中读取服务器 `.env`，不要复制到仓库或日志。
