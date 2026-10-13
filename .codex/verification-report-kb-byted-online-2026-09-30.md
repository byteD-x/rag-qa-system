# kb.byted.online 部署验证记录

日期：2026-09-30

## 部署结果

- 服务器：2 核、约 2 GB RAM、2 GB swap；部署时根分区剩余约 17 GB。
- 域名：`kb.byted.online`，Nginx 为新域名单独添加站点，证书由 Let’s Encrypt 管理；原有 `blog.byted.online` 配置未改动。
- 服务：Qdrant、KB Service、Gateway 均运行并健康；PostgreSQL 复用服务器上独立的 `kb_app` / `gateway_app` 数据库。
- 持久化：Qdrant 与文件对象存储落在 `ops/deploy/qdrant-data`、`ops/deploy/kb-data`；`.env` 留在服务器且权限为 `600`，认证默认密码已替换为随机值，未记录或输出凭据。
- 低配策略：Compose 对三个常驻容器分别限制 384 / 560 / 420 MiB；FastEmbed 单线程、批次 16；服务端口仅监听回环地址。

## 验证证据

- `docker compose -f ops/deploy/docker-compose.lowmem.yml config --quiet`：通过。
- `python -m compileall -q packages/python/shared/stack_init.py`：通过。
- `python -m pytest -q tests/test_shared_stack.py`：当前工作区 Python 环境缺少 `langchain_core`，测试收集失败；未将其记为通过。
- 服务器 `python -m shared.stack_init`：成功，Gateway 11 项、KB 13 项迁移已登记；Qdrant collection `kb-evidence` 初始化成功，空库 payload 状态完成初始化。
- `http://127.0.0.1:8300/readyz` 与 `http://127.0.0.1:8080/readyz`：均返回 `ready`。
- 域名验证：HTTP 返回 301 到 HTTPS；HTTPS 证书校验通过；首页和 `/api/v1/system/metrics-summary` 返回 200；原有 `https://blog.byted.online/` 返回 200。
- 部署后观察到容器实际内存约为 Gateway 118 MiB、KB 162 MiB、Qdrant 27 MiB；主机可用内存约 1.0 GiB，swap 余量约 1.5 GiB。

## 代码与限制

- 新增低内存 Compose 和专属 Nginx 站点配置；Dockerfile 支持覆写 PyPI index，以适应服务器下载环境。
- 修复初始化摘要对文件存储后端错误访问 S3 `bucket` 字段的问题；仅影响初始化输出，不改变存储数据。
- 当前部署未导入业务文档，因此没有执行真实文档解析/向量索引负载测试。后续大批量索引可能增加内存和 swap 使用，需观察 `docker stats` 与主机内存。
