# Phase 0 基线与安全网 — 验证记录

日期:2026-07-16
分支策略:用户要求仓库只保留 `main`,重设计直接在 main 上做;每个 Phase 验证通过后才提交推送,失败则本地回退到上一 Phase 提交,远端 main 始终保持绿。

## 测试基线(权威口径)

- **正确跑法**:`run_pytest_groups.py`(每测试文件独立子进程),规避两个服务共用包名 `app` 的跨文件 `sys.modules` 污染。
- **命令**:`.venv/Scripts/python.exe scripts/quality/run_pytest_groups.py tests --max-workers 4`
- **结果**:`groups=34 failed=0 scheduled=34 skipped=0`,全绿,耗时约 58s。
- **注意**:平铺 `pytest tests` 单进程会假性失败 43 项(`No module named 'app.tool_registry'` 等),那是包名冲突假象,非真实红。后续每阶段一律用分组跑法对比。

## 既有真红修复(动手前清零)

- `test_api_route_index.py::test_api_route_index_document_matches_current_sources` 在动手前即失败。
- 根因:`docs/API_ROUTE_INDEX.md` 记录的路由源码行号与当前源码漂移(既有,非本次改动引入;已核实两次提交未碰任何路由/gateway 文件)。
- 修复:官方生成器 `python scripts/generate_api_route_index.py --output docs/API_ROUTE_INDEX.md`,仅刷新 21 行行号,测试转绿。

## Compose 结构校验(Docker 缺失的替代)

- 本机无 Docker,`docker compose config` 不可用。
- 替代:PyYAML 解析 `docker-compose.yml`,YAML 结构有效。
- 服务清单(7 个):postgres、minio、qdrant、stack-init、kb-service、kb-worker、gateway。

## 检索质量基线(离线确定性锚点)

- **命令**:`python scripts/evaluation/run-retrieval-ablation.py --fixture tests/fixtures/evals/retrieval-ablation-fixture.json`
- **结果**:三变体 fusion_only / rewrite_plus_fusion / rewrite_plus_fusion_plus_rerank,recall@1 = recall@3 = mrr = ndcg@3 = **1.0**。
- 用途:Phase 3 检索改动的非劣化锚点,不得低于此。

## 环境约束(影响验证口径)

- **无 Docker**:无法测活体检索延迟/吞吐,无法做全新 `docker compose up` 闭环冒烟。
- **影响 Phase 3**:提速收益改由「往返次数/连接复用的结构分析 + 离线评测非劣化 + 单测」验证,不承诺活体延迟数字。
- **影响 Phase 4**:单机 compose 闭环冒烟在本环境无法执行,只能做结构校验与单测;活体闭环留待有 Docker 的环境复核(记为交付限制)。
