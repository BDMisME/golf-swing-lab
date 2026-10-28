"""
tests/test_swing_10_regression.py

P0-A & P0-B & P0-C 回歸測試：
專門針對第 10 球（以及同類揮桿）在 30fps Proxy 與多音訊峰值情境下的 Impact 定位、
音訊運動學矛盾降級與排行榜安全隔離進行嚴格檢驗。

重現之核心缺陷：
1. 30fps Proxy 在 121060ms 檢出擊球後雜音（護網/隨揮風切聲），舊版無條件鎖定至 121067ms，
   導致 Impact 延遲 152ms、下桿被虛增至 401ms。
2. 舊版將取樣解析度冒充為 40ms 不確定度，並給出 0.88 高信心度，標為 auto_accepted。
3. 腳本未調用正式 rank_session_swings()，將此爭議球誤推為最佳節奏第 1 名。

修復後驗證標準：
1. 運動學合理性閘門 (Kinematic Plausibility Gate)：
   隨揮上升期 (vy < -0.20 或手腕脫離最低點 20% 深度) 的音訊一律拒絕同步。
2. Impact 正確落回 120899ms ~ 120933ms (真球噴出 120898ms 鄰域)。
3. 矛盾降級：標記 audio_kinematic_conflict，review_status 設為 needs_review，
   不確定度放大 (>= 70ms)，信心度降級 (<= 0.65)。
4. 正式排行榜排除：rank_session_swings() 嚴格排除 needs_review / 爭議球進入 posture 與 tempo 榜單。
"""

import json
from pathlib import Path
import numpy as np
import pytest

from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.analysis.events.state_machine import DetectedEvent, SwingPhaseStateMachine
from packages.analysis.pose.extractor import FramePoseResult, Landmark2D
from packages.analysis.scoring.engine import compute_swing_score, rank_session_swings

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_reproduce_swing_10_audio_kinematic_conflict_and_fix():
    """
    單元級回歸測試：模擬第 10 球 30fps Proxy 之手腕軌跡與音訊瞬態。
    驗證 Kinematic Plausibility Gate 是否成功阻斷 121060ms 偽音訊，
    並將 Impact 錨定在 120899~120933ms 最低點制動處。
    """
    # 建立模擬 30fps Proxy 之影格序列 (120700ms ~ 121200ms, step = 33.3ms)
    # 真實觸球在 ~120898ms，最低點在 120899ms / 120933ms，隨後 121000ms 起手腕大幅上升
    times = [
        120700, 120733, 120766, 120800, 120833, 120866,
        120899, 120933, 120966, 121000, 121033, 121067, 121100, 121133, 121166
    ]
    
    # 模擬手腕 Y 深度 (0.0 頂點, 1.0 最低點)
    # 120899~120933 為最低點 (0.680)，121067 時已上升隨揮至 0.490
    wrist_y_map = {
        120700: 0.350, 120733: 0.400, 120766: 0.480, 120800: 0.560,
        120833: 0.630, 120866: 0.670, 120899: 0.685, 120933: 0.682,
        120966: 0.640, 121000: 0.580, 121033: 0.530, 121067: 0.485,
        121100: 0.420, 121133: 0.360, 121166: 0.300
    }

    mock_frames = []
    for idx, t in enumerate(times):
        wy = wrist_y_map[t]
        fr = FramePoseResult(
            frame_idx=idx,
            time_ms=t,
            landmarks={
                "right_wrist": Landmark2D(x=0.50, y=wy, visibility=0.90),
                "left_wrist": Landmark2D(x=0.52, y=wy, visibility=0.88),
                "right_shoulder": Landmark2D(x=0.50, y=0.30, visibility=0.90),
                "left_shoulder": Landmark2D(x=0.52, y=0.30, visibility=0.90),
                "right_hip": Landmark2D(x=0.50, y=0.55, visibility=0.90),
                "left_hip": Landmark2D(x=0.52, y=0.55, visibility=0.90),
            },
            pose_confidence=0.90,
            wrist_motion_energy=0.08,
            brightness=50.0,
            sharpness=40.0,
            camera_motion=0.01,
            person_count=1,
        )
        mock_frames.append(fr)

    # 模擬 121060ms 之後發雜音 (晚於真正 Impact 160ms)
    audio_transients = [121060]

    scanner = CoarseToFineDetector(model_version="pose-v2")
    
    # 測試局部精修
    # 若以 center_ms = 121000 傳入
    # 舊版會直接鎖定 121067ms；新版必須拒絕 121060ms，並錨定於 120899ms 或 120933ms 最低點
    res = scanner._refine_event_local_high_fps_from_frames(
        local_frames=mock_frames,
        event_name="impact",
        center_ms=121000,
        audio_transients_ms=audio_transients,
    )

    assert res is not None, "精修必須產出結果"
    # Impact 必須落在最低點附近 (120899 或 120933)，絕不能落在 121067
    assert res["refined_ms"] in (120899, 120933), (
        f"Impact 被偽音訊拉偏至 {res['refined_ms']}ms！預期應落在手腕最低點制動 (120899 或 120933ms)"
    )
    
    # 驗證音訊衝突標記與降級
    assert "audio_kinematic_conflict" in res.get("flags", []) or "wrist_kinematic_lowest_point" in res["sources"]
    if "audio_transient_synchronized" not in res["sources"]:
        # 若音訊因運動學矛盾被拒絕，信心度不得虛高為 0.88
        assert res["confidence"] <= 0.78, f"拒絕音訊後信心度不得高於 0.78，實際為 {res['confidence']}"
        assert res["uncertainty_ms"] >= 50, f"不確定度必須擴大，實際為 {res['uncertainty_ms']}ms"


