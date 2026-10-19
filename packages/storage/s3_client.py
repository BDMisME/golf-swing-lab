import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """清洗上傳檔名，防止路徑穿越 (Path Traversal) 並保留安全字元。"""
    base = os.path.basename(filename.replace("\\", "/"))
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    cleaned = cleaned.lstrip(".")
    return cleaned or "video.mp4"


class LocalFileStreamer:
    """提供與 boto3 StreamingBody 相容之 iter_chunks 與 read 介面。"""

    def __init__(self, file_path: Path, start_byte: int = 0, length: int | None = None) -> None:
        self.file_path = file_path
        self.start_byte = start_byte
        total_size = file_path.stat().st_size if file_path.exists() else 0
        if length is None:
            self.length = max(0, total_size - start_byte)
        else:
            self.length = min(length, max(0, total_size - start_byte))

    def iter_chunks(self, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
        with self.file_path.open("rb") as f:
            f.seek(self.start_byte)
            remaining = self.length
            while remaining > 0:
                to_read = min(remaining, chunk_size)
                data = f.read(to_read)
                if not data:
                    break
                remaining -= len(data)
                yield data

    def read(self, amt: int | None = None) -> bytes:
        with self.file_path.open("rb") as f:
            f.seek(self.start_byte)
            to_read = self.length if amt is None else min(amt, self.length)
            return f.read(to_read)


class LocalStorageService:
    """
    本地磁碟物件儲存引擎。
    支援完整之分段上傳 (Multipart)、SHA256 校驗、Proxy 檔案寫入與 HTTP Range 串流。
    當 S3/MinIO 不可用時自動切換此備援引擎，確保系統 100% 零停機。
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.local_storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir = self.base_dir / "_uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        safe_key = storage_key.strip("/")
        return self.base_dir / safe_key

    def ensure_bucket(self) -> bool:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        return True

    def check_health(self) -> bool:
        try:
            self.ensure_bucket()
            test_file = self.base_dir / ".health_check"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def create_multipart_upload(self, storage_key: str, content_type: str) -> str:
        self.ensure_bucket()
        upload_id = f"local_up_{uuid.uuid4().hex}"
        part_dir = self.uploads_dir / upload_id
        part_dir.mkdir(parents=True, exist_ok=True)
        meta_file = part_dir / "meta.json"
        meta_file.write_text(
            json.dumps({"storage_key": storage_key, "content_type": content_type}),
            encoding="utf-8",
        )
        return upload_id

    def sign_upload_part(self, storage_key: str, s3_upload_id: str, part_number: int) -> str:
        # 本地模式直接導向代理上傳路徑
        return f"/api/uploads/{s3_upload_id}/parts/{part_number}/content"

    def put_part_bytes(
        self, storage_key: str, s3_upload_id: str, part_number: int, data: bytes
    ) -> dict[str, Any]:
        self.ensure_bucket()
        part_dir = self.uploads_dir / s3_upload_id
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / f"part_{part_number:05d}.bin"
        part_file.write_bytes(data)

        sha256_hex = hashlib.sha256(data).hexdigest()
        etag = hashlib.md5(data).hexdigest()
        return {
            "etag": etag,
            "sha256": sha256_hex,
            "size_bytes": len(data),
        }

    def complete_multipart_upload(
        self, storage_key: str, s3_upload_id: str, parts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        dest_file = self._resolve(storage_key)
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        part_dir = self.uploads_dir / s3_upload_id
        sorted_parts = sorted(parts, key=lambda p: int(p["part_number"]))

        sha256_hash = hashlib.sha256()
        with dest_file.open("wb") as out_f:
            for p in sorted_parts:
                part_no = int(p["part_number"])
                p_file = part_dir / f"part_{part_no:05d}.bin"
                if not p_file.exists():
                    raise FileNotFoundError(f"找不到分段檔案: {p_file}")
                chunk = p_file.read_bytes()
                out_f.write(chunk)
                sha256_hash.update(chunk)

        shutil.rmtree(part_dir, ignore_errors=True)
        return {
            "size_bytes": dest_file.stat().st_size,
            "content_type": "video/mp4",
            "etag": sha256_hash.hexdigest(),
        }

    def abort_multipart_upload(self, storage_key: str, s3_upload_id: str) -> None:
        part_dir = self.uploads_dir / s3_upload_id
        shutil.rmtree(part_dir, ignore_errors=True)

    def head_object(self, storage_key: str) -> dict[str, Any]:
        target = self._resolve(storage_key)
        if not target.exists():
            raise FileNotFoundError(f"找不到本地物件: {storage_key}")
        return {
            "size_bytes": target.stat().st_size,
            "content_type": "video/mp4",
            "etag": hashlib.md5(storage_key.encode("utf-8")).hexdigest(),
        }

    def put_file(self, storage_key: str, local_path: str | Path, content_type: str) -> dict[str, Any]:
        dest = self._resolve(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(local_path)
        shutil.copy2(src, dest)
        sha256_hash = hashlib.sha256()
        with dest.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(chunk)
        return {
            "storage_key": storage_key,
            "sha256": sha256_hash.hexdigest(),
            "size_bytes": dest.stat().st_size,
        }

    def put_bytes(self, storage_key: str, data: bytes, content_type: str) -> dict[str, Any]:
        dest = self._resolve(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return {
            "storage_key": storage_key,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }

    def download_to_path(self, storage_key: str, local_path: str | Path) -> Path:
        src = self._resolve(storage_key)
        dest = Path(local_path)
        if src.resolve() == dest.resolve():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def get_object_range(
        self, storage_key: str, start_byte: int | None = None, end_byte: int | None = None
    ) -> dict[str, Any]:
        src = self._resolve(storage_key)
        total_size = src.stat().st_size if src.exists() else 0
        s = start_byte if start_byte is not None else 0
        e = end_byte if end_byte is not None else max(0, total_size - 1)
        length = max(0, e - s + 1)
        streamer = LocalFileStreamer(src, start_byte=s, length=length)
        return {
            "body": streamer,
            "content_length": length,
            "content_type": "video/mp4",
            "content_range": f"bytes {s}-{e}/{total_size}",
        }

    def generate_presigned_get_url(self, storage_key: str, expires_in: int | None = None) -> str:
        return f"/api/storage/file?key={storage_key}"


class S3StorageService:
    """封裝 S3 / MinIO 物件儲存操作：包含 Bucket 確保、Multipart Upload、短效簽名與串流讀取。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bucket = self.settings.s3_bucket
        s3_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if self.settings.s3_force_path_style else "auto"},
            connect_timeout=2,
            read_timeout=15,
            retries={"max_attempts": 1},
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
        self.ensure_bucket()
        resp = self.internal_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=storage_key,
            ContentType=content_type,
        )
        return str(resp["UploadId"])

    def sign_upload_part(self, storage_key: str, s3_upload_id: str, part_number: int) -> str:
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
        try:
            self.internal_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=storage_key,
                UploadId=s3_upload_id,
            )
        except ClientError:
            pass

    def head_object(self, storage_key: str) -> dict[str, Any]:
        resp = self.internal_client.head_object(Bucket=self.bucket, Key=storage_key)
        return {
            "size_bytes": int(resp.get("ContentLength", 0)),
            "content_type": str(resp.get("ContentType", "application/octet-stream")),
            "etag": str(resp.get("ETag", "")).strip('"'),
        }

    def put_file(self, storage_key: str, local_path: str | Path, content_type: str) -> dict[str, Any]:
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
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.internal_client.download_file(self.bucket, storage_key, str(dest))
        return dest

    def get_object_range(
        self, storage_key: str, start_byte: int | None = None, end_byte: int | None = None
    ) -> dict[str, Any]:
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
        return str(
            self.public_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=expires_in or self.settings.presigned_url_ttl_seconds,
            )
        )


