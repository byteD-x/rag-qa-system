# Token-aware 分块验证记录

日期：2026-06-09

## 范围

- 将 `api-gateway` 原有 `estimate_tokens()` 估算逻辑抽到 `packages/python/shared/token_estimation.py`。
- 让 `apps/services/api-gateway/src/app/context_window.py` 继续以原名称导出 `estimate_tokens()`，但复用 shared 实现。
- 在 `apps/services/knowledge-base/src/app/parsing.py` 的 `build_section_chunks()` 增加显式可选 `max_tokens` / `token_overlap` 参数。
- 保持默认入库路径仍为字符滑窗，不新增环境变量，不改变 batch dry-run、ingest 或 auto-index 响应字段。

## 子代理结论与采用情况

- Huygens 只读调查确认分块核心在 `apps/services/knowledge-base/src/app/parsing.py::build_section_chunks()`，默认参数为 `DEFAULT_CHUNK_WINDOW = 1000`、`DEFAULT_CHUNK_OVERLAP = 120`。
- Huygens 指出 `apps/services/api-gateway/src/app/context_window.py` 已有可复用 token 估算逻辑，建议抽到 `packages/python/shared`，避免 knowledge-base 反向依赖 api-gateway。已采用。
- Huygens 建议不改数据库 schema、手工 chunk 治理与向量索引流程。已采用。
- 子代理已关闭；最终实现、测试、文档和提交由主线程整合完成。

## 验证命令与结果

```powershell
.venv\Scripts\python.exe -m pytest tests/test_context_optimization.py -q
```

结果：27 passed。

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ai_platform_capabilities.py -q
```

结果：17 passed。

```powershell
.venv\Scripts\python.exe -m pytest tests/test_context_optimization.py tests/test_ai_platform_capabilities.py -q
```

结果：44 passed。

```powershell
.venv\Scripts\python.exe -m compileall packages/python apps/services/api-gateway apps/services/knowledge-base
```

结果：通过。

```powershell
.venv\Scripts\python.exe scripts\quality\check-encoding.py --root .
```

结果：Encoding check passed，Checked 435 files。

```powershell
git diff --check
```

结果：通过，仅有 Windows 工作区行尾提示。

```powershell
docker compose config --quiet
```

结果：未通过，当前环境没有 `docker` 命令，需在安装 Docker CLI / Docker Desktop 的环境补跑。

## 风险与边界

- `build_section_chunks()` 默认仍按字符 `window` 和 `overlap` 切片，现有 worker、batch ingest、dry-run 和 auto-index 默认行为不变。
- `max_tokens` 使用本地估算工具，不等同具体 provider tokenizer，也不是财务级或模型级精确 token 计数。
- 本轮没有实现 semantic chunking，也没有把 token-aware 模式切到默认入库主路径。
