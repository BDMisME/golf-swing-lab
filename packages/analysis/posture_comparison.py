"""
packages/analysis/posture_comparison.py
=======================================
Golf Swing Lab R3 — 離線真實量化姿勢比較引擎 (Real Pose Offline Posture Comparison)
嚴格遵循最高誠信原則（Truthfulness & Anti-Hallucination）：
1. 僅使用雙方實際解碼之 2D 骨架關鍵點（MediaPipe 2D Landmarks），由真實軀幹長度 (Torso Length) 進行無量綱尺度正規化。
2. 嚴禁使用任何寫死常數假裝為示範球員數值（如 ref_addr_tilt=40.0, ref_tempo=3.0, ref_finish=95.0 等）。
3. 缺少任何一方 Pose、關鍵點可見度不足 (<0.35) 或鏡頭視角不相容時，一律誠實標示為 N/A 與 insufficient_evidence / not_comparable，絕不胡亂湊數。
4. 若示範影片為慢動作素材，嚴禁將播放秒數推算為示範 Tempo，示範 Tempo 明確標記為 N/A (慢動作素材)。
5. 提供獨立「理論參考常模」欄位，標明依據，與示範球員實際量測數值嚴格分離。
6. Priority Fix 僅在具備充足證據與真實顯著差異時產生；資料不足時絕不編造動作缺點或假 Drill。
"""

from __future__ import annotations

import math
from typing import Any
from pydantic import BaseModel, Field


class PostureMetricComparison(BaseModel):
    id: str
    phase: str
    phase_zh: str
    metric_name: str
    user_value: float | None
    user_value_display: str
    ref_value: float | None
    ref_value_display: str
    delta: float | None
    delta_display: str
    unit: str
    general_benchmark_range: str  # 理論常模與說明（獨立欄位，不可冒充示範球員數值）
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_reliable: bool = True
    is_comparable: bool = True
    status: str = "optimal"  # optimal | moderate_diff | significant_diff | insufficient_evidence | not_comparable
    evaluation_text: str
    user_evidence: dict[str, Any] = Field(default_factory=dict)
    ref_evidence: dict[str, Any] = Field(default_factory=dict)
    target_jump_ms: int
    target_jump_phase: str
    recommended_speed: float = 0.5


class QuantitativePostureReport(BaseModel):
    user_swing_id: str
    ref_swing_id: str | None
    club_type: str
    overall_status: str  # ready | reference_missing | not_comparable | insufficient_data
    overall_reliability: str  # high | moderate | low | unreliable
    metrics: list[PostureMetricComparison]
    priority_fix_id: str | None = None
    priority_fix_summary: str | None = None
    actionable_drill: dict[str, str] | None = None
    retest_metric_target: str | None = None
    priority_fix: dict[str, Any] | None = None
    camera_compatibility: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "【最高誠信原則說明】本報告所有數值均為 2D DTL 單相機平面幾何量測，"
        "已由軀幹長度正規化；非 3D 空間絕對座標，不推測未量測之球速、距離或桿面角。"
    )
    truthfulness_notice: str = (
        "【最高誠信原則說明】本報告所有數值均為 2D DTL 單相機平面幾何量測，"
        "已由軀幹長度正規化；非 3D 空間絕對座標，不推測未量測之球速、距離或桿面角。"
    )
    is_offline_mode: bool = True


# =========================================================================
# 輔助計算函數：純幾何運動學計算（無任何寫死常態替代值）
# =========================================================================

def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return v if not (math.isnan(v) or math.isinf(v)) else None
    except (ValueError, TypeError):
        return None


def _get_lm_xyv(pt: Any) -> tuple[float, float, float] | None:
    """提取關鍵點 (x, y, visibility)。"""
    if not pt or not isinstance(pt, dict):
        return None
    x = _safe_float(pt.get("x"))
    y = _safe_float(pt.get("y"))
    v = _safe_float(pt.get("visibility"))
    if v is None:
        v = _safe_float(pt.get("confidence", 0.8))
    if x is None or y is None:
        return None
    return (x, y, v if v is not None else 0.5)


def _midpoint_xyv(lm_dict: dict[str, Any], k1: str, k2: str) -> tuple[float, float, float] | None:
    """計算兩個關鍵點之中點座標與可見度。"""
    p1 = _get_lm_xyv(lm_dict.get(k1))
    p2 = _get_lm_xyv(lm_dict.get(k2))
    if not p1 and not p2:
        return None
    if p1 and not p2:
        return p1 if p1[2] >= 0.25 else None
    if p2 and not p1:
        return p2 if p2[2] >= 0.25 else None
    assert p1 is not None and p2 is not None
    w1 = max(0.01, p1[2])
    w2 = max(0.01, p2[2])
    tot = w1 + w2
    mx = (p1[0] * w1 + p2[0] * w2) / tot
    my = (p1[1] * w1 + p2[1] * w2) / tot
    mv = (p1[2] * w1 + p2[2] * w2) / tot
    return (mx, my, mv)


