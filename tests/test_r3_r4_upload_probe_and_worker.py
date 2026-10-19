import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.db import SessionLocal
from apps.api.main import app
from apps.api.models import AnalysisJob
from packages.analysis.probe import probe_video_file
from packages.storage.s3_client import sanitize_filename
from tests.fixtures.video_factory import create_synthetic_dtl_video

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    s = get_settings()
    r = client.post("/api/auth/login", json={"email": s.admin_email, "password": s.admin_password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_filename_sanitization_and_upload_validation() -> None:
    assert sanitize_filename("../../etc/passwd.mov") == "passwd.mov"
    assert sanitize_filename("..\\..\\secret\\swing 01.MP4") == "swing_01.MP4"

    headers = _auth_headers()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"title": "上傳驗證測試", "date": "2026-10-19", "club": "7I", "handedness": "right"},
    ).json()

    # 不合法的副檔名
    bad_ext = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "exploit.sh",
            "mime_type": "video/mp4",
            "size_bytes": 10240,
        },
    )
    assert bad_ext.status_code == 400
    assert bad_ext.json()["code"] == "UNSUPPORTED_FILE_EXTENSION"

    # 超過最大上傳限制
    too_big = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "huge.mov",
            "mime_type": "video/quicktime",
            "size_bytes": get_settings().max_upload_bytes + 1024,
        },
    )
    assert too_big.status_code == 413


def test_multipart_upload_resumable_and_range_stream(tmp_path: Path) -> None:
    headers = _auth_headers()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"title": "分段續傳測試場次", "date": "2026-10-19", "club": "7I", "handedness": "right"},
    ).json()

    # 建立真實 H.264 旋轉 90 度之 MOV 測試影片
    mov_path = create_synthetic_dtl_video(
        tmp_path / "iphone_rotated.mov",
        duration_ms=6000,
        fps=30,
        codec="libx264",
        rotation=90,
        swings_spec=[{"start_ms": 1200, "end_ms": 4500, "label": "valid_swing"}],
    )
    video_bytes = mov_path.read_bytes()
    sha256_hex = hashlib.sha256(video_bytes).hexdigest()

    # 以單段進行 Multipart Upload + 冪等重入測試
    idem_key = f"idem-{sess['id'][:12]}-{sha256_hex[:8]}"
    init_1 = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "iphone_rotated.mov",
            "mime_type": "video/quicktime",
            "size_bytes": len(video_bytes),
            "part_size_bytes": max(5242880, len(video_bytes)),
            "sha256": sha256_hex,
            "idempotency_key": idem_key,
        },
    )
    assert init_1.status_code == 200, init_1.text
    upload_id = init_1.json()["upload_id"]
    video_id = init_1.json()["video_id"]

    # 測試簽發短效 URL
    sign_r = client.post(
        f"/api/uploads/{upload_id}/parts/sign",
        headers=headers,
        json={"part_number": 1},
    )
    assert sign_r.status_code == 200
    assert "presigned_url" in sign_r.json()

    # 上傳第 1 段
    put_r = client.put(
        f"/api/uploads/{upload_id}/parts/1/content",
        headers=headers,
        content=video_bytes,
    )
    assert put_r.status_code == 200
    part_etag = put_r.json()["etag"]

    # 模擬斷網重連：以相同 idempotency_key 再次呼叫 initiate，應回傳已上傳之 Part 清單
    init_resume = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "iphone_rotated.mov",
            "mime_type": "video/quicktime",
            "size_bytes": len(video_bytes),
            "part_size_bytes": max(5242880, len(video_bytes)),
            "sha256": sha256_hex,
            "idempotency_key": idem_key,
        },
    )
    assert init_resume.status_code == 200
    assert init_resume.json()["idempotent_reused"] is True
    assert len(init_resume.json()["uploaded_parts"]) == 1

    # 完成上傳並驗證 ffprobe 解析出旋轉角度與時長
    comp_r = client.post(
        f"/api/uploads/{upload_id}/complete",
        headers=headers,
        json={
            "parts": [{"part_number": 1, "etag": part_etag}],
            "sha256": sha256_hex,
        },
    )
    assert comp_r.status_code == 200, comp_r.text
    c_data = comp_r.json()
    assert c_data["state"] == "completed"
    assert c_data["duration_ms"] >= 5500
    assert c_data["rotation"] in (90, 270)

    # 測試 HTTP Range 206 串流播放
    stream_r = client.get(
        f"/api/videos/{video_id}/stream",
        headers={**headers, "Range": "bytes=0-1023"},
    )
    assert stream_r.status_code == 206
    assert stream_r.headers["Accept-Ranges"] == "bytes"
    assert stream_r.headers["Content-Range"].startswith("bytes 0-1023/")
    assert len(stream_r.content) == 1024


