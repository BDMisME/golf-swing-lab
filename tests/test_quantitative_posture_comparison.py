"""
tests/test_quantitative_posture_comparison.py
=============================================
驗證 R3: 離線量化姿勢比較 (Quantitative Posture Comparison)
依據最高誠信原則（Truthfulness & Anti-Hallucination）：
1. 示範影片更換時，回傳相應的真實量化資料，不得依賴寫死假常數。
2. 無示範庫或示範無 Pose 時，回傳明確不可比或缺少證據狀態，不得塞假分數。
3. 慢動作示範影片的節奏比必須標示為慢動作不適用，不得計算假數值。
4. 視角不相容時，必須標示無法比對。
5. 相同輸入的重算一致性（Deterministic）。
6. 優先改善建議 (Priority Fix) 的真實性：缺少實質差異或缺少足夠資料時，不得隨機產生 Drill。
7. API 端點 GET /api/swings/{id}/posture-comparison 完整性驗證。
"""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from packages.analysis.posture_comparison import (
    PostureMetricComparison,
    QuantitativePostureReport,
    compute_quantitative_posture_comparison,
)


def _make_landmarks(
    sh_x: float = 0.45,
    sh_y: float = 0.30,
    hp_x: float = 0.55,
    hp_y: float = 0.60,
    wrist_y: float = 0.65,
    nose_x: float = 0.45,
    nose_y: float = 0.20,
    vis: float = 0.95,
) -> dict:
    """產生標準測試用 2D landmarks 字典。"""
    return {
        "left_shoulder": {"x": sh_x - 0.02, "y": sh_y, "visibility": vis},
        "right_shoulder": {"x": sh_x + 0.02, "y": sh_y, "visibility": vis},
        "left_hip": {"x": hp_x - 0.02, "y": hp_y, "visibility": vis},
        "right_hip": {"x": hp_x + 0.02, "y": hp_y, "visibility": vis},
        "left_wrist": {"x": hp_x, "y": wrist_y, "visibility": vis},
        "right_wrist": {"x": hp_x, "y": wrist_y, "visibility": vis},
        "nose": {"x": nose_x, "y": nose_y, "visibility": vis},
    }


def _make_standard_user_swing(
    addr_tilt_x: float = 0.45,
    top_tilt_x: float = 0.45,
    vis: float = 0.95,
) -> dict:
    """產生包含 4 大階段 keyframes 的使用者揮桿測試物件。"""
    # 站姿：肩 (addr_tilt_x, 0.30)，髖 (0.55, 0.60)，dy=0.30
    addr_lms = _make_landmarks(sh_x=addr_tilt_x, hp_x=0.55, vis=vis)
    top_lms = _make_landmarks(sh_x=top_tilt_x, hp_x=0.55, vis=vis)
    imp_lms = _make_landmarks(sh_x=addr_tilt_x, hp_x=0.58, vis=vis)
    fin_lms = _make_landmarks(sh_x=0.54, hp_x=0.55, wrist_y=0.25, vis=vis)

    return {
        "id": "user-swing-001",
        "club_type": "7I",
        "camera_angle": "DTL",
        "start_ms": 1000,
        "events": [
            {"event_name": "address", "time_ms": 1100},
            {"event_name": "top", "time_ms": 2200},
            {"event_name": "impact_estimated", "time_ms": 2550},
            {"event_name": "finish", "time_ms": 3400},
        ],
        "subscores": {
            "spine_tilt_stability": {"score": 75.0, "raw_value": 4.5, "confidence": 0.88},
            "head_stability": {"score": 80.0, "raw_value": 0.06, "confidence": 0.85},
            "tempo_consistency": {"score": 72.0, "raw_value": 2.3, "confidence": 0.90},
            "finish_balance": {"score": 70.0, "raw_value": 70.0, "confidence": 0.82},
        },
        "metrics": [
            {"metric_key": "spine_tilt_delta_deg", "value": 4.5, "confidence": 0.88},
            {"metric_key": "head_displacement_ratio", "value": 0.06, "confidence": 0.85},
            {"metric_key": "backswing_downswing_ratio", "value": 2.3, "confidence": 0.90},
        ],
        "keyframes": [
            {"time_ms": 1100, "landmarks": addr_lms, "pose_confidence": vis},
            {"time_ms": 2200, "landmarks": top_lms, "pose_confidence": vis},
            {"time_ms": 2550, "landmarks": imp_lms, "pose_confidence": vis},
            {"time_ms": 3400, "landmarks": fin_lms, "pose_confidence": vis},
        ],
    }


