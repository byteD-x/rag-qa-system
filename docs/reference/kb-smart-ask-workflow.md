# KB Smart Ask Workflow

本文说明文档详情页到聊天页的结构化提问链路，覆盖当前版本问答、版本比较问答和截图区域问答三个场景。

## 目标

- 减少用户手工补 prompt 的成本
- 让版本、截图、区域等上下文以结构化方式进入聊天链路
- 避免聊天页误复用旧会话导致上下文错位

## 入口

页面：`/workspace/kb/documents/:id`

新增的“智能提问”面板支持三类动作：

- 按当前版本提问
- 比较当前与所选版本
- 聚焦当前截图区域

同时提供一个保底输入框和若干问题模板，允许用户继续补充自己的问题。

## 路由预设

文档页跳转到 `/workspace/chat` 时，会写入一组 KB 专用预设参数：

- `preset=kb`
- `baseId`
- `documentId`
- `compareDocumentId?`
- `question`
- `focusHint`

其中 `focusHint` 为 JSON 字符串，描述本次问答的结构化焦点。

## focusHint 结构

### 当前版本

```json
{
  "kind": "single_version",
  "document_ids": ["doc-current"],
  "primary_document_id": "doc-current",
  "version_label": "v3",
  "version_family_key": "expense-policy",
  "display_text": "Expense Policy"
}
```

### 版本比较

```json
{
  "kind": "compare_versions",
  "document_ids": ["doc-current", "doc-history"],
  "primary_document_id": "doc-current",
  "compare_document_ids": ["doc-current", "doc-history"],
  "version_labels": ["v3", "v2"],
  "version_family_key": "expense-policy",
  "display_text": "v3 vs v2"
}
```

### 截图区域

```json
{
  "kind": "visual_region",
  "document_ids": ["doc-current"],
  "primary_document_id": "doc-current",
  "asset_id": "asset-1",
  "region_id": "region-1",
  "region_label": "红框配置",
  "page_number": 3,
  "version_label": "v3",
  "display_text": "v3 / 第 3 页 / 红框配置"
}
```

## 聊天页行为

聊天页检测到 KB 预设后，会执行以下行为：

- 新建草稿会话
- 应用对应知识库和文档范围
- 将 `focusHint` 保存到聊天 store
- 将默认问题回填到输入框
- 不自动切回旧会话

这样可以保证从文档页进入聊天时，用户看到的是和当前文档焦点一致的新上下文，而不是历史对话残留状态。

## 验证重点

- 路由预设能正确序列化和反序列化 `focusHint`
- 相同文档 ID 不会在作用域内重复
- 文档页三类入口都能跳转到聊天页
- 聊天页会保留 `focusHint` 并随提问请求发送 `focus_hint`

## 新增联合场景

文档页现在支持把“版本比较”和“截图焦点”合并到同一条提问链路里。

当用户已经：

- 选中了一个对比版本
- 选中了当前文档中的截图或截图区域

再触发“比较当前与所选版本”时，前端会把以下信息一起写入 `focusHint`：

- `kind = compare_versions`
- `document_ids`
- `compare_document_ids`
- `version_labels`
- `asset_id`
- `region_id`
- `region_label`
- `page_number`

这样后端既能保留版本比较语义，也能在检索排序时优先关注当前截图焦点，更接近“比较两个版本在这块截图标注中的变化”这一企业问答场景。

## 文档版本摘要视图

文档版本检查面板现在提供三种查看方式：

- `快速摘要`：优先展示前几个章节的浓缩摘要，适合快速理解当前版本重点。
- `版本内容`：展示完整章节正文，适合逐段核对。
- `与当前版本差异`：展示变更切片统计和 diff 文本，适合做版本比对。

这让用户可以在“先看摘要”与“直接看全文”之间自行切换，不需要先进入聊天才能获得版本概览。

## 跨版本截图区域差异高亮

当满足以下前提时，文档页会直接生成“跨版本截图区域差异高亮”面板：

- 已选中一个对照版本
- 已聚焦当前版本中的截图或截图区域

系统会按以下顺序自动寻找历史版本中的对应截图区域：

1. 同页码 + 同区域标签
2. 同页码 + 相似布局提示或 bbox
3. 只匹配到同页截图时，回退为同页截图区域对比

在匹配成功后，前端会：

- 裁剪当前版本和历史版本的对应截图区域
- 生成像素级差异热区图
- 在当前版本、历史版本和热区图上同步用橙框标出主要变化区域

如果历史版本没有找到足够接近的截图区域，页面会明确提示未找到对应截图，而不是伪造对比结果。
