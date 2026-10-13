# Docker 本地运行验证记录

## 已通过

- `docker compose build`：Gateway、KB Service、PostgreSQL 镜像构建成功。
- `scripts/dev/init.ps1`：数据库迁移、文件系统对象存储和 Qdrant 初始化返回 `status: ok`。
- `scripts/dev/up.ps1 -NoBuild -SkipPull`：基础服务和前端启动成功。
- `docker compose ps`：PostgreSQL、Qdrant、KB Service、Gateway 均为运行状态，应用容器为 `healthy`。
- `http://localhost:5173/`、Gateway/KB `/readyz`、Qdrant `/healthz`：均返回 HTTP 200。
- 前端单测：17 个测试文件、37 个测试通过。
- 前端生产构建：`npm run build` 成功。
- Python 编译、编码检查、Compose 配置检查：通过。

## 外部限制

- 在线 smoke eval 的上传、索引和检索链路成功；生成请求被外部 DashScope 返回 `403 AllocationQuota.FreeTierOnly`，表示当前账号免费额度耗尽。回归门禁因此失败，未将该外部配额问题伪装成代码通过。
- 宿主 Python 运行 `tests/test_container_assets.py tests/test_shared_stack.py` 时因缺少 `langchain_core` 在收集阶段失败；Docker 镜像已在运行时依赖中包含该包。