def _make_standard_ref_swing(
    ref_id: str = "ref-7i-001",
    camera_angle: str = "DTL",
    is_slow_mo: bool = False,
    events_reliable: bool = True,
    has_pose: bool = True,
    addr_tilt_x: float = 0.40,
) -> dict:
    """產生示範球員測試物件。"""
    addr_lms = _make_landmarks(sh_x=addr_tilt_x, hp_x=0.55)
    top_lms = _make_landmarks(sh_x=addr_tilt_x, hp_x=0.55)
    imp_lms = _make_landmarks(sh_x=addr_tilt_x, hp_x=0.60)
    fin_lms = _make_landmarks(sh_x=0.54, hp_x=0.55, wrist_y=0.25)

    ref_obj = {
        "id": ref_id,
        "club_type": "7I",
        "title": "DJ Watts 7I Standard",
        "camera_angle": camera_angle,
        "event_timestamps": {
            "address": 200,
            "top": 1400,
            "impact": 1800,
            "finish": 2600,
        },
        "calibration_params": {
            "is_slow_motion": is_slow_mo,
            "events_reliable": events_reliable,
        },
    }
    if has_pose:
        ref_obj["pose_artifact"] = {
            "landmarks": {
                "200": addr_lms,
                "1400": top_lms,
                "1800": imp_lms,
                "2600": fin_lms,
            }
        }
    else:
        ref_obj["pose_artifact"] = {}
    return ref_obj


# =========================================================================
# 測試案例
# =========================================================================

def test_posture_comparison_with_real_keyframes_and_evidence():
    """1. 測試真實 Pose 幾何量測與證據生成。"""
    user_swing = _make_standard_user_swing(addr_tilt_x=0.45)
    ref_swing = _make_standard_ref_swing(addr_tilt_x=0.38)

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)

    assert isinstance(report, QuantitativePostureReport)
    assert report.user_swing_id == "user-swing-001"
    assert report.ref_swing_id == "ref-7i-001"
    assert report.overall_status == "ready"
    assert report.overall_reliability in ("high", "moderate")
    assert len(report.metrics) >= 7

    # 驗證四大階段指標均有生成
    phases = {m.phase for m in report.metrics}
    assert {"address", "top", "impact", "finish"}.issubset(phases)

    # 驗證各指標計算結果與單位（嚴禁任何公分或英吋）
    for m in report.metrics:
        assert "cm" not in m.unit.lower()
        assert "inch" not in m.unit.lower()
        assert "公分" not in m.unit
        assert m.target_jump_ms > 0
        assert m.recommended_speed in (0.25, 0.5)
        # 理論常模獨立存在
        assert len(m.general_benchmark_range) > 0

    # 驗證最高誠信原則說明
    assert "2D DTL" in report.truthfulness_notice
    assert "不推測未量測之球速" in report.truthfulness_notice


