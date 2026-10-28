"""
tests/test_true_e2e_pipeline.py

Golf Swing Lab — Release Candidate (RC) 真正全鏈路端到端 (True E2E) 測試
涵蓋：
1. 真實 11 秒 iPhone 錄影完整 Pipeline:
   Probe (PTS/VFR) -> 720p/30fps Safari Proxy 生成 -> Coarse-to-Fine 掃描
   -> 9 階段事件狀態機 -> 指標計算 -> 評分引擎 -> DB 持久化
   -> FastAPI Client 訪問 /report 與 /swings/{id} -> 排行榜驗證 -> 安全自動清理。
2. 動作分類硬門檻防護 (Classification Gate & Non-Swing Defense):
   走路、放球、空揮試擺嚴格標記，揮桿總分 overall_nullable 必然為 None，杜絕「走路拿 70 分」。
3. 動作品質嚴懲扣分 (Bad Swing Harsh Penalty):
   抬頭起身、急躁失控節奏 (如 1.2:1)、收桿失衡予以嚴厲扣分 (30~55分)，杜絕爛球虛高 70+ 分。
4. 儲存與 API 契約一致性驗證。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.db import SessionLocal
from apps.api.main import app
from apps.api.models import (
    AnalysisJob,
    PoseArtifact,
    PracticeSession,
    SwingEvent,
    SwingMetric,
    SwingScore,
    SwingSegment,
    Video,
)
from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.analysis.events.state_machine import DetectedEvent, SwingPhaseStateMachine
from packages.analysis.pose.extractor import FramePoseResult, Landmark2D
from packages.analysis.probe import generate_proxy_and_thumbnail, probe_video_file
from packages.analysis.scoring.engine import compute_swing_score, rank_session_swings

REPO_ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def _get_auth_headers() -> dict[str, str]:
    settings = get_settings()
    res = client.post(
        "/api/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert res.status_code == 200, f"登入失敗: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """建立測試專用暫存目錄，測試結束後 100% 安全清理。"""
    tmp_path = Path(tempfile.mkdtemp(prefix="gsl_test_e2e_"))
    yield tmp_path
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_e2e_real_11s_full_pipeline(temp_output_dir: Path):
    """
    實測 1: 真實 11 秒 iPhone 錄影全鏈路端到端測試
    """
    raw_video = REPO_ROOT / "測試影片" / "11秒.mov"
    if not raw_video.exists():
        pytest.skip(f"找不到測試影片: {raw_video}")

    proxy_path = temp_output_dir / "proxy_11s.mp4"
    thumb_path = temp_output_dir / "thumb_11s.jpg"

    # Step 1: Probe 探測真實 PTS 與 FPS
    meta = probe_video_file(raw_video)
    assert meta.duration_ms > 8000, "影片長度探測異常"
    assert meta.fps_num > 0, "FPS 探測異常"

    # Step 2: 生成 Safari 相容 720p/30fps Proxy 與縮圖
    generate_proxy_and_thumbnail(raw_video, proxy_path, thumb_path)
    assert proxy_path.exists() and proxy_path.stat().st_size > 1024, "Proxy 未成功生成"
    assert thumb_path.exists() and thumb_path.stat().st_size > 100, "縮圖未成功生成"

    # Step 3: 使用 CoarseToFineDetector 執行分析
    detector = CoarseToFineDetector()
    segments, quality_summary = detector.analyze_video(
        video_path=proxy_path,
        duration_ms=meta.duration_ms,
    )
    assert len(segments) >= 1, "未偵測到 11 秒影片中的揮桿動作"

    # Step 4: 寫入資料庫 (模擬 Worker 持久化)
    headers = _get_auth_headers()
    # 建立 Session
    sess_res = client.post(
        "/api/sessions",
        headers=headers,
        json={"title": "E2E 11秒實測場次", "date": "2026-10-24", "club": "7I", "handedness": "right"},
    )
    assert sess_res.status_code in (200, 201), f"建立場次失敗: {sess_res.text}"
    session_id = sess_res.json()["id"]

    db = SessionLocal()
    try:
        # 取得 owner_id
        owner_id = sess_res.json()["owner_id"]
        video_record = Video(
            id=f"vid_e2e_11s_{os.getpid()}",
            owner_id=owner_id,
            session_id=session_id,
            storage_key="test_e2e/11s.mov",
            original_name="11秒.mov",
            size_bytes=raw_video.stat().st_size,
            mime="video/quicktime",
            duration_ms=meta.duration_ms,
            width=meta.width,
            height=meta.height,
            fps_num=meta.fps_num,
            fps_den=meta.fps_den,
            has_audio=meta.has_audio,
            is_vfr=meta.is_vfr,
            proxy_storage_key=str(proxy_path),
            thumbnail_storage_key=str(thumb_path),
            ingest_status="ready",
        )
        db.add(video_record)
        db.commit()

        # 持久化揮桿片段與評分
        saved_segment_ids = []
        for s_idx, cand in enumerate(segments, start=1):
            seg_id = f"seg_e2e_11s_{s_idx}_{os.getpid()}"
            saved_segment_ids.append(seg_id)
            seg = SwingSegment(
                id=seg_id,
                owner_id=owner_id,
                video_id=video_record.id,
                sequence_no=s_idx,
                start_ms=cand.start_ms,
                end_ms=cand.end_ms,
                label=cand.label,
                confidence=cand.confidence,
                ball_strike_status=cand.ball_strike_status,
                review_status=cand.review_status,
                review_flags_json=cand.review_flags,
            )
            db.add(seg)

            for ev in cand.events:
                db.add(
                    SwingEvent(
                        segment_id=seg.id,
                        event_name=ev.event_name,
                        time_ms=ev.time_ms,
                        confidence=ev.confidence,
                        detection_source=ev.detection_source,
                        model_version=ev.model_version,
                        rationale=ev.rationale,
                    )
                )

            for m in cand.metrics:
                db.add(
                    SwingMetric(
                        segment_id=seg.id,
                        metric_key=m["metric_key"],
                        value=m["value"],
                        unit=m["unit"],
                        confidence=m["confidence"],
                        source=m.get("source", "pose-v2"),
                        observability=m.get("observability", "observable_2d"),
                    )
                )

            score_res = compute_swing_score(
                metrics=cand.metrics,
                quality_metadata=cand.quality_metadata,
                label=cand.label,
            )
            db.add(
                SwingScore(
                    segment_id=seg.id,
                    score_version=score_res.score_version,
                    overall_nullable=score_res.overall_nullable,
                    ig_visual_score=score_res.ig_visual_score,
                    partial_score=score_res.partial_score,
                    subscores_json=score_res.subscores,
                    coverage=score_res.coverage,
                    confidence=score_res.confidence,
                    explanation=score_res.explanation,
                )
            )
            db.add(
                PoseArtifact(
                    segment_id=seg.id,
                    storage_key=None,
                    quality_metadata=cand.quality_metadata,
                    keyframes_json=cand.keyframes,
                )
            )
        db.commit()

        # Step 5: 透過 FastAPI 訪問 /api/sessions/{session_id}/report
        report_res = client.get(f"/api/sessions/{session_id}/report", headers=headers)
        assert report_res.status_code == 200, f"取得報告失敗: {report_res.text}"
        rep_json = report_res.json()
        assert rep_json["session"]["id"] == session_id
        assert "rankings" in rep_json
        assert "swings" in rep_json
        assert len(rep_json["swings"]) == len(segments)

        # Step 6: 透過 FastAPI 訪問單球詳情 /api/swings/{swing_id}
        first_seg_id = saved_segment_ids[0]
        swing_res = client.get(f"/api/swings/{first_seg_id}", headers=headers)
        assert swing_res.status_code == 200, f"取得單球失敗: {swing_res.text}"
        sw_json = swing_res.json()
        assert sw_json["id"] == first_seg_id
        assert "events" in sw_json
        assert "overall_score" in sw_json
        assert "subscores" in sw_json

        # 驗證生理下桿合理性
        top_ev = next((e for e in sw_json["events"] if e["event_name"] == "top"), None)
        imp_ev = next((e for e in sw_json["events"] if e["event_name"] == "impact_estimated"), None)
        if top_ev and imp_ev:
            ds = imp_ev["time_ms"] - top_ev["time_ms"]
            assert 180 <= ds <= 600, f"下桿時間異常: {ds}ms"

    finally:
        # 清理測試資料庫記錄
        try:
            for s_id in saved_segment_ids:
                db.query(PoseArtifact).filter(PoseArtifact.segment_id == s_id).delete()
                db.query(SwingScore).filter(SwingScore.segment_id == s_id).delete()
                db.query(SwingMetric).filter(SwingMetric.segment_id == s_id).delete()
                db.query(SwingEvent).filter(SwingEvent.segment_id == s_id).delete()
                db.query(SwingSegment).filter(SwingSegment.id == s_id).delete()
            db.query(Video).filter(Video.id == f"vid_e2e_11s_{os.getpid()}").delete()
            db.query(PracticeSession).filter(PracticeSession.id == session_id).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


def test_e2e_non_swing_protection_and_penalties():
    """
    實測 2: 走路/放球/微動之動作分類硬門檻與 0 評分防護，
    以及動作嚴重走樣時的扣分檢驗。
    """
    # 1. 模擬走路動作 (手腕垂直振幅極小，無實質揮桿)
    times = list(range(0, 3000, 33))
    mock_walk_frames = []
    for t in times:
        # 手腕維持在腹部微晃 (y: 0.58 ~ 0.59)，振幅只有 0.01
        wy = 0.58 + 0.01 * (1.0 if (t // 500) % 2 == 0 else 0.0)
        lm = {
            "right_wrist": Landmark2D(x=0.5, y=wy, visibility=0.9),
            "left_wrist": Landmark2D(x=0.52, y=wy, visibility=0.9),
            "right_shoulder": Landmark2D(x=0.45, y=0.35, visibility=0.9),
            "left_shoulder": Landmark2D(x=0.55, y=0.35, visibility=0.9),
            "right_hip": Landmark2D(x=0.47, y=0.60, visibility=0.9),
            "left_hip": Landmark2D(x=0.53, y=0.60, visibility=0.9),
        }
        mock_walk_frames.append(FramePoseResult(time_ms=t, frame_idx=t // 33, landmarks=lm))

    sm = SwingPhaseStateMachine()
    events, trace, label = sm.extract_events(frames=mock_walk_frames)
    # 必須判定為非 valid_swing (如 walking, practice_swing, swing_candidate, rejected)
    assert label != "valid_swing", f"走路被誤判為正式揮桿: {label}"

    # 傳入評分引擎：非 valid_swing 嚴禁給分
    metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 0.5, "confidence": 0.9, "unit": "deg_2d", "category": "posture"},
        {"metric_key": "head_displacement_ratio", "value": 0.02, "confidence": 0.9, "unit": "torso_ratio", "category": "posture"},
    ]
    score_walk = compute_swing_score(metrics=metrics, label=label)
    assert score_walk.overall_nullable is None, "走路或非揮桿絕不可給予揮桿技術評分"
    assert score_walk.ig_visual_score is None

    # 2. 模擬動作嚴重變形之爛球 (抬頭起身 Δ=9.5°、節奏比 1.2:1、收桿站不穩 sway=0.18)
    bad_metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 9.5, "confidence": 0.9, "unit": "deg_2d", "category": "posture"},
        {"metric_key": "head_displacement_ratio", "value": 0.16, "confidence": 0.85, "unit": "torso_ratio", "category": "posture"},
        {"metric_key": "single_swing_plane_gap_ratio", "value": 0.18, "confidence": 0.85, "unit": "ratio", "category": "kinematics"},
        {"metric_key": "backswing_downswing_ratio", "value": 1.20, "confidence": 0.9, "unit": "ratio", "category": "tempo"},
        {"metric_key": "finish_hold_ms", "value": 400.0, "confidence": 0.85, "unit": "ms", "category": "balance"},
        {"metric_key": "finish_sway_ratio", "value": 0.18, "confidence": 0.85, "unit": "sway_ratio", "category": "balance"},
    ]
    score_bad = compute_swing_score(metrics=bad_metrics, label="valid_swing")
    assert score_bad.overall_nullable is not None
    # 動作嚴重變形時，總分必須在 45 分以下，絕不給虛高 70+ 分
    assert score_bad.overall_nullable <= 45.0, f"爛球虛高評分: {score_bad.overall_nullable}分"
    assert score_bad.subscores["tempo_consistency"]["score"] <= 20.0
    assert score_bad.subscores["finish_balance"]["score"] <= 25.0


def test_e2e_official_ranking_consistency():
    """
    實測 3: 驗證 rank_session_swings 正式榜單排除 needs_review 與爭議球，
    且嚴格遵守多維度加權排序契約。
    """
    mock_swings = [
        {
            "id": "s-1",
            "sequence_no": 1,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "review_flags": [],
            "overall_score": 68.0,
            "ig_visual_score": 75.0,
            "confidence": 0.85,
            "subscores": {
                "spine_tilt_stability": {"score": 75.0},
                "head_stability": {"score": 70.0},
                "tempo_consistency": {"score": 30.0, "raw_value": 1.4},
                "finish_balance": {"score": 80.0, "hold_ms": 1500, "raw_value": 0.05},
            },
            "quality_metadata": {"body_visibility_ratio": 1.0},
        },
        {
            "id": "s-2",
            "sequence_no": 2,
            "label": "valid_swing",
            "review_status": "needs_review",  # 跨模態衝突球，不可進入姿態與節奏榜
            "review_flags": ["audio_kinematic_conflict"],
            "overall_score": 88.0,
            "ig_visual_score": 90.0,
            "confidence": 0.60,
            "subscores": {
                "spine_tilt_stability": {"score": 95.0},
                "head_stability": {"score": 90.0},
                "tempo_consistency": {"score": 95.0, "raw_value": 3.0},
                "finish_balance": {"score": 90.0, "hold_ms": 2000, "raw_value": 0.03},
            },
            "quality_metadata": {"body_visibility_ratio": 1.0},
        },
    ]

    rankings = rank_session_swings(mock_swings, top_k=3)
    # 驗證 needs_review 球絕不進入 posture 與 tempo 榜單第一名
    for cat in ["posture", "tempo"]:
        top_items = rankings.get(cat, [])
        for item in top_items:
            assert item["segment_id"] != "s-2", f"爭議球誤入 {cat} 榜單: {item}"
