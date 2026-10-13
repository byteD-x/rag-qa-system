# 通用知识库类型接入

知识库类型采用注册表 + JSON Schema 驱动。接入新的知识库领域时，不需要新增一套 RAG：

1. 管理员调用 `POST /api/v1/kb/types` 注册 `type_key`、显示名称和 `schema`。
2. 在 Schema 的 `properties` 中声明该领域的可配置 metadata；支持 `string`、`number`、`integer`、`boolean`、`array`、`enum`、`required`、长度/数值范围等约束。
3. 创建或编辑知识库时提交 `type_keys`、`job_position_ids`（可选）和 `metadata`。后端会按已启用类型的 Schema 校验。
4. 上传文档时可填写 `content_kind`、`question_type`、`difficulty`、`tags`；这些字段会随文档进入现有切分、向量化、FTS、结构化和 Qdrant 检索结果。

示例：

```json
{
  "type_key": "product_manual",
  "display_name": "产品手册库",
  "schema": {
    "type": "object",
    "properties": {
      "product_line": {"type": "string", "minLength": 1},
      "locale": {"type": "string", "enum": ["zh-CN", "en-US"]},
      "versions": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["product_line"],
    "additionalProperties": false
  }
}
```

旧知识库自动归类为 `general`，未填写领域 metadata 的上传和问答行为保持不变。禁用类型不会影响已存在数据，但不能用于新建或更新知识库。

部署时先运行现有的 `stack-init`。迁移 `013_vector_index_payload_state.sql` 会将向量载荷状态置为 pending；`stack-init` 随后复用现有索引函数重建可查询文档，成功后标记版本完成。重建失败会使初始化失败并保留 pending，下一次部署会自动重试。可通过 `KB_AUTO_REINDEX_AFTER_MIGRATION=false` 暂停自动重建，之后使用现有 `scripts/dev/reindex-qdrant.py` 完成手动重建。