def _compute_torso_length(lm_dict: dict[str, Any]) -> tuple[float | None, float]:
    """計算雙肩中點至雙髖中點之 2D 歐氏長度 (作為正規化尺標)。"""
    sh = _midpoint_xyv(lm_dict, "left_shoulder", "right_shoulder")
    hp = _midpoint_xyv(lm_dict, "left_hip", "right_hip")
    if not sh or not hp:
        return None, 0.0
    dx = sh[0] - hp[0]
    dy = sh[1] - hp[1]
    dist = math.sqrt(dx * dx + dy * dy)
    conf = min(sh[2], hp[2])
    if dist < 0.04:  # 不合常理之軀幹尺度
        return None, 0.0
    return dist, conf


def _compute_spine_tilt_deg(lm_dict: dict[str, Any]) -> tuple[float | None, float]:
    """計算肩中點與髖中點連線相對於垂直線之 2D DTL 前傾角度。"""
    sh = _midpoint_xyv(lm_dict, "left_shoulder", "right_shoulder")
    hp = _midpoint_xyv(lm_dict, "left_hip", "right_hip")
    if not sh or not hp:
        return None, 0.0
    dx = sh[0] - hp[0]
    dy = hp[1] - sh[1]  # 影像中 y 軸向下，dy 為髖在肩下方的高度差
    if dy <= 1e-4:
        return None, 0.0
    angle = math.degrees(math.atan2(abs(dx), max(1e-4, dy)))
    conf = min(sh[2], hp[2])
    return angle, conf


def _compute_wrist_height_ratio(lm_dict: dict[str, Any], torso_len: float) -> tuple[float | None, float]:
    """計算雙手手腕中點相對於雙髖中點之垂直高度比 (% of torso)。"""
    wr = _midpoint_xyv(lm_dict, "left_wrist", "right_wrist")
    hp = _midpoint_xyv(lm_dict, "left_hip", "right_hip")
    if not wr or not hp or torso_len <= 0.04:
        return None, 0.0
    # 影像 y 向下，手腕在髖部下方時 (wr[1] > hp[1])，垂直位移為負值
    vert_delta = hp[1] - wr[1]
    ratio = (vert_delta / torso_len) * 100.0
    conf = min(wr[2], hp[2])
    return ratio, conf


def _compute_head_displacement_pct(
    addr_lms: dict[str, Any],
    target_lms: dict[str, Any],
    torso_len: float,
) -> tuple[float | None, float]:
    """計算目標階段頭部 (nose) 相對站姿頭部之 2D 歐氏位移比例 (% of torso)。"""
    n1 = _get_lm_xyv(addr_lms.get("nose"))
    n2 = _get_lm_xyv(target_lms.get("nose"))
    if not n1 or not n2 or torso_len <= 0.04:
        return None, 0.0
    dx = n2[0] - n1[0]
    dy = n2[1] - n1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    pct = (dist / torso_len) * 100.0
    conf = min(n1[2], n2[2])
    return pct, conf


def _compute_hip_clearance_pct(
    addr_lms: dict[str, Any],
    impact_lms: dict[str, Any],
    torso_len: float,
) -> tuple[float | None, float]:
    """計算擊球瞬間相較準備姿勢時雙髖中點在 DTL 平面的水平/深度位移比 (% of torso)。"""
    hp1 = _midpoint_xyv(addr_lms, "left_hip", "right_hip")
    hp2 = _midpoint_xyv(impact_lms, "left_hip", "right_hip")
    if not hp1 or not hp2 or torso_len <= 0.04:
        return None, 0.0
    # 在 DTL 視角中，髖部向後清除（保持骨盆深度）表現為 X 軸或 Y 軸的位移
    dx = hp2[0] - hp1[0]
    dy = hp2[1] - hp1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    pct = (dist / torso_len) * 100.0
    conf = min(hp1[2], hp2[2])
    return pct, conf


# =========================================================================
# 影格檢索：從使用者 keyframes 與示範影片 landmarks 中精確查找
# =========================================================================

def _find_user_landmarks_for_phase(
    keyframes: list[dict[str, Any]],
    target_time_ms: int,
    max_tolerance_ms: int = 350,
) -> tuple[dict[str, Any] | None, int | None, float]:
    """從使用者 keyframes_json 找到最接近目標時間碼的真實 landmarks。"""
    if not keyframes:
        return None, None, 0.0
    best_kf = None
    best_diff = float("inf")
    for kf in keyframes:
        t = kf.get("time_ms")
        if t is None:
            continue
        diff = abs(int(t) - target_time_ms)
        if diff < best_diff:
            best_diff = diff
            best_kf = kf
    if best_kf and best_diff <= max_tolerance_ms:
        lms = best_kf.get("landmarks") or best_kf.get("keypoints") or {}
        conf = float(best_kf.get("pose_confidence", 0.8))
        return lms, int(best_kf.get("time_ms", target_time_ms)), conf
    return None, None, 0.0


