from __future__ import annotations

from pathlib import Path

import boto3
from botocore.config import Config


class S3Store:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, use_ssl: bool):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if use_ssl else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def download_to(self, storage_key: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, storage_key, str(target_path))