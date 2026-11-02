"""
Golf Tracer Studio R4 — API, Security (401/403 IDOR/503 Feature Flag), Copy-on-Write Revision,
R3 Isolation & Deterministic MP4/Sidecar Export Tests (`tests/test_tracer_api_and_security.py`).
"""

import hashlib
from pathlib import Path
import subprocess

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest
from sqlalchemy import select

from apps.api.auth import create_session_token, hash_password
from apps.api.config import get_settings
from apps.api.db import SessionLocal
from apps.api.main import app
from apps.api.models import (
    PracticeSession,
    SwingEvent,
    SwingScore,
    SwingSegment,
    User,
    Video,
)
from packages.analysis.probe import probe_video_file
from packages.storage.s3_client import get_storage_service

client = TestClient(app)


def _get_admin_user_and_headers() -> tuple[str, dict[str, str]]:
    s = get_settings()
    resp = client.post(
        "/api/auth/login",
        json={"email": s.admin_email, "password": s.admin_password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    user_id = resp.json()["user"]["id"]
    return user_id, {"Authorization": f"Bearer {token}"}


def _get_other_user_headers() -> dict[str, str]:
    with SessionLocal() as db:
        email = "r4_idor_tester@swinglab.local"
        u = db.scalar(select(User).where(User.email == email))
        if not u:
            u = User(
                email=email,
                username="R4 IDOR Tester",
                password_hash=hash_password("OtherPass!2026"),
                role="user",
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        token = create_session_token(u)
        return {"Authorization": f"Bearer {token}"}


def _generate_hd_clip_with_audio(out_path: Path, width: int = 1280, height: int = 720, fps: int = 30) -> tuple[Path, str]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_vid = out_path.with_suffix(".raw_v.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps}/1",
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(raw_vid),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for i in range(45):
            img = np.full((height, width, 3), (32, 46, 30), dtype=np.uint8)
            wx, wy = int(width * 0.48), int(height * 0.52)
            ang = -0.8 + (i / 44.0) * 2.4
            hx = int(wx + np.cos(ang) * (width * 0.18))
            hy = int(wy + np.sin(ang) * (height * 0.22))
            cv2.line(img, (wx, wy), (hx, hy), (245, 245, 250), 4, cv2.LINE_AA)
            # 畫飛球亮點
            if i >= 18:
                bx = int(width * min(0.92, 0.50 + (i - 18) * 0.02))
                by = int(height * max(0.10, 0.76 - (i - 18) * 0.03))
                cv2.circle(img, (bx, by), 7, (255, 255, 255), -1, cv2.LINE_AA)
            proc.stdin.write(img.tobytes())
    finally:
        proc.stdin.close()
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.read()
        proc.stderr.close()
    proc.wait(timeout=30)

    # 混入 1.5 秒正弦音軌供 preserve / mute 測試
    mux_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_vid),
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1.5",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(mux_cmd, capture_output=True, text=True, timeout=30, check=True)
    raw_vid.unlink(missing_ok=True)
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    return out_path, sha


def _seed_session_video_and_two_segments(owner_id: str, tmp_path: Path) -> tuple[str, str, str]:
    vid_file, sha = _generate_hd_clip_with_audio(tmp_path / "r4_api_fixture.mp4")
    storage = get_storage_service()
    storage_key = f"videos/{owner_id}/r4_api_fixture_{sha[:8]}.mp4"
    storage.put_file(storage_key, vid_file, content_type="video/mp4")

    with SessionLocal() as db:
        ps = PracticeSession(
            owner_id=owner_id,
            title="R4 Tracer Studio API 測試場次",
            date="2026-10-31",
            club="7I",
            handedness="right",
            camera_angle="DTL",
            status="completed",
        )
        db.add(ps)
        db.flush()

        video = Video(
            session_id=ps.id,
            owner_id=owner_id,
            original_name="r4_api_fixture.mp4",
            mime="video/mp4",
            size_bytes=vid_file.stat().st_size,
            sha256=sha,
            storage_key=storage_key,
            ingest_status="ready",
            duration_ms=1500,
            width=1280,
            height=720,
            fps_num=30,
            fps_den=1,
            rotation=0,
            codec="h264",
            is_vfr=False,
            has_audio=True,
        )
        db.add(video)
        db.flush()

        seg1 = SwingSegment(
            owner_id=owner_id,
            video_id=video.id,
            sequence_no=1,
            start_ms=60,
            end_ms=1350,
            label="valid_swing",
            ball_strike_status="confirmed_strike",
            confidence=0.92,
        )
        seg2 = SwingSegment(
            owner_id=owner_id,
            video_id=video.id,
            sequence_no=2,
            start_ms=100,
            end_ms=1400,
            label="valid_swing",
            ball_strike_status="confirmed_strike",
            confidence=0.90,
        )
        db.add_all([seg1, seg2])
        db.flush()

        for seg, top_ms, imp_ms in [(seg1, 420, 600), (seg2, 450, 650)]:
            db.add_all(
                [
                    SwingEvent(segment_id=seg.id, event_name="address", time_ms=100, confidence=0.9),
                    SwingEvent(segment_id=seg.id, event_name="top", time_ms=top_ms, confidence=0.91),
                    SwingEvent(segment_id=seg.id, event_name="impact_estimated", time_ms=imp_ms, confidence=0.89),
                    SwingEvent(segment_id=seg.id, event_name="finish", time_ms=1250, confidence=0.90),
                ]
            )
            db.add(
                SwingScore(
                    segment_id=seg.id,
                    score_version="v1.0",
                    overall_nullable=84.5,
                    ig_visual_score=88.0,
                    coverage=1.0,
                    confidence=0.90,
                    subscores_json={"spine_tilt": 85.0},
                    explanation="R3 原始評分",
                )
            )
        db.commit()
        return video.id, seg1.id, seg2.id


def test_tracer_api_unauthenticated_and_feature_flag_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. 未登入存取所有 /api/tracer/* 必回傳 401
    unauth = TestClient(app)
    for ep in ["/api/tracer/models", "/api/tracer/presets", "/api/tracer/projects"]:
        r = unauth.get(ep)
        assert r.status_code == 401

    # 2. 當 GSL_ENABLE_TRACER_STUDIO=false 時，所有 /api/tracer/* 回傳 503 TRACER_STUDIO_DISABLED
    _, admin_headers = _get_admin_user_and_headers()
    s = get_settings()
    monkeypatch.setattr(s, "enable_tracer_studio", False)
    r_disabled = client.get("/api/tracer/models", headers=admin_headers)
    assert r_disabled.status_code == 503
    assert r_disabled.json()["code"] == "TRACER_STUDIO_DISABLED"
    monkeypatch.setattr(s, "enable_tracer_studio", True)


def test_tracer_full_lifecycle_idor_isolation_r3_non_interference_and_exports(tmp_path: Path) -> None:
    admin_id, admin_headers = _get_admin_user_and_headers()
    other_headers = _get_other_user_headers()

    video_id, seg1_id, seg2_id = _seed_session_video_and_two_segments(admin_id, tmp_path)

    # 1. 檢查模型註冊表與 6 組內建預設配方
    r_models = client.get("/api/tracer/models", headers=admin_headers)
    assert r_models.status_code == 200
    models_list = {m["id"]: m for m in r_models.json()["models"]}
    assert "golf_ball_yolov8n" in models_list
    assert "swingtrace_yolo11m" in models_list

    r_presets = client.get("/api/tracer/presets", headers=admin_headers)
    assert r_presets.status_code == 200
    assert len(r_presets.json()["presets"]) == 6

    # 2. 建立專案 1 與專案 2 (含自動追蹤)
    r_p1 = client.post(
        "/api/tracer/projects",
        headers=admin_headers,
        json={"segment_id": seg1_id, "preset_id": "studio_neon", "auto_analyze": True},
    )
    assert r_p1.status_code == 200, r_p1.text
    p1 = r_p1.json()
    p1_id = p1["id"]
    assert p1["active_swing_revision"] == 1
    assert p1["active_shot_revision"] == 1

    r_p2 = client.post(
        "/api/tracer/projects",
        headers=admin_headers,
        json={"segment_id": seg2_id, "preset_id": "clean_analysis", "auto_analyze": True},
    )
    assert r_p2.status_code == 200
    p2_id = r_p2.json()["id"]

    # 3. 跨使用者 IDOR 隔離檢驗 (403 RESOURCE_FORBIDDEN)
    assert client.get(f"/api/tracer/projects/{p1_id}", headers=other_headers).status_code == 403
    assert (
        client.post(
            f"/api/tracer/projects/{p1_id}/edits",
            headers=other_headers,
            json={
                "track_type": "ball",
                "edits": [{"op": "add", "source_pts_us": 600_000, "x_norm": 0.5, "y_norm": 0.5}],
            },
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/tracer/projects/{p1_id}/anchors",
            headers=other_headers,
            json={"top_pts_us": 450_000},
        ).status_code
        == 403
    )

    # 4. 驗證原始高解析串流端點 ?source=original
    r_stream = client.get(f"/api/videos/{video_id}/stream?source=original", headers=admin_headers)
    assert r_stream.status_code in (200, 206)
    assert len(r_stream.content) > 1024

    # 5. Copy-on-Write 逐幀手動編輯與回滾至 Revision 1
    r_edit = client.post(
        f"/api/tracer/projects/{p1_id}/edits",
        headers=admin_headers,
        json={
            "track_type": "ball",
            "recompute_between_manual_anchors": True,
            "note": "新增手動升空錨點",
            "edits": [
                {
                    "op": "add",
                    "source_pts_us": 600_000,
                    "source_frame_index": 18,
                    "x_norm": 0.50,
                    "y_norm": 0.76,
                    "point_role": "manual_anchor",
                },
                {
                    "op": "add",
                    "source_pts_us": 700_000,
                    "source_frame_index": 21,
                    "x_norm": 0.56,
                    "y_norm": 0.54,
                    "point_role": "manual_anchor",
                },
                {
                    "op": "add",
                    "source_pts_us": 800_000,
                    "source_frame_index": 24,
                    "x_norm": 0.62,
                    "y_norm": 0.34,
                    "point_role": "manual_anchor",
                },
            ],
        },
    )
    assert r_edit.status_code == 200, r_edit.text
    p1_after_edit = r_edit.json()
    assert p1_after_edit["active_shot_revision"] == 2
    assert p1_after_edit["shot_mode"] == "MANUAL_ANCHORED"
    assert p1_after_edit["shot_track"]["point_count"] >= 5

    # 確認 Revision 1 完好無損且可回滾
    r_rev1 = client.get(
        f"/api/tracer/projects/{p1_id}/tracks/ball/revisions/1",
        headers=admin_headers,
    )
    assert r_rev1.status_code == 200
    assert r_rev1.json()["revision"] == 1

    r_rollback = client.post(
        f"/api/tracer/projects/{p1_id}/tracks/ball/rollback/1",
        headers=admin_headers,
    )
    assert r_rollback.status_code == 200
    assert r_rollback.json()["active_shot_revision"] == 1

    # 切回 Revision 2 供後續匯出測試
    client.post(f"/api/tracer/projects/{p1_id}/tracks/ball/rollback/2", headers=admin_headers)

    # 6. 測試 Studio 錨點更新與 R3 SwingEvent / SwingScore 100% 隔離不污染
    r_anchor = client.put(
        f"/api/tracer/projects/{p1_id}/anchors",
        headers=admin_headers,
        json={
            "top_pts_us": 445_000,
            "impact_pts_us": 625_000,
            "landing_pts_us": 1_050_000,
            "apex_xy_norm": [0.66, 0.22],
            "landing_xy_norm": [0.74, 0.48],
            "artistic_extension_enabled": True,
            "recompute_tracks": True,
        },
    )
    assert r_anchor.status_code == 200, r_anchor.text
    p1_anchored = r_anchor.json()
    assert p1_anchored["anchors"]["top_pts_us"] == 445_000
    assert p1_anchored["anchors"]["impact_pts_us"] == 625_000
    assert p1_anchored["shot_mode"] == "ARTISTIC_EXTENSION"

    with SessionLocal() as db:
        r3_events = {
            ev.event_name: ev.time_ms
            for ev in db.scalars(select(SwingEvent).where(SwingEvent.segment_id == seg1_id)).all()
        }
        r3_score = db.scalar(select(SwingScore).where(SwingScore.segment_id == seg1_id))
        # R3 原始事件時間碼 (top=420ms, impact_estimated=600ms) 與分數 (84.5) 絕不可被 Studio 修改！
        assert r3_events["top"] == 420
        assert r3_events["impact_estimated"] == 600
        assert r3_score is not None and r3_score.overall_nullable == 84.5

    # 7. 測試單球特效匯出 (9:16 × 60fps × mute) 與 .tracer.json Sidecar 對齊驗證
    r_exp_single = client.post(
        "/api/tracer/exports",
        headers=admin_headers,
        json={
            "project_id": p1_id,
            "aspect_ratio": "9:16",
            "fps": 60,
            "audio_mode": "mute",
            "run_sync": True,
        },
    )
    assert r_exp_single.status_code == 200, r_exp_single.text
    exp1 = r_exp_single.json()
    assert exp1["state"] == "completed"
    assert exp1["output_width"] == 1080
    assert exp1["output_height"] == 1920
    assert exp1["fps"] == 60
    assert exp1["has_audio_stream"] is False
    assert exp1["parity_report"]["coordinate_parity_passed"] is True
    assert exp1["parity_report"]["pts_parity_passed"] is True
    assert exp1["parity_report"]["max_coordinate_error_px"] <= 2.0
    assert exp1["parity_report"]["max_frame_delta_frames"] <= 1.0

    # 下載 MP4 與 Sidecar 並以 ffprobe 實證
    r_dl_mp4 = client.get(exp1["download_url"], headers=admin_headers)
    assert r_dl_mp4.status_code == 200
    mp4_tmp = tmp_path / "exported_single_9x16.mp4"
    mp4_tmp.write_bytes(r_dl_mp4.content)
    probed = probe_video_file(mp4_tmp)
    assert probed.width == 1080
    assert probed.height == 1920
    assert probed.codec == "h264"

    r_dl_sidecar = client.get(exp1["sidecar_url"], headers=admin_headers)
    assert r_dl_sidecar.status_code == 200
    assert r_dl_sidecar.json()["schema_version"] == "r4_tracer_sidecar_v1"

    # 8. 測試多球合輯批次匯出 (2 球 × 16:9 × 30fps × preserve)
    r_exp_batch = client.post(
        "/api/tracer/exports",
        headers=admin_headers,
        json={
            "project_ids": [p1_id, p2_id],
            "aspect_ratio": "16:9",
            "fps": 30,
            "audio_mode": "preserve",
            "run_sync": True,
        },
    )
    assert r_exp_batch.status_code == 200, r_exp_batch.text
    exp_batch = r_exp_batch.json()
    assert exp_batch["state"] == "completed"
    assert len(exp_batch["project_ids"]) == 2
    assert exp_batch["output_width"] == 1920
    assert exp_batch["output_height"] == 1080
    assert exp_batch["fps"] == 30
    assert exp_batch["has_audio_stream"] is True
    assert exp_batch["parity_report"]["coordinate_parity_passed"] is True


def test_tracer_zero_point_anchors_preserve_flags_and_reanalyze_with_studio_overrides(tmp_path: Path) -> None:
    """驗證 P0-4 (0 點 Shot 完整手動錨點建立)、P1-1 (修改 Top/Impact 不意外重置 artistic_extension_enabled，且支援 clear_*)、
    以及 P1-2 (修改 Studio Impact 後重新執行 POST /analyze 實際採用新錨點且不污染 R3)。"""
    admin_id, admin_headers = _get_admin_user_and_headers()
    _, seg1_id, _ = _seed_session_video_and_two_segments(admin_id, tmp_path)

    # 1. 建立不自動分析之空專案 (模擬 0-point UNAVAILABLE 狀態)
    r_create = client.post(
        "/api/tracer/projects",
        headers=admin_headers,
        json={"segment_id": seg1_id, "preset_id": "studio_neon", "auto_analyze": False},
    )
    assert r_create.status_code == 200
    proj = r_create.json()
    pid = proj["id"]
    assert proj["shot_mode"] == "UNAVAILABLE"

    # 2. P0-4: 在 0 點狀態下直接設定 Launch + Apex + Landing -> 產生 MANUAL_ANCHORED 軌跡
    r_zero_manual = client.put(
        f"/api/tracer/projects/{pid}/anchors",
        headers=admin_headers,
        json={
            "launch_pts_us": 610_000,
            "launch_xy_norm": [0.51, 0.77],
            "apex_xy_norm": [0.60, 0.25],
            "landing_pts_us": 1_120_000,
            "landing_xy_norm": [0.70, 0.50],
            "artistic_extension_enabled": False,
            "recompute_tracks": True,
        },
    )
    assert r_zero_manual.status_code == 200, r_zero_manual.text
    p_manual = r_zero_manual.json()
    assert p_manual["shot_mode"] == "MANUAL_ANCHORED"
    assert p_manual["shot_track"]["point_count"] >= 5
    assert p_manual["anchors"]["anchors_json"]["launch_xy_norm"] == [0.51, 0.77]

    # 3. 開啟 artistic_extension_enabled=True -> 切換為 ARTISTIC_EXTENSION
    r_artistic_on = client.put(
        f"/api/tracer/projects/{pid}/anchors",
        headers=admin_headers,
        json={"artistic_extension_enabled": True, "recompute_tracks": True},
    )
    assert r_artistic_on.status_code == 200
    assert r_artistic_on.json()["anchors"]["anchors_json"]["artistic_extension_enabled"] is True
    assert r_artistic_on.json()["shot_mode"] == "ARTISTIC_EXTENSION"

    # 4. P1-1: 單獨更新 top_pts_us / impact_pts_us (不傳 artistic_extension_enabled)，既有 True 與空間錨點必須保留！
    r_update_time_only = client.put(
        f"/api/tracer/projects/{pid}/anchors",
        headers=admin_headers,
        json={"top_pts_us": 460_000, "impact_pts_us": 640_000, "recompute_tracks": True},
    )
    assert r_update_time_only.status_code == 200
    p_preserved = r_update_time_only.json()
    assert p_preserved["anchors"]["top_pts_us"] == 460_000
    assert p_preserved["anchors"]["impact_pts_us"] == 640_000
    assert p_preserved["anchors"]["anchors_json"]["artistic_extension_enabled"] is True
    assert p_preserved["anchors"]["anchors_json"]["apex_xy_norm"] == [0.60, 0.25]
    assert p_preserved["anchors"]["anchors_json"]["landing_xy_norm"] == [0.70, 0.50]

    # 5. P1-1: 測試 clear_apex 與 clear_landing 明確清除空間錨點
    r_clear = client.put(
        f"/api/tracer/projects/{pid}/anchors",
        headers=admin_headers,
        json={
            "clear_apex": True,
            "clear_landing": True,
            "artistic_extension_enabled": False,
            "recompute_tracks": False,
        },
    )
    assert r_clear.status_code == 200
    p_cleared = r_clear.json()
    assert p_cleared["anchors"]["anchors_json"].get("apex_xy_norm") is None
    assert p_cleared["anchors"]["anchors_json"].get("landing_xy_norm") is None
    assert p_cleared["anchors"]["anchors_json"]["artistic_extension_enabled"] is False

    # 6. P1-2: 呼叫 POST /api/tracer/projects/{id}/analyze，確認重算保留並使用 Studio 覆寫之 460_000 / 640_000，且 R3 SwingEvent 仍為 420 / 600ms
    r_reanalyze = client.post(
        f"/api/tracer/projects/{pid}/analyze",
        headers=admin_headers,
        json={"run_sync": True},
    )
    assert r_reanalyze.status_code == 200, r_reanalyze.text
    p_reanalyzed = r_reanalyze.json()["project"]
    assert p_reanalyzed["anchors"]["top_pts_us"] == 460_000
    assert p_reanalyzed["anchors"]["impact_pts_us"] == 640_000
    assert p_reanalyzed["swing_track"] is not None
    # 檢查 Swing 軌跡中位於 430_000us (介於原始 420ms 與新 460ms 之間) 的點必須被歸類為 backswing 而非 downswing
    for pt in p_reanalyzed["swing_track"]["points"]:
        if 425_000 <= pt["source_pts_us"] < 460_000:
            assert pt["phase"] == "backswing"
        elif 460_000 <= pt["source_pts_us"] < 640_000:
            assert pt["phase"] == "downswing"

    with SessionLocal() as db:
        r3_evs = {
            ev.event_name: ev.time_ms
            for ev in db.scalars(select(SwingEvent).where(SwingEvent.segment_id == seg1_id)).all()
        }
        assert r3_evs["top"] == 420
        assert r3_evs["impact_estimated"] == 600