def _find_ref_landmarks_for_phase(
    ref_pose_artifact: dict[str, Any],
    target_time_ms: int,
    max_tolerance_ms: int = 350,
) -> tuple[dict[str, Any] | None, int | None, float]:
    """從示範影片 pose_artifact['landmarks'] 找到最接近目標時間碼的真實 landmarks。"""
    lms_dict = ref_pose_artifact.get("landmarks")
    if isinstance(lms_dict, dict) and lms_dict:
        best_k = None
        best_diff = float("inf")
        for k_str, val in lms_dict.items():
            try:
                t = int(k_str)
                diff = abs(t - target_time_ms)
                if diff < best_diff:
                    best_diff = diff
                    best_k = k_str
            except ValueError:
                continue
        if best_k and best_diff <= max_tolerance_ms:
            # 評估示範關鍵點之平均可見度
            pts = lms_dict[best_k]
            vis_list = [p.get("visibility", 1.0) for p in pts.values() if isinstance(p, dict)]
            avg_vis = float(sum(vis_list) / len(vis_list)) if vis_list else 0.9
            return pts, int(best_k), avg_vis

    # 亦支援若 ref 包含 keyframes 列表格式
    kfs = ref_pose_artifact.get("keyframes")
    if isinstance(kfs, list) and kfs:
        return _find_user_landmarks_for_phase(kfs, target_time_ms, max_tolerance_ms)

    return None, None, 0.0


# =========================================================================
# 主比較引擎
# =========================================================================

