# 文档总览

> Last updated: 2026-06-06

本目录收纳项目的参考文档、API 规范、面试材料和架构图。日常使用优先阅读根目录 [README.md](../README.md)，需要接口、工作流或展示口径细节时再进入本目录。

## 推荐阅读顺序

| 场景 | 文档 | 用途 |
|---|---|---|
| 了解项目和本地启动 | [README.md](../README.md) | 项目能力、快速开始、环境变量、验证命令 |
| 查接口契约 | [reference/api-specification.md](reference/api-specification.md) | Gateway 与 KB Service 的核心 HTTP API |
| 查路由索引 | [API_ROUTE_INDEX.md](API_ROUTE_INDEX.md) | 静态生成的 FastAPI path、method、handler 与源码位置清单 |
| 理解企业聊天补问 | [reference/enterprise-chat-v2.md](reference/enterprise-chat-v2.md) | LangGraph v2 线程、运行、中断、恢复与 `answer_basis` |
| 理解人工接管队列 | [reference/api-specification.md](reference/api-specification.md) | Gateway 本地接管队列、认领请求与生产后端边界 |
| 理解知识库智能提问 | [reference/kb-smart-ask-workflow.md](reference/kb-smart-ask-workflow.md) | 文档详情页到聊天页的结构化提问链路 |
| 理解知识库运维页 | [reference/kb-governance-workbench.md](reference/kb-governance-workbench.md) | 治理、队列、低置信视觉区域、受控 rebuild、批量 JSON 预览/写入、只读索引摘要与批处理事件 |
| 准备项目展示 | [../AI_HIGHLIGHTS.md](../AI_HIGHLIGHTS.md) | AI 能力亮点、工程边界与作品集表达 |
| 快速校准面试口径 | [interview-playbook.md](interview-playbook.md) | 最新 Tool Calling、MCP、缓存、Docker 与 trace 边界 |
| 查看一页式亮点 | [PROJECT_HIGHLIGHTS_SUMMARY.md](PROJECT_HIGHLIGHTS_SUMMARY.md) | 简历可写能力、证据路径和边界说明 |
| 查看仓库盘点 | [STAR_REPO_INVENTORY.md](STAR_REPO_INVENTORY.md) | tracked source、入口点、文档和质量门禁 |
| 查看 STAR 主材料 | [STAR_REPO_STAR.md](STAR_REPO_STAR.md) | 当前仓库 STAR 条目、Action/Result 与证据 |
| 准备 STAR 面试 | [reference/RAG_STAR_TECHNICAL_CHALLENGES.md](reference/RAG_STAR_TECHNICAL_CHALLENGES.md) | 技术难点、解决方案、证据路径、验证命令 |
| 准备完整问答 | [reference/RAG_INTERVIEW_MATERIAL.md](reference/RAG_INTERVIEW_MATERIAL.md) | 深度面试材料和追问索引 |
| 练习面试问答 | [reference/rag-ai-engineer-interview-master-qa.md](reference/rag-ai-engineer-interview-master-qa.md) | 主审问答顺序 |
| 补充实现细节 | [reference/rag-ai-engineer-interview-qa-detailed.md](reference/rag-ai-engineer-interview-qa-detailed.md) | 详细问答版 |
| 练习口语表达 | [reference/rag-ai-engineer-interview-spoken.md](reference/rag-ai-engineer-interview-spoken.md) | 口语版表达 |

## 维护规则

- API、环境变量、启动方式、目录结构、脚本入口或用户可见页面发生变化时，同步更新 [README.md](../README.md) 和对应 `docs/reference/*`。
- 涉及面试或简历表达时，继续区分“已实现”“已验证”“可选增强”“待补指标”，不要把最小 fixture 结果写成真实业务收益。
- 文档类改动至少执行：

```powershell
python scripts/quality/check-encoding.py --root .
docker compose config --quiet
```

## 图示资产

- [assets/architecture-overview.svg](assets/architecture-overview.svg)：README 中引用的系统架构图。
