"""
Golf Tracer Studio R4 — Content-Addressed Track Artifact Cache (`artifact_cache.py`).
負責將每一個 `TracerTrackRevision` 之 `CanonicalTrackPoint` 列表序列化為 Gzipped JSONL
(`tracer/tracks/{project_id}/{track_type}_rev{revision}_{sha256[:12]}.jsonl.gz`)，
透過 `get_storage_service()` 儲存與讀取，並強制檢驗 SHA256 完整性。
"""

import gzip
import hashlib
import json
from typing import Any

from packages.analysis.tracer.contracts import CanonicalTrackPoint
from packages.storage.s3_client import get_storage_service


def serialize_track_points_gzip_jsonl(points: list[CanonicalTrackPoint]) -> tuple[bytes, str]:
    """將 `CanonicalTrackPoint` 列表序列化為 Gzip 壓縮之 JSON Lines 位元組與 SHA256。"""
    sorted_pts = sorted(points, key=lambda p: p.source_pts_us)
    lines = [json.dumps(pt.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) for pt in sorted_pts]
    raw_jsonl = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    compressed = gzip.compress(raw_jsonl, compresslevel=6)
    sha256_hex = hashlib.sha256(compressed).hexdigest()
    return compressed, sha256_hex


def deserialize_track_points_gzip_jsonl(
    compressed_bytes: bytes,
    expected_sha256: str | None = None,
) -> list[CanonicalTrackPoint]:
    """解壓縮並驗證 Gzipped JSONL 位元組，還原為 `CanonicalTrackPoint` 列表。"""
    if expected_sha256:
        actual = hashlib.sha256(compressed_bytes).hexdigest()
        if actual != expected_sha256:
            raise ValueError(f"軌跡點檔案 SHA256 校驗失敗: expected={expected_sha256}, actual={actual}")

    if not compressed_bytes:
        return []

    raw_text = gzip.decompress(compressed_bytes).decode("utf-8")
    points: list[CanonicalTrackPoint] = []
    for line in raw_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        payload: dict[str, Any] = json.loads(clean)
        points.append(CanonicalTrackPoint.model_validate(payload))
    points.sort(key=lambda p: p.source_pts_us)
    return points


def save_track_revision_artifact(
    project_id: str,
    track_type: str,
    revision: int,
    points: list[CanonicalTrackPoint],
) -> tuple[str, str, int]:
    """
    將軌跡修訂版寫入物件儲存，回傳 `(storage_key, sha256_hex, size_bytes)`。
    """
    compressed, sha256_hex = serialize_track_points_gzip_jsonl(points)
    storage_key = f"tracer/tracks/{project_id}/{track_type}_rev{int(revision)}_{sha256_hex[:12]}.jsonl.gz"
    storage = get_storage_service()
    storage.put_bytes(
        storage_key=storage_key,
        data=compressed,
        content_type="application/gzip",
    )
    return storage_key, sha256_hex, len(compressed)


def load_track_revision_artifact(
    storage_key: str,
    expected_sha256: str | None = None,
) -> list[CanonicalTrackPoint]:
    """
    從物件儲存讀取並還原 `CanonicalTrackPoint` 列表。
    """
    storage = get_storage_service()
    res = storage.get_object_range(storage_key=storage_key)
    body = res["body"]
    compressed = body.read()
    return deserialize_track_points_gzip_jsonl(compressed, expected_sha256=expected_sha256)
