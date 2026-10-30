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
    aspect_ratio: float | None = 0.5625,
    video_width: int | None = 1080,
    video_height: int | None = 1920,
    video_rotation: int = 0,
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
        "video_width": video_width,
        "video_height": video_height,
        "video_rotation": video_rotation,
        "aspect_ratio": aspect_ratio,
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
    aspect_ratio: float | None = 1.7778,
    video_width: int | None = 640,
    video_height: int | None = 360,
    video_rotation: int = 0,
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
        "video_width": video_width,
        "video_height": video_height,
        "video_rotation": video_rotation,
        "aspect_ratio": aspect_ratio,
        "event_timestamps": {
            "address": 200,
            "top": 1400,
            "impact": 1800,
            "finish": 2600,
        },
        "calibration_params": {
            "is_slow_motion": is_slow_mo,
            "events_reliable": events_reliable,
            "video_width": video_width,
            "video_height": video_height,
            "video_rotation": video_rotation,
            "aspect_ratio": aspect_ratio,
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
    # 當使用者與示範姿勢完全一致時（相同長寬比與座標）
    user_swing = _make_standard_user_swing(
        addr_tilt_x=0.45,
        aspect_ratio=0.5625,
        video_width=1080,
        video_height=1920,
    )
    ref_swing = _make_standard_ref_swing(
        addr_tilt_x=0.45,
        aspect_ratio=0.5625,
        video_width=1080,
        video_height=1920,
    )
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
            width=1080,
            height=1920,
            rotation=0,
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


# =========================================================================
# P0-B: 跨影片比例與解析度幾何不變性測試 (Aspect Ratio & Resolution Invariance)
# =========================================================================

def test_cross_aspect_ratio_invariance_portrait_vs_landscape():
    """
    10. 跨比例不變性：直式 iPhone (1080x1920, A=0.5625) 與橫式示範 (640x360, A=1.7778)。
    驗證相同的真實物理平面幾何動作（例如前傾 30°），在等比例座標系下計算出的角度一致（<0.1°），
    而若未校正 raw norm 座標計算之角度差距高達 20°~30°。
    """
    import math

    # 真實物理影像前傾角設為 30°
    target_deg = 30.0
    tan_theta = math.tan(math.radians(target_deg))  # ≈ 0.57735
    dy_norm = 0.30  # 髖部 (y=0.60) - 肩部 (y=0.30)
    dx_iso = dy_norm * tan_theta  # ≈ 0.173205

    # 1. 直式相機 (A = 1080/1920 = 0.5625)
    aspect_portrait = 0.5625
    dx_norm_portrait = dx_iso / aspect_portrait  # ≈ 0.30792
    sh_x_portrait = 0.55 - dx_norm_portrait

    # 2. 橫式相機 (A = 640/360 = 1.7778)
    aspect_landscape = 1.7778
    dx_norm_landscape = dx_iso / aspect_landscape  # ≈ 0.097427
    sh_x_landscape = 0.55 - dx_norm_landscape

    # 驗證若未校正時之巨大拉伸失真
    raw_portrait_deg = math.degrees(math.atan2(dx_norm_portrait, dy_norm))  # ≈ 45.74°
    raw_landscape_deg = math.degrees(math.atan2(dx_norm_landscape, dy_norm))  # ≈ 17.99°
    distortion_gap = abs(raw_portrait_deg - raw_landscape_deg)
    assert distortion_gap > 25.0, f"Raw norm distortion gap should be >25°, got {distortion_gap}°"

    # 建立分別具備直式與橫式長寬比的揮桿物件
    user_portrait = _make_standard_user_swing(
        addr_tilt_x=sh_x_portrait,
        aspect_ratio=aspect_portrait,
        video_width=1080,
        video_height=1920,
    )
    ref_landscape = _make_standard_ref_swing(
        addr_tilt_x=sh_x_landscape,
        aspect_ratio=aspect_landscape,
        video_width=640,
        video_height=360,
    )

    report = compute_quantitative_posture_comparison(user_portrait, ref_landscape)
    spine_m = next(m for m in report.metrics if m.id == "address_spine_tilt")

    # 經過等比例校正後，兩者前傾角皆應為 30.0°，差距小於 0.1°
    assert spine_m.user_value is not None
    assert spine_m.ref_value is not None
    assert abs(spine_m.user_value - target_deg) < 0.1, f"User angle {spine_m.user_value}° != {target_deg}°"
    assert abs(spine_m.ref_value - target_deg) < 0.1, f"Ref angle {spine_m.ref_value}° != {target_deg}°"
    assert abs(spine_m.delta) < 0.1, f"Delta {spine_m.delta}° should be near 0"


def test_resolution_scaling_invariance():
    """
    11. 尺度不變性 (Scale Invariance)：1080x1920 vs 540x960（相同長寬比 A=0.5625）。
    驗證相同 normalized landmarks 在不同解析度下，角度與軀幹百分比完全一致（0.00 誤差）。
    """
    user_high_res = _make_standard_user_swing(
        addr_tilt_x=0.45,
        video_width=1080,
        video_height=1920,
        aspect_ratio=0.5625,
    )
    user_low_res = _make_standard_user_swing(
        addr_tilt_x=0.45,
        video_width=540,
        video_height=960,
        aspect_ratio=0.5625,
    )
    ref_standard = _make_standard_ref_swing(addr_tilt_x=0.40)

    rep_high = compute_quantitative_posture_comparison(user_high_res, ref_standard)
    rep_low = compute_quantitative_posture_comparison(user_low_res, ref_standard)

    for m_hi, m_lo in zip(rep_high.metrics, rep_low.metrics):
        if m_hi.user_value is not None and m_lo.user_value is not None:
            assert m_hi.user_value == pytest.approx(m_lo.user_value, abs=1e-4)


def test_rotation_metadata_dimension_swap():
    """
    12. 旋轉 Metadata 測試：1920x1080 帶 rotation: 90 / 270 時，自動對調為 1080x1920 直式。
    """
    user_rotated = _make_standard_user_swing(
        addr_tilt_x=0.45,
        video_width=1920,
        video_height=1080,
        video_rotation=90,
        aspect_ratio=None,  # 迫使系統由 width/height/rotation 計算
    )
    ref_standard = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_rotated, ref_standard)
    geom = report.geometry_calibration

    assert geom["user_resolution"] == "1080x1920"
    assert geom["user_aspect_ratio"] == 0.5625
    assert geom["is_aspect_corrected"] is True


