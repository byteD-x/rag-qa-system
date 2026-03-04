# 前端联调清单（RAG-P 后端）

> 更新时间：2026-03-04
> 后端基础地址：`http://localhost:8080/v1`

## 1. 启动与健康检查
1. 执行一键启动：
   - `powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1`
2. 健康检查：
   - `GET http://localhost:8080/healthz`
   - `GET http://localhost:8000/healthz`
3. 预期：两个接口均返回 `status=ok`。

## 2. 鉴权联调
1. 登录：`POST /auth/login`
2. 请求体示例：
```json
{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```
3. 预期：返回 `access_token`；后续接口带 `Authorization: Bearer <token>`。

## 3. 资料库（Corpus）联调
1. 创建资料库（admin）：`POST /corpora`
2. 获取资料库列表：`GET /corpora`
3. 预期：提问前用户必须显式选择资料范围（单库或多库）。

## 4. 上传入库联调（两段式）
1. 申请上传地址：`POST /documents/upload-url`
2. 用返回的 `upload_url` 执行 `PUT` 上传文件（浏览器直传）
3. 完成入库：`POST /documents/upload`（携带 `storage_key`）
4. 轮询任务：`GET /ingest-jobs/{job_id}` 直到 `done|failed`

### 4.1 上传限制
- 文件类型：`txt/pdf/docx`
- 文件大小：`<=500MB`

## 5. 会话与问答联调
1. 创建会话：`POST /chat/sessions`
2. 发送提问：`POST /chat/sessions/{id}/messages`
3. `scope` 必填，示例：
```json
{
  "question": "主角第一次出场在哪里？",
  "scope": {
    "mode": "single",
    "corpus_ids": ["<corpus_uuid>"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

## 6. 响应渲染规范（前端）
1. 以 `answer_sentences[]` 作为主答案渲染。
2. `evidence_type=source`：必须展示/可点击 `citation_ids`。
3. `evidence_type=common_knowledge`：显示“非资料证据”标签。
4. 引用详情来自 `citations[]`：`file_name/page_or_loc/snippet/chunk_id`。

## 7. 错误码处理
- `400`：scope 非法、资料不存在、文档未 ready、参数错误
- `401`：登录失效或 token 无效
- `403`：权限不足（如 member 创建 corpus）
- `404`：资源不存在（会话/任务等）
- `503`：入队失败（可提示重试）

## 8. 最小验收场景
1. 单资料问答：返回 `source` 句，且有引用。
2. 多资料问答：支持 `mode=multi` 并返回引用。
3. 空资料提问：返回 400（无 ready 文档）。
4. 开启常识补充：`allow_common_knowledge=true` 时可出现“非资料证据”句。
5. 上传链路：`queued -> running -> done` 状态流转完整。

## 9. 联调建议
1. 前端请求/响应类型建议强类型化（TypeScript Interface）。
2. 引用弹窗建议按“句子 -> citation_id -> citation详情”映射。
3. 聊天消息建议保留 `scope` 快照，便于复现回答来源。

## 10. 知识库文档在线操作（新增）
1. 文档详情：`GET /documents/{document_id}`，用于详情抽屉/弹窗展示元信息。
2. 在线查看：`GET /documents/{document_id}/preview`
   - `txt`：返回 `preview_mode=text` 与文本内容；
   - `pdf/docx`：返回 `preview_mode=url` 与时效预览链接。
3. 在线修改（仅 `txt`）：`PUT /documents/{document_id}/content`
   - 请求体：`{"content":"..."}`；
   - 保存成功后返回 `job_id`，前端可提示“已入队重建索引”并刷新列表状态。