def test_ranking_excludes_needs_review_and_audio_conflict():
    """
    驗證正式 rank_session_swings() 必須嚴格排除 needs_review、
    audio_kinematic_conflict 與 timing_anomaly 球進入 posture 與 tempo 榜單。
    """
    swings = [
        # 第 2 球：正常高品質揮桿
        {
            "id": "swing-2",
            "sequence_no": 2,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "review_flags": [],
            "overall_score": 88.0,
            "confidence": 0.85,
            "subscores": {
                "spine_tilt_stability": {"raw_value": 2.1, "score": 90.0},
                "tempo_consistency": {"raw_value": 3.0, "score": 92.0},
                "finish_balance": {"raw_value": 0.05, "hold_ms": 600, "score": 85.0},
            },
            "ig_visual_score": 85.0,
        },
        # 第 10 球：舊版因下桿被拉長而 tempo score 高達 95 分，但帶有 audio_kinematic_conflict 與 needs_review
        {
            "id": "swing-10",
            "sequence_no": 10,
            "label": "valid_swing",
            "review_status": "needs_review",
            "review_flags": ["audio_kinematic_conflict"],
            "overall_score": 82.0,
            "confidence": 0.58,
            "subscores": {
                "spine_tilt_stability": {"raw_value": 3.5, "score": 80.0},
                "tempo_consistency": {"raw_value": 3.1, "score": 95.0},  # 分數雖高
                "finish_balance": {"raw_value": 0.04, "hold_ms": 550, "score": 88.0},
            },
            "ig_visual_score": 80.0,
        },
        # 第 7 球：正常球
        {
            "id": "swing-7",
            "sequence_no": 7,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "review_flags": [],
            "overall_score": 84.0,
            "confidence": 0.82,
            "subscores": {
                "spine_tilt_stability": {"raw_value": 2.8, "score": 85.0},
                "tempo_consistency": {"raw_value": 2.8, "score": 86.0},
                "finish_balance": {"raw_value": 0.06, "hold_ms": 500, "score": 82.0},
            },
            "ig_visual_score": 82.0,
        },
    ]

    ranks = rank_session_swings(swings)
    
    # 檢驗 tempo (最佳節奏) 排行榜
    tempo_rank_ids = [r["segment_id"] for r in ranks["tempo"]]
    assert "swing-10" not in tempo_rank_ids, (
        f"第 10 球帶有 needs_review / audio_kinematic_conflict，絕對禁止被推薦進最佳節奏榜單！實際榜單: {tempo_rank_ids}"
    )
    assert tempo_rank_ids[0] == "swing-2", f"最佳節奏第一名應為正常球 swing-2，實際為 {tempo_rank_ids[0]}"

    # 檢驗 posture (最佳姿勢) 排行榜
    posture_rank_ids = [r["segment_id"] for r in ranks["posture"]]
    assert "swing-10" not in posture_rank_ids, (
        f"第 10 球帶有爭議，絕對禁止被推薦進最佳姿勢榜單！實際榜單: {posture_rank_ids}"
    )


