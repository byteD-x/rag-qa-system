# Phase 1(L0)零风险清理 — 验证记录

日期:2026-07-16

## 改动项(均先核实计划断言在当前代码成立,防旧审阅漂移)

1. **删 rapidocr-onnxruntime**(`apps/services/knowledge-base/requirements.runtime.txt:18`)
   - 核实:全仓无 `import rapidocr`,纯占镜像(~130MB,含 cv2)。删 1 行。

2. **删 qdrant_store 死码嵌入**(`packages/python/shared/qdrant_store.py`)
   - 核实:`embed_passages`/`embed_query`/`_get_fastembed_model` 全仓零引用(旧审阅说的 tests/scripts 引用已不存在);`_vector_to_list` 仅被这几个函数调用,是传递性孤儿,一并删。删 4 个函数共 32 行。
   - 保留:`TextEmbedding` 导入(第 118 行 `list_supported_models` 仍用)、`lru_cache`(第 134 行另一处仍用)、全部 `fastembed_*` settings 字段(描述集合嵌入配置,活码)。
   - `semantic_cache.py` 的 `_default_embed_query` 是不同符号(用 `shared.embeddings.embed_query_text`),不受影响。

3. **删 compose AI_* 冗余透传**(`docker-compose.yml` x-llm-env 锚点,删 16 个 AI_ 行)
   - 核实:全部 16 个 AI_* 在代码中均为 `_read_env("LLM_x", "AI_x")` 形式即 **LLM_ 优先、AI_ 兜底**(证据:`ai_client.py:185-206`、`llm_settings.py:137-158`、`gateway_config.py:56-64/211-219`、`gateway_llm_models.py:67`、`gateway_chat_service.py:992`)。
   - 保留:代码里的 AI_ fallback 读取不动(无害);compose 只留 16 个 LLM_ 键即可驱动全部功能。
   - 注意命名非纯前缀替换的对:AI_CHAT_ENABLED↔LLM_ENABLED、AI_CHAT_TIMEOUT_SECONDS↔LLM_TIMEOUT_SECONDS、AI_DEFAULT_TEMPERATURE↔LLM_TEMPERATURE、AI_DEFAULT_MAX_TOKENS↔LLM_MAX_TOKENS,均已逐一核对。

4. **新建 `.env.minimal`**(+ `.gitignore` 白名单放行)
   - 定位:最短的、能起功能可用且基本安全的单机演示 env。
   - 基础设施项(DSN/QDRANT_URL/KB_SERVICE_URL)有面向 compose 内网的可用默认,未纳入。
   - 显式标注耦合坑:改 POSTGRES_PASSWORD 须同步改两个 DSN。

## 验证

- 分组测试(权威口径):`groups=34 failed=0 scheduled=34 skipped=0`,与基线一致,零回归。
- compose YAML 有效;gateway 环境 AI_ 键 0 个、LLM_ 键 16 个(锚点正确合并)。
- import 冒烟:`shared.qdrant_store` 干净导入(死码函数已消失)、`app.main`(KB)导入 OK。
- tests 无任何对被删项(AI_ 透传/rapidocr/embed_passages)的断言。

## 未验证/限制

- 无 Docker:未做镜像体积实测(rapidocr 省 ~130MB 为依赖体积估算)、未做活体 up + healthz。