def test_missing_resolution_graceful_handling():
    """
    13. 缺少長寬比資訊時之優雅降級：不崩潰，標示 insufficient_evidence 與 insufficient_data。
    """
    user_no_aspect = _make_standard_user_swing(
        aspect_ratio=None,
        video_width=None,
        video_height=None,
    )
    ref_standard = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_no_aspect, ref_standard)
    assert report.overall_status == "insufficient_data"
    assert report.priority_fix_id is None
    assert "缺少影像長寬比幾何資訊" in (report.priority_fix_summary or "")

    geom = report.geometry_calibration
    assert geom["is_aspect_corrected"] is False
    assert geom["coordinate_system"] == "uncalibrated_anisotropic"

    # 幾何相關指標皆標示為 insufficient_evidence
    spine_m = next(m for m in report.metrics if m.id == "address_spine_tilt")
    assert spine_m.status == "insufficient_evidence"
    assert spine_m.delta is None


# =========================================================================
# P0-C: 時序收緊與事件邊界互斥測試 (Temporal Constraints & Evidence Tracking)
# =========================================================================

def test_top_and_impact_cannot_share_frame():
    """
    14. 時序收緊：Top 與 Impact 不得共用同一影格。
    若影片只有單一影格，不得同時被 Top 與 Impact 冒用。
    """
    user_swing = _make_standard_user_swing()
    # 破壞 keyframes，使其只有 2200ms 一個影格
    single_lms = _make_landmarks(sh_x=0.45, hp_x=0.55)
    user_swing["keyframes"] = [
        {"time_ms": 2200, "landmarks": single_lms, "pose_confidence": 0.95},
    ]

    ref_swing = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)

    # 驗證 Top 採用 2200ms，而 Impact (2550ms) 找不到獨立影格時，Impact 指標必須標記為 insufficient_evidence
    impact_m = next(m for m in report.metrics if m.id == "impact_hip_clearance")
    assert impact_m.status == "insufficient_evidence"
    assert impact_m.user_value is None
    assert impact_m.delta is None


