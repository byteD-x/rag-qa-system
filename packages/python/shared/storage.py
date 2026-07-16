from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
import os
import shutil
import time
from logging import getLogger
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from botocore.config import Config


logger = getLogger(__name__)


@dataclass(frozen=True)
class ObjectStorageSettings:
    endpoint: str
    public_endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    secure: bool


def load_object_storage_settings(prefix: str = "OBJECT_STORAGE") -> ObjectStorageSettings:
    """Load object storage configuration from environment variables."""
    endpoint = os.getenv(f"{prefix}_ENDPOINT", "http://minio:9000").strip().rstrip("/")
    public_endpoint = os.getenv(f"{prefix}_PUBLIC_ENDPOINT", endpoint).strip().rstrip("/")
    region = os.getenv(f"{prefix}_REGION", "us-east-1").strip() or "us-east-1"
    return ObjectStorageSettings(
        endpoint=endpoint,
        public_endpoint=public_endpoint or endpoint,
        access_key=os.getenv(f"{prefix}_ACCESS_KEY", "minioadmin").strip() or "minioadmin",
        secret_key=os.getenv(f"{prefix}_SECRET_KEY", "minioadmin").strip() or "minioadmin",
        bucket=os.getenv(f"{prefix}_BUCKET", "rag-assets").strip() or "rag-assets",
        region=region,
        secure=endpoint.startswith("https://"),
    )