def test_reference_change_affects_values_deterministically():
    """2. 示範影片更換時，數值隨之改變，不得有固定寫死值；相同輸入重算保證 100% 一致。"""
    user_swing = _make_standard_user_swing(addr_tilt_x=0.45)

    ref_a = _make_standard_ref_swing(ref_id="ref-a", addr_tilt_x=0.40)
    ref_b = _make_standard_ref_swing(ref_id="ref-b", addr_tilt_x=0.32)

    rep_a1 = compute_quantitative_posture_comparison(user_swing, ref_a)
    rep_a2 = compute_quantitative_posture_comparison(user_swing, ref_a)
    rep_b = compute_quantitative_posture_comparison(user_swing, ref_b)

    # 決定性一致性 (Deterministic)
    assert rep_a1.model_dump() == rep_a2.model_dump()

    # 更換 Reference 時數值必定不同（非假固定值）
    m_a = next(m for m in rep_a1.metrics if m.id == "address_spine_tilt")
    m_b = next(m for m in rep_b.metrics if m.id == "address_spine_tilt")
    assert m_a.ref_value != m_b.ref_value
    assert m_a.delta != m_b.delta


def test_missing_reference_strict_handling():
    """3. 無示範庫或未指定示範時，回傳明確 reference_missing，絕不偷偷 fallback 到 7I。"""
    user_swing = _make_standard_user_swing()
    empty_ref = {}

    report = compute_quantitative_posture_comparison(user_swing, empty_ref)
    assert report.overall_status == "reference_missing"
    assert report.overall_reliability == "unreliable"
    assert len(report.metrics) == 0
    assert report.priority_fix_id is None
    assert "尚無" in (report.priority_fix_summary or "")


def test_missing_or_empty_pose_handling():
    """4. 示範無 Pose 或使用者缺少 keyframes 時，明確回報 insufficient_evidence，絕不塞假分數。"""
    user_swing = _make_standard_user_swing()
    ref_without_pose = _make_standard_ref_swing(has_pose=False)

    report = compute_quantitative_posture_comparison(user_swing, ref_without_pose)
    assert report.overall_status in ("insufficient_data", "ready")
    assert report.overall_reliability in ("low", "unreliable")
    assert report.priority_fix_id is None

    # 所有依賴 pose 的項目皆標記為 insufficient_evidence
    spine_metric = next(m for m in report.metrics if m.id == "address_spine_tilt")
    assert spine_metric.status == "insufficient_evidence"
    assert spine_metric.ref_value is None
    assert spine_metric.ref_value_display == "N/A"
    assert spine_metric.delta is None


def test_low_confidence_pose_handling():
    """5. 關鍵點信心度過低 (<0.35) 時，誠實標示為不可靠與無充分證據。"""
    user_low_conf = _make_standard_user_swing(vis=0.20)
    ref_swing = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_low_conf, ref_swing)
    spine_metric = next(m for m in report.metrics if m.id == "address_spine_tilt")
    assert spine_metric.status == "insufficient_evidence"
    assert spine_metric.is_comparable is False
    assert report.priority_fix_id is None


def test_slow_motion_ref_tempo_protection():
    """6. 慢動作示範影片的節奏比必須標示為慢動作不適用，不得計算假數值。"""
    user_swing = _make_standard_user_swing()
    ref_slow_mo = _make_standard_ref_swing(is_slow_mo=True)

    report = compute_quantitative_posture_comparison(user_swing, ref_slow_mo)
    tempo_metric = next(m for m in report.metrics if m.id == "swing_tempo_ratio")
    assert tempo_metric.ref_value is None
    assert "慢動作" in tempo_metric.ref_value_display
    assert tempo_metric.delta is None
    assert tempo_metric.status == "insufficient_evidence"


def test_incompatible_camera_angle_handling():
    """7. 視角不相容（非標準 DTL）時，必須標示無法比對 (not_comparable)，不推算 2D 差異。"""
    user_swing = _make_standard_user_swing()
    ref_oblique = _make_standard_ref_swing(camera_angle="rear_oblique")

    report = compute_quantitative_posture_comparison(user_swing, ref_oblique)
    assert report.overall_status == "not_comparable"
    assert report.camera_compatibility["is_compatible"] is False
    assert "視角不相容" in report.camera_compatibility["reason"]
    assert report.priority_fix_id is None

    for m in report.metrics:
        assert m.status == "not_comparable"
        assert m.is_comparable is False
        assert m.delta is None


