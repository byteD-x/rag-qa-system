# Phase 4 P4.2 pgvector→postgres:16 — 验证记录

日期:2026-07-16

## 改动
- `api-gateway/database/migrations/001_init.sql`:删 `CREATE EXTENSION vector`(gateway 库无向量对象,仅曾建扩展)。
- `knowledge-base/database/migrations/002_ingest_and_retrieval.sql`:删 `CREATE EXTENSION vector`、`kb_embedding_cache` 表、kb_sections/kb_chunks 的 `embedding VECTOR(512)` 列、两个 hnsw 索引。保留 fts_document/GIN、pg_trgm(KB 001,contrib 自带)。
- `ops/docker/postgres/Dockerfile`:`FROM pgvector/pgvector:pg16` → `FROM postgres:16`。保留自定义镜像(init 脚本建 kb_app/gateway_app 两库,不可丢)。

## 核实
- 代码零读写 kb_embedding_cache 与 embedding 列(向量检索全在 Qdrant)。
- 迁移无其他非标准扩展依赖(pg_trgm 为 contrib,postgres:16 自带;无 gen_random_uuid,ID 由应用传)。
- 分组测试 33/33 全绿。

## 未验证(无 Docker,标注 UNVERIFIED)
- 全新 `docker compose up` 用 stock postgres:16 起库跑通迁移 → 未活体验证。
- 迁移 checksum:改的是 001/002,已应用的库重跑 stack-init 会报 checksum mismatch → **仅对全新安装生效**(演示形态默认全新安装,已与用户确认可接受)。