def test_missing_event_timestamp_no_fake_offset():
    """
    15. 誠實回報：缺少 Top 或 Impact 時間碼時，絕不捏造固定時間偏移（如 +333ms），標記為無充分證據。
    """
    user_swing = _make_standard_user_swing()
    # 移除 top 事件
    user_swing["events"] = [e for e in user_swing["events"] if e["event_name"] != "top"]

    ref_swing = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)

    # 依賴 top 事件的指標應顯示缺少證據
    top_spine_m = next(m for m in report.metrics if m.id == "top_spine_retention")
    assert top_spine_m.status == "insufficient_evidence"
    assert top_spine_m.user_value is None
    assert top_spine_m.delta is None
    assert "未偵測到頂點" in top_spine_m.user_value_display or "N/A" in top_spine_m.user_value_display


def test_event_time_error_tracking():
    """
    16. 證據可信度：精確記錄選用影格時間與事件標註時間之誤差 (frame_time_error_ms)。
    """
    user_swing = _make_standard_user_swing()
    # 將 top keyframe 時間改為 2233ms（事件時間為 2200ms，誤差 33ms）
    for kf in user_swing["keyframes"]:
        if kf["time_ms"] == 2200:
            kf["time_ms"] = 2233

    ref_swing = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)
    top_spine_m = next(m for m in report.metrics if m.id == "top_spine_retention")

    assert top_spine_m.user_evidence is not None
    assert top_spine_m.user_evidence.get("frame_time_error_ms") == 33
    assert top_spine_m.user_evidence.get("frame_time_ms") == 2233
    assert top_spine_m.user_evidence.get("event_time_ms") == 2200


def test_geometry_calibration_and_truthfulness_notice_in_report():
    """
    17. 報告元資料與免責聲明：包含 geometry_calibration，且常模標記為實驗性參考區間。
    """
    user_swing = _make_standard_user_swing()
    ref_swing = _make_standard_ref_swing()

    report = compute_quantitative_posture_comparison(user_swing, ref_swing)

    # 驗證 geometry_calibration 結構
    geom = report.geometry_calibration
    assert geom["coordinate_system"] == "isotropic_height_normalized"
    assert geom["is_aspect_corrected"] is True
    assert geom["user_aspect_ratio"] == 0.5625
    assert geom["ref_aspect_ratio"] == 1.7778

    # 驗證最高誠信原則與常模標記
    assert "等比例校正" in report.truthfulness_notice
    assert "不推測未量測之球速" in report.truthfulness_notice
    for m in report.metrics:
        assert "非認證標準" in m.general_benchmark_range


# =========================================================================
# P0-A: 旋轉 Metadata 重複套用修正與 API 整合測試 (Rotation Idempotency)
# =========================================================================

