# 平台质量切片验证记录

日期：2026-06-09

## 范围

- `apps/services/knowledge-base/src/app/worker.py`
  - `_build_section_and_chunks()` 增加可选 `max_tokens` / `token_overlap` 透传。
  - 默认生产调用仍不传参，保持字符窗口分块行为不变。
- `scripts/quality/select_fast_tests.py`
  - 补齐 `business_tools.py`、`token_estimation.py`、KB `parsing.py` / `worker.py` 的快速测试映射。
- `tests/*`
  - 增加 worker token 分块透传、selector 映射、shared tracing 边界回归。

## 子代理结果

- selector 子代理：只修改 `scripts/quality/select_fast_tests.py` 与 `tests/test_eval_pipeline.py`，已运行 selector 相关定向测试并通过；主代理补充纳入新增 worker token 透传测试。
- tracing 子代理：只修改 `tests/test_shared_stack.py`，已运行 shared stack 定向测试并通过。

## 验证

- `.venv\Scripts\python.exe -m pytest tests/test_ai_platform_capabilities.py tests/test_eval_pipeline.py tests/test_shared_stack.py -q`
  - 结果：`74 passed`
- `.venv\Scripts\python.exe -m py_compile apps/services/knowledge-base/src/app/worker.py scripts/quality/select_fast_tests.py packages/python/shared/tracing.py tests/test_ai_platform_capabilities.py tests/test_eval_pipeline.py tests/test_shared_stack.py`
  - 结果：通过
- `.venv\Scripts\python.exe scripts/quality/check-encoding.py --root .`
  - 结果：`Encoding check passed. Checked 435 files.`
- `git diff --check`
  - 结果：通过；仅出现 Git 工作区 CRLF 提示。

## 风险

- 本批未接入新的环境配置，也未改变默认 ingestion 分块策略。
- `worker.py` 只开放显式参数透传；真实默认路径仍沿用 `build_section_chunks(section)` 等价行为。
