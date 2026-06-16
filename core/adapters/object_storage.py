"""
对象存储适配器
==============
记忆树 Markdown 源文件、导出包、附件存储。优先 MinIO/S3（boto3 兼容），
不可用时退化为本地文件系统，保证开发/离线可用。
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import structlog

from core.config import settings

logger = structlog.get_logger(__name__)


class ObjectStorageAdapter:
    def __init__(self) -> None:
        self._client = None
        self._use_s3: Optional[bool] = None
        self._local_root = Path("./data/object_store")

    def _client_ok(self) -> bool:
        if self._use_s3 is not None:
            return self._use_s3
        try:
            import boto3
            from botocore.client import Config

            endpoint = settings.object_storage_endpoint
            scheme = "https" if settings.object_storage_use_ssl else "http"
            self._client = boto3.client(
                "s3",
                endpoint_url=f"{scheme}://{endpoint}",
                aws_access_key_id=settings.object_storage_access_key,
                aws_secret_access_key=settings.object_storage_secret_key,
                config=Config(signature_version="s3v4"),
            )
            self._ensure_bucket()
            self._use_s3 = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("object storage S3 unavailable, local fs fallback", error=str(exc))
            self._use_s3 = False
            self._local_root.mkdir(parents=True, exist_ok=True)
        return self._use_s3

    def _ensure_bucket(self) -> None:
        bucket = settings.object_storage_bucket
        try:
            self._client.head_bucket(Bucket=bucket)
        except Exception:
            self._client.create_bucket(Bucket=bucket)

    def put_text(self, key: str, text: str, content_type: str = "text/markdown") -> str:
        return self.put_bytes(key, text.encode("utf-8"), content_type)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if self._client_ok():
            self._client.put_object(
                Bucket=settings.object_storage_bucket, Key=key,
                Body=io.BytesIO(data), ContentType=content_type,
            )
        else:
            path = self._local_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> Optional[bytes]:
        if self._client_ok():
            try:
                obj = self._client.get_object(Bucket=settings.object_storage_bucket, Key=key)
                return obj["Body"].read()
            except Exception:
                return None
        path = self._local_root / key
        return path.read_bytes() if path.exists() else None

    def get_text(self, key: str) -> Optional[str]:
        data = self.get_bytes(key)
        return data.decode("utf-8") if data is not None else None

    def presigned_url(self, key: str, expires: int = 3600) -> Optional[str]:
        if self._client_ok():
            try:
                return self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.object_storage_bucket, "Key": key},
                    ExpiresIn=expires,
                )
            except Exception:
                return None
        return f"file://{(self._local_root / key).resolve()}"

    def delete(self, key: str) -> None:
        if self._client_ok():
            try:
                self._client.delete_object(Bucket=settings.object_storage_bucket, Key=key)
            except Exception:
                pass
        else:
            path = self._local_root / key
            if path.exists():
                path.unlink()


object_storage = ObjectStorageAdapter()