def test_rotation_metadata_api_integration_no_double_swap():
    """
    18. P0-A 旋轉 Metadata 修正驗證：
    測試 API 端點在面對：
    1. 1080×1920，rotation=0
    2. 1920×1080，rotation=90
    3. 1920×1080，rotation=270
    4. 640×360，rotation=0
    5. Reference 的已校正尺寸重新傳入量化引擎。
    驗證 display dimensions 恆定，且同一物理動作在 rot=0 與 rot=90/270 下角度 100% 一致，絕不發生二次對調！
    """
    from apps.api.db import SessionLocal
    from apps.api.models import User, PracticeSession, Video, SwingSegment, SwingEvent, PoseArtifact, ReferenceSwing
    from apps.api.auth import hash_password, create_session_token

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "rot_test@example.com").first()
        if not user:
            user = User(
                email="rot_test@example.com",
                username="rot_test",
                password_hash=hash_password("Test123456!"),
                role="owner",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = create_session_token(user)

        sess = PracticeSession(
            owner_id=user.id,
            title="Rotation Integration Session",
            date="2026-10-30",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)

        # 建立 4 種不同維度的 Video
        # Case 1: 1080x1920, rot=0
        v_1080_0 = Video(
            owner_id=user.id, session_id=sess.id, original_name="v_1080_0.mp4",
            storage_key="test/v_1080_0.mp4", mime="video/mp4", ingest_status="ready",
            width=1080, height=1920, rotation=0,
        )
        # Case 2: 1920x1080, rot=90
        v_1920_90 = Video(
            owner_id=user.id, session_id=sess.id, original_name="v_1920_90.mp4",
            storage_key="test/v_1920_90.mp4", mime="video/mp4", ingest_status="ready",
            width=1920, height=1080, rotation=90,
        )
        # Case 3: 1920x1080, rot=270
        v_1920_270 = Video(
            owner_id=user.id, session_id=sess.id, original_name="v_1920_270.mp4",
            storage_key="test/v_1920_270.mp4", mime="video/mp4", ingest_status="ready",
            width=1920, height=1080, rotation=270,
        )
        # Case 4: 640x360, rot=0
        v_640_0 = Video(
            owner_id=user.id, session_id=sess.id, original_name="v_640_0.mp4",
            storage_key="test/v_640_0.mp4", mime="video/mp4", ingest_status="ready",
            width=640, height=360, rotation=0,
        )
        db.add_all([v_1080_0, v_1920_90, v_1920_270, v_640_0])
        db.commit()

        # 建立相同動作的 2D 關鍵點（站姿前傾角）
        # 在正立的顯示影像座標系中：sh_x=0.45, hp_x=0.55
        addr_lms = _make_landmarks(sh_x=0.45, hp_x=0.55)
        top_lms = _make_landmarks(sh_x=0.45, hp_x=0.55)
        imp_lms = _make_landmarks(sh_x=0.45, hp_x=0.58)
        fin_lms = _make_landmarks(sh_x=0.54, hp_x=0.55, wrist_y=0.25)
        kf_list = [
            {"time_ms": 1100, "landmarks": addr_lms, "pose_confidence": 0.95},
            {"time_ms": 2200, "landmarks": top_lms, "pose_confidence": 0.95},
            {"time_ms": 2550, "landmarks": imp_lms, "pose_confidence": 0.95},
            {"time_ms": 3400, "landmarks": fin_lms, "pose_confidence": 0.95},
        ]

        def _create_seg_with_events(video_id: str) -> str:
            s = SwingSegment(
                owner_id=user.id, video_id=video_id, start_ms=1000, end_ms=4000,
                label="valid_swing", sequence_no=1, ball_strike_status="confirmed_strike",
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            db.add(SwingEvent(segment_id=s.id, event_name="address", time_ms=1100))
            db.add(SwingEvent(segment_id=s.id, event_name="top", time_ms=2200))
            db.add(SwingEvent(segment_id=s.id, event_name="impact_estimated", time_ms=2550))
            db.add(SwingEvent(segment_id=s.id, event_name="finish", time_ms=3400))
            db.add(PoseArtifact(
                segment_id=s.id, storage_key="test/pose.json",
                quality_metadata={"model": "mediapipe_2d"}, keyframes_json=kf_list,
            ))
            db.commit()
            return s.id

        seg_1080_0 = _create_seg_with_events(v_1080_0.id)
        seg_1920_90 = _create_seg_with_events(v_1920_90.id)
        seg_1920_270 = _create_seg_with_events(v_1920_270.id)
        seg_640_0 = _create_seg_with_events(v_640_0.id)

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 驗證 Case 1: 1080x1920, rot=0 -> display: 1080x1920, aspect=0.5625
        res1 = client.get(f"/api/swings/{seg_1080_0}/posture-comparison", headers=headers)
        assert res1.status_code == 200
        data1 = res1.json()
        geom1 = data1["geometry_calibration"]
        assert geom1["user_display_width"] == 1080
        assert geom1["user_display_height"] == 1920
        assert geom1["user_display_aspect"] == 0.5625
        user_tilt1 = next(m for m in data1["metrics"] if m["id"] == "address_spine_tilt")["user_value"]

        # 驗證 Case 2: 1920x1080, rot=90 -> display: 1080x1920, aspect=0.5625 (絕不可二次對調為 1.7778)
        res2 = client.get(f"/api/swings/{seg_1920_90}/posture-comparison", headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        geom2 = data2["geometry_calibration"]
        assert geom2["user_display_width"] == 1080
        assert geom2["user_display_height"] == 1920
        assert geom2["user_display_aspect"] == 0.5625, "rot=90 被二次對調為 1.7778！"
        user_tilt2 = next(m for m in data2["metrics"] if m["id"] == "address_spine_tilt")["user_value"]

        # 驗證同一動作在 rot=0 與 rot=90 幾何角度 100% 一致 (0.00° 誤差)
        assert user_tilt1 == pytest.approx(user_tilt2, abs=1e-3)

        # 驗證 Case 3: 1920x1080, rot=270 -> display: 1080x1920, aspect=0.5625
        res3 = client.get(f"/api/swings/{seg_1920_270}/posture-comparison", headers=headers)
        assert res3.status_code == 200
        data3 = res3.json()
        geom3 = data3["geometry_calibration"]
        assert geom3["user_display_width"] == 1080
        assert geom3["user_display_height"] == 1920
        assert geom3["user_display_aspect"] == 0.5625
        user_tilt3 = next(m for m in data3["metrics"] if m["id"] == "address_spine_tilt")["user_value"]
        assert user_tilt1 == pytest.approx(user_tilt3, abs=1e-3)

        # 驗證 Case 4: 640x360, rot=0 -> display: 640x360, aspect=1.7778
        res4 = client.get(f"/api/swings/{seg_640_0}/posture-comparison", headers=headers)
        assert res4.status_code == 200
        data4 = res4.json()
        geom4 = data4["geometry_calibration"]
        assert geom4["user_display_width"] == 640
        assert geom4["user_display_height"] == 360
        assert geom4["user_display_aspect"] == 1.7778

        # 驗證 Case 5: Reference 的已校正尺寸重新傳入量化引擎 (Idempotent 測試)
        ref_reentry = {
            "id": "ref-idempotent-test",
            "club_type": "7I",
            "camera_angle": "DTL",
            "video_width": 1080,
            "video_height": 1920,
            "video_rotation": 90,  # 帶有 rotation=90 但已有校正過的寬高與 aspect_ratio
            "aspect_ratio": 0.5625,
            "is_display_dimensions": True,
            "event_timestamps": {"address": 100, "top": 1200, "impact": 1550, "finish": 2400},
            "calibration_params": {
                "video_width": 1080, "video_height": 1920, "video_rotation": 90,
                "aspect_ratio": 0.5625, "is_display_dimensions": True,
            },
            "pose_artifact": {"landmarks": {"100": addr_lms, "1200": top_lms, "1550": imp_lms, "2400": fin_lms}}
        }
        user_reentry = _make_standard_user_swing(aspect_ratio=0.5625, video_width=1080, video_height=1920)
        report_re = compute_quantitative_posture_comparison(user_reentry, ref_reentry)
        geom_re = report_re.geometry_calibration
        assert geom_re["ref_display_width"] == 1080
        assert geom_re["ref_display_height"] == 1920
        assert geom_re["ref_display_aspect"] == 0.5625, "Reference 尺寸在重入時被二次對調！"


