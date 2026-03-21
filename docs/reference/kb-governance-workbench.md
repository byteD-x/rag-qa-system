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

## Notes

- 治理接口要求 `kb.manage` 权限。
- 工作台内联修正依赖 `kb.write` 权限。
- `summary` 是全量计数，`queues.*` 只返回受 `limit` 控制的样本。
- 低置信截图区域当前仍以“文档级治理项”暴露，方便企业运营同学直接处理，不强制进入独立 bbox 审核流。
- 治理页支持按文档懒加载完整的低置信 `visual_region` 列表，仍然复用现有视觉资产与 region 查询接口，不新增独立的区域批量接口。