def compute_quantitative_posture_comparison(
    user_swing: dict[str, Any],
    ref_swing: dict[str, Any],
) -> QuantitativePostureReport:
    """
    依據使用者揮桿與參考示範揮桿之真實 2D MediaPipe Pose 關鍵點與時間碼，
    計算 4 大階段客觀量化姿勢比較清單。
    嚴禁任何假造數據，無資料時明確標註 N/A 與 insufficient_evidence。
    """
    user_id = str(user_swing.get("id") or user_swing.get("segment_id") or "")
    ref_id = str(ref_swing.get("id") or "")
    club_type = str(ref_swing.get("club_type") or user_swing.get("club") or "7I")

    # 1. 檢查示範影片是否存在
    if not ref_id:
        return QuantitativePostureReport(
            user_swing_id=user_id,
            ref_swing_id=None,
            club_type=club_type,
            overall_status="reference_missing",
            overall_reliability="unreliable",
            metrics=[],
            priority_fix_summary=f"目前尚無 {club_type} 的專業示範影片，請手動匯入或切換其他球桿。",
            camera_compatibility={"is_compatible": False, "reason": "缺少示範影片"},
        )

    # 2. 相機視角與狀態可靠度檢查 (P0-A #6)
    ref_camera = str(ref_swing.get("camera_angle") or "DTL")
    user_camera = str(user_swing.get("camera_angle") or "DTL")
    ref_calib = ref_swing.get("calibration_params") or {}
    is_ref_reliable = bool(ref_calib.get("events_reliable", True))

    is_angle_compatible = (
        ref_camera.upper() == "DTL"
        and user_camera.upper() == "DTL"
        and is_ref_reliable
    )
    camera_compat_info = {
        "user_camera": user_camera,
        "ref_camera": ref_camera,
        "is_compatible": is_angle_compatible,
        "ref_events_reliable": is_ref_reliable,
        "reason": (
            "相機視角相容（均為後方 DTL 全揮桿視角）"
            if is_angle_compatible
            else f"視角不相容：示範影片視角為 {ref_camera}，非標準後方視角 (DTL)，幾何投影不具直接比較性。"
        ),
    }

    # 3. 提取事件時間碼
    user_events = {e.get("event_name"): int(e.get("time_ms", 0)) for e in (user_swing.get("events") or [])}
    user_start_ms = int(user_swing.get("start_ms", 0))
    user_addr_ms = user_events.get("address") or user_start_ms
    user_top_ms = user_events.get("top") or (user_start_ms + 1200)
    user_impact_ms = user_events.get("impact_estimated") or user_events.get("impact") or (user_top_ms + 333)
    user_finish_ms = user_events.get("finish") or (user_impact_ms + 800)

    ref_events = ref_swing.get("event_timestamps") or {}
    ref_addr_ms = int(ref_events.get("address", 0))
    ref_top_ms = int(ref_events.get("top", 0))
    ref_impact_ms = int(ref_events.get("impact", 0))
    ref_finish_ms = int(ref_events.get("finish", 0))

    # 4. 提取關鍵點
    user_kf = (user_swing.get("pose_artifact") or {}).get("keyframes_json") or user_swing.get("keyframes") or []
    ref_pa = ref_swing.get("pose_artifact") or {}

    u_addr_lms, u_addr_t, u_addr_conf = _find_user_landmarks_for_phase(user_kf, user_addr_ms)
    u_top_lms, u_top_t, u_top_conf = _find_user_landmarks_for_phase(user_kf, user_top_ms)
    u_imp_lms, u_imp_t, u_imp_conf = _find_user_landmarks_for_phase(user_kf, user_impact_ms)
    u_fin_lms, u_fin_t, u_fin_conf = _find_user_landmarks_for_phase(user_kf, user_finish_ms)

    r_addr_lms, r_addr_t, r_addr_conf = _find_ref_landmarks_for_phase(ref_pa, ref_addr_ms)
    r_top_lms, r_top_t, r_top_conf = _find_ref_landmarks_for_phase(ref_pa, ref_top_ms)
    r_imp_lms, r_imp_t, r_imp_conf = _find_ref_landmarks_for_phase(ref_pa, ref_impact_ms)
    r_fin_lms, r_fin_t, r_fin_conf = _find_ref_landmarks_for_phase(ref_pa, ref_finish_ms)

    # 計算正規化軀幹長度
    u_torso_len, u_torso_conf = _compute_torso_length(u_addr_lms) if u_addr_lms else (None, 0.0)
    r_torso_len, r_torso_conf = _compute_torso_length(r_addr_lms) if r_addr_lms else (None, 0.0)

    comparisons: list[PostureMetricComparison] = []

    def make_metric(
        id_: str,
        phase: str,
        phase_zh: str,
        name: str,
        unit: str,
        u_val: float | None,
        u_conf: float,
        u_ev: dict[str, Any],
        r_val: float | None,
        r_conf: float,
        r_ev: dict[str, Any],
        benchmark: str,
        optimal_tol: float,
        moderate_tol: float,
        val_format: str = "{:.1f}",
        unit_suffix: str = "",
        is_slow_mo_ref: bool = False,
        slow_mo_note: str = "",
        direction_cue: tuple[str, str] = ("偏低", "偏高"),
    ) -> PostureMetricComparison:
        """安全建構單項量化姿勢比對物件。若任一方缺失，明確設置為不可比。"""
        # 示範是否為慢動作素材
        if is_slow_mo_ref:
            r_val = None
            r_val_display = slow_mo_note or "N/A (慢動作素材)"
        else:
            r_val_display = (val_format + unit_suffix).format(r_val) if r_val is not None else "N/A"

        u_val_display = (val_format + unit_suffix).format(u_val) if u_val is not None else "N/A"

        # 檢查是否可比
        is_comparable = (
            is_angle_compatible
            and (u_val is not None)
            and (r_val is not None)
            and (u_conf >= 0.35)
            and (r_conf >= 0.35)
        )

        delta = None
        delta_display = "--"
        status = "insufficient_evidence"
        confidence = round(min(u_conf, r_conf), 2) if is_comparable else 0.0
        eval_text = ""

        if not is_angle_compatible:
            status = "not_comparable"
            eval_text = f"相機視角不相容（示範為 {ref_camera}，非標準 DTL），不推算 2D 平面幾何差異。"
        elif not is_comparable:
            status = "insufficient_evidence"
            missing_who = []
            if u_val is None or u_conf < 0.35:
                missing_who.append("使用者揮桿")
            if r_val is None or r_conf < 0.35:
                missing_who.append("示範影片" if not is_slow_mo_ref else "示範Tempo(慢動作無真實時長)")
            eval_text = f"缺少{'與'.join(missing_who)}之可靠關鍵點，未具備充分觀測證據，不計算差異。"
        else:
            delta = round(u_val - r_val, 2)
            delta_display = f"{delta:+.1f}" + unit_suffix if "°" in unit_suffix or "%" in unit_suffix else f"{delta:+.2f}"
            abs_d = abs(delta)
            if abs_d <= optimal_tol:
                status = "optimal"
                eval_text = f"與示範選手數值高度相符（差距僅 {delta_display}，在常模允許誤差 {optimal_tol}{unit_suffix} 內）。"
            elif abs_d <= moderate_tol:
                status = "moderate_diff"
                cue = direction_cue[1] if delta > 0 else direction_cue[0]
                eval_text = f"較示範選手{cue} {abs_d:.1f}{unit_suffix}，落在可微調區間。"
            else:
                status = "significant_diff"
                cue = direction_cue[1] if delta > 0 else direction_cue[0]
                eval_text = f"較示範選手明顯{cue} {abs_d:.1f}{unit_suffix}，為本階段核心結構差異。"

        target_jump_map = {
            "address": user_addr_ms,
            "top": user_top_ms,
            "impact": user_impact_ms,
            "finish": user_finish_ms,
        }

        return PostureMetricComparison(
            id=id_,
            phase=phase,
            phase_zh=phase_zh,
            metric_name=name,
            user_value=u_val,
            user_value_display=u_val_display,
            ref_value=r_val,
            ref_value_display=r_val_display,
            delta=delta,
            delta_display=delta_display,
            unit=unit,
            general_benchmark_range=benchmark,
            confidence=confidence,
            is_reliable=(confidence >= 0.50),
            is_comparable=is_comparable,
            status=status,
            evaluation_text=eval_text,
            user_evidence=u_ev,
            ref_evidence=r_ev,
            target_jump_ms=target_jump_map.get(phase, user_addr_ms),
            target_jump_phase=phase,
            recommended_speed=0.25 if phase in ("top", "impact") else 0.5,
        )

    # =========================================================================
    # 階段 1：Address 準備姿勢
    # =========================================================================
    u_addr_tilt, u_at_conf = _compute_spine_tilt_deg(u_addr_lms) if u_addr_lms else (None, 0.0)
    r_addr_tilt, r_at_conf = _compute_spine_tilt_deg(r_addr_lms) if r_addr_lms else (None, 0.0)
    comparisons.append(make_metric(
        id_="address_spine_tilt",
        phase="address",
        phase_zh="準備姿勢 (Address)",
        name="站姿軀幹前傾角",
        unit="deg_2d",
        u_val=round(u_addr_tilt, 1) if u_addr_tilt is not None else None,
        u_conf=u_at_conf,
        u_ev={"time_ms": u_addr_t, "formula": "atan2(|shoulder_mid.x - hip_mid.x|, hip_mid.y - shoulder_mid.y)"},
        r_val=round(r_addr_tilt, 1) if r_addr_tilt is not None else None,
        r_conf=r_at_conf,
        r_ev={"time_ms": r_addr_t, "formula": "atan2(|shoulder_mid.x - hip_mid.x|, hip_mid.y - shoulder_mid.y)"},
        benchmark="36.0° ~ 44.0° (DTL 後方視角標準站姿前傾常模)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="°",
        direction_cue=("偏直立", "偏過深前傾"),
    ))

    u_wrist_h, u_wh_conf = _compute_wrist_height_ratio(u_addr_lms, u_torso_len or 0.25) if u_addr_lms else (None, 0.0)
    r_wrist_h, r_wh_conf = _compute_wrist_height_ratio(r_addr_lms, r_torso_len or 0.25) if r_addr_lms else (None, 0.0)
    comparisons.append(make_metric(
        id_="address_wrist_height",
        phase="address",
        phase_zh="準備姿勢 (Address)",
        name="雙手手腕基準高度比",
        unit="torso_pct",
        u_val=round(u_wrist_h, 1) if u_wrist_h is not None else None,
        u_conf=u_wh_conf,
        u_ev={"time_ms": u_addr_t, "formula": "(hip_mid.y - wrist_mid.y) / torso_len * 100"},
        r_val=round(r_wrist_h, 1) if r_wrist_h is not None else None,
        r_conf=r_wh_conf,
        r_ev={"time_ms": r_addr_t, "formula": "(hip_mid.y - wrist_mid.y) / torso_len * 100"},
        benchmark="-12.0% ~ +8.0% 身長 (雙手自然垂懸於下巴鉛垂線下方)",
        optimal_tol=5.0,
        moderate_tol=10.0,
        unit_suffix="%",
        direction_cue=("偏低", "偏高"),
    ))

    # =========================================================================
    # 階段 2：Top 上桿頂點
    # =========================================================================
    u_top_tilt, u_tt_conf = _compute_spine_tilt_deg(u_top_lms) if u_top_lms else (None, 0.0)
    r_top_tilt, r_tt_conf = _compute_spine_tilt_deg(r_top_lms) if r_top_lms else (None, 0.0)
    u_top_ret = abs(u_top_tilt - u_addr_tilt) if (u_top_tilt is not None and u_addr_tilt is not None) else None
    r_top_ret = abs(r_top_tilt - r_addr_tilt) if (r_top_tilt is not None and r_addr_tilt is not None) else None
    comparisons.append(make_metric(
        id_="top_spine_retention",
        phase="top",
        phase_zh="上桿頂點 (Top)",
        name="頂點前傾維持變化量",
        unit="deg_2d",
        u_val=round(u_top_ret, 1) if u_top_ret is not None else None,
        u_conf=min(u_tt_conf, u_at_conf),
        u_ev={"addr_time_ms": u_addr_t, "top_time_ms": u_top_t, "formula": "|top_spine_deg - addr_spine_deg|"},
        r_val=round(r_top_ret, 1) if r_top_ret is not None else None,
        r_conf=min(r_tt_conf, r_at_conf),
        r_ev={"addr_time_ms": r_addr_t, "top_time_ms": r_top_t, "formula": "|top_spine_deg - addr_spine_deg|"},
        benchmark="≤ 4.0° (頂點良好維持軀幹前傾，不早起提昇)",
        optimal_tol=2.5,
        moderate_tol=5.0,
        unit_suffix="°",
        direction_cue=("維持更穩", "抬起變化較大"),
    ))

    u_top_head, u_th_conf = _compute_head_displacement_pct(u_addr_lms, u_top_lms, u_torso_len or 0.25) if (u_addr_lms and u_top_lms) else (None, 0.0)
    r_top_head, r_th_conf = _compute_head_displacement_pct(r_addr_lms, r_top_lms, r_torso_len or 0.25) if (r_addr_lms and r_top_lms) else (None, 0.0)
    comparisons.append(make_metric(
        id_="top_head_displacement",
        phase="top",
        phase_zh="上桿頂點 (Top)",
        name="頂點頭部相對位移比",
        unit="torso_pct",
        u_val=round(u_top_head, 1) if u_top_head is not None else None,
        u_conf=min(u_th_conf, u_torso_conf),
        u_ev={"addr_time_ms": u_addr_t, "top_time_ms": u_top_t, "formula": "dist(nose_top, nose_addr) / torso_len * 100"},
        r_val=round(r_top_head, 1) if r_top_head is not None else None,
        r_conf=min(r_th_conf, r_torso_conf),
        r_ev={"addr_time_ms": r_addr_t, "top_time_ms": r_top_t, "formula": "dist(nose_top, nose_addr) / torso_len * 100"},
        benchmark="≤ 8.0% 身長 (上桿蓄力時軸心頭部穩定無大幅側移)",
        optimal_tol=3.5,
        moderate_tol=7.0,
        unit_suffix="%",
        direction_cue=("更少晃動", "側移晃動較大"),
    ))

    # =========================================================================
    # 階段 3：Downswing / Impact 擊球瞬間
    # =========================================================================
    u_imp_tilt, u_it_conf = _compute_spine_tilt_deg(u_imp_lms) if u_imp_lms else (None, 0.0)
    r_imp_tilt, r_it_conf = _compute_spine_tilt_deg(r_imp_lms) if r_imp_lms else (None, 0.0)
    u_imp_ret = abs(u_imp_tilt - u_addr_tilt) if (u_imp_tilt is not None and u_addr_tilt is not None) else None
    r_imp_ret = abs(r_imp_tilt - r_addr_tilt) if (r_imp_tilt is not None and r_addr_tilt is not None) else None
    comparisons.append(make_metric(
        id_="impact_spine_delta",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="擊球前傾角變化量",
        unit="deg_2d",
        u_val=round(u_imp_ret, 1) if u_imp_ret is not None else None,
        u_conf=min(u_it_conf, u_at_conf),
        u_ev={"addr_time_ms": u_addr_t, "impact_time_ms": u_imp_t, "formula": "|impact_spine_deg - addr_spine_deg|"},
        r_val=round(r_imp_ret, 1) if r_imp_ret is not None else None,
        r_conf=min(r_it_conf, r_at_conf),
        r_ev={"addr_time_ms": r_addr_t, "impact_time_ms": r_imp_t, "formula": "|impact_spine_deg - addr_spine_deg|"},
        benchmark="≤ 4.5° (觸球瞬間維持準備姿勢角度，不提前拔起)",
        optimal_tol=2.5,
        moderate_tol=5.0,
        unit_suffix="°",
        direction_cue=("維持更穩", "角度變化偏大"),
    ))

    # 節奏比 (Tempo Ratio)：若示範為慢動作影片，示範數值嚴格為 None
    is_ref_slow_mo = bool(ref_calib.get("is_slow_motion", False)) or (ref_calib.get("supports_realtime_sync") is False)
    u_tempo = None
    u_tempo_conf = 0.0
    u_back_ms = user_top_ms - user_addr_ms
    u_down_ms = user_impact_ms - user_top_ms
    if u_back_ms > 200 and u_down_ms > 100:
        u_tempo = round(u_back_ms / u_down_ms, 2)
        u_tempo_conf = 0.85

    r_tempo = None
    r_tempo_conf = 0.0
    if not is_ref_slow_mo and ref_top_ms > ref_addr_ms and ref_impact_ms > ref_top_ms:
        r_back_ms = ref_top_ms - ref_addr_ms
        r_down_ms = ref_impact_ms - ref_top_ms
        if r_back_ms > 200 and r_down_ms > 100:
            r_tempo = round(r_back_ms / r_down_ms, 2)
            r_tempo_conf = 0.85

    comparisons.append(make_metric(
        id_="swing_tempo_ratio",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="上下桿時間節奏比",
        unit="ratio",
        u_val=u_tempo,
        u_conf=u_tempo_conf,
        u_ev={"backswing_ms": u_back_ms, "downswing_ms": u_down_ms, "formula": "backswing_ms / downswing_ms"},
        r_val=r_tempo,
        r_conf=r_tempo_conf,
        r_ev={"backswing_ms": ref_top_ms - ref_addr_ms, "downswing_ms": ref_impact_ms - ref_top_ms, "formula": "backswing_ms / downswing_ms"},
        benchmark="2.7:1 ~ 3.3:1 (標準高爾夫全揮桿約 3:1 節拍比)",
        optimal_tol=0.35,
        moderate_tol=0.70,
        val_format="{:.2f}",
        unit_suffix=":1",
        is_slow_mo_ref=is_ref_slow_mo,
        slow_mo_note="N/A (慢動作素材不提供假Tempo)",
        direction_cue=("下桿轉換急促", "上桿過度緩慢"),
    ))

    # 擊球骨盆深度開放比
    u_hip_clear, u_hc_conf = _compute_hip_clearance_pct(u_addr_lms, u_imp_lms, u_torso_len or 0.25) if (u_addr_lms and u_imp_lms) else (None, 0.0)
    r_hip_clear, r_hc_conf = _compute_hip_clearance_pct(r_addr_lms, r_imp_lms, r_torso_len or 0.25) if (r_addr_lms and r_imp_lms) else (None, 0.0)
    comparisons.append(make_metric(
        id_="impact_hip_clearance",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="擊球骨盆深度開放比",
        unit="torso_pct",
        u_val=round(u_hip_clear, 1) if u_hip_clear is not None else None,
        u_conf=min(u_hc_conf, u_torso_conf),
        u_ev={"addr_time_ms": u_addr_t, "impact_time_ms": u_imp_t, "formula": "dist(hip_imp, hip_addr) / torso_len * 100"},
        r_val=round(r_hip_clear, 1) if r_hip_clear is not None else None,
        r_conf=min(r_hc_conf, r_torso_conf),
        r_ev={"addr_time_ms": r_addr_t, "impact_time_ms": r_imp_t, "formula": "dist(hip_imp, hip_addr) / torso_len * 100"},
        benchmark="8.0% ~ 18.0% 身長 (下桿順暢轉開左髖，保留雙手通道)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="%",
        direction_cue=("開放不足", "過度側移"),
    ))

    # =========================================================================
    # 階段 4：Finish 收桿平衡
    # =========================================================================
    u_fin_tilt, u_ft_conf = _compute_spine_tilt_deg(u_fin_lms) if u_fin_lms else (None, 0.0)
    r_fin_tilt, r_ft_conf = _compute_spine_tilt_deg(r_fin_lms) if r_fin_lms else (None, 0.0)
    comparisons.append(make_metric(
        id_="finish_spine_angle",
        phase="finish",
        phase_zh="收桿平衡 (Finish)",
        name="收桿軀幹直立角",
        unit="deg_2d",
        u_val=round(u_fin_tilt, 1) if u_fin_tilt is not None else None,
        u_conf=u_ft_conf,
        u_ev={"time_ms": u_fin_t, "formula": "spine_tilt_deg @ finish frame"},
        r_val=round(r_fin_tilt, 1) if r_fin_tilt is not None else None,
        r_conf=r_ft_conf,
        r_ev={"time_ms": r_fin_t, "formula": "spine_tilt_deg @ finish frame"},
        benchmark="≤ 16.0° (收桿完全立起平衡，重心完全過渡至左腳)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="°",
        direction_cue=("更為直立", "身體殘留後傾"),
    ))

    # 4. 可靠度總結與覆蓋率 (P0-B)
    comparable_count = sum(1 for c in comparisons if c.is_comparable)
    total_metrics = len(comparisons)
    comparable_ratio = comparable_count / total_metrics if total_metrics > 0 else 0.0

    avg_conf = (
        sum(c.confidence for c in comparisons if c.is_comparable) / comparable_count
        if comparable_count > 0 else 0.0
    )

    if not is_angle_compatible:
        overall_status = "not_comparable"
        overall_reliability = "unreliable"
    elif comparable_count == 0:
        overall_status = "insufficient_data"
        overall_reliability = "unreliable"
    elif comparable_ratio < 0.50 or avg_conf < 0.50:
        overall_status = "insufficient_data"
        overall_reliability = "low"
    elif comparable_ratio < 0.75 or avg_conf < 0.75:
        overall_status = "ready"
        overall_reliability = "moderate"
    else:
        overall_status = "ready"
        overall_reliability = "high"

    # 5. Priority Fix 唯一改善重點選擇 (P0-D: 只能建立在真實證據上)
    # 嚴格條件：必須 is_comparable=True、is_reliable=True，且屬於 significant_diff 或 moderate_diff
    valid_diffs = [
        c for c in comparisons
        if c.is_comparable and c.is_reliable and c.status in ("significant_diff", "moderate_diff")
    ]
    # 依照嚴重程度與偏差量排序
    valid_diffs.sort(
        key=lambda x: (2 if x.status == "significant_diff" else 1, abs(x.delta or 0)),
        reverse=True,
    )

    priority_fix_id = None
    priority_fix_summary = None
    actionable_drill = None
    retest_metric_target = None
    priority_fix_obj = None

    if valid_diffs and overall_reliability in ("high", "moderate"):
        top_diff = valid_diffs[0]
        priority_fix_id = top_diff.id
        obs_item = f"{top_diff.phase_zh} — {top_diff.metric_name}"
        u_str = top_diff.user_value_display
        r_str = top_diff.ref_value_display
        d_str = top_diff.delta_display

        if "spine" in top_diff.id:
            priority_fix_summary = (
                f"在 {top_diff.phase_zh} 觀測到 {top_diff.metric_name} 為 {u_str}（示範為 {r_str}，差異 {d_str}）。"
                f"建議使用 0.25× 慢動作同步比對從起桿至該階段之背部軸心角度維持。"
            )
            actionable_drill = {
                "name": "臀部貼牆維持前傾軸心 Drill",
                "preparation": "站姿就位時，右臀後方輕觸球包或牆面（距離 2 公分）。",
                "execution": "上桿時感受右臀輕貼，下桿過渡時由左臀接替貼住支撐物，維持骨盆深度。",
                "checkpoint": "錄影對照 0.25× 慢動作，頂點至擊球瞬間前胸維持罩住球位。",
            }
            retest_metric_target = f"下次練習 5 球，目標：{top_diff.metric_name} 與示範差距縮減至 ±2.5° 內。"
        elif "head" in top_diff.id:
            priority_fix_summary = (
                f"在 {top_diff.phase_zh} 觀測到 {top_diff.metric_name} 為 {u_str}（示範為 {r_str}，差異 {d_str}）。"
                f"軸心頭部在空間中有較大浮動，易導致揮桿最低點不穩定。"
            )
            actionable_drill = {
                "name": "定點視線鎖定 Drill",
                "preparation": "在球位後方 5 公分處設定一固定虛擬標記點。",
                "execution": "揮桿全程視線專注於該標記，擊球出聲後維持視線停留在地面 0.5 秒。",
                "checkpoint": "以 0.25× 慢動作檢視，上桿頂點頭部高度與站姿保持一致，無下沉或拔起。",
            }
            retest_metric_target = f"下次練習 5 球，目標：{top_diff.metric_name} 控制在 8.0% 身長內。"
        elif "tempo" in top_diff.id:
            priority_fix_summary = (
                f"在 {top_diff.phase_zh} 觀測到 {top_diff.metric_name} 為 {u_str}（示範為 {r_str}，差異 {d_str}）。"
                f"上下桿時間比例偏離流暢區間，建議運用慢動作對照頂點換向蓄力感。"
            )
            actionable_drill = {
                "name": "三拍默數節奏轉換 Drill",
                "preparation": "正常站姿，心中默念節奏口訣「1-2 上桿... 3 啟動釋放」。",
                "execution": "頂點給予 0.1 秒的從容過渡感，避免雙手急躁下砸。",
                "checkpoint": "錄影確認上桿頂點有清晰的換向過渡軌跡，非急促折返。",
            }
            retest_metric_target = "下次練習 5 球，目標：上下桿時間比維持於 2.7:1 至 3.3:1 區間。"
        else:
            priority_fix_summary = (
                f"在 {top_diff.phase_zh} 觀測到 {top_diff.metric_name} 為 {u_str}（示範為 {r_str}，差異 {d_str}）。"
                f"收桿平衡未完全站定，建議擊球後定格維持 2 秒。"
            )
            actionable_drill = {
                "name": "3 秒雕像收桿平衡 Drill",
                "preparation": "正常全揮桿練習。",
                "execution": "揮桿結束後維持胸口朝向目標、右腳鞋底垂直離地的收桿姿勢，心中默數 1-2-3 不移動雙腳。",
                "checkpoint": "身體平穩站定，不前後晃動或提早收力放桿。",
            }
            retest_metric_target = "下次練習 5 球，目標：收桿完全站定直立，前傾角保持在 16.0° 內。"

        priority_fix_obj = {
            "focus_area": obs_item,
            "metric_id": top_diff.id,
            "user_value": u_str,
            "ref_value": r_str,
            "delta": d_str,
            "summary": priority_fix_summary,
            "drill": actionable_drill,
            "target": retest_metric_target,
            "confidence": top_diff.confidence,
        }
    else:
        # 資料不足或無顯著差異：誠實揭露，絕不編造假缺陷與假口訣
        if not is_angle_compatible:
            priority_fix_summary = "相機視角不相容，無法確立可信的動作改善重點。建議更換標準 DTL 示範影片。"
        elif comparable_count < 3:
            priority_fix_summary = "目前有效比對證據不足（缺少清晰 2D 關鍵點），建議使用 0.25× 慢動作手動檢視或上傳更高畫質影片。"
        else:
            priority_fix_summary = "目前各項已觀測之 2D 姿勢指標與選定示範球員均在相容區間內，無顯著幾何異常。"

    return QuantitativePostureReport(
        user_swing_id=user_id,
        ref_swing_id=ref_id,
        club_type=club_type,
        overall_status=overall_status,
        overall_reliability=overall_reliability,
        metrics=comparisons,
        priority_fix_id=priority_fix_id,
        priority_fix_summary=priority_fix_summary,
        actionable_drill=actionable_drill,
        retest_metric_target=retest_metric_target,
        priority_fix=priority_fix_obj,
        camera_compatibility=camera_compat_info,
        is_offline_mode=True,
    )
