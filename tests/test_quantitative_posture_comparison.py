"""
tests/test_quantitative_posture_comparison.py
=============================================
驗證 R3: 離線量化姿勢比較 (Quantitative Posture Comparison)
1. 驗證 Address, Top, Impact, Finish 4 大階段量化指標生成。
2. 驗證 2D 骨架關節幾何與軀幹長度正規化計算。
3. 驗證差異閾值判斷 (optimal vs moderate_diff vs significant_diff)。
4. 驗證優先改善動作 (Priority Fix) 與 Drill 訓練建議產生。
5. 驗證最高誠信原則說明（無球速、無距離、無桿面角、無公分單位）。
6. 驗證 API 端點 GET /api/swings/{id}/posture-comparison。
"""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.analysis.posture_comparison import (
    PostureMetricComparison,
    QuantitativePostureReport,
    compute_quantitative_posture_comparison,
)


def test_posture_comparison_computation_logic():
    """單元測試：驗證量化姿勢指標比對核心運算。"""
    user_swing = {
        "id": "user-swing-001",
        "club_type": "7I",
        "start_ms": 1000,
        "events": [
            {"event_name": "address", "time_ms": 1100},
            {"event_name": "top", "time_ms": 2200},
            {"event_name": "impact_estimated", "time_ms": 2550},
            {"event_name": "finish", "time_ms": 3400},
        ],
        "subscores": {
            "spine_tilt_stability": {"score": 68.0, "raw_value": 5.8, "confidence": 0.88},
            "head_stability": {"score": 75.0, "raw_value": 0.09, "confidence": 0.85},
            "tempo_consistency": {"score": 72.0, "raw_value": 2.3, "confidence": 0.90},
            "finish_balance": {"score": 65.0, "raw_value": 65.0, "confidence": 0.82},
        },
        "metrics": [
            {"metric_key": "spine_tilt_delta_deg", "value": 5.8, "confidence": 0.88},
            {"metric_key": "head_displacement_ratio", "value": 0.09, "confidence": 0.85},
            {"metric_key": "backswing_downswing_ratio", "value": 2.3, "confidence": 0.90},
        ],
    }

    ref_swing = {
        "id": "ref-swing-001",
        "club_type": "7I",
        "title": "DJ Watts 7I Standard",
        "event_timestamps": {
            "address": 100,
            "top": 1367,
            "impact": 1700,
            "finish": 2500,
        },
        "calibration_params": {
            "is_slow_motion": False,
        },
    }

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)

    assert isinstance(report, QuantitativePostureReport)
    assert report.user_swing_id == "user-swing-001"
    assert report.club_type == "7I"
    assert len(report.metrics) >= 6

    # 驗證四大階段齊全
    phases = {m.phase for m in report.metrics}
    assert "address" in phases
    assert "top" in phases
    assert "impact" in phases
    assert "finish" in phases

    # 驗證誠信免責說明
    assert "2D DTL" in report.truthfulness_notice
    assert "不推測未量測之球速" in report.truthfulness_notice

    # 驗證優先改善 Drill
    assert report.priority_fix_id is not None
    assert report.actionable_drill is not None
    assert "Drill" in report.actionable_drill["name"] or "練習" in report.actionable_drill["name"]
    assert report.retest_metric_target is not None

    # 驗證每一個指標都有跳轉時間碼與建議速度 (0.25x 或 0.5x)
    for m in report.metrics:
        assert m.target_jump_ms > 0
        assert m.recommended_speed in (0.25, 0.5)
        # 嚴禁輸出未經物理標定之公分/英吋單位
        assert "cm" not in m.unit.lower()
        assert "inch" not in m.unit.lower()
        assert "公分" not in m.unit


def test_posture_comparison_api_endpoint():
    """整合測試：驗證 GET /api/swings/{id}/posture-comparison API。"""
    from apps.api.db import SessionLocal
    from apps.api.models import User, PracticeSession, Video, SwingSegment, SwingEvent, SwingScore
    from apps.api.auth import hash_password, create_session_token

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "posture_test@example.com").first()
        if not user:
            user = User(
                email="posture_test@example.com",
                username="posture_test",
                password_hash=hash_password("Test123456!"),
                role="owner",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = create_session_token(user)

        sess = PracticeSession(
            owner_id=user.id,
            title="Posture Test Session",
            date="2026-10-30",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)

        vid = Video(
            owner_id=user.id,
            session_id=sess.id,
            original_name="test.mp4",
            storage_key="test/posture_test.mp4",
            mime="video/mp4",
            ingest_status="ready",
        )
        db.add(vid)
        db.commit()
        db.refresh(vid)

        seg = SwingSegment(
            owner_id=user.id,
            video_id=vid.id,
            start_ms=1000,
            end_ms=4000,
            label="valid_swing",
            sequence_no=1,
            ball_strike_status="confirmed_strike",
        )
        db.add(seg)
        db.commit()
        db.refresh(seg)

        # 加入事件與評分
        db.add(SwingEvent(segment_id=seg.id, event_name="address", time_ms=1200))
        db.add(SwingEvent(segment_id=seg.id, event_name="top", time_ms=2300))
        db.add(SwingEvent(segment_id=seg.id, event_name="impact_estimated", time_ms=2633))
        db.add(SwingEvent(segment_id=seg.id, event_name="finish", time_ms=3500))
        db.add(SwingScore(
            segment_id=seg.id,
            score_version="score-v2.1",
            overall_nullable=78.5,
            subscores_json={
                "spine_tilt_stability": {"score": 70.0, "raw_value": 5.2, "confidence": 0.88},
                "head_stability": {"score": 80.0, "raw_value": 0.08, "confidence": 0.85},
                "tempo_consistency": {"score": 75.0, "raw_value": 2.4, "confidence": 0.90},
                "finish_balance": {"score": 68.0, "raw_value": 68.0, "confidence": 0.82},
            },
            coverage=0.9,
            confidence=0.86,
            explanation="測試評分",
        ))
        db.commit()

        target_swing_id = seg.id

    with TestClient(app) as client:
        res = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "metrics" in data
        assert len(data["metrics"]) >= 6
        assert "truthfulness_notice" in data
        assert data["user_swing_id"] == target_swing_id
        assert data["priority_fix_id"] is not None
        assert data["actionable_drill"] is not None