class ObjectStorageClient:
    """Minimal multipart upload helper for MinIO/S3-compatible storage."""

    provider = "s3"

    def __init__(self, settings: ObjectStorageSettings | None = None):
        self.settings = settings or load_object_storage_settings()
        self._internal = self._create_client(self.settings.endpoint)
        self._public = self._create_client(self.settings.public_endpoint)

    def ensure_bucket(self) -> None:
        buckets = self._internal.list_buckets().get("Buckets", [])
        if not any(item.get("Name") == self.settings.bucket for item in buckets):
            self._internal.create_bucket(Bucket=self.settings.bucket)
        self._ensure_cors()

    def check_bucket_access(self) -> None:
        """Verify that the configured bucket exists and is readable.

        Failure:
        - Raises RuntimeError when the bucket is missing or the storage backend
          is not reachable with the current credentials.
        """
        try:
            self._internal.head_bucket(Bucket=self.settings.bucket)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code") or "")
            if error_code in {"404", "NoSuchBucket", "NotFound"}:
                raise RuntimeError(f"object storage bucket does not exist: {self.settings.bucket}") from exc
            raise RuntimeError(
                f"object storage bucket is not accessible: {error_code or 'client_error'}"
            ) from exc

    def create_multipart_upload(self, storage_key: str, *, metadata: dict[str, str] | None = None) -> str:
        result = self._internal.create_multipart_upload(
            Bucket=self.settings.bucket,
            Key=storage_key,
            Metadata=metadata or {},
        )
        return str(result["UploadId"])

    def presign_upload_part(self, storage_key: str, upload_id: str, part_number: int, *, expires_in: int = 3600) -> str:
        return str(
            self._public.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.settings.bucket,
                    "Key": storage_key,
                    "UploadId": upload_id,
                    "PartNumber": int(part_number),
                },
                ExpiresIn=expires_in,
            )
        )

    def presign_get_object(self, storage_key: str, *, expires_in: int = 3600) -> str:
        return str(
            self._public.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.settings.bucket,
                    "Key": storage_key,
                },
                ExpiresIn=expires_in,
            )
        )

    def presign_download_url(self, storage_key: str, *, expires_in: int = 3600) -> str:
        return str(
            self._public.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.settings.bucket,
                    "Key": storage_key,
                },
                ExpiresIn=expires_in,
            )
        )

    def list_parts(self, storage_key: str, upload_id: str) -> list[dict[str, Any]]:
        response = self._internal.list_parts(
            Bucket=self.settings.bucket,
            Key=storage_key,
            UploadId=upload_id,
        )
        return list(response.get("Parts", []) or [])

    def complete_multipart_upload(
        self,
        storage_key: str,
        upload_id: str,
        parts: list[dict[str, Any]],
    ) -> None:
        self._internal.complete_multipart_upload(
            Bucket=self.settings.bucket,
            Key=storage_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def abort_multipart_upload(self, storage_key: str, upload_id: str) -> None:
        try:
            self._internal.abort_multipart_upload(
                Bucket=self.settings.bucket,
                Key=storage_key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code") or "")
            if error_code in {"NoSuchUpload", "404", "NotFound"}:
                return
            raise

    def stat_object(self, storage_key: str) -> dict[str, Any]:
        return dict(
            self._internal.head_object(
                Bucket=self.settings.bucket,
                Key=storage_key,
            )
        )

    def delete_object(self, storage_key: str) -> None:
        try:
            self._internal.delete_object(
                Bucket=self.settings.bucket,
                Key=storage_key,
            )
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code") or "")
            if error_code in {"NoSuchKey", "404", "NotFound"}:
                return
            raise

    def put_bytes(
        self,
        storage_key: str,
        body: bytes,
        *,
        metadata: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> None:
        self._internal.put_object(
            Bucket=self.settings.bucket,
            Key=storage_key,
            Body=body,
            Metadata=metadata or {},
            ContentType=content_type or "application/octet-stream",
        )

    def download_file(self, storage_key: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._internal.download_file(self.settings.bucket, storage_key, str(target_path))

    def get_object_bytes(self, storage_key: str) -> tuple[bytes, str]:
        response = self._internal.get_object(Bucket=self.settings.bucket, Key=storage_key)
        body = response["Body"].read()
        content_type = str(response.get("ContentType") or "application/octet-stream")
        return body, content_type

    def build_storage_key(self, *, service: str, document_id: str, file_name: str) -> str:
        safe_name = (file_name or "source.bin").replace("\\", "_").replace("/", "_")
        return f"{service}/{document_id}/{safe_name}"

    def _create_client(self, endpoint_url: str) -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.settings.access_key,
            aws_secret_access_key=self.settings.secret_key,
            region_name=self.settings.region,
            use_ssl=endpoint_url.startswith("https://"),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _ensure_cors(self) -> None:
        origins = [item.strip() for item in os.getenv("OBJECT_STORAGE_ALLOWED_ORIGINS", "*").split(",") if item.strip()]
        try:
            self._internal.put_bucket_cors(
                Bucket=self.settings.bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedHeaders": ["*"],
                            "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
                            "AllowedOrigins": origins or ["*"],
                            "ExposeHeaders": ["ETag"],
                            "MaxAgeSeconds": 3600,
                        }
                    ]
                },
            )
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code") or "")
            if error_code == "NotImplemented":
                logger.warning("bucket CORS configuration is not supported by the current object storage backend; continuing without CORS")
                return
            raise


# ---------------------------------------------------------------------------
# 文件系统存储后端(单机形态,去 minio)
# ---------------------------------------------------------------------------


def _fs_token_secret() -> str:
    # 复用 JWT_SECRET 约定,不新增密钥。与 S3 预签名同一安全模型(URL 内签名、免会话)。
    return os.getenv("JWT_SECRET", "change-me-in-env").strip() or "change-me-in-env"


def sign_storage_token(operation: str, storage_key: str, part_number: int, expires_at: int) -> str:
    """对(操作+对象键+分片号+过期时刻)做 HMAC-SHA256 签名,作为同源上传/下载 URL 的令牌。"""
    message = f"{operation}\n{storage_key}\n{int(part_number)}\n{int(expires_at)}".encode("utf-8")
    digest = hmac.new(_fs_token_secret().encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_storage_token(token: str, operation: str, storage_key: str, part_number: int, expires_at: int) -> bool:
    """校验令牌:签名匹配且未过期。"""
    if int(expires_at) < int(time.time()):
        return False
    expected = sign_storage_token(operation, storage_key, part_number, expires_at)
    return hmac.compare_digest(expected, token or "")


@dataclass(frozen=True)
class FilesystemStorageSettings:
    root: Path
    public_base_path: str


def load_filesystem_storage_settings(prefix: str = "OBJECT_STORAGE") -> FilesystemStorageSettings:
    # 默认落在 KB_BLOB_ROOT 下的 object-store 子目录,与源文件解析用的 BLOB_ROOT 隔离。
    default_root = Path(os.getenv("KB_BLOB_ROOT", "/data/kb")) / "object-store"
    root = Path(os.getenv(f"{prefix}_FS_ROOT", str(default_root))).resolve()
    base_path = os.getenv(f"{prefix}_FS_PUBLIC_BASE_PATH", "/api/v1/kb/object-store").strip().rstrip("/")
    return FilesystemStorageSettings(root=root, public_base_path=base_path or "/api/v1/kb/object-store")


class FilesystemStorageClient:
    """文件系统对象存储后端,接口与 ObjectStorageClient 对齐(单机形态去 minio)。

    - 直接读写类落盘;multipart 用本地暂存分片 + 完成时按 PartNumber 拼接;ETag 用分片 md5。
    - presign 返回同源相对 URL + HMAC 令牌,由 KB 分片接收/对象读取路由校验(与 S3 预签名同模型)。
    """

    provider = "filesystem"
    _URL_EXPIRES_DEFAULT = 3600

    def __init__(self, settings: FilesystemStorageSettings | None = None):
        self.settings = settings or load_filesystem_storage_settings()

    def _object_path(self, storage_key: str) -> Path:
        # 防目录穿越:storage_key 由 build_storage_key 生成(service/doc_id/file),按分隔符规整。
        safe = storage_key.replace("\\", "/").lstrip("/")
        target = (self.settings.root / safe).resolve()
        if not str(target).startswith(str(self.settings.root)):
            raise RuntimeError(f"invalid storage key path: {storage_key}")
        return target

    def _staging_dir(self, storage_key: str, upload_id: str) -> Path:
        digest = hashlib.sha256(f"{storage_key}\n{upload_id}".encode("utf-8")).hexdigest()
        return (self.settings.root / ".uploads" / digest).resolve()

    def build_storage_key(self, *, service: str, document_id: str, file_name: str) -> str:
        safe_name = (file_name or "source.bin").replace("\\", "_").replace("/", "_")
        return f"{service}/{document_id}/{safe_name}"

    def ensure_bucket(self) -> None:
        self.settings.root.mkdir(parents=True, exist_ok=True)

    def check_bucket_access(self) -> None:
        try:
            self.settings.root.mkdir(parents=True, exist_ok=True)
            probe = self.settings.root / ".healthz"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"filesystem object storage root is not writable: {self.settings.root}") from exc

    # --- 直接读写(接口与 S3 对齐,调用方零改动) ---
    def put_bytes(self, storage_key: str, body: bytes, *, metadata: dict[str, str] | None = None, content_type: str | None = None) -> None:
        target = self._object_path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

    def get_object_bytes(self, storage_key: str) -> tuple[bytes, str]:
        target = self._object_path(storage_key)
        if not target.is_file():
            raise RuntimeError(f"object not found: {storage_key}")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target.read_bytes(), content_type

    def download_file(self, storage_key: str, target_path: Path) -> None:
        source = self._object_path(storage_key)
        if not source.is_file():
            raise RuntimeError(f"object not found: {storage_key}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target_path)

    def stat_object(self, storage_key: str) -> dict[str, Any]:
        target = self._object_path(storage_key)
        if not target.is_file():
            raise RuntimeError(f"object not found: {storage_key}")
        return {"ContentLength": target.stat().st_size}

    def delete_object(self, storage_key: str) -> None:
        self._object_path(storage_key).unlink(missing_ok=True)

    # --- multipart(本地暂存分片 + 完成时拼接) ---
    def create_multipart_upload(self, storage_key: str, *, metadata: dict[str, str] | None = None) -> str:
        upload_id = uuid4().hex
        self._staging_dir(storage_key, upload_id).mkdir(parents=True, exist_ok=True)
        return upload_id

    def write_part(self, storage_key: str, upload_id: str, part_number: int, body: bytes) -> str:
        staging = self._staging_dir(storage_key, upload_id)
        staging.mkdir(parents=True, exist_ok=True)
        (staging / f"{int(part_number):06d}.part").write_bytes(body)
        return hashlib.md5(body).hexdigest()

    def list_parts(self, storage_key: str, upload_id: str) -> list[dict[str, Any]]:
        staging = self._staging_dir(storage_key, upload_id)
        if not staging.is_dir():
            return []
        parts: list[dict[str, Any]] = []
        for item in sorted(staging.glob("*.part")):
            data = item.read_bytes()
            parts.append({"PartNumber": int(item.stem), "ETag": hashlib.md5(data).hexdigest(), "Size": len(data)})
        return parts

    def complete_multipart_upload(self, storage_key: str, upload_id: str, parts: list[dict[str, Any]]) -> None:
        staging = self._staging_dir(storage_key, upload_id)
        target = self._object_path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            for item in sorted(parts, key=lambda row: int(row["PartNumber"])):
                part_file = staging / f"{int(item['PartNumber']):06d}.part"
                if not part_file.is_file():
                    raise RuntimeError(f"missing upload part {item['PartNumber']} for {storage_key}")
                out.write(part_file.read_bytes())
        shutil.rmtree(staging, ignore_errors=True)

    def abort_multipart_upload(self, storage_key: str, upload_id: str) -> None:
        shutil.rmtree(self._staging_dir(storage_key, upload_id), ignore_errors=True)

    # --- presign(返回同源相对 URL + HMAC 令牌) ---
    def _signed_url(self, operation: str, storage_key: str, part_number: int, expires_in: int) -> str:
        expires_at = int(time.time()) + max(int(expires_in), 1)
        token = sign_storage_token(operation, storage_key, part_number, expires_at)
        key_b64 = base64.urlsafe_b64encode(storage_key.encode("utf-8")).decode("ascii").rstrip("=")
        base = self.settings.public_base_path
        if operation == "upload_part":
            return f"{base}/parts?key={key_b64}&part={int(part_number)}&exp={expires_at}&sig={token}"
        return f"{base}/object?key={key_b64}&exp={expires_at}&sig={token}"

    def presign_upload_part(self, storage_key: str, upload_id: str, part_number: int, *, expires_in: int = _URL_EXPIRES_DEFAULT) -> str:
        return self._signed_url("upload_part", storage_key, int(part_number), expires_in)

    def presign_get_object(self, storage_key: str, *, expires_in: int = _URL_EXPIRES_DEFAULT) -> str:
        return self._signed_url("get_object", storage_key, 0, expires_in)

    def presign_download_url(self, storage_key: str, *, expires_in: int = _URL_EXPIRES_DEFAULT) -> str:
        return self._signed_url("get_object", storage_key, 0, expires_in)


def create_object_storage_client() -> ObjectStorageClient | FilesystemStorageClient:
    """按 OBJECT_STORAGE_PROVIDER 选择后端:filesystem→本地落盘去 minio;否则→S3/MinIO。"""
    provider = os.getenv("OBJECT_STORAGE_PROVIDER", "s3").strip().lower()
    if provider == "filesystem":
        return FilesystemStorageClient()
    return ObjectStorageClient()