def test_hevc_and_vfr_probe_and_corrupt_rejection(tmp_path: Path) -> None:
    # 測試 HEVC (H.265) + VFR 影片產生與 ffprobe 解析
    hevc_path = create_synthetic_dtl_video(
        tmp_path / "hevc_vfr_sample.mov",
        duration_ms=4000,
        fps=30,
        codec="libx265",
        vfr=True,
        swings_spec=[{"start_ms": 800, "end_ms": 3200, "label": "valid_swing"}],
    )
    meta = probe_video_file(hevc_path, collect_pts=True)
    assert meta.codec == "hevc"
    assert meta.duration_ms >= 3000
    assert len(meta.pts_timestamps_ms) > 10

    # 測試損毀檔案上傳在 Complete 階段優雅拒絕 (422 INVALID_VIDEO_MEDIA)
    headers = _auth_headers()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"title": "損毀檔測試", "date": "2026-10-19", "club": "7I", "handedness": "right"},
    ).json()
    corrupt_bytes = b"not-a-valid-video-container-at-all" * 50
    init_c = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "corrupt.mp4",
            "mime_type": "video/mp4",
            "size_bytes": len(corrupt_bytes),
        },
    ).json()
    up_id = init_c["upload_id"]
    p_res = client.put(f"/api/uploads/{up_id}/parts/1/content", headers=headers, content=corrupt_bytes).json()
    comp_bad = client.post(
        f"/api/uploads/{up_id}/complete",
        headers=headers,
        json={"parts": [{"part_number": 1, "etag": p_res["etag"]}]},
    )
    assert comp_bad.status_code == 422
    assert comp_bad.json()["code"] == "INVALID_VIDEO_MEDIA"


def test_worker_job_idempotency_cancel_and_retry_limits(tmp_path: Path) -> None:
    headers = _auth_headers()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={"title": "佇列控制測試", "date": "2026-10-19", "club": "7I", "handedness": "right"},
    ).json()

    v_path = create_synthetic_dtl_video(tmp_path / "short.mp4", duration_ms=4000)
    v_bytes = v_path.read_bytes()
    up = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "short.mp4",
            "mime_type": "video/mp4",
            "size_bytes": len(v_bytes),
        },
    ).json()
    pr = client.put(f"/api/uploads/{up['upload_id']}/parts/1/content", headers=headers, content=v_bytes).json()
    client.post(
        f"/api/uploads/{up['upload_id']}/complete",
        headers=headers,
        json={"parts": [{"part_number": 1, "etag": pr["etag"]}]},
    )

    video_id = up["video_id"]
    j1 = client.post(f"/api/videos/{video_id}/analyze", headers=headers).json()
    j2 = client.post(f"/api/videos/{video_id}/analyze", headers=headers).json()
    assert j1["job_id"] == j2["job_id"]
    assert j2["idempotent_reused"] is True

    job_id = j1["job_id"]
    # 測試取消任務
    cancel_r = client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
    assert cancel_r.status_code == 200
    assert cancel_r.json()["status"] == "cancelled"

    # 模擬孤兒任務恢復與達到最大重試上限 (max_attempts=3)
    with SessionLocal() as db:
        job_row = db.get(AnalysisJob, job_id)
        assert job_row is not None
        job_row.status = "running"
        job_row.heartbeat_at = datetime.now(UTC) - timedelta(seconds=300)
        job_row.attempt_count = 2
        db.commit()

    # 因為 heartbeat 逾時 > 180s，允許安全重試
    retry_ok = client.post(f"/api/jobs/{job_id}/retry", headers=headers)
    assert retry_ok.status_code == 200

    # 當 attempt_count 已達 3 次上限，再次重試必須拒絕 (400 JOB_MAX_RETRIES_EXCEEDED)
    with SessionLocal() as db:
        job_row = db.get(AnalysisJob, job_id)
        assert job_row is not None
        job_row.status = "failed"
        job_row.attempt_count = 3
        db.commit()

    retry_blocked = client.post(f"/api/jobs/{job_id}/retry", headers=headers)
    assert retry_blocked.status_code == 400
    assert retry_blocked.json()["code"] == "JOB_MAX_RETRIES_EXCEEDED"
