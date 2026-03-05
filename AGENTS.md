# AGENTS.md

> 本文件定义本仓库的人机协作协议（Owner / AI Agent / Reviewer）。
> Last updated: 2026-03-06

## 1. 目标与范围

本规范适用于仓库根目录及所有子目录，目标是让 AI 参与开发时做到：
- 结果可验证：每项完成都能用命令或测试结果证明
- 过程可追踪：任务状态、阻塞原因、变更范围清晰
- 风险可控：默认小步变更、可回滚、避免破坏性操作

## 2. 角色定义

- `Owner`：定义业务目标、确认优先级、做最终取舍
- `AI Agent`：执行实现、补齐测试与文档、输出验证证据
- `Reviewer`：审查风险与回归，确认是否达到交付标准

## 3. 协作原则（必须遵守）

1. 不暴露敏感信息：禁止输出或提交密钥、口令、token、连接串、`.env` 内容。
2. 不使用高风险命令：默认禁止破坏性操作（删库、强推、覆盖生产配置等）。
3. 不做“猜测完成”：没有验证结果时不得标记 `done`。
4. 不做超大改动：超过当前任务边界的重构必须先拆分并获得确认。
5. 保持编码一致性：新增或修改文件统一使用 `UTF-8`（无 BOM）。
6. 接口/配置变更必须同步文档：至少更新 `README.md`、`AGENTS.md` 或相关 `docs/*`。

## 4. 状态机

任务状态统一使用以下枚举：
- `todo`：已记录，尚未开始
- `in_progress`：正在执行
- `blocked`：存在外部依赖或关键不确定项，无法继续
- `review`：开发完成，等待审查或验收
- `done`：验证通过并完成交接

允许的流转：
- `todo -> in_progress -> review -> done`
- 任意状态在遇到阻塞时可转 `blocked`
- `blocked` 解除后回到 `in_progress`

## 5. AI Agent 标准执行流程

1. 明确范围：复述目标、列出本次改动边界。
2. 读取上下文：先看相关代码与文档，再落地改动。
3. 最小实现：优先小改动，避免无关重构。
4. 自检验证：执行必要测试/检查，记录命令与结果。
5. 文档同步：使用方式、接口、配置变化必须更新文档。
6. 交付说明：输出 What / Why / How to verify。

## 6. Definition of Done

同时满足以下条件才可标记 `done`：
- 功能或文档改动与任务目标一致
- 关键路径验证通过（测试、脚本或手工步骤）
- 无新增敏感信息泄露风险
- 受影响文档已同步
- 交接信息完整（变更文件、验证命令、已知限制）

## 7. 基线验证命令

在仓库根目录执行：

- `python scripts/check_encoding.py`
- `cd services/go-api && go test ./...`
- `cd services/py-rag-service && python -m pytest -q`
- `cd services/py-worker && python -m pytest -q`
- `docker compose config --quiet`

说明：
- 文档类改动至少执行编码检查与 `docker compose config --quiet`
- 涉及服务逻辑时需补跑对应模块测试

## 8. 任务记录规范

### 8.1 里程碑表模板
| milestone | description | owner | status | updated_at |
|---|---|---|---|---|
| Mx | 一句话目标 | `@owner` | `todo` | YYYY-MM-DD |

### 8.2 任务表模板
| task_id | milestone | title | assignee | status | verify_cmd | expected_result | updated_at |
|---|---|---|---|---|---|---|---|
| T-XXX-001 | Mx | 任务名称 | `@agent` | `todo` | `cmd` | 一句话结果 | YYYY-MM-DD |

记录要求：
- 开始执行前将状态改为 `in_progress`
- 遇阻塞立即改为 `blocked` 并写明原因
- 进入 `review` 前必须补齐验证命令
- 验收后再改为 `done`

## 9. Blocked 上报格式

当任务进入 `blocked`，按以下结构同步：
- `问题`：阻塞点是什么
- `影响`：阻塞影响了哪些交付
- `已尝试`：做过哪些排查或替代方案
- `需要决策`：Owner 需要给出的最小决策

## 10. 交付输出模板（提交/PR 描述）

- `What`：改了什么
- `Why`：为什么这样改
- `How to verify`：如何验证（命令 + 预期结果）
- `Risk`：已知风险与回滚方式
