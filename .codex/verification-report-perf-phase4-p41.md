# Phase 4 P4.1 去 minio(文件系统存储后端)— 验证记录

日期:2026-07-16
性质:这是"为去容器而新增代码"的一项(用户已知并确认全做)。新增约 260 行(storage 后端 + 路由 + 令牌)。

## 改动(分 4 次提交)
1. `storage.py` 新增 `FilesystemStorageClient`(接口与 ObjectStorageClient 对齐)+ `create_object_storage_client` 工厂 + HMAC 令牌签发/校验(复用 JWT_SECRET)。multipart 本地暂存分片+完成拼接,ETag=分片 md5;暂存目录按 storage_key 定位(库内唯一)。
2. `runtime.py`/`stack_init.py` 存储单例改用工厂(默认 s3 不变,OBJECT_STORAGE_PROVIDER=filesystem 切换)。
3. 新增 `kb_object_store_routes`:PUT `/api/v1/kb/object-store/parts`(分片接收)+ GET `/api/v1/kb/object-store/object`(对象读取),URL 内令牌鉴权,仅 filesystem 模式生效(s3 模式返 404)。main 注册。
4. `.env.example`/`.env.minimal` 增 OBJECT_STORAGE_PROVIDER 开关(minimal 默认 filesystem)。

## 鉴权模型
与 S3 预签名一致:presign 返回同源相对 URL + HMAC 令牌(签名覆盖 操作+storage_key+part+过期),浏览器裸 XHR PUT(无会话头)经 gateway `proxy_kb`(catch-all,无 auth 依赖,转发 query 串)到达 KB 令牌路由。非新增安全模型。

## 前端零改动
- `multipartUpload.ts` 用 presign 返回的 URL 原样 `xhr.open('PUT', url)`;相对同源 URL 由浏览器按页面 origin 解析,经现有代理链路到 KB。
- `image_url` 前端未消费(apps/web/src 零引用);缩略图走既有服务端中转路由(get_object_bytes,filesystem 模式已支持)。

## 验证
- 隔离单测:multipart 拼接/ETag/stat/delete/令牌签发校验/防篡改。
- TestClient 端到端:PUT 200+ETag、GET 拼接得原文、篡改令牌 403、过期令牌 403、s3 模式 404。
- 分组测试全程 33/33 全绿。

## 未验证(无 Docker,UNVERIFIED)
- 全新 `docker compose up`(filesystem 模式、无 minio 容器)下真实浏览器分片上传→索引→问答闭环,未活体验证。
- 浏览器裸 XHR 对相对 URL 经 vite/prod 反代→gateway→KB 的实际连通性(理论成立:proxy_kb 无 auth、转发 query、ETag 非 hop-by-hop 头可回传),未活体验证。
- 建议:在有 Docker 环境跑一次 filesystem 模式上传闭环确认。
