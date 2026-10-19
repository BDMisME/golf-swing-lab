import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from apps.api.config import get_settings


def sanitize_filename(filename: str) -> str:
    """清洗上傳檔名，防止路徑穿越 (Path Traversal) 並保留安全字元。"""
    base = os.path.basename(filename.replace("\\", "/"))
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    cleaned = cleaned.lstrip(".")
    return cleaned or "video.mp4"


class S3StorageService:
    """封裝 S3 / MinIO 物件儲存操作：包含 Bucket 確保、Multipart Upload、短效簽名與串流讀取。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bucket = self.settings.s3_bucket
        s3_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if self.settings.s3_force_path_style else "auto"},
        )
        self.internal_client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_internal_endpoint_url,
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
            config=s3_config,
        )
        self.public_client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
            config=s3_config,
        )

    def ensure_bucket(self) -> bool:
        """確保目標私有 Bucket 存在。"""
        try:
            self.internal_client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in ("404", "NoSuchBucket", "NotFound"):
                self.internal_client.create_bucket(Bucket=self.bucket)
                return True
            raise

    def check_health(self) -> bool:
        """Readiness 檢查：確認 S3/MinIO 可連線且 Bucket 存在。"""
        try:
            return self.ensure_bucket()
        except Exception:
            return False

    def create_multipart_upload(self, storage_key: str, content_type: str) -> str:
        """在 S3 建立 Multipart Upload 並回傳 S3 UploadId。"""
        self.ensure_bucket()
        resp = self.internal_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=storage_key,
            ContentType=content_type,
        )
        return str(resp["UploadId"])

    def sign_upload_part(self, storage_key: str, s3_upload_id: str, part_number: int) -> str:
        """簽發指定 Part 的短效 Presigned PUT URL。"""
        return str(
            self.public_client.generate_presigned_url(
                ClientMethod="upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": storage_key,
                    "UploadId": s3_upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=self.settings.presigned_url_ttl_seconds,
            )
        )

    def put_part_bytes(
        self, storage_key: str, s3_upload_id: str, part_number: int, data: bytes
    ) -> dict[str, Any]:
        """直接上傳單一 Part 二進位內容至 S3 並回傳 ETag 與 SHA256。"""
        self.ensure_bucket()
        sha256_hex = hashlib.sha256(data).hexdigest()
        resp = self.internal_client.upload_part(
            Bucket=self.bucket,
            Key=storage_key,
            UploadId=s3_upload_id,
            PartNumber=part_number,
            Body=data,
        )
        etag = str(resp.get("ETag", "")).strip('"')
        return {
            "etag": etag,
            "sha256": sha256_hex,
            "size_bytes": len(data),
        }

    def complete_multipart_upload(
        self, storage_key: str, s3_upload_id: str, parts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """完成 S3 Multipart Upload 並驗證物件存在。"""
        sorted_parts = sorted(parts, key=lambda p: int(p["part_number"]))
        s3_parts = [
            {
                "PartNumber": int(p["part_number"]),
                "ETag": f'"{str(p["etag"]).strip(chr(34))}"',
            }
            for p in sorted_parts
        ]
        self.internal_client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=storage_key,
            UploadId=s3_upload_id,
            MultipartUpload={"Parts": s3_parts},
        )
        head = self.head_object(storage_key)
        return head

    def abort_multipart_upload(self, storage_key: str, s3_upload_id: str) -> None:
        """中止未完成的 Multipart Upload 並釋放碎片。"""
        try:
            self.internal_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=storage_key,
                UploadId=s3_upload_id,
            )
        except ClientError:
            pass

    def head_object(self, storage_key: str) -> dict[str, Any]:
        """查詢 S3 物件 Metadata。"""
        resp = self.internal_client.head_object(Bucket=self.bucket, Key=storage_key)
        return {
            "size_bytes": int(resp.get("ContentLength", 0)),
            "content_type": str(resp.get("ContentType", "application/octet-stream")),
            "etag": str(resp.get("ETag", "")).strip('"'),
        }

    def put_file(self, storage_key: str, local_path: str | Path, content_type: str) -> dict[str, Any]:
        """上傳本地檔案至 S3。"""
        self.ensure_bucket()
        path_obj = Path(local_path)
        sha256_hash = hashlib.sha256()
        with path_obj.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(chunk)
        self.internal_client.upload_file(
            str(path_obj),
            self.bucket,
            storage_key,
            ExtraArgs={"ContentType": content_type},
        )
        return {
            "storage_key": storage_key,
            "sha256": sha256_hash.hexdigest(),
            "size_bytes": path_obj.stat().st_size,
        }

    def put_bytes(self, storage_key: str, data: bytes, content_type: str) -> dict[str, Any]:
        """寫入 bytes 至 S3。"""
        self.ensure_bucket()
        sha256_hex = hashlib.sha256(data).hexdigest()
        self.internal_client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=data,
            ContentType=content_type,
        )
        return {
            "storage_key": storage_key,
            "sha256": sha256_hex,
            "size_bytes": len(data),
        }

    def download_to_path(self, storage_key: str, local_path: str | Path) -> Path:
        """從 S3 下載物件至本地暫存路徑。"""
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.internal_client.download_file(self.bucket, storage_key, str(dest))
        return dest

    def get_object_range(
        self, storage_key: str, start_byte: int | None = None, end_byte: int | None = None
    ) -> dict[str, Any]:
        """讀取物件完整或指定 Byte Range 串流（供 Safari HTTP Range 206 播放）。"""
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": storage_key}
        if start_byte is not None and end_byte is not None:
            params["Range"] = f"bytes={start_byte}-{end_byte}"
        resp = self.internal_client.get_object(**params)
        return {
            "body": resp["Body"],
            "content_length": int(resp.get("ContentLength", 0)),
            "content_type": str(resp.get("ContentType", "video/mp4")),
            "content_range": resp.get("ContentRange"),
        }

    def generate_presigned_get_url(self, storage_key: str, expires_in: int | None = None) -> str:
        """產生短效簽名下載/預覽 URL。"""
        return str(
            self.public_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=expires_in or self.settings.presigned_url_ttl_seconds,
            )
        )


@lru_cache
def get_storage_service() -> S3StorageService:
    return S3StorageService()
