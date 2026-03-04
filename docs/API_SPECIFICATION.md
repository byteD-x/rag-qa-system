# RAG-QA System API 规范

> **版本**: 2.1.0  
> **最后更新**: 2026-03-04  
> **Base URL**: `http://localhost:8080/v1`

---

## 📋 目录

1. [概述](#概述)
2. [认证机制](#认证机制)
3. [错误处理](#错误处理)
4. [API 端点](#api-端点)
5. [数据模型](#数据模型)
6. [使用示例](#使用示例)

---

## 概述

### 服务架构

```
┌─────────────────┐
│   Frontend      │
│   (Vue 3 + TS)  │
└────────┬────────┘
         │ HTTP/JSON
         ▼
┌─────────────────────────┐
│   go-api (Port 8080)    │  ←─── 本 API 文档描述的服务
│   - REST Gateway        │
│   - JWT Auth            │
│   - Business Logic      │
└─┬───────────────────────┘
  │
  ├──────────────┬──────────────┬─────────────┐
  ▼              ▼              ▼             ▼
┌────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐
│Postgres│  │  Redis   │  │  MinIO  │  │  Qdrant  │
│  :5432 │  │  :6379   │  │ :19000  │  │  :6333   │
└────────┘  └────┬─────┘  └─────────┘  └──────────┘
                 │
                 ▼
          ┌──────────────┐
          │py-rag-service│
          │   (Port 8000)│
          └──────────────┘
```

### 基础信息

- **协议**: HTTP/1.1
- **数据格式**: JSON (`application/json`)
- **字符编码**: UTF-8
- **认证方式**: Bearer Token (JWT)
- **版本前缀**: `/v1`

### 健康检查

```http
GET /healthz
```

**响应示例**:
```json
{
  "status": "ok",
  "service": "go-api",
  "time": "2026-03-04T10:30:00Z"
}
```

---

## 认证机制

### 认证流程

1. 调用 `/auth/login` 获取访问令牌
2. 在所有受保护请求的 `Authorization` header 中携带令牌
3. 令牌过期后重新登录

### 请求头格式

```http
Authorization: Bearer <access_token>
```

### Token 信息

- **类型**: 随机生成的 64 字符十六进制字符串
- **有效期**: 默认 120 分钟 (可通过 `AUTH_TOKEN_TTL_MINUTES` 配置)
- **存储**: 服务端内存存储 (Redis)
- **角色**: `admin` 或 `member`

### 角色权限

| 端点 | admin | member |
|------|-------|--------|
| POST /corpora | ✅ | ❌ |
| DELETE /corpora/{id} | ✅ | ❌ |
| POST /corpora/batch-delete | ✅ | ❌ |
| GET /corpora | ✅ | ✅ |
| GET /corpora/{id}/documents | ✅ | ✅ |
| POST /documents/upload-url | ✅ | ✅ |
| POST /documents/upload | ✅ | ✅ |
| POST /chat/sessions/* | ✅ | ✅ |

---

## 错误处理

### 错误响应格式

```json
{
  "error": "错误消息"
}
```

### HTTP 状态码

| 状态码 | 含义 | 常见场景 |
|--------|------|----------|
| 200 OK | 请求成功 | GET/PUT 成功 |
| 201 Created | 资源创建成功 | POST 创建资源 |
| 202 Accepted | 请求已接受处理 | 异步任务提交 |
| 204 No Content | 删除成功 | DELETE 成功 |
| 400 Bad Request | 请求参数错误 | 验证失败 |
| 401 Unauthorized | 未认证 | 缺少/无效 Token |
| 403 Forbidden | 权限不足 | 角色权限不足 |
| 404 Not Found | 资源不存在 | ID 错误 |
| 409 Conflict | 资源冲突 | 任务进行中 |
| 413 Payload Too Large | 文件过大 | 超过限制 |
| 429 Too Many Requests | 请求过多 | 限流 |
| 500 Internal Server Error | 服务器错误 | 内部异常 |

### 常见错误码

```json
// 认证错误
{ "error": "missing authorization header" }
{ "error": "invalid authorization format" }
{ "error": "invalid or expired token" }

// 权限错误
{ "error": "only admin can create corpus" }
{ "error": "only admin can delete corpus" }

// 验证错误
{ "error": "email and password are required" }
{ "error": "name is required" }
{ "error": "name too long, max 128" }
{ "error": "scope.mode=single requires exactly one corpus_id" }
{ "error": "corpus_ids contains duplicate value" }

// 资源错误
{ "error": "corpus not found" }
{ "error": "document not found" }
{ "error": "job not found" }

// 系统错误
{ "error": "create corpus failed" }
{ "error": "purge vector resources failed" }
{ "error": "enqueue ingest job failed" }
```

---

## API 端点

### 认证接口

#### POST /auth/login

用户登录获取访问令牌。

**请求**:
```http
POST /v1/auth/login
Content-Type: application/json

{
  "email": "admin@local",
  "password": "ChangeMe123!"
}
```

**响应 (200 OK)**:
```json
{
  "access_token": "a1b2c3d4e5f6...",
  "user": {
    "user_id": "11111111-1111-1111-1111-111111111111",
    "email": "admin@local",
    "role": "admin"
  },
  "token_type": "Bearer",
  "expires_in": 7200
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| access_token | string | 访问令牌 |
| user.user_id | string | 用户 UUID |
| user.email | string | 邮箱地址 |
| user.role | string | 角色 (`admin`/`member`) |
| token_type | string | 令牌类型 |
| expires_in | number | 过期时间 (秒) |

**错误响应**:
- `400 Bad Request`: `email and password are required`
- `401 Unauthorized`: `invalid email or password`

---

### 知识库接口

#### POST /corpora

创建新的知识库 (需要 admin 权限)。

**请求**:
```http
POST /v1/corpora
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "产品文档库",
  "description": "存储产品相关文档"
}
```

**响应 (201 Created)**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "产品文档库",
  "description": "存储产品相关文档",
  "owner_user_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2026-03-04T10:30:00Z"
}
```

**验证规则**:
- `name`: 必填，1-128 字符
- `description`: 可选
- 仅 admin 角色可创建

**错误响应**:
- `400 Bad Request`: `name is required` / `name too long, max 128`
- `403 Forbidden`: `only admin can create corpus`
- `500 Internal Server Error`: `create corpus failed`

---

#### GET /corpora

查询知识库列表。

**请求**:
```http
GET /v1/corpora
Authorization: Bearer <token>
```

**响应 (200 OK)**:
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "产品文档库",
      "description": "存储产品相关文档",
      "owner_user_id": "11111111-1111-1111-1111-111111111111",
      "created_at": "2026-03-04T10:30:00Z"
    }
  ],
  "count": 1
}
```

---

#### DELETE /corpora/{corpus_id}

删除指定知识库及其所有关联资源 (需要 admin 权限)。

**请求**:
```http
DELETE /v1/corpora/{corpus_id}
Authorization: Bearer <token>
```

**响应**:
- `204 No Content`: 删除成功
- `400 Bad Request`: `invalid corpusID`
- `403 Forbidden`: `only admin can delete corpus`
- `404 Not Found`: `corpus not found`
- `500 Internal Server Error`: 删除失败

**删除流程**:
1. 验证 corpusID 格式 (UUID)
2. 验证知识库存在
3. 验证用户权限 (admin)
4. 删除 Qdrant 向量数据
5. 删除 MinIO 对象存储
6. 删除数据库记录

---

#### POST /corpora/batch-delete

批量删除知识库 (需要 admin 权限，最大 100 个/次)。

**请求**:
```http
POST /v1/corpora/batch-delete
Authorization: Bearer <token>
Content-Type: application/json

{
  "corpus_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440001"
  ]
}
```

**响应 (200 OK)**:
```json
{
  "deleted_count": 2
}
```

**验证规则**:
- `corpus_ids`: 必填，1-100 个 UUID
- 不允许重复 ID
- 所有 ID 必须存在

**错误响应**:
- `400 Bad Request`: `corpus_ids too many, max 100` / `corpus_ids contains duplicate value`
- `403 Forbidden`: `only admin can delete corpus`

---

### 文档接口

#### GET /corpora/{corpus_id}/documents

查询知识库中的文档列表。

**请求**:
```http
GET /v1/corpora/{corpus_id}/documents
Authorization: Bearer <token>
```

**响应 (200 OK)**:
```json
{
  "items": [
    {
      "id": "doc_uuid",
      "corpus_id": "corpus_uuid",
      "file_name": "product_manual.pdf",
      "file_type": "pdf",
      "size_bytes": 1048576,
      "status": "ready",
      "created_at": "2026-03-04T10:30:00Z",
      "created_by": "user_uuid"
    }
  ],
  "count": 1
}
```

**文档状态**:
- `uploaded`: 已上传，等待处理
- `indexing`: 处理中
- `ready`: 已完成，可检索
- `failed`: 处理失败

---

#### GET /documents/{document_id}

获取文档详情。

**请求**:
```http
GET /v1/documents/{document_id}
Authorization: Bearer <token>
```

**响应 (200 OK)**:
```json
{
  "id": "doc_uuid",
  "corpus_id": "corpus_uuid",
  "file_name": "product_manual.pdf",
  "file_type": "pdf",
  "size_bytes": 1048576,
  "status": "ready",
  "storage_key": "path/to/file.pdf",
  "created_at": "2026-03-04T10:30:00Z",
  "created_by": "user_uuid"
}
```

---

#### GET /documents/{document_id}/preview

获取文档预览内容。

**请求**:
```http
GET /v1/documents/{document_id}/preview
Authorization: Bearer <token>
```

**响应 (TXT 文档)**:
```json
{
  "document": { /* 文档详情 */ },
  "preview_mode": "text",
  "editable": true,
  "text": "文档文本内容...",
  "content_type": "text/plain; charset=utf-8",
  "max_inline_bytes": 1048576,
  "expires_in_seconds": 0
}
```

**响应 (PDF/DOCX 文档)**:
```json
{
  "document": { /* 文档详情 */ },
  "preview_mode": "url",
  "editable": false,
  "view_url": "http://localhost:19000/rag-raw/path/to/file.pdf?X-Amz-...",
  "content_type": "application/pdf",
  "expires_in_seconds": 1800
}
```

**说明**:
- TXT 文档：直接返回文本内容，支持在线编辑
- PDF/DOCX 文档：返回预签名 URL，30 分钟有效期
- 最大内联文本：1MB

---

#### PUT /documents/{document_id}/content

在线修改文档内容 (仅支持 TXT 格式)。

**请求**:
```http
PUT /v1/documents/{document_id}/content
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "新的文档内容..."
}
```

**响应 (202 Accepted)**:
```json
{
  "document_id": "doc_uuid",
  "job_id": "job_uuid",
  "status": "queued",
  "message": "document content updated and queued for re-indexing"
}
```

**验证规则**:
- 仅支持 TXT 格式文档
- 内容不能为空
- 最大 1MB
- 不能有进行中的入库任务

**错误响应**:
- `400 Bad Request`: `only txt document supports online edit` / `content is required`
- `409 Conflict`: `document ingest is in progress, try later`
- `413 Payload Too Large`: `content too large for online edit, max 1048576 bytes`

---

#### POST /documents/upload-url

申请文件上传 URL (双阶段上传第一步)。

**请求**:
```http
POST /v1/documents/upload-url
Authorization: Bearer <token>
Content-Type: application/json

{
  "corpus_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "product_manual.pdf",
  "file_type": "pdf",
  "size_bytes": 1048576
}
```

**响应 (200 OK)**:
```json
{
  "upload_url": "http://localhost:19000/rag-raw/path/to/file.pdf?X-Amz-...",
  "storage_key": "path/to/file.pdf"
}
```

**验证规则**:
- `corpus_id`: 必填，有效的 UUID
- `file_name`: 必填
- `file_type`: 必填，仅支持 `txt`/`pdf`/`docx`
- `size_bytes`: 必填，范围 (0, 524288000] (500MB)

**错误响应**:
- `400 Bad Request`: 参数验证失败
- `404 Not Found`: `corpus not found`

---

#### POST /documents/upload

确认文件上传完成并创建入库任务 (双阶段上传第二步)。

**请求**:
```http
POST /v1/documents/upload
Authorization: Bearer <token>
Content-Type: application/json

{
  "corpus_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "product_manual.pdf",
  "file_type": "pdf",
  "size_bytes": 1048576,
  "storage_key": "path/to/file.pdf"
}
```

**响应 (202 Accepted)**:
```json
{
  "document_id": "doc_uuid",
  "job_id": "job_uuid",
  "status": "queued",
  "message": "document metadata accepted and queued for indexing"
}
```

**说明**:
- 验证文件已上传到对象存储
- 创建文档元数据记录
- 创建异步入库任务
- 任务状态可通过 `/ingest-jobs/{job_id}` 查询

---

#### GET /ingest-jobs/{job_id}

查询入库任务状态。

**请求**:
```http
GET /v1/ingest-jobs/{job_id}
Authorization: Bearer <token>
```

**响应 (200 OK)**:
```json
{
  "id": "job_uuid",
  "status": "running",
  "progress": 45
}
```

**任务状态**:
- `queued`: 等待处理
- `running`: 处理中
- `done`: 处理完成
- `failed`: 处理失败

---

### 问答接口

#### POST /chat/sessions

创建新的会话。

**请求**:
```http
POST /v1/chat/sessions
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "产品咨询会话"
}
```

**响应 (201 Created)**:
```json
{
  "id": "session_uuid",
  "user_id": "user_uuid",
  "title": "产品咨询会话",
  "created_at": "2026-03-04T11:00:00Z"
}
```

**验证规则**:
- `title`: 可选，默认 "Untitled Session"，最大 200 字符

---

#### GET /chat/sessions

查询当前用户的会话列表。

**请求**:
```http
GET /v1/chat/sessions
Authorization: Bearer <token>
```

**响应 (200 OK)**:
```json
{
  "items": [
    {
      "id": "session_uuid",
      "user_id": "user_uuid",
      "title": "产品咨询会话",
      "created_at": "2026-03-04T11:00:00Z"
    }
  ],
  "count": 1
}
```

---

#### POST /chat/sessions/{session_id}/messages

发送问题并获取回答。

**请求**:
```http
POST /v1/chat/sessions/{session_id}/messages
Authorization: Bearer <token>
Content-Type: application/json

{
  "question": "产品的保修政策是什么？",
  "scope": {
    "mode": "single",
    "corpus_ids": ["550e8400-e29b-41d4-a716-446655440000"],
    "document_ids": [],
    "allow_common_knowledge": false
  }
}
```

**响应 (200 OK)**:
```json
{
  "session_id": "session_uuid",
  "answer_sentences": [
    {
      "text": "产品提供一年有限保修服务，自购买之日起生效。",
      "evidence_type": "source",
      "citation_ids": ["c1", "c2"],
      "confidence": 0.95
    },
    {
      "text": "【常识补充】以下内容为模型补充推断，请结合原文证据核验。",
      "evidence_type": "common_knowledge",
      "citation_ids": [],
      "confidence": 0.3
    }
  ],
  "citations": [
    {
      "citation_id": "c1",
      "file_name": "product_manual.pdf",
      "page_or_loc": "Page 5",
      "chunk_id": "chunk_uuid_1",
      "snippet": "一年有限保修服务，自购买之日起生效。保修范围涵盖..."
    },
    {
      "citation_id": "c2",
      "file_name": "product_manual.pdf",
      "page_or_loc": "Page 6",
      "chunk_id": "chunk_uuid_2",
      "snippet": "保修范围涵盖制造缺陷和材料问题，但不包括..."
    }
  ],
  "allow_common_knowledge": false
}
```

**Scope 参数说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mode | string | 是 | `single` 或 `multi` |
| corpus_ids | string[] | 是 | 知识库 ID 列表 |
| document_ids | string[] | 否 | 文档 ID 列表 (优先级更高) |
| allow_common_knowledge | boolean | 否 | 是否允许常识补充，默认 false |

**Scope 验证规则**:
- `mode=single`: 必须有且仅有 1 个 `corpus_id`
- `mode=multi`: 必须有至少 2 个 `corpus_ids`
- `corpus_ids`: 不能为空，不能重复，必须是有效 UUID
- `document_ids`: 如果提供，必须存在于对应的知识库中

**AnswerSentence 字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| text | string | 句子文本 |
| evidence_type | string | `source` (基于证据) 或 `common_knowledge` (常识补充) |
| citation_ids | string[] | 引用的 citation_id 列表 |
| confidence | float | 置信度分数 (0-1) |

**证据类型约束**:
- `source`: 必须包含至少一个有效的 `citation_ids`
- `common_knowledge`: 
  - 不能包含 `citation_ids`
  - `text` 必须以 `【常识补充】` 开头
  - 最多占回答句子的 15%
  - 仅在 `allow_common_knowledge=true` 时允许

**Citation 字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| citation_id | string | 引用 ID (格式：`c1`, `c2`, ...) |
| file_name | string | 来源文件名 |
| page_or_loc | string | 页码或位置 |
| chunk_id | string | 文本块 UUID |
| snippet | string | 引用片段 (最大 220 字符) |

**错误响应**:
- `400 Bad Request`: 参数验证失败
- `404 Not Found`: `chat session not found`
- `500 Internal Server Error`: RAG 服务异常 (会返回降级响应)

**降级响应** (RAG 服务异常时):
```json
{
  "answer_sentences": [
    {
      "text": "【常识补充】当前问答服务暂不可用，请稍后重试。",
      "evidence_type": "common_knowledge",
      "citation_ids": [],
      "confidence": 0.15
    }
  ],
  "citations": []
}
```

---

## 数据模型

### Corpus (知识库)

```typescript
interface Corpus {
  id: string;              // UUID
  name: string;            // 1-128 字符
  description: string;     // 可选
  owner_user_id: string;   // 创建者 UUID
  created_at: string;      // ISO 8601 时间戳
}
```

### Document (文档)

```typescript
interface Document {
  id: string;              // UUID
  corpus_id: string;       // 所属知识库 UUID
  file_name: string;       // 文件名
  file_type: 'txt' | 'pdf' | 'docx';
  size_bytes: number;      // 文件大小 (字节)
  status: 'uploaded' | 'indexing' | 'ready' | 'failed';
  storage_key: string;     // S3 存储路径
  created_at: string;      // ISO 8601 时间戳
  created_by?: string;     // 上传用户 UUID
}
```

### ChatSession (会话)

```typescript
interface ChatSession {
  id: string;              // UUID
  user_id: string;         // 用户 UUID
  title: string;           // 会话标题
  created_at: string;      // ISO 8601 时间戳
}
```

### Scope (检索作用域)

```typescript
interface Scope {
  mode: 'single' | 'multi';
  corpus_ids: string[];    // UUID 列表
  document_ids?: string[]; // UUID 列表 (可选)
  allow_common_knowledge?: boolean; // 默认 false
}
```

### AnswerSentence (回答句子)

```typescript
interface AnswerSentence {
  text: string;
  evidence_type: 'source' | 'common_knowledge';
  citation_ids: string[];
  confidence: number;      // 0-1
}
```

### Citation (引用)

```typescript
interface Citation {
  citation_id: string;     // 格式：c1, c2, ...
  file_name: string;
  page_or_loc: string;     // 页码或位置
  chunk_id: string;        // UUID
  snippet: string;         // 最大 220 字符
}
```

### IngestJob (入库任务)

```typescript
interface IngestJob {
  id: string;              // UUID
  status: 'queued' | 'running' | 'done' | 'failed';
  progress: number;        // 0-100
}
```

### User (用户)

```typescript
interface User {
  user_id: string;         // UUID
  email: string;
  role: 'admin' | 'member';
}
```

---

## 使用示例

### 完整工作流 (TypeScript)

```typescript
import axios from 'axios';

const BASE_URL = 'http://localhost:8080/v1';

// 1. 登录
async function login(email: string, password: string): Promise<string> {
  const response = await axios.post(`${BASE_URL}/auth/login`, {
    email,
    password
  });
  return response.data.access_token;
}

// 2. 创建知识库
async function createCorpus(token: string, name: string, description: string): Promise<string> {
  const response = await axios.post(`${BASE_URL}/corpora`, {
    name,
    description
  }, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return response.data.id;
}

// 3. 上传文档
async function uploadDocument(
  token: string,
  corpusId: string,
  file: File
): Promise<{ documentId: string; jobId: string }> {
  // 3.1 申请上传 URL
  const { data: uploadUrlData } = await axios.post(
    `${BASE_URL}/documents/upload-url`,
    {
      corpus_id: corpusId,
      file_name: file.name,
      file_type: file.name.split('.').pop()?.toLowerCase() || 'txt',
      size_bytes: file.size
    },
    {
      headers: { Authorization: `Bearer ${token}` }
    }
  );

  // 3.2 上传到对象存储
  await axios.put(uploadUrlData.upload_url, file, {
    headers: { 'Content-Type': file.type || 'application/octet-stream' }
  });

  // 3.3 确认入库
  const { data: confirmData } = await axios.post(
    `${BASE_URL}/documents/upload`,
    {
      corpus_id: corpusId,
      storage_key: uploadUrlData.storage_key,
      file_name: file.name,
      file_type: file.name.split('.').pop()?.toLowerCase() || 'txt',
      size_bytes: file.size
    },
    {
      headers: { Authorization: `Bearer ${token}` }
    }
  );

  return {
    documentId: confirmData.document_id,
    jobId: confirmData.job_id
  };
}

// 4. 查询任务状态
async function getJobStatus(token: string, jobId: string): Promise<string> {
  const { data } = await axios.get(`${BASE_URL}/ingest-jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return data.status;
}

// 5. 创建会话并提问
async function askQuestion(
  token: string,
  sessionId: string,
  question: string,
  corpusIds: string[]
) {
  const mode = corpusIds.length === 1 ? 'single' : 'multi';
  
  const { data } = await axios.post(
    `${BASE_URL}/chat/sessions/${sessionId}/messages`,
    {
      question,
      scope: {
        mode,
        corpus_ids: corpusIds,
        allow_common_knowledge: false
      }
    },
    {
      headers: { Authorization: `Bearer ${token}` }
    }
  );

  return {
    answerSentences: data.answer_sentences,
    citations: data.citations
  };
}

// 使用示例
async function main() {
  // 登录
  const token = await login('admin@local', 'ChangeMe123!');
  console.log('✓ 登录成功');

  // 创建知识库
  const corpusId = await createCorpus(token, '产品文档库', '产品相关文档');
  console.log(`✓ 创建知识库：${corpusId}`);

  // 上传文档
  const file = new File(['test content'], 'manual.pdf', { type: 'application/pdf' });
  const { documentId, jobId } = await uploadDocument(token, corpusId, file);
  console.log(`✓ 文档上传中，任务 ID: ${jobId}`);

  // 等待处理完成
  console.log('⏳ 等待文档处理完成...');
  let status = await getJobStatus(token, jobId);
  while (status === 'queued' || status === 'running') {
    await new Promise(resolve => setTimeout(resolve, 2000));
    status = await getJobStatus(token, jobId);
  }
  console.log(`✓ 文档处理完成，状态：${status}`);

  // 创建会话
  const { data: sessionData } = await axios.post(
    `${BASE_URL}/chat/sessions`,
    { title: '产品咨询' },
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const sessionId = sessionData.id;

  // 提问
  const result = await askQuestion(token, sessionId, '产品的保修政策是什么？', [corpusId]);
  
  console.log('\n=== 回答 ===');
  result.answerSentences.forEach((sentence: any) => {
    console.log(`- ${sentence.text}`);
    if (sentence.citation_ids.length > 0) {
      console.log(`  引用：${sentence.citation_ids.join(', ')}`);
    }
  });

  console.log('\n=== 引用 ===');
  result.citations.forEach((citation: any) => {
    console.log(`[${citation.citation_id}] ${citation.file_name} - ${citation.page_or_loc}`);
    console.log(`  ${citation.snippet}`);
  });
}
```

### cURL 测试脚本

```bash
#!/bin/bash

set -e

BASE_URL="http://localhost:8080/v1"
EMAIL="admin@local"
PASSWORD="ChangeMe123!"

echo "=== 1. 登录 ==="
TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r '.access_token')

echo "✓ Token: ${TOKEN:0:20}..."

echo -e "\n=== 2. 创建知识库 ==="
CORPUS_ID=$(curl -s -X POST "$BASE_URL/corpora" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试库","description":"测试用"}' | jq -r '.id')

echo "✓ 知识库 ID: $CORPUS_ID"

echo -e "\n=== 3. 创建会话 ==="
SESSION_ID=$(curl -s -X POST "$BASE_URL/chat/sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"测试会话\"}" | jq -r '.id')

echo "✓ 会话 ID: $SESSION_ID"

echo -e "\n=== 4. 提问 ==="
curl -s -X POST "$BASE_URL/chat/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "如何重置密码？",
    "scope": {
      "mode": "single",
      "corpus_ids": ["'"$CORPUS_ID"'"],
      "allow_common_knowledge": false
    }
  }' | jq .

echo -e "\n✓ 完成!"
```

---

## 附录

### 配置项参考

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HTTP_ADDR` | `:8080` | API 监听地址 |
| `MAX_UPLOAD_BYTES` | `524288000` | 最大上传文件大小 (500MB) |
| `AUTH_TOKEN_TTL_MINUTES` | `120` | Token 有效期 (分钟) |
| `ADMIN_EMAIL` | `admin@local` | 管理员账号 |
| `ADMIN_PASSWORD` | `ChangeMe123!` | 管理员密码 |
| `MEMBER_EMAIL` | `member@local` | 普通用户账号 |
| `MEMBER_PASSWORD` | `ChangeMe123!` | 普通用户密码 |

### 支持的文件类型

| 类型 | MIME Type | 说明 |
|------|-----------|------|
| txt | text/plain | 支持在线编辑和预览 |
| pdf | application/pdf | 仅预览 |
| docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document | 仅预览 |

### 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 登录响应时间 | < 100ms | 本地验证 |
| 创建知识库 | < 200ms | 数据库插入 |
| 文档列表查询 | < 500ms | 取决于文档数量 |
| 问答响应时间 | < 5s | 取决于 LLM 响应 |
| 文档上传 | < 2s | 元数据创建 |
| 文档入库 | < 60s | 异步处理，取决于文件大小 |

---

**文档维护**: RAG-QA Team  
**最后更新**: 2026-03-04
