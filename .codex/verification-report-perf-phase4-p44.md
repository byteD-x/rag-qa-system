# Phase 4 P4.4 compose 重写单机最小 + healthz→readyz — 验证记录

日期:2026-07-16

## 改动(docker-compose.yml)
- 删 `minio` 服务 + `minio_data` 卷(P4.1 文件系统后端替代)。
- 删 `kb-worker` 服务;kb-service 加 `KB_RUN_WORKER=${KB_RUN_WORKER:-true}`(P4.3 进程内 worker),单机减一容器。
- kb-service/stack-init 去掉 `depends_on: minio`;两者加 `OBJECT_STORAGE_PROVIDER=${OBJECT_STORAGE_PROVIDER:-filesystem}` 默认。
- kb-service 与 gateway 健康检查 `/healthz`→`/readyz`(深检依赖:kb 查 DB/存储/qdrant/config,gateway 查 DB/kb)。
- postgres 服务保留 `build:`(自定义镜像的 init 脚本建 kb_app/gateway_app 双库,不可改 image)。

## 服务拓扑(改后 5 个,原 7 个)
postgres、qdrant、stack-init(init profile)、kb-service(含进程内 worker)、gateway。

## 关键判断
- **readyz 做 healthcheck 无死锁**:依赖为 DAG(gateway→kb→DB/qdrant,kb 不依赖 gateway),无环。gateway `depends_on: kb-service service_healthy` 实现深度就绪门控。
- `x-object-storage-env` 锚点保留(其 minio 默认值在 filesystem 模式无害),使 s3 模式仍可配置(设 OBJECT_STORAGE_PROVIDER=s3 需自备 minio/S3)。

## 验证
- PyYAML 解析有效;服务列表/卷/环境/依赖/健康检查逐项核对正确;无 minio/kb-worker 残留(仅锚点默认值)。
- 无测试锁定 compose 服务;分组测试 33/33 全绿。

## 未验证(无 Docker,UNVERIFIED)
- 全新 `docker compose up`(5 服务、filesystem、进程内 worker、readyz 门控)真实起栈跑通上传→索引→问答闭环,未活体验证。
- readyz 作为 healthcheck 的实际就绪时序(20 次重试×5s=100s 窗口)是否足够,未活体验证。

## 待用户定夺(narrative,未擅改)
README 仍有 minio/kb-worker 部署引用(服务清单 227/230、健康地址 530-531、badge、env 段)。属作品集叙事,非测试门禁,与面试材料同批待用户决定是否更新为单机形态口径。