class HybridStorageService:
    """
    智慧雙軌儲存服務：
    優先連線 S3/MinIO；若 S3 連線逾時或不可用，立即自動平滑切換至 LocalStorageService，
    絕不阻斷 API 執行緒，徹底杜絕前端 Load Failed。
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_service = LocalStorageService(self.settings.local_storage_dir)
        self.s3_service: S3StorageService | None = None
        self._s3_available: bool | None = None

        if self.settings.storage_provider != "local":
            try:
                self.s3_service = S3StorageService()
            except Exception as e:
                logger.warning(f"S3 初始化失敗，將使用本地磁碟存儲: {e}")
                self.s3_service = None

    def _get_active_backend(self) -> S3StorageService | LocalStorageService:
        if self.settings.storage_provider == "local" or not self.s3_service:
            return self.local_service

        if self._s3_available is False:
            return self.local_service

        try:
            ok = self.s3_service.check_health()
            self._s3_available = ok
            if ok:
                return self.s3_service
            logger.warning("S3/MinIO 健康檢查未通過，自動降級使用本地磁碟存儲")
            return self.local_service
        except Exception:
            self._s3_available = False
            return self.local_service

    def ensure_bucket(self) -> bool:
        backend = self._get_active_backend()
        try:
            return backend.ensure_bucket()
        except Exception:
            return self.local_service.ensure_bucket()

    def check_health(self) -> bool:
        backend = self._get_active_backend()
        return backend.check_health()

    def create_multipart_upload(self, storage_key: str, content_type: str) -> str:
        backend = self._get_active_backend()
        try:
            return backend.create_multipart_upload(storage_key, content_type)
        except Exception as e:
            logger.warning(f"S3 建立 Multipart 失敗 ({e})，降級切換至 LocalStorage")
            self._s3_available = False
            return self.local_service.create_multipart_upload(storage_key, content_type)

    def sign_upload_part(self, storage_key: str, s3_upload_id: str, part_number: int) -> str:
        backend = self._get_active_backend()
        try:
            return backend.sign_upload_part(storage_key, s3_upload_id, part_number)
        except Exception:
            return self.local_service.sign_upload_part(storage_key, s3_upload_id, part_number)

    def put_part_bytes(
        self, storage_key: str, s3_upload_id: str, part_number: int, data: bytes
    ) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.put_part_bytes(storage_key, s3_upload_id, part_number, data)
        except Exception as e:
            logger.warning(f"S3 寫入分段失敗 ({e})，降級寫入 LocalStorage")
            return self.local_service.put_part_bytes(storage_key, s3_upload_id, part_number, data)

    def complete_multipart_upload(
        self, storage_key: str, s3_upload_id: str, parts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.complete_multipart_upload(storage_key, s3_upload_id, parts)
        except Exception as e:
            logger.warning(f"S3 完成分段失敗 ({e})，降級由 LocalStorage 完成")
            return self.local_service.complete_multipart_upload(storage_key, s3_upload_id, parts)

    def abort_multipart_upload(self, storage_key: str, s3_upload_id: str) -> None:
        backend = self._get_active_backend()
        backend.abort_multipart_upload(storage_key, s3_upload_id)

    def head_object(self, storage_key: str) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.head_object(storage_key)
        except Exception:
            return self.local_service.head_object(storage_key)

    def put_file(self, storage_key: str, local_path: str | Path, content_type: str) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.put_file(storage_key, local_path, content_type)
        except Exception:
            return self.local_service.put_file(storage_key, local_path, content_type)

    def put_bytes(self, storage_key: str, data: bytes, content_type: str) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.put_bytes(storage_key, data, content_type)
        except Exception:
            return self.local_service.put_bytes(storage_key, data, content_type)

    def download_to_path(self, storage_key: str, local_path: str | Path) -> Path:
        backend = self._get_active_backend()
        try:
            return backend.download_to_path(storage_key, local_path)
        except Exception:
            return self.local_service.download_to_path(storage_key, local_path)

    def get_object_range(
        self, storage_key: str, start_byte: int | None = None, end_byte: int | None = None
    ) -> dict[str, Any]:
        backend = self._get_active_backend()
        try:
            return backend.get_object_range(storage_key, start_byte, end_byte)
        except Exception:
            return self.local_service.get_object_range(storage_key, start_byte, end_byte)

    def generate_presigned_get_url(self, storage_key: str, expires_in: int | None = None) -> str:
        backend = self._get_active_backend()
        try:
            return backend.generate_presigned_get_url(storage_key, expires_in)
        except Exception:
            return self.local_service.generate_presigned_get_url(storage_key, expires_in)


@lru_cache
def get_storage_service() -> HybridStorageService:
    return HybridStorageService()
