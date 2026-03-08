# 文档中心

本目录是 `RAG-QA 2.0` 的正式文档入口，覆盖接口、启动方式、排障和报告说明。

## 导航

| 文档 | 用途 |
| --- | --- |
| [API 说明](API_SPECIFICATION.md) | 统一聊天、认证、上传、检索接口说明 |
| [开发脚本与本地工作流](dev-scripts.md) | 本地启动、停止、构建、验证和常用命令 |
| [运行手册](runbook.md) | 常见故障、排障顺序和安全恢复建议 |
| [Demo 数据集](demo-dataset/README.md) | 演示语料和样例数据的使用方式 |
| [报告目录](reports/README.md) | benchmark、ablation、eval 报告说明 |

## 文档边界

以下内容不视为正式产品说明文档：

- `docs/demo-dataset/**/*`：示例输入和评测数据
- `docs/reports/*`：阶段性评测与 benchmark 输出

## AI 定价与成本估算

- 根目录 [`.env.example`](/E:/Project/rag-qa-system/.env.example) 与 [`.env`](/E:/Project/rag-qa-system/.env) 默认包含 `AI_PRICE_CURRENCY` 和 `AI_PRICE_TIERS_JSON`。
- 当前示例档位对应 DashScope `qwen3.5-plus` 中国内地价格，按输入 token 档位切换输入与输出单价。
- `AI_INPUT_PRICE_PER_1K_TOKENS` 与 `AI_OUTPUT_PRICE_PER_1K_TOKENS` 仅在未配置 `AI_PRICE_TIERS_JSON` 时作为回退值使用。
- 统一聊天接口中的 `cost` 字段结构与含义以 [API 说明](API_SPECIFICATION.md) 为准。

## 维护约定

- 接口、环境变量、启动方式发生变化时，必须同步更新本目录文档。
- 文档以当前默认运行路径为准，不再描述旧的单服务直连方式。
- 新增文档优先回答三个问题：做什么、怎么用、怎么验证。
