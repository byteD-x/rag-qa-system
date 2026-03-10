# 开发脚本与本地工作流

## 推荐顺序

```powershell
make preflight
make init
make up
make smoke-eval
```

这四步分别对应：

- `make preflight`：启动前基线检查
- `make init`：显式初始化数据库、对象存储和 Qdrant
- `make up`：启动完整项目并托管前端开发服务器
- `make smoke-eval`：上传最小样例文档并执行 grounded / agent / refusal smoke 评测

## 常用目标

| 命令 | 作用 |
| --- | --- |
| `make preflight` | 运行编码检查、前端构建、Python 编译、后端测试、compose 配置检查 |
| `make init` | 启动 `postgres`、`minio`、`qdrant` 并执行 `stack-init` |
| `make up` | 启动 `postgres`、`minio`、`qdrant`、`kb-service`、`kb-worker`、`gateway` 和前端 |
| `make down` | 停止本地环境 |
| `make logs` | 查看最近日志 |
| `make logs-follow` | 持续跟随日志 |
| `make smoke-eval` | 创建 smoke corpus、上传 fixture、等待 ingest 并跑 eval suite |

## 脚本入口

- `scripts/dev/preflight.ps1`
- `scripts/dev/init.ps1`
- `scripts/dev/up.ps1`
- `scripts/dev/down.ps1`
- `scripts/dev/smoke-eval.ps1`
- `scripts/dev/smoke_eval.py`

## smoke-eval 行为

`make smoke-eval` 会自动完成以下动作：

1. 读取 `.env` 中的 `ADMIN_EMAIL` 与 `ADMIN_PASSWORD`
2. 调用本地 `gateway` 登录
3. 创建两套 smoke knowledge base
4. 上传内置 fixture 文档
5. 轮询 ingest job，直到完成
6. 生成运行时 suite 配置
7. 调用 `scripts/evaluation/run-eval-suite.py`
8. 输出报告到 `artifacts/reports/agent_smoke_report.json` 和 `artifacts/reports/agent_smoke_report.md`

## CI 友好参数

`scripts/dev/smoke_eval.py` 现在支持以下参数，便于在 GitHub Actions 或本地容器化环境里直接复用：

- `--wait-for-ready`：先轮询 `gateway` 与 `kb-service` 的就绪地址，再开始 smoke
- `--wait-timeout-seconds <n>`：控制等待上限
- `--gateway-health-url <url>`：覆盖默认的 `gateway /readyz`
- `--kb-health-url <url>`：覆盖默认的 `kb-service /readyz`

典型 CI 调用：

```bash
python scripts/dev/smoke_eval.py --password ChangeMe123! --wait-for-ready --wait-timeout-seconds 240
```

## Eval 报告补充

统一 eval 报告现在除了原有的召回、拒答与延迟指标，还会补充：

- `dataset_version`
- `prompt_version`
- `model_version`
- `execution_mode`
- `citation_alignment`
- `faithfulness`
- `correctness`

其中后三者是可解释启发式指标，用于回答质量门禁和面试答辩，不应被表述成严格人工标注分。

`run-eval-suite.py` 生成的 suite 级 Markdown 摘要也会把 `suite_version`、`dataset version`、`execution modes`、`prompt versions`、`model versions` 一并带出，便于 CI artifact 直接横向对比。

## 基线命令

```powershell
python scripts/quality/check-encoding.py
cd apps/web && npm run build
python -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
python -m pytest tests -q
docker compose config --quiet
```

## AI 平台配置入口

与新增后端能力相关的环境变量如下：

- `PROMPT_REGISTRY_JSON` / `PROMPT_REGISTRY_PATH`
  覆盖内置 prompt 的 `key`、`version`、`route_key`
- `LLM_MODEL_ROUTING_JSON` / `AI_MODEL_ROUTING_JSON`
  为 `grounded`、`common_knowledge`、`agent` 指定不同模型与 provider
- `RERANK_PROVIDER`
  默认是 `heuristic`，可切换为 `external-cross-encoder`
- `RERANK_API_BASE_URL` / `RERANK_API_KEY` / `RERANK_MODEL`
  外部 rerank provider 的最小配置
- `RERANK_TIMEOUT_SECONDS` / `RERANK_TOP_N` / `RERANK_EXTRA_BODY_JSON`
  rerank provider 的超时、候选数和扩展请求体
- `VISION_PROVIDER` / `VISION_FALLBACK_PROVIDER` / `VISION_API_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL`
  视觉 OCR / VLM provider 配置

当外部视觉 provider 返回 `layout_hints` 与 `regions` 时，worker 会额外生成 `visual_region` section/chunk，用于更细粒度的检索与 rerank。

完整约定见 [`docs/backend/ai-platform-governance.md`](../backend/ai-platform-governance.md)。
