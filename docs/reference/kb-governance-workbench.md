# KB Governance Workbench

企业治理工作台通过 `GET /api/v1/kb/analytics/governance` 返回知识库治理队列，供前端 `/workspace/kb/governance` 页面直接消费。

## Query

- `view`: `personal | admin`
- `limit`: 每个队列返回的样本数，默认 `8`

## Response summary

`summary` 当前包含：

- `pending_review`
- `approved_ready`
- `rejected_documents`
- `expired_documents`
- `visual_attention`
- `visual_low_confidence`
- `missing_version_family`
- `version_conflicts`

`queues` 当前包含：

- `pending_review`
- `approved_ready`
- `rejected_documents`
- `expired_documents`
- `visual_attention`
- `visual_low_confidence`
- `missing_version_family`
- `version_conflicts`

## Queue semantics

- `pending_review`: `review_status=review_pending` 的文档，或尚未提交审核的 `draft` 版本。
- `approved_ready`: `review_status=approved`，但还没有正式发布或切到当前版本的文档。
- `rejected_documents`: `review_status=rejected` 的文档。
- `expired_documents`: `effective_to < now()` 的已过期文档。
- `visual_attention`: 文档存在截图或视觉资产，但 `enhancement_status` 尚未进入 `visual_ready / summary_vectors_ready / chunk_vectors_ready`。
- `visual_low_confidence`: 文档已经完成视觉入库，但存在 `confidence < 0.8` 的截图区域，需要人工复核。
- `missing_version_family`: 已填写 `version_label / version_number / supersedes_document_id`，但缺少 `version_family_key`。
- `version_conflicts`: 同一 `version_family_key` 下存在多个 `is_current_version = true`。

## Document item fields

治理文档项除原有版本、审核、负责人字段外，还会补充：

- `visual_asset_count`
- `low_confidence_region_count`
- `low_confidence_asset_id`
- `low_confidence_region_id`
- `low_confidence_region_label`
- `low_confidence_region_confidence`
- `low_confidence_region_bbox`
- `reason`

其中 `low_confidence_region_count` 表示当前文档中低于治理阈值的截图区域数量；其余 `low_confidence_*` 字段用于把治理项直接深链到文档页里的具体截图区域。

## Controlled rebuild

治理页已接入单文档受控 rebuild 动作。页面只允许在已选择 1 个文档时预览或执行 rebuild；预览会按当前 payload 生成签名并调用固定 `POST /api/knowledge_base/rebuild`，只有 `lastDryRunSignature` 与当前 payload signature 一致时才允许执行正式 rebuild。

正式 rebuild 成功后，页面只展示摘要字段，例如 `doc_id`、`version`、`chunk_count`、`indexed_chunks`、`deleted_previous`。该入口不新增文件上传、目录扫描、任意路径读取或手工输入 `source_path` 能力，也不会把治理页扩展为通用文件重建工具。

## Batch dry-run preview

`POST /api/knowledge_base/batch-dry-run` 提供多文档分块预览摘要。请求体只接收 `documents` 数组，每个元素使用内联 `content`，可选 `doc_id` / `document_id` 与 `file_name`；服务端最多接收 20 篇、合计 300000 字符。响应只返回文档数、总字符数、section/chunk 计数、字符范围和脱敏后的叶子文件名，不返回原文、chunk text、embedding 或完整路径。

该入口只用于预览分块规模和治理操作前的安全检查，不读取 `source_file` / `source_path`，不扫描目录，不上传文件，不写入数据库或向量库，也不触发批量 rebuild。

## Batch ingest API

`POST /api/knowledge_base/batch-ingest` 提供受控的 Web API 批量写入口。请求体只接收 `documents` 数组，每个元素必须提供 `base_id` 与内联 `content`，可选 `doc_id` / `document_id`、`file_name` 与 `category`；服务端会按顺序创建文档、写入 section/chunk，并触发现有向量索引。

该入口不同于 batch dry-run：它会写入数据库和向量库，但仍不读取 `source_file` / `source_path`，不扫描目录，不上传文件，不批量 rebuild/delete，也不接入桌面设置页。响应只返回聚合计数、服务端生成的文档 ID 和脱敏文件名，不返回正文、chunk text、embedding 或完整路径。

## Notes

- 治理接口要求 `kb.manage` 权限。
- 工作台内联修正依赖 `kb.write` 权限。
- `summary` 是全量计数，`queues.*` 只返回受 `limit` 控制的样本。
- 低置信截图区域当前仍以“文档级治理项”暴露，方便企业运营同学直接处理，不强制进入独立 bbox 审核流。
- 治理页支持按文档懒加载完整的低置信 `visual_region` 列表，仍然复用现有视觉资产与 region 查询接口，不新增独立的区域批量接口。