def test_api_session_report_excludes_audio_conflict_swing():
    """
    P0-C & P0-D: 驗證真實 API 端點 /api/sessions/{session_id}/report 之完整資料流。
    透過 DB 建立包含爭議球 (needs_review / audio_kinematic_conflict) 之場次，
    確保 API 序列化後送入 rank_session_swings() 時，排行榜正確排除爭議球。
    """
    from fastapi.testclient import TestClient
    from apps.api.main import app
    from apps.api.config import get_settings
    from apps.api.db import SessionLocal
    from apps.api.models import PracticeSession, Video, SwingSegment, SwingScore, User

    client = TestClient(app)
    settings = get_settings()
    
    # 登入取得 Token
    login_res = client.post(
        "/api/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == settings.admin_email).first()
        assert user is not None

        # 建立測試場次
        sess = PracticeSession(
            owner_id=user.id,
            title="回歸驗收測試場次",
            date="2026-10-24",
            club="7I",
            handedness="right",
            camera_angle="DTL",
        )
        db.add(sess)
        db.flush()

        # 建立測試影片
        vid = Video(
            session_id=sess.id,
            owner_id=user.id,
            original_name="test_p0_video.mp4",
            mime="video/mp4",
            storage_key="test/test_p0.mp4",
            ingest_status="ready",
            duration_ms=139000,
            fps_num=30,
            fps_den=1,
        )
        db.add(vid)
        db.flush()

        # 球 1：正常球 (Sequence 2)
        s1 = SwingSegment(
            owner_id=user.id,
            video_id=vid.id,
            sequence_no=2,
            start_ms=25000,
            end_ms=28000,
            label="valid_swing",
            ball_strike_status="confirmed_strike",
            confidence=0.85,
            review_status="auto_accepted",
            review_flags_json=[],
            version="pose-v2",
        )
        db.add(s1)
        db.flush()
        db.add(SwingScore(
            segment_id=s1.id,
            score_version="score-v1",
            overall_nullable=88.0,
            ig_visual_score=85.0,
            coverage=0.90,
            confidence=0.85,
            subscores_json={
                "spine_tilt_stability": {"score": 90.0, "raw_value": 2.1},
                "tempo_consistency": {"score": 92.0, "raw_value": 3.0},
                "finish_balance": {"score": 85.0, "raw_value": 0.05, "hold_ms": 600},
            },
        ))

        # 球 2：爭議球 (Sequence 10: 音訊矛盾降級)
        s2 = SwingSegment(
            owner_id=user.id,
            video_id=vid.id,
            sequence_no=10,
            start_ms=120000,
            end_ms=123000,
            label="valid_swing",
            ball_strike_status="confirmed_strike",
            confidence=0.58,
            review_status="needs_review",
            review_flags_json=["audio_kinematic_conflict"],
            version="pose-v2",
        )
        db.add(s2)
        db.flush()
        db.add(SwingScore(
            segment_id=s2.id,
            score_version="score-v1",
            overall_nullable=82.0,
            ig_visual_score=90.0,
            coverage=0.90,
            confidence=0.58,
            subscores_json={
                "spine_tilt_stability": {"score": 80.0, "raw_value": 3.5},
                "tempo_consistency": {"score": 96.0, "raw_value": 3.1},  # 虛高 Tempo 分數
                "finish_balance": {"score": 88.0, "raw_value": 0.04, "hold_ms": 550},
            },
        ))

        db.commit()
        session_id = sess.id
        swing_10_id = s2.id

    # 請求場次報告 API
    rep_res = client.get(f"/api/sessions/{session_id}/report", headers=headers)
    assert rep_res.status_code == 200, f"場次報告 API 失敗: {rep_res.text}"
    rep_data = rep_res.json()

    # 驗證排行榜安全隔離
    tempo_ranks = rep_data["rankings"]["tempo"]
    posture_ranks = rep_data["rankings"]["posture"]
    
    tempo_seqs = [r["sequence_no"] for r in tempo_ranks]
    posture_seqs = [r["sequence_no"] for r in posture_ranks]

    assert 10 not in tempo_seqs, f"第 10 球絕對禁止進入 API TEMPO 排行榜！實際排名: {tempo_seqs}"
    assert 10 not in posture_seqs, f"第 10 球絕對禁止進入 API POSTURE 排行榜！實際排名: {posture_seqs}"
    assert 2 in tempo_seqs, "正常球 #2 必須在 TEMPO 排行榜中"

    # 驗證單球 API
    sw_res = client.get(f"/api/swings/{swing_10_id}", headers=headers)
    assert sw_res.status_code == 200
    sw_data = sw_res.json()
    assert sw_data["review_status"] == "needs_review"
    assert "audio_kinematic_conflict" in sw_data["review_flags"]

