"""文件系统对象存储的令牌门控路由(仅 OBJECT_STORAGE_PROVIDER=filesystem 生效)。

去 minio 后,浏览器分片上传/可视资产读取不再直连 S3,而是 PUT/GET 到本服务的同源端点。
鉴权模型与 S3 预签名一致:URL 内携带 HMAC 令牌(免用户会话),由 storage 层签发与校验。
S3 模式下这些端点返回 404(彼时 presign 直指 MinIO,无需服务端中转)。
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Request, Response

from shared.storage import verify_storage_token

from .kb_runtime import storage


router = APIRouter()


def _decode_key(key_b64: str) -> str:
    padded = key_b64 + "=" * (-len(key_b64) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _require_filesystem_backend() -> None:
    if getattr(storage, "provider", "s3") != "filesystem":
        raise HTTPException(status_code=404, detail={"detail": "not found", "code": "not_found"})


@router.put("/api/v1/kb/object-store/parts")
async def upload_object_part(request: Request) -> Response:
    _require_filesystem_backend()
    key_b64 = request.query_params.get("key", "")
    part = request.query_params.get("part", "")
    exp = request.query_params.get("exp", "")
    sig = request.query_params.get("sig", "")
    try:
        storage_key = _decode_key(key_b64)
        part_number = int(part)
        expires_at = int(exp)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail={"detail": "invalid upload token parameters", "code": "invalid_token_params"})
    if not verify_storage_token(sig, "upload_part", storage_key, part_number, expires_at):
        raise HTTPException(status_code=403, detail={"detail": "invalid or expired upload token", "code": "invalid_upload_token"})
    body = await request.body()
    etag = storage.write_part(storage_key, "", part_number, body)
    return Response(status_code=200, headers={"ETag": etag})


@router.get("/api/v1/kb/object-store/object")
def read_object(request: Request) -> Response:
    _require_filesystem_backend()
    key_b64 = request.query_params.get("key", "")
    exp = request.query_params.get("exp", "")
    sig = request.query_params.get("sig", "")
    try:
        storage_key = _decode_key(key_b64)
        expires_at = int(exp)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail={"detail": "invalid object token parameters", "code": "invalid_token_params"})
    if not verify_storage_token(sig, "get_object", storage_key, 0, expires_at):
        raise HTTPException(status_code=403, detail={"detail": "invalid or expired object token", "code": "invalid_object_token"})
    try:
        body, content_type = storage.get_object_bytes(storage_key)
    except RuntimeError:
        raise HTTPException(status_code=404, detail={"detail": "object not found", "code": "object_not_found"})
    return Response(content=body, media_type=content_type)