def test_priority_fix_requires_real_evidence_no_random_drill():
    """8. 優先改善建議必須建立在真實顯著差異上；差距極小時不得隨意挑選 Drill。"""
    # 當使用者與示範姿勢完全一致時
    user_swing = _make_standard_user_swing(addr_tilt_x=0.45)
    ref_swing = _make_standard_ref_swing(addr_tilt_x=0.45)
    # 對齊 tempo 時間碼使節奏比相同 (1100 / 350)
    ref_swing["event_timestamps"] = {
        "address": 100,
        "top": 1200,
        "impact": 1550,
        "finish": 2400,
    }
    # 對齊擊球 hip 位移
    ref_swing["pose_artifact"]["landmarks"]["1550"] = _make_landmarks(sh_x=0.45, hp_x=0.58)

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)
    # 所有指標都在 optimal 範圍內
    for m in report.metrics:
        if m.is_comparable:
            assert m.status == "optimal", f"Metric {m.id} status is {m.status}"

    # 無 significant_diff 或 moderate_diff 時，priority_fix 誠實為 None
    assert report.priority_fix_id is None
    assert report.actionable_drill is None
    assert "無顯著幾何異常" in (report.priority_fix_summary or "")


def test_posture_comparison_api_endpoint():
    """9. 整合測試：驗證 GET /api/swings/{id}/posture-comparison API。"""
    from apps.api.db import SessionLocal
    from apps.api.models import User, PracticeSession, Video, SwingSegment, SwingEvent, SwingScore, PoseArtifact
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

        # 加入事件
        db.add(SwingEvent(segment_id=seg.id, event_name="address", time_ms=1200))
        db.add(SwingEvent(segment_id=seg.id, event_name="top", time_ms=2300))
        db.add(SwingEvent(segment_id=seg.id, event_name="impact_estimated", time_ms=2633))
        db.add(SwingEvent(segment_id=seg.id, event_name="finish", time_ms=3500))

        # 加入關鍵影格 PoseArtifact
        addr_lms = _make_landmarks(sh_x=0.45, hp_x=0.55)
        top_lms = _make_landmarks(sh_x=0.45, hp_x=0.55)
        imp_lms = _make_landmarks(sh_x=0.45, hp_x=0.58)
        fin_lms = _make_landmarks(sh_x=0.54, hp_x=0.55, wrist_y=0.25)

        pa = PoseArtifact(
            segment_id=seg.id,
            storage_key="test/pose.json",
            quality_metadata={"model": "mediapipe_2d"},
            keyframes_json=[
                {"time_ms": 1200, "landmarks": addr_lms, "pose_confidence": 0.95},
                {"time_ms": 2300, "landmarks": top_lms, "pose_confidence": 0.95},
                {"time_ms": 2633, "landmarks": imp_lms, "pose_confidence": 0.95},
                {"time_ms": 3500, "landmarks": fin_lms, "pose_confidence": 0.95},
            ],
        )
        db.add(pa)
        db.commit()

        target_swing_id = seg.id

    with TestClient(app) as client:
        # 測試一般比對
        res = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "metrics" in data
        assert "truthfulness_notice" in data
        assert data["user_swing_id"] == target_swing_id
        assert data["is_offline_mode"] is True

        # 測試指定不存在的球桿時，回傳 reference_missing，絕不偷偷 fallback 到 7I
        res_missing = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison?club_type=NON_EXISTENT_CLUB_XYZ",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_missing.status_code == 200
        missing_data = res_missing.json()
        assert missing_data["overall_status"] == "reference_missing"
        assert missing_data["metrics"] == []
        assert "尚無" in missing_data["priority_fix_summary"]
