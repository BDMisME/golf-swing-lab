import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db import SessionLocal
from apps.api.models import User, ReferenceSwing, SwingSegment, SwingScore, SwingEvent, Video, PracticeSession
from packages.analysis.coach import (
    compute_swing_action_differences,
    generate_deep_vision_insight,
    ActionDifference,
    FORBIDDEN_HALLUCINATION_TERMS,
)
from apps.api.auth import hash_password, create_session_token

client = TestClient(app)


def get_test_token(db):
    user = db.query(User).filter(User.email == "coach_test@example.com").first()
    if not user:
        user = User(
            email="coach_test@example.com",
            username="coach_test",
            password_hash=hash_password("Test123456!"),
            role="owner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return create_session_token(user)


def test_reference_swings_catalog_17_clubs():
    """驗證示範揮桿目錄包含完整 17 種球桿分類與真實狀態"""
    with SessionLocal() as db:
        token = get_test_token(db)

    resp = client.get("/api/reference-swings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "clubs" in data
    assert "available_clubs" in data
    assert "total_clubs" in data
    assert data["total_clubs"] == 17

    club_types = [c["club_type"] for c in data["clubs"]]
    expected_clubs = [
        "Driver", "3W", "5W", "3H", "4H", "5H",
        "4I", "5I", "6I", "7I", "8I", "9I",
        "PW", "GW/AW", "SW", "LW", "Putter"
    ]
    for c in expected_clubs:
        assert c in club_types, f"缺少球桿分類: {c}"

    # 驗證 7I 有標準示範影片
    club_7i = next(c for c in data["clubs"] if c["club_type"] == "7I")
    assert club_7i["status"] == "available"
    assert club_7i["reference_count"] >= 1
    assert club_7i["default_reference"]["verified_club"] is True
    assert club_7i["default_reference"]["camera_angle"].lower() == "dtl"

    # 驗證 Driver 為 close_up 特寫，verified_camera_angle 為 False
    club_driver = next(c for c in data["clubs"] if c["club_type"] == "Driver")
    if club_driver["status"] == "available":
        assert club_driver["default_reference"]["camera_angle"] == "close_up"
        assert club_driver["default_reference"]["verified_camera_angle"] is False

    # 驗證尚無合法素材之球桿如 3W 狀態為 missing_reference
    club_3w = next(c for c in data["clubs"] if c["club_type"] == "3W")
    assert club_3w["status"] == "missing_reference"


def test_reference_swing_range_streaming_206():
    """驗證示範揮桿支援 HTTP 206 Partial Content Range 串流"""
    with SessionLocal() as db:
        token = get_test_token(db)
        ref_7i = db.query(ReferenceSwing).filter(ReferenceSwing.club_type == "7I").first()
        assert ref_7i is not None, "未找到 7I 示範影片種子"
        ref_id = ref_7i.id

    # 請求前 1024 bytes
    resp = client.get(
        f"/api/reference-swings/{ref_id}/stream",
        headers={"Authorization": f"Bearer {token}", "Range": "bytes=0-1023"},
    )
    assert resp.status_code == 206, f"預期 HTTP 206，得到 {resp.status_code}"
    assert "bytes 0-1023/" in resp.headers.get("content-range", "")
    assert len(resp.content) == 1024


def test_compute_swing_action_differences_and_hallucination_guard():
    """驗證動作差異分析推導：最多 1~2 項、影像證據對齊、嚴禁幻覺名詞"""
    subscores = {
        "spine_tilt_stability": {
            "score": 68.0,
            "weight": 0.25,
            "raw_value": 7.5,
            "confidence": 0.88,
            "how_calculated": "脊柱傾角變化 7.5 度",
        },
        "tempo_consistency": {
            "score": 65.0,
            "weight": 0.20,
            "raw_value": 2.1,
            "confidence": 0.90,
            "how_calculated": "上下桿比例 2.1:1",
        },
        "head_stability": {
            "score": 85.0,
            "weight": 0.15,
            "raw_value": 0.08,
            "confidence": 0.85,
            "how_calculated": "頭部位移比 8%",
        },
    }
    events = [
        {"event_name": "address", "time_ms": 1000},
        {"event_name": "top", "time_ms": 1700},
        {"event_name": "impact_estimated", "time_ms": 2000},
        {"event_name": "finish", "time_ms": 2800},
    ]

    diffs = compute_swing_action_differences(subscores, events)
    assert len(diffs) <= 2, "動作差異不得超過 2 項"
    assert len(diffs) >= 1

    # 檢查第一項差異
    diff1 = diffs[0]
    assert diff1.phase in ("top", "impact_estimated")
    assert diff1.time_ms in (1700, 2000)
    assert "度" in diff1.magnitude or ":" in diff1.magnitude or "%" in diff1.magnitude

    # 深度解讀
    report = generate_deep_vision_insight(diff1, {"id": "test_seg"})
    assert report.diff_id == diff1.id
    assert report.step_by_step_drill["preparation"]
    assert report.step_by_step_drill["execution"]
    assert report.step_by_step_drill["checkpoint"]

    # 驗證誠信原則：教練分析實質內容不含任何未測量物理名詞
    content_text = (
        report.visual_evidence_analysis
        + report.kinetic_chain_effect
        + report.step_by_step_drill["execution"]
    ).lower()
    for forbidden in FORBIDDEN_HALLUCINATION_TERMS:
        assert forbidden.lower() not in content_text, f"報告實質內容包含禁止名詞: {forbidden}"

    # 驗證免責聲明存在
    assert "不推測" in report.truthfulness_notice or "未經" in report.truthfulness_notice


def test_deep_insight_api_endpoint():
    """驗證 POST /api/swings/{id}/deep-insight API 正確回傳解析"""
    with SessionLocal() as db:
        token = get_test_token(db)
        user = db.query(User).filter(User.email == "coach_test@example.com").first()

        # 建立測試場次、影片與揮桿
        sess = PracticeSession(
            owner_id=user.id,
            title="Deep Insight Test Session",
            date="2026-10-28",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)

        vid = Video(
            owner_id=user.id,
            session_id=sess.id,
            original_name="test.mp4",
            storage_key="test/test.mp4",
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
            end_ms=3000,
            sequence_no=1,
            label="valid_swing",
            ball_strike_status="confirmed_strike",
        )
        db.add(seg)
        db.commit()
        db.refresh(seg)

        # 加入事件與分數
        ev_top = SwingEvent(
            segment_id=seg.id,
            event_name="top",
            time_ms=1700,
            confidence=0.9,
            detection_source="test",
        )
        ev_impact = SwingEvent(
            segment_id=seg.id,
            event_name="impact_estimated",
            time_ms=2000,
            confidence=0.88,
            detection_source="test",
        )
        db.add_all([ev_top, ev_impact])

        score = SwingScore(
            segment_id=seg.id,
            score_version="score-v1",
            overall_nullable=72.0,
            coverage=0.85,
            subscores_json={
                "spine_tilt_stability": {
                    "score": 65.0,
                    "weight": 0.25,
                    "raw_value": 7.8,
                    "confidence": 0.88,
                    "how_calculated": "脊柱傾角變化 7.8 度",
                }
            },
        )
        db.add(score)
        db.commit()
        seg_id = seg.id

    # 測試 GET /api/swings/{id} 回傳包含 action_differences
    resp_get = client.get(f"/api/swings/{seg_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp_get.status_code == 200
    seg_data = resp_get.json()
    assert "action_differences" in seg_data
    assert len(seg_data["action_differences"]) >= 1
    diff_id = seg_data["action_differences"][0]["id"]

    # 測試 POST /api/swings/{id}/deep-insight
    resp_insight = client.post(
        f"/api/swings/{seg_id}/deep-insight",
        headers={"Authorization": f"Bearer {token}"},
        json={"diff_id": diff_id},
    )
    assert resp_insight.status_code == 200, resp_insight.text
    insight_data = resp_insight.json()
    assert insight_data["diff_id"] == diff_id
    assert "visual_evidence_analysis" in insight_data
    assert "kinetic_chain_effect" in insight_data
    assert "step_by_step_drill" in insight_data
    assert "truthfulness_notice" in insight_data
