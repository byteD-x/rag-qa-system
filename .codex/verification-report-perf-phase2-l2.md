# Phase 2(L2)物理删除死代码 — 验证记录

日期:2026-07-16

## 删除的 14 个模块(均先核实零生产引用)

agent_orchestrator, agent_metacognition, agent_error_recovery, agent_guardrails,
context_compressor, memory_extractor, memory_injection, memory_integrator,
complexity_classifier, instruction_merger, ttft_optimizer, scene_templates,
request_coalescer, instruction_hotreload。

核实手段:①非测试文件对每个模块的 import 全为空;②无动态导入(importlib/__import__);③app 包 __init__ 无再导出;④无模块注册 FastAPI 路由(API 索引不受影响)。删除后全仓生产码对这 14 模块零残留导入,gateway 全量 compileall 通过,app.main 导入 OK。

## 测试处理

- **整删**:test_agent_metacognition.py(纯测 agent_metacognition + agent_error_recovery)。
- **外科编辑(保留活码用例,均单验通过)**:
  - test_agent_orchestration(删 TestAgentOrchestrator,保留 cost_budget 的两个测试类)
  - test_memory_enhancement(删五元组/整合器/注入器,保留 memory_importance/user_profile)
  - test_context_optimization(删 TestExtractiveCompressor,保留 context_window/prioritizer)
  - test_agent_capabilities(删 TestMemoryExtractor + 集成内 test_memory_store_upsert_and_search)
  - test_platform_ecosystem_phase2(删护栏/热更新/TTFT,保留共享 banner 下的 AB 评估器)
  - test_platform_ecosystem(删 instruction_merger/scene_templates/集成块,保留幻觉检测/SDK)
  - test_inference_optimization(删复杂度/请求合并,保留语义缓存/模型健康)
  - 各文件同步更新 docstring(去已删模块名)

## 映射/证据脚本连带清理(强耦合,成对改)

- `select_fast_tests.py`:删 13 个死模块的路由映射键。
- `test_eval_pipeline.py`:5 个路由断言函数删死输入+死输出(精确 == 断言,与上表成对)。
- `check-job-alignment-evidence.py`:删 agent_orchestrator 的 EvidenceCheck(文件已删)、去掉 test_inference_optimization 断言里的 RequestCoalescer 符号。

## 保留的活码(严守 14 清单,不扩删)

cost_budget、memory_importance(仅被同批删的 memory_injection/integrator 引用,删后变孤儿但守清单不扩删,标记为待跟进)、user_profile、context_window、context_prioritizer、tool_registry、semantic_cache、hallucination_detector、pii_detector、instruction_evaluator、model_health、task_decomposer、agent_reflection。

## README 事实文档修正

README「项目结构」架构树删去 5 个已删文件行(memory_extractor/instruction_merger/scene_templates/complexity_classifier/request_coalescer),保留活码行。

## 验证

- 分组测试(权威口径):`groups=33 failed=0 scheduled=33 skipped=0`(原 34 组,减 test_agent_metacognition)。
- gateway compileall 通过;app.main(Gateway)与 shared/KB 导入 OK;全仓零残留死模块导入。

## 待用户定夺(未擅自改的叙事项)

两份**面试材料**仍把已删模块当技术亮点展示,非测试门禁,属作品集自我定位,按既有约定「简历亮点须确认」不擅自重写:
- `docs/job-driven-project-enhancement.md`:第 73-74 行代码指针含 agent_orchestrator、ttft_optimizer。
- `docs/reference/RAG_STAR_TECHNICAL_CHALLENGES.md`:第 308/311 行描述 ComplexityClassifier、RequestCoalescer。
建议:或更新为"已建后为单机精简移除"的叙事,或删除对应段落——待用户选择。
