# 企业聊天 v2

`/api/v2/chat/threads/{thread_id}/runs` 与 `/api/v2/chat/runs/{run_id}/resume` 现已支持第一阶段企业级澄清闭环，覆盖：

- 多版本文档确认
- 截图区域确认
- 先比较再回答
- 显式回答依据元数据

## 澄清触发顺序

网关会按以下顺序判断是否需要先补问：

1. 检索范围为空
2. 时间或版本语义不明确
3. 检索结果命中版本冲突
4. 检索结果命中多个截图区域
5. 证据不足

这样可以让客户端的补问流程更稳定，也更容易预测。

## 中断载荷

当系统暂时不能安全作答时，接口会返回 `status=interrupted`，并在 `interrupt.payload` 中携带补问信息：

- `kind`: `time_ambiguity | version_conflict | visual_ambiguity | scope_ambiguity | insufficient_evidence`
- `title`
- `detail`
- `question`
- `subject?`
  - `type`: `version_family | visual_region_group`
  - `id`
  - `summary`
- `options[]`
  - `id`
  - `label`
  - `description`
  - `badges?`：用于展示的扁平标签，例如 `current`、`effective`、`v2`、`p.3`、`72.0%`
  - `meta?`：结构化展示信息，例如 `version_label`、`page_number`、`region_id`、`confidence`
  - `patch`：服务端恢复运行时使用的内部补丁数据
- `recommended_option_id`
- `allow_free_text`
- `fallback_prompt`

### 版本确认选项

当 `kind` 为 `time_ambiguity` 或 `version_conflict` 时，选项中可能出现：

- 当前有效版本
- 历史版本候选
- `compare:*` 比较选项
- 自由补充输入兜底

即使前端使用单选 UI，也可以直接处理比较选项。服务端会把比较选项映射为：

- `document_ids`：包含两个版本
- `focus_hint.kind = compare_versions`
- 内部追加的 `question_suffix`，用于提示模型先总结差异再回答

### 截图确认选项

当 `kind` 为 `visual_ambiguity` 时，每个选项中可能包含：

- 版本标签
- 页码
- 区域标签
- 置信度
- `focus_hint.kind = visual_region`

用户选定区域后，系统会优先用该区域参与后续检索与重排，而不是只把它当作自由文本提示。

## 恢复请求

`POST /api/v2/chat/runs/{run_id}/resume` 支持以下字段：

- `selected_option_ids`
- `free_text`
- `question`
- `allow_common_knowledge`
- `target_version_ids`
- `effective_at`
- `override_scope`
- `focus_hint`

其中 `focus_hint` 是可选且向后兼容的。正常产品流程下，它通常由用户选中的补问选项自动生成。

## 最终回答载荷

回答成功后，响应中会包含 `answer_basis`：

- `kind`
  - `single_version`
  - `compare_versions`
  - `visual_region`
  - `evidence`
- `label`
- `document_ids?`
- `asset_id?`
- `region_id?`
- `version_labels?`
- `compare_summary?`

回答正文也会带上可读的“回答依据”前缀。在版本比较模式下，差异摘要会出现在最终答案正文之前。

## 引用跳转行为

视觉类引用仍会返回：

- `assetId`
- `regionId`

前端现在会把引用深链到文档详情页，并附带：

- `versionId`
- `assetId`
- `regionId`

这样用户跳转后，就能同时聚焦到对应版本、对应截图和对应区域。

## 上传与同步时的版本辅助

知识库上传完成响应与连接器同步结果中，可能包含 `version_assist`：

- `suggested_version_family_key`
- `suggested_version_label`
- `suggested_supersedes_document_id`
- `confidence`
- `reasons[]`
- `auto_apply`

版本辅助规则按以下顺序评估：

1. 显式传入的版本字段
2. 显式传入的 `supersedes_document_id`
3. 从文件名或标题推断出的版本号或时间标签
4. 来源路径相同或标题相似
5. 来源更新时间

自动应用会被有意限制在低风险场景：

- 显式指定了 `supersedes_document_id`
- 高置信连续版本关系，且不存在人工版本元数据冲突

其余情况只会把建议写入 `stats_json.version_assist`，供人工确认。

## 典型客户端流程

1. 用户发起问题。
2. 接口要么直接回答，要么返回 `status=interrupted`。
3. 前端渲染补问卡片，展示标签、元数据与自由补充输入框。
4. 用户选择版本或截图区域后，前端调用恢复接口继续运行。
5. 最终答案展示回答依据与引用跳转信息。
