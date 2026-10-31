"""
packages/analysis/posture_comparison.py
=======================================
Golf Swing Lab R3 — 離線真實量化姿勢比較引擎 (Real Pose Offline Posture Comparison)
恪守最高誠信原則（Truthfulness & Anti-Hallucination）：
1. 影像座標等比例長寬比校正（Isotropic Aspect Ratio Correction）：
   - MediaPipe / YOLO 歸一化座標 x_norm, y_norm 分別被影像寬度與高度正規化至 [0, 1]。
   - 若直接計算 atan2(abs(dx), dy)，在直式 (9:16) 與橫式 (16:9) 影片間會產生高達 20°~30° 的人為拉伸失真。
   - 本引擎將所有座標轉換至以高度為尺標的等比例 2D 平面座標系：
     x_iso = x_norm * (Display_Width / Display_Height) = x_norm * aspect_ratio
     y_iso = y_norm
     所有角度 atan2(abs(dx_iso), dy_iso)、歐氏距離與軀幹長度均在該物理等比例座標系下計算。
2. 嚴格收緊事件關鍵影格邊界約束：
   - Address、Top、Impact、Finish 各自擁有獨立事件證據與時間碼，嚴禁使用固定偏移 (+1200ms, +333ms) 捏造事件。
   - Top 絕對不可使用 Impact 影格冒充；Impact 亦不可使用 Top 影格冒充。
   - 精確追蹤影格選用時間與事件標註時間之誤差 (frame_time_error_ms)。
3. 嚴禁寫死常數：
   - 示範球員數值 (ref_value) 100% 來自示範影片真實骨架；缺少或不足時誠實輸出 None / N/A。
   - 理論常模獨立標明為「實驗性參考區間（非專業認證標準）」，不冒充專業認證真理。
4. 示範慢動作素材保護：
   - 慢動作示範影片嚴禁推算假 Tempo，明確標示為 N/A (慢動作素材不提供假Tempo)。
5. 視角與幾何相容性檢查：
   - 非標準 DTL 視角標記 not_comparable；缺少寬高比資訊時標記 insufficient_evidence。
   - Priority Fix 唯有在幾何相容、長寬比校正齊全且具實質顯著差異時方可產出，無異常時誠實回報無顯著差異。
"""

from __future__ import annotations

import math
from typing import Any
from pydantic import BaseModel, Field


class PostureMetricComparison(BaseModel):
    id: str
    phase: str
    phase_zh: str = ""
    metric_name: str = ""
    name_zh: str | None = None
    observation: str | None = None
    user_value: float | None = None
    user_value_display: str = ""
    ref_value: float | None = None
    ref_value_display: str = ""
    delta: float | None = None
    delta_display: str = ""
    unit: str = ""
    general_benchmark_range: str = ""  # 實驗性參考區間（獨立欄位，不可冒充示範球員數值）
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_reliable: bool = True
    is_comparable: bool = True
    status: str = "optimal"  # optimal | moderate_diff | significant_diff | insufficient_evidence | not_comparable
    evaluation_text: str = ""
    optimal_tol: float = 0.0
    moderate_tol: float = 0.0
    geometry_coord_system: str = "isotropic_height_normalized"
    event_accuracy_ms: int | None = None
    user_evidence: dict[str, Any] = Field(default_factory=dict)
    ref_evidence: dict[str, Any] = Field(default_factory=dict)
    relative_status: str = "aligned"  # aligned | moderate_diff | significant_diff | smaller_than_ref | larger_than_ref
    benchmark_status: str = "unassessed"  # within_benchmark | outside_benchmark | not_applicable
    target_jump_ms: int = 0
    target_jump_phase: str = ""
    recommended_speed: float = 0.5


class PriorityFixItem(BaseModel):
    focus_area: str
    metric_id: str
    user_value: str
    ref_value: str
    delta: str
    summary: str
    drill: dict[str, str] | None = None
    target: str | None = None
    confidence: float = 0.0

    @property
    def actionable_drill(self) -> dict[str, str] | None:
        return self.drill

    @property
    def issue_title(self) -> str:
        return self.focus_area


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
    priority_fix: PriorityFixItem | dict[str, Any] | None = None
    camera_compatibility: dict[str, Any] = Field(default_factory=dict)
    geometry_calibration: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "【最高誠信原則說明】本報告所有數值均為 2D DTL 單相機平面幾何量測，"
        "已由畫面長寬比等比例校正（Isotropic Aspect Ratio Correction）並由受測者軀幹長度正規化；"
        "非 3D 空間絕對座標，不推測未量測之球速、距離或桿面角。長寬比校正僅消除影像像素縮放失真，"
        "不消除相機放置高度、透視視角或鏡頭畸變差異。"
    )
    truthfulness_notice: str = (
        "【最高誠信原則說明】本報告所有數值均為 2D DTL 單相機平面幾何量測，"
        "已由畫面長寬比等比例校正（Isotropic Aspect Ratio Correction）並由受測者軀幹長度正規化；"
        "非 3D 空間絕對座標，不推測未量測之球速、距離或桿面角。長寬比校正僅消除影像像素縮放失真，"
        "不消除相機放置高度、透視視角或鏡頭畸變差異。"
    )
    is_offline_mode: bool = True


# =========================================================================
# 輔助計算函數：純幾何運動學計算與等比例座標轉換
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


def _extract_display_dimensions_and_aspect(
    swing: dict[str, Any],
) -> tuple[int | None, int | None, float | None]:
    """
    從揮桿資料字典提取影像顯示寬高與長寬比 (Aspect Ratio = Display Width / Display Height)。
    統一資料契約：
    1. 若已提供 display_width / display_height，或標註 is_display_dimensions=True，直接採納。
    2. 若已提供 aspect_ratio 且與現有 (w / h) 相符，直接採納，嚴禁因 rotation 重複交換。
    3. 若僅提供原始編碼尺寸 (coded_width, coded_height) 或未校正之尺寸，才依據 rotation (90°/270°) 交換一次。
    """
    if not isinstance(swing, dict):
        return None, None, None

    calib = swing.get("calibration_params") or {}
    q_meta = swing.get("quality_metadata") or {}
    vid_meta = swing.get("video") or {}

    # 1. 檢查是否有已明確宣告的 display 尺寸
    disp_w = _safe_float(swing.get("display_width") or calib.get("display_width"))
    disp_h = _safe_float(swing.get("display_height") or calib.get("display_height"))
    disp_aspect = _safe_float(
        swing.get("display_aspect_ratio")
        or swing.get("aspect_ratio")
        or calib.get("display_aspect_ratio")
        or calib.get("aspect_ratio")
    )

    if disp_w and disp_h and disp_w > 0 and disp_h > 0:
        w_int = int(round(disp_w))
        h_int = int(round(disp_h))
        aspect = disp_aspect or round(w_int / h_int, 4)
        return w_int, h_int, aspect

    # 2. 檢查是否標註為已套用旋轉之顯示尺寸 (is_display_dimensions)
    is_already_display = bool(
        swing.get("is_display_dimensions")
        or calib.get("is_display_dimensions")
        or calib.get("is_aspect_corrected")
    )

    # 3. 提取一般寬高與旋轉
    coded_w = _safe_float(swing.get("coded_width") or vid_meta.get("width"))
    coded_h = _safe_float(swing.get("coded_height") or vid_meta.get("height"))

    w = (
        coded_w
        or _safe_float(swing.get("video_width"))
        or _safe_float(calib.get("video_width"))
        or _safe_float(q_meta.get("video_width"))
    )
    h = (
        coded_h
        or _safe_float(swing.get("video_height"))
        or _safe_float(calib.get("video_height"))
        or _safe_float(q_meta.get("video_height"))
    )
    rot = (
        _safe_float(swing.get("video_rotation"))
        or _safe_float(calib.get("video_rotation"))
        or _safe_float(vid_meta.get("rotation"))
        or 0.0
    )

    if w and h and w > 0 and h > 0:
        w_int = int(round(w))
        h_int = int(round(h))
        rot_int = int(round(rot))

        # 若已標註為 display dimensions，絕不重複交換
        if is_already_display:
            aspect = disp_aspect or round(w_int / h_int, 4)
            return w_int, h_int, aspect

        # 若已提供 aspect_ratio，且現有 (w_int / h_int) 已經與 aspect_ratio 吻合（誤差 < 0.01）
        # 說明此寬高已經是顯示尺寸，絕不能再交換！
        if disp_aspect and disp_aspect > 0:
            current_ratio = w_int / h_int
            if abs(current_ratio - disp_aspect) < 0.01:
                return w_int, h_int, round(disp_aspect, 4)
            swapped_ratio = h_int / w_int
            if abs(swapped_ratio - disp_aspect) < 0.01:
                return h_int, w_int, round(disp_aspect, 4)

        # 未標示且無明確長寬比對齊時，依 rotation (90/270) 執行一次旋轉校正
        if rot_int in (90, 270, -90, -270):
            w_int, h_int = h_int, w_int

        aspect = round(w_int / h_int, 4)
        return w_int, h_int, aspect

    if disp_aspect and disp_aspect > 0:
        return None, None, round(disp_aspect, 4)

    return None, None, None


def _make_isotropic_landmarks(
    lm_dict: dict[str, Any] | None,
    aspect_ratio: float | None,
) -> dict[str, tuple[float, float, float]] | None:
    """
    將 MediaPipe / YOLO 歸一化 [0, 1] 關鍵點轉換為以影像高度為基準的等比例 (Isotropic) 2D 座標。
    x_iso = x_norm * (W / H) = x_norm * aspect_ratio
    y_iso = y_norm
    若缺少長寬比資訊，回傳 None（標記幾何資訊不足，不推算 2D 差異）。
    """
    if not lm_dict or not aspect_ratio or aspect_ratio <= 0:
        return None
    iso_dict: dict[str, tuple[float, float, float]] = {}
    for k, v in lm_dict.items():
        if isinstance(v, dict):
            pt = _get_lm_xyv(v)
            if pt is not None:
                iso_dict[k] = (pt[0] * aspect_ratio, pt[1], pt[2])
    return iso_dict if iso_dict else None


def _midpoint_xyv(
    lm_dict: dict[str, tuple[float, float, float]],
    k1: str,
    k2: str,
) -> tuple[float, float, float] | None:
    """計算兩個等比例關鍵點之中點座標與可見度。"""
    p1 = lm_dict.get(k1)
    p2 = lm_dict.get(k2)
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


def _compute_torso_length(lm_dict: dict[str, tuple[float, float, float]]) -> tuple[float | None, float]:
    """計算雙肩中點至雙髖中點在等比例座標系下之 2D 歐氏長度 (作為正規化尺標)。"""
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


def _compute_spine_tilt_deg(lm_dict: dict[str, tuple[float, float, float]]) -> tuple[float | None, float]:
    """計算肩中點與髖中點連線在等比例座標系下相對於垂直線之 2D DTL 前傾角度。"""
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


def _compute_wrist_height_ratio(
    lm_dict: dict[str, tuple[float, float, float]],
    torso_len: float,
) -> tuple[float | None, float]:
    """計算雙手手腕中點相對於雙髖中點在等比例座標系下之垂直高度比 (% of torso)。"""
    wr = _midpoint_xyv(lm_dict, "left_wrist", "right_wrist")
    hp = _midpoint_xyv(lm_dict, "left_hip", "right_hip")
    if not wr or not hp or torso_len <= 0.04:
        return None, 0.0
    vert_delta = hp[1] - wr[1]
    ratio = (vert_delta / torso_len) * 100.0
    conf = min(wr[2], hp[2])
    return ratio, conf


def _compute_head_displacement_pct(
    addr_lms: dict[str, tuple[float, float, float]],
    target_lms: dict[str, tuple[float, float, float]],
    torso_len: float,
) -> tuple[float | None, float]:
    """計算目標階段頭部 (nose) 相對站姿頭部在等比例座標系下之 2D 歐氏位移比例 (% of torso)。"""
    n1 = addr_lms.get("nose")
    n2 = target_lms.get("nose")
    if not n1 or not n2 or torso_len <= 0.04:
        return None, 0.0
    dx = n2[0] - n1[0]
    dy = n2[1] - n1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    pct = (dist / torso_len) * 100.0
    conf = min(n1[2], n2[2])
    return pct, conf


def _compute_hip_displacement_pct(
    addr_lms: dict[str, tuple[float, float, float]],
    impact_lms: dict[str, tuple[float, float, float]],
    torso_len: float,
) -> tuple[float | None, float]:
    """
    計算擊球瞬間相較準備姿勢時雙髖中點在等比例座標系下之 2D 平面位移比 (% of torso)。
    【最高誠信原則與運動學說明】：
    本指標僅計算 2D 影像投影平面上雙髖中點之歐氏位移距離 (Euclidean Distance)，
    無法推論 3D 空間之骨盆旋轉角度 (Pelvis Rotation)，亦無法單由平面位移大小區分
    臀部是向後退開清出擊球通道 (Hip Clearance) 抑或向前頂出 (Early Extension)。
    嚴禁將此歐氏位移距離直接當作骨盆旋轉度數或具方向性之後退量。
    """
    hp1 = _midpoint_xyv(addr_lms, "left_hip", "right_hip")
    hp2 = _midpoint_xyv(impact_lms, "left_hip", "right_hip")
    if not hp1 or not hp2 or torso_len <= 0.04:
        return None, 0.0
    dx = hp2[0] - hp1[0]
    dy = hp2[1] - hp1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    pct = (dist / torso_len) * 100.0
    conf = min(hp1[2], hp2[2])
    return pct, conf


_compute_hip_clearance_pct = _compute_hip_displacement_pct


# =========================================================================
# 影格檢索：嚴格時序邊界與事件對齊（P0-C）
# =========================================================================

def _find_user_landmarks_for_phase(
    keyframes: list[dict[str, Any]],
    target_time_ms: int | None,
    phase_name: str,
    min_time_ms: int | None = None,
    max_time_ms: int | None = None,
    forbidden_times: set[int] | None = None,
    max_tolerance_ms: int = 250,
) -> tuple[dict[str, Any] | None, int | None, float, int | None]:
    """
    從使用者 keyframes_json 找到最接近目標時間碼且符合階段時序邊界的真實 landmarks。
    回傳: (landmarks_dict, frame_time_ms, pose_confidence, frame_time_error_ms)
    """
    if not keyframes or target_time_ms is None or target_time_ms <= 0:
        return None, None, 0.0, None

    forbidden = forbidden_times or set()
    best_kf = None
    best_diff = float("inf")

    for kf in keyframes:
        t_val = kf.get("time_ms")
        if t_val is None:
            continue
        try:
            t = int(t_val)
        except (ValueError, TypeError):
            continue

        if t in forbidden:
            continue
        if min_time_ms is not None and t < min_time_ms:
            continue
        if max_time_ms is not None and t > max_time_ms:
            continue

        diff = abs(t - target_time_ms)
        if diff < best_diff:
            best_diff = diff
            best_kf = kf

    if best_kf is not None and best_diff <= max_tolerance_ms:
        lms = best_kf.get("landmarks") or best_kf.get("keypoints") or {}
        conf = float(best_kf.get("pose_confidence", 0.8))
        f_time = int(best_kf.get("time_ms", target_time_ms))
        return lms, f_time, conf, int(best_diff)

    return None, None, 0.0, None


def _find_ref_landmarks_for_phase(
    ref_pose_artifact: dict[str, Any],
    target_time_ms: int | None,
    phase_name: str,
    min_time_ms: int | None = None,
    max_time_ms: int | None = None,
    forbidden_times: set[int] | None = None,
    max_tolerance_ms: int = 250,
) -> tuple[dict[str, Any] | None, int | None, float, int | None]:
    """
    從示範影片 pose_artifact 找到最接近目標時間碼且符合階段時序邊界的真實 landmarks。
    回傳: (landmarks_dict, frame_time_ms, pose_confidence, frame_time_error_ms)
    """
    if not ref_pose_artifact or target_time_ms is None or target_time_ms <= 0:
        return None, None, 0.0, None

    forbidden = forbidden_times or set()
    lms_dict = ref_pose_artifact.get("landmarks")
    if isinstance(lms_dict, dict) and lms_dict:
        best_k = None
        best_diff = float("inf")
        for k_str, val in lms_dict.items():
            try:
                t = int(k_str)
            except (ValueError, TypeError):
                continue

            if t in forbidden:
                continue
            if min_time_ms is not None and t < min_time_ms:
                continue
            if max_time_ms is not None and t > max_time_ms:
                continue

            diff = abs(t - target_time_ms)
            if diff < best_diff:
                best_diff = diff
                best_k = k_str

        if best_k is not None and best_diff <= max_tolerance_ms:
            pts = lms_dict[best_k]
            vis_list = [p.get("visibility", 1.0) for p in pts.values() if isinstance(p, dict)]
            avg_vis = float(sum(vis_list) / len(vis_list)) if vis_list else 0.9
            return pts, int(best_k), avg_vis, int(best_diff)

    # 亦支援 keyframes 列表格式
    kfs = ref_pose_artifact.get("keyframes")
    if isinstance(kfs, list) and kfs:
        return _find_user_landmarks_for_phase(
            kfs,
            target_time_ms=target_time_ms,
            phase_name=phase_name,
            min_time_ms=min_time_ms,
            max_time_ms=max_time_ms,
            forbidden_times=forbidden,
            max_tolerance_ms=max_tolerance_ms,
        )

    return None, None, 0.0, None


def _metric_severity_score(m: PostureMetricComparison) -> float:
    """
    無量綱標準化嚴重度評分（Normalized Defect Severity）。
    杜絕將度數（°）、百分比（%）、節奏比例（ratio）之原始絕對值混排。
    """
    tol = m.moderate_tol if m.moderate_tol > 0 else 1.0
    abs_d = abs(m.delta or 0.0)
    norm_ratio = abs_d / tol
    status_weight = 2.0 if m.status in ("significant_diff", "significant_difference") else 1.0
    return status_weight * norm_ratio * m.confidence


ACTIONABLE_DRILL_METRICS = {
    "address_spine_tilt",
    "top_spine_retention",
    "top_head_displacement",
    "impact_spine_delta",
    "swing_tempo_ratio",
    "finish_spine_angle",
}
OBSERVATION_ONLY_METRICS = {
    "address_wrist_height",
    "impact_hip_clearance",
}


def _build_priority_fix(
    comparisons: list[PostureMetricComparison],
    overall_reliability: str = "high",
    is_aspect_corrected: bool = True,
    is_angle_compatible: bool = True,
    comparable_count: int = 8,
) -> PriorityFixItem | None:
    """
    Priority Fix 唯一改善重點選擇。
    【運動學與診斷可行動性原則】：
    1. 優先篩選具備有效 2D Actionable Drill 且確實構成動作缺陷的候選項目（如站姿前傾、節奏、脊椎維持）。
    2. 若指標屬於越小越好（如頂點前傾維持、頂點頭部位移），且使用者數值小於或等於示範（delta <= 0），
       代表使用者維持度優於示範，絕不得作為優先「動作缺陷」誤導使用者修正。
    3. 骨盆平面位移比與手腕高度屬於純 2D 幾何觀察指標，無法推論 3D 骨盆旋轉或站位舒適度，
       若選中則安全降級為客觀觀察（actionable_drill = None），嚴禁配發方向性假 Drill。
    4. 若所有指標皆在容許相容區間內或無可靠缺陷，回傳 None。
    """
    if not (comparisons and overall_reliability in ("high", "moderate") and is_aspect_corrected and is_angle_compatible):
        return None

    # 篩選具備改善建議資格（Coaching Eligibility）的真實動作缺陷
    real_defects = []
    for c in comparisons:
        if not (c.is_comparable and c.is_reliable):
            continue
        # 【P0 守衛】：若使用者數值落在實驗性參考區間內 (within_benchmark)，
        # 即使與示範選手有差異，亦代表個人風格差異，絕不得視為使用者動作缺陷，嚴禁配發 Drill！
        if c.benchmark_status == "within_benchmark":
            continue
        # 若為 lower_better 且 delta <= 0（使用者數值小於或等於示範），使用者維持更佳，絕非動作缺陷
        if c.id in ("top_spine_retention", "top_head_displacement", "impact_spine_delta", "finish_spine_angle") and (c.delta or 0.0) <= 0:
            continue
        # 若差異極小（abs_d <= optimal_tol），差距在允許誤差內，非顯著缺陷
        if c.delta is not None and abs(c.delta) <= c.optimal_tol:
            continue
        # 必須具有偏離狀態（significant_diff 或 moderate_diff）
        if c.status in ("significant_diff", "moderate_diff", "significant_difference", "needs_attention") or c.relative_status in ("significant_diff", "moderate_diff"):
            real_defects.append(c)

    # 分離具備 Actionable Drill 之診斷指標與純觀察指標
    actionable_candidates = [c for c in real_defects if c.id in ACTIONABLE_DRILL_METRICS]
    observation_candidates = [c for c in real_defects if c.id in OBSERVATION_ONLY_METRICS]

    actionable_candidates.sort(key=_metric_severity_score, reverse=True)
    observation_candidates.sort(key=_metric_severity_score, reverse=True)

    # 優先選取具備可行動改善方案之指標；若無，再考慮純觀察指標
    if actionable_candidates:
        top_diff = actionable_candidates[0]
    elif observation_candidates:
        top_diff = observation_candidates[0]
    elif real_defects:
        real_defects.sort(key=_metric_severity_score, reverse=True)
        top_diff = real_defects[0]
    else:
        return None

    obs_item = f"{top_diff.phase_zh or top_diff.phase} — {top_diff.metric_name or top_diff.name_zh}"
    u_str = top_diff.user_value_display or f"{top_diff.user_value}{top_diff.unit}"
    r_str = top_diff.ref_value_display or f"{top_diff.ref_value}{top_diff.unit}"
    d_str = top_diff.delta_display or f"{'+' if (top_diff.delta or 0) > 0 else ''}{top_diff.delta}{top_diff.unit}"
    delta_val = top_diff.delta or 0.0

    actionable_drill = None
    retest_metric_target = None

    if top_diff.id == "address_spine_tilt":
        if delta_val < 0:
            priority_fix_summary = (
                f"在準備姿勢（Address）經長寬比等比例校正後，軀幹前傾角為 {u_str}（示範選手為 {r_str}，偏直立 {d_str}）。"
                f"此為站姿幾何設定差異，建議檢視髖部後推（Hip Hinge）幅度，使胸部自然罩住球位。"
            )
        else:
            priority_fix_summary = (
                f"在準備姿勢（Address）經長寬比等比例校正後，軀幹前傾角為 {u_str}（示範選手為 {r_str}，前傾較深 {d_str}）。"
                f"建議確認重心分布，避免身體過度前傾壓迫腳趾。"
            )
        actionable_drill = {
            "name": "站姿髖關節鉸鏈（Hip Hinge）前傾設定 Drill",
            "preparation": "雙腳與肩同寬自然站立，雙手橫握球桿貼於大腿前側。",
            "execution": "膝蓋微曲保持彈性，感受髖部向後推動讓桿身順大腿下滑至膝蓋上方，上半身自然前傾約 35°~40°。",
            "checkpoint": "以 0.25× 慢動作停格檢視準備姿勢，背部維持平直延伸，非彎腰弓背或過度站直。",
        }
        retest_metric_target = f"下次練習 5 球，目標：站姿軀幹前傾角調整至 35.0°~42.0° 參考區間。"

    elif top_diff.id == "top_spine_retention":
        priority_fix_summary = (
            f"在上桿頂點（Top）觀測到前傾維持變化為 {u_str}（示範選手為 {r_str}，變化偏大 {d_str}）。"
            f"顯示上桿至頂點時胸部前傾軸心有所抬起，建議在換向過程維持後背角度。"
        )
        actionable_drill = {
            "name": "臀部貼牆維持前傾軸心 Drill",
            "preparation": "站姿就位時，右臀後方輕觸球包或牆面（距離約 2 公分）。",
            "execution": "上桿時感受右臀輕貼，維持骨盆深度與軀幹前傾角度，避免頂點提早起立。",
            "checkpoint": "錄影對照 0.25× 慢動作，頂點瞬間胸口依然朝向球位。",
        }
        retest_metric_target = f"下次練習 5 球，目標：頂點前傾維持變化量控制在 ≤3.5° 內。"

    elif top_diff.id == "top_head_displacement":
        priority_fix_summary = (
            f"在上桿頂點（Top）觀測到頭部相對位移比為 {u_str}（示範選手為 {r_str}，位移偏大 {d_str}）。"
            f"上桿過程頭部空間位移較大，建議運用慢動作觀察頂點頭部軸心穩定度。"
        )
        actionable_drill = {
            "name": "定點視線鎖定 Drill",
            "preparation": "在球位後方 5 公分處設定一固定地面視覺標記點。",
            "execution": "揮桿全程視線專注於該標記，上桿至頂點維持頭部空間定位。",
            "checkpoint": "以 0.25× 慢動作檢視，上桿頂點頭部高度與站姿保持一致，無下沉或拔起。",
        }
        retest_metric_target = f"下次練習 5 球，目標：頂點頭部位移比控制在 ≤8.0% 身長內。"

    elif top_diff.id == "impact_spine_delta":
        priority_fix_summary = (
            f"在擊球瞬間（Impact）觀測到前傾角度變化為 {u_str}（示範選手為 {r_str}，變化偏大 {d_str}）。"
            f"下桿至觸球瞬間前傾角度變化偏大，顯示有提早起立或脫離原始旋轉平面的傾向。"
        )
        actionable_drill = {
            "name": "擊球維持胸口罩球 Drill",
            "preparation": "胸前抱一球桿橫放於雙肩，進入標準站姿。",
            "execution": "啟動下桿轉身至擊球瞬間，確保桿身持續指向球位前方地面，感受前傾維持。",
            "checkpoint": "對照 0.25× 慢動作，擊球瞬間脊椎角度與站姿相比變化不超過 3.5°。",
        }
        retest_metric_target = f"下次練習 5 球，目標：擊球前傾角度變化控制在 ≤3.5° 內。"

    elif top_diff.id == "swing_tempo_ratio":
        if delta_val > 0:
            priority_fix_summary = (
                f"在擊球瞬間（Impact）上下桿節奏時間比為 {u_str}（示範選手為 {r_str}，比例偏大 {d_str}）。"
                f"上桿耗時相對於下桿較長，轉換啟動偏慢，建議運用慢動作對照頂點換向節奏。"
            )
        else:
            priority_fix_summary = (
                f"在擊球瞬間（Impact）上下桿節奏時間比為 {u_str}（示範選手為 {r_str}，比例偏小 {d_str}）。"
                f"上桿轉換過於急促，建議在上桿頂點給予充足時間完成蓄力。"
            )
        actionable_drill = {
            "name": "三拍默數節奏轉換 Drill",
            "preparation": "正常站姿，心中默念節奏口訣「1-2 上桿... 3 啟動釋放」。",
            "execution": "頂點給予 0.1 秒的從容過渡感，避免雙手急躁下砸。",
            "checkpoint": "錄影確認上桿頂點有清晰的換向過渡軌跡，非急促折返。",
        }
        retest_metric_target = "下次練習 5 球，目標：上下桿時間比維持於 2.7:1 至 3.3:1 區間。"

    elif top_diff.id == "impact_hip_clearance":
        priority_fix_summary = (
            f"在擊球瞬間（Impact）觀測到骨盆2D平面相對位移比為 {u_str}（示範選手為 {r_str}，差異 {d_str}）。"
            f"此指標為 2D 影像雙髖中點在投影平面之歐氏位移距離，無法推論 3D 骨盆旋轉角度或臀部後退方向，"
            f"不配發單向 Drill，降級為純客觀幾何觀察。"
        )
        actionable_drill = None
        retest_metric_target = "建議在 0.25× 慢動作停格檢視擊球瞬間骨盆平面位置與重心維持。"

    elif top_diff.id == "finish_spine_angle":
        priority_fix_summary = (
            f"在收桿平衡（Finish）觀測到軀幹直立角為 {u_str}（示範選手為 {r_str}，差異 {d_str}）。"
            f"收桿結束時身體未完全隨動力自然站直，可能影響動作平衡與完整性。"
        )
        actionable_drill = {
            "name": "3 秒雕像收桿平衡 Drill",
            "preparation": "正常全揮桿練習。",
            "execution": "揮桿結束後維持胸口朝向目標、右腳鞋底垂直離地的收桿姿勢，心中默數 1-2-3 不移動雙腳。",
            "checkpoint": "身體平穩站定，不前後晃動或提早收力放桿。",
        }
        retest_metric_target = "下次練習 5 球，目標：收桿完全站定直立，前傾角保持在 12.0° 內。"

    elif top_diff.id == "address_wrist_height":
        if delta_val < 0:
            priority_fix_summary = (
                f"在準備姿勢（Address）觀測到雙手手腕基準高度為 {u_str}（示範選手為 {r_str}，偏低 {d_str}）。"
                f"此為個人站姿與手臂自然垂放設定差異，不代表動作缺陷。建議透過慢放跳轉檢視手腕與大腿間距是否自然舒展。"
            )
        else:
            priority_fix_summary = (
                f"在準備姿勢（Address）觀測到雙手手腕基準高度為 {u_str}（示範選手為 {r_str}，偏高 {d_str}）。"
                f"此為個人站姿設定差異，顯示手臂向前伸展幅度較大，可對照示範選手觀察站位距離。"
            )
        actionable_drill = None
        retest_metric_target = "建議在 0.25× 慢動作播放器中對照示範選手的準備站姿手腕距離，視擊球舒適度自行微調。"

    else:
        priority_fix_summary = (
            f"在 {top_diff.phase_zh or top_diff.phase} 觀測到 {top_diff.metric_name or top_diff.name_zh} 為 {u_str}（示範選手為 {r_str}，差異 {d_str}）。"
            f"建議使用 0.25× 慢動作同步比對兩者在該影格的姿勢特徵。"
        )
        actionable_drill = None
        retest_metric_target = f"建議透過慢放跳轉至 {top_diff.phase_zh or top_diff.phase} 觀察動作差異。"

    return PriorityFixItem(
        focus_area=obs_item,
        metric_id=top_diff.id,
        user_value=u_str,
        ref_value=r_str,
        delta=d_str,
        summary=priority_fix_summary,
        drill=actionable_drill,
        target=retest_metric_target,
        confidence=top_diff.confidence,
    )


_determine_priority_fix = _build_priority_fix


# =========================================================================
# 主比較引擎
# =========================================================================

def compute_quantitative_posture_comparison(
    user_swing: dict[str, Any],
    ref_swing: dict[str, Any],
) -> QuantitativePostureReport:
    """
    依據使用者揮桿與參考示範揮桿之真實 2D MediaPipe Pose 關鍵點與時間碼，
    經由等比例長寬比校正（Isotropic Aspect Ratio Correction）計算 4 大階段客觀量化姿勢比較清單。
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
            geometry_calibration={"is_aspect_corrected": False, "reason": "缺少示範影片"},
        )

    # 2. 幾何長寬比解析 (P0-A)
    u_w, u_h, u_aspect = _extract_display_dimensions_and_aspect(user_swing)
    r_w, r_h, r_aspect = _extract_display_dimensions_and_aspect(ref_swing)
    is_aspect_corrected = bool(u_aspect and r_aspect and u_aspect > 0 and r_aspect > 0)

    geometry_calib_info = {
        "is_aspect_corrected": is_aspect_corrected,
        "coordinate_system": "isotropic_height_normalized" if is_aspect_corrected else "uncalibrated_anisotropic",
        "user_display_width": u_w,
        "user_display_height": u_h,
        "user_display_aspect": u_aspect,
        "user_resolution": f"{u_w}x{u_h}" if (u_w and u_h) else "unknown",
        "user_aspect_ratio": u_aspect,
        "ref_display_width": r_w,
        "ref_display_height": r_h,
        "ref_display_aspect": r_aspect,
        "ref_resolution": f"{r_w}x{r_h}" if (r_w and r_h) else "unknown",
        "ref_aspect_ratio": r_aspect,
        "disclaimer": (
            "已完成 2D 影像長寬比等比例校正（Isotropic Coordinate Space）。"
            "請注意：長寬比校正僅消除影像像素座標之縮放失真，"
            "不等於消除相機俯仰角、透視景深與鏡頭畸變差異。"
        ),
    }

    # 3. 相機視角與狀態可靠度檢查
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

    # 4. 提取真實事件時間碼（嚴禁捏造時間碼，缺少即為 None - P0-C）
    raw_user_events = user_swing.get("events")
    if isinstance(raw_user_events, dict):
        user_events = raw_user_events
    elif isinstance(raw_user_events, list):
        user_events = {
            e.get("event_name"): int(e.get("time_ms", 0))
            for e in raw_user_events
            if isinstance(e, dict) and e.get("event_name")
        }
    else:
        user_events = {}
    u_addr_ms = user_events.get("address")
    u_top_ms = user_events.get("top")
    u_impact_ms = user_events.get("impact_estimated") or user_events.get("impact")
    u_finish_ms = user_events.get("finish")

    ref_events = ref_swing.get("event_timestamps") or {}
    r_addr_ms = int(ref_events["address"]) if "address" in ref_events else None
    r_top_ms = int(ref_events["top"]) if "top" in ref_events else None
    r_impact_ms = int(ref_events["impact"]) if "impact" in ref_events else None
    r_finish_ms = int(ref_events["finish"]) if "finish" in ref_events else None

    # 5. 檢索關鍵點並受限於時序邊界（P0-C: Top 不冒充 Impact，Impact 不冒充 Top）
    user_kf = (user_swing.get("pose_artifact") or {}).get("keyframes_json") or user_swing.get("keyframes") or []
    ref_pa = ref_swing.get("pose_artifact") or {}

    # Address
    u_addr_lms, u_addr_t, u_addr_conf, u_addr_err = _find_user_landmarks_for_phase(
        user_kf, u_addr_ms, "address", max_time_ms=u_top_ms, max_tolerance_ms=250
    )
    r_addr_lms, r_addr_t, r_addr_conf, r_addr_err = _find_ref_landmarks_for_phase(
        ref_pa, r_addr_ms, "address", max_time_ms=r_top_ms, max_tolerance_ms=250
    )

    # Top（必須在 address 之後，impact 之前）
    u_top_lms, u_top_t, u_top_conf, u_top_err = _find_user_landmarks_for_phase(
        user_kf, u_top_ms, "top",
        min_time_ms=u_addr_t,
        max_time_ms=(u_impact_ms - 30) if u_impact_ms else None,
        max_tolerance_ms=180,
    )
    r_top_lms, r_top_t, r_top_conf, r_top_err = _find_ref_landmarks_for_phase(
        ref_pa, r_top_ms, "top",
        min_time_ms=r_addr_t,
        max_time_ms=(r_impact_ms - 30) if r_impact_ms else None,
        max_tolerance_ms=180,
    )

    # Impact（必須在 top 之後，且禁止使用 top 影格）
    forbidden_u_imp = {u_top_t} if u_top_t is not None else set()
    forbidden_r_imp = {r_top_t} if r_top_t is not None else set()
    u_imp_lms, u_imp_t, u_imp_conf, u_imp_err = _find_user_landmarks_for_phase(
        user_kf, u_impact_ms, "impact",
        min_time_ms=(u_top_ms + 30) if u_top_ms else None,
        max_time_ms=u_finish_ms,
        forbidden_times=forbidden_u_imp,
        max_tolerance_ms=180,
    )
    r_imp_lms, r_imp_t, r_imp_conf, r_imp_err = _find_ref_landmarks_for_phase(
        ref_pa, r_impact_ms, "impact",
        min_time_ms=(r_top_ms + 30) if r_top_ms else None,
        max_time_ms=r_finish_ms,
        forbidden_times=forbidden_r_imp,
        max_tolerance_ms=180,
    )

    # Finish（必須在 impact 之後，且禁止使用 top/impact 影格）
    forbidden_u_fin = {t for t in (u_top_t, u_imp_t) if t is not None}
    forbidden_r_fin = {t for t in (r_top_t, r_imp_t) if t is not None}
    u_fin_lms, u_fin_t, u_fin_conf, u_fin_err = _find_user_landmarks_for_phase(
        user_kf, u_finish_ms, "finish",
        min_time_ms=u_imp_t,
        forbidden_times=forbidden_u_fin,
        max_tolerance_ms=300,
    )
    r_fin_lms, r_fin_t, r_fin_conf, r_fin_err = _find_ref_landmarks_for_phase(
        ref_pa, r_finish_ms, "finish",
        min_time_ms=r_imp_t,
        forbidden_times=forbidden_r_fin,
        max_tolerance_ms=300,
    )

    # 6. 等比例長寬比校正轉換 (P0-A)
    u_addr_iso = _make_isotropic_landmarks(u_addr_lms, u_aspect)
    u_top_iso = _make_isotropic_landmarks(u_top_lms, u_aspect)
    u_imp_iso = _make_isotropic_landmarks(u_imp_lms, u_aspect)
    u_fin_iso = _make_isotropic_landmarks(u_fin_lms, u_aspect)

    r_addr_iso = _make_isotropic_landmarks(r_addr_lms, r_aspect)
    r_top_iso = _make_isotropic_landmarks(r_top_lms, r_aspect)
    r_imp_iso = _make_isotropic_landmarks(r_imp_lms, r_aspect)
    r_fin_iso = _make_isotropic_landmarks(r_fin_lms, r_aspect)

    # 計算等比例軀幹長度
    u_torso_len, u_torso_conf = _compute_torso_length(u_addr_iso) if u_addr_iso else (None, 0.0)
    r_torso_len, r_torso_conf = _compute_torso_length(r_addr_iso) if r_addr_iso else (None, 0.0)

    # 是否為慢動作示範
    is_ref_slow_mo = bool(ref_calib.get("is_slow_motion", False))

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
        requires_geometry: bool = True,
        is_lower_better: bool = False,
        is_higher_better: bool = False,
        benchmark_bounds: tuple[float | None, float | None] | None = None,
    ) -> PostureMetricComparison:
        """安全建構單項量化姿勢比對物件。若任一方缺失，明確設置為不可比。"""
        # 示範是否為慢動作素材
        if is_slow_mo_ref:
            r_val = None
            r_val_display = slow_mo_note or "N/A (慢動作素材)"
        else:
            r_val_display = (val_format + unit_suffix).format(r_val) if r_val is not None else "N/A"

        u_val_display = (val_format + unit_suffix).format(u_val) if u_val is not None else "N/A"

        # 幾何校正完整性檢查
        geometry_ok = is_aspect_corrected if requires_geometry else True

        # 檢查是否可比
        is_comparable = (
            is_angle_compatible
            and geometry_ok
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
        relative_status = "unassessed"
        benchmark_status = "unassessed"

        # 1. 實驗性參考區間評估 (Experimental Benchmark Evaluation)
        if u_val is not None:
            if benchmark_bounds is not None:
                b_min, b_max = benchmark_bounds
                in_b = True
                if b_min is not None and u_val < b_min:
                    in_b = False
                if b_max is not None and u_val > b_max:
                    in_b = False
                benchmark_status = "within_benchmark" if in_b else "outside_benchmark"
            else:
                benchmark_status = "not_applicable"

        # 2. 相對示範評估 (Relative Reference Comparison)
        if not is_angle_compatible:
            status = "not_comparable"
            relative_status = "not_comparable"
            eval_text = f"相機視角不相容（示範為 {ref_camera}，非標準 DTL），不推算 2D 平面幾何差異。"
        elif not geometry_ok:
            status = "insufficient_evidence"
            relative_status = "insufficient_evidence"
            eval_text = "缺少影片解析度或長寬比資訊，無法進行等比例影像座標校正，不推算 2D 差異。"
        elif not is_comparable:
            status = "insufficient_evidence"
            relative_status = "insufficient_evidence"
            missing_who = []
            if u_val is None or u_conf < 0.35:
                missing_who.append("使用者揮桿")
            if r_val is None or r_conf < 0.35:
                missing_who.append("示範影片" if not is_slow_mo_ref else "示範Tempo(慢動作無真實時長)")
            eval_text = f"缺少{'與'.join(missing_who)}之可靠關鍵點或時間碼，未具備充分觀測證據，不計算差異。"
        else:
            delta = round(u_val - r_val, 2)
            delta_display = f"{delta:+.1f}" + unit_suffix if "°" in unit_suffix or "%" in unit_suffix else f"{delta:+.2f}"
            abs_d = abs(delta)

            # 計算示範相對狀態 relative_status
            if abs_d <= optimal_tol:
                relative_status = "aligned"
            elif abs_d <= moderate_tol:
                relative_status = "moderate_diff"
            else:
                relative_status = "significant_diff"

            # 綜合品質判定 (結合相對差異與常模區間，分離 Relative Difference 與 Experimental Benchmark)
            if is_lower_better and delta <= 0:
                if benchmark_status == "within_benchmark":
                    status = "optimal"
                    eval_text = f"數值為 {u_val_display}，落在實驗性參考區間內且相較示範選手（{r_val_display}）維持更佳穩定度。"
                else:
                    # 使用者數值小於示範，但超出實驗性參考區間，絕不可盲目判定為 optimal
                    status = "aligned" if abs_d <= optimal_tol else "moderate_diff"
                    eval_text = f"數值為 {u_val_display}，相較示範選手（{r_val_display}）位移或變化量較小，但仍超出實驗性參考區間（{benchmark}）。"
            elif is_higher_better and delta >= 0:
                if benchmark_status == "within_benchmark":
                    status = "optimal"
                    eval_text = f"數值為 {u_val_display}，落在實驗性參考區間內且相較示範選手（{r_val_display}）展現充分幅度。"
                else:
                    status = "aligned" if abs_d <= optimal_tol else "moderate_diff"
                    eval_text = f"數值為 {u_val_display}，相較示範選手（{r_val_display}）幅度較大，但超出實驗性參考區間（{benchmark}）。"
            elif abs_d <= optimal_tol:
                # 雙方數值高度相符 (abs_d <= optimal_tol)
                if benchmark_status in ("within_benchmark", "not_applicable"):
                    # 落在參考區間內且與示範高度相符 -> 始可宣稱為最佳 (optimal)
                    status = "optimal"
                    eval_text = f"落在實驗性參考區間內且與示範選手數值高度相符（差距僅 {delta_display}）。"
                else:
                    # 超出實驗性參考區間，即使與示範高度相符，亦僅為與示範相符 (aligned)，絕不可冒稱動作品質最佳 (optimal)
                    status = "aligned"
                    eval_text = f"與示範選手數值高度相符（差距僅 {delta_display}），但目前數值（{u_val_display}）在實驗性參考區間（{benchmark}）之外。"
            elif benchmark_status == "within_benchmark":
                # 使用者自身落在實驗性參考區間內，但與示範選手存在差異 (如節奏 3.27:1 vs 1.90:1)
                # 此為個人揮桿風格差異，無動作缺陷證據，不可列為缺陷或配發矯正 Drill
                status = "aligned"
                eval_text = f"數值（{u_val_display}）位於實驗性參考區間內；示範選手（{r_val_display}）數值不同，此為個人揮桿風格差異，無動作缺陷證據。"
            elif abs_d <= moderate_tol:
                status = "moderate_diff"
                cue = direction_cue[1] if delta > 0 else direction_cue[0]
                eval_text = f"較示範選手{cue} {abs_d:.1f}{unit_suffix}，且數值超出實驗性參考區間，落在可微調區間。"
            else:
                status = "significant_diff"
                cue = direction_cue[1] if delta > 0 else direction_cue[0]
                eval_text = f"較示範選手明顯{cue} {abs_d:.1f}{unit_suffix}，且超出實驗性參考區間，為本階段核心結構差異。"

        target_jump_map = {
            "address": u_addr_t or u_addr_ms or 0,
            "top": u_top_t or u_top_ms or 0,
            "impact": u_imp_t or u_impact_ms or 0,
            "finish": u_fin_t or u_finish_ms or 0,
        }

        u_err = u_ev.get("frame_time_error_ms")
        r_err = r_ev.get("frame_time_error_ms")
        acc_ms = max(u_err or 0, r_err or 0) if (u_err is not None or r_err is not None) else None

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
            optimal_tol=optimal_tol,
            moderate_tol=moderate_tol,
            geometry_coord_system="isotropic_height_normalized" if geometry_ok else "uncalibrated_anisotropic",
            event_accuracy_ms=acc_ms,
            user_evidence=u_ev,
            ref_evidence=r_ev,
            relative_status=relative_status,
            benchmark_status=benchmark_status,
            target_jump_ms=target_jump_map.get(phase, 0),
            target_jump_phase=phase,
            recommended_speed=0.25 if phase in ("top", "impact") else 0.5,
        )

    # =========================================================================
    # 階段 1：Address 準備姿勢
    # =========================================================================
    u_addr_tilt, u_at_conf = _compute_spine_tilt_deg(u_addr_iso) if u_addr_iso else (None, 0.0)
    r_addr_tilt, r_at_conf = _compute_spine_tilt_deg(r_addr_iso) if r_addr_iso else (None, 0.0)
    comparisons.append(make_metric(
        id_="address_spine_tilt",
        phase="address",
        phase_zh="準備姿勢 (Address)",
        name="站姿軀幹前傾角",
        unit="deg_2d",
        u_val=round(u_addr_tilt, 1) if u_addr_tilt is not None else None,
        u_conf=u_at_conf,
        u_ev={
            "frame_time_ms": u_addr_t, "event_time_ms": u_addr_ms, "frame_time_error_ms": u_addr_err,
            "video_width": u_w, "video_height": u_h, "aspect_ratio": u_aspect,
            "landmark_source": "user_keyframes_json" if u_addr_lms else "none",
            "formula": "atan2(|sh_iso.x - hp_iso.x|, hp_iso.y - sh_iso.y)"
        },
        r_val=round(r_addr_tilt, 1) if r_addr_tilt is not None else None,
        r_conf=r_at_conf,
        r_ev={
            "frame_time_ms": r_addr_t, "event_time_ms": r_addr_ms, "frame_time_error_ms": r_addr_err,
            "video_width": r_w, "video_height": r_h, "aspect_ratio": r_aspect,
            "landmark_source": "ref_pose_artifact" if r_addr_lms else "none",
            "formula": "atan2(|sh_iso.x - hp_iso.x|, hp_iso.y - sh_iso.y)"
        },
        benchmark="36.0° ~ 44.0° (實驗性參考區間，非認證標準)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="°",
        direction_cue=("偏直立", "偏過深前傾"),
        benchmark_bounds=(36.0, 44.0),
    ))

    u_wrist_h, u_wh_conf = _compute_wrist_height_ratio(u_addr_iso, u_torso_len or 0.25) if u_addr_iso else (None, 0.0)
    r_wrist_h, r_wh_conf = _compute_wrist_height_ratio(r_addr_iso, r_torso_len or 0.25) if r_addr_iso else (None, 0.0)
    comparisons.append(make_metric(
        id_="address_wrist_height",
        phase="address",
        phase_zh="準備姿勢 (Address)",
        name="雙手手腕基準高度比",
        unit="torso_pct",
        u_val=round(u_wrist_h, 1) if u_wrist_h is not None else None,
        u_conf=u_wh_conf,
        u_ev={
            "frame_time_ms": u_addr_t, "event_time_ms": u_addr_ms, "frame_time_error_ms": u_addr_err,
            "video_width": u_w, "video_height": u_h, "aspect_ratio": u_aspect,
            "landmark_source": "user_keyframes_json" if u_addr_lms else "none",
            "formula": "(hp_iso.y - wr_iso.y) / torso_len_iso * 100"
        },
        r_val=round(r_wrist_h, 1) if r_wrist_h is not None else None,
        r_conf=r_wh_conf,
        r_ev={
            "frame_time_ms": r_addr_t, "event_time_ms": r_addr_ms, "frame_time_error_ms": r_addr_err,
            "video_width": r_w, "video_height": r_h, "aspect_ratio": r_aspect,
            "landmark_source": "ref_pose_artifact" if r_addr_lms else "none",
            "formula": "(hp_iso.y - wr_iso.y) / torso_len_iso * 100"
        },
        benchmark="-12.0% ~ +8.0% 身長 (實驗性參考區間，非認證標準)",
        optimal_tol=5.0,
        moderate_tol=10.0,
        unit_suffix="%",
        direction_cue=("偏低", "偏高"),
        benchmark_bounds=(-12.0, 8.0),
    ))

    # =========================================================================
    # 階段 2：Top 上桿頂點
    # =========================================================================
    u_top_tilt, u_tt_conf = _compute_spine_tilt_deg(u_top_iso) if u_top_iso else (None, 0.0)
    r_top_tilt, r_tt_conf = _compute_spine_tilt_deg(r_top_iso) if r_top_iso else (None, 0.0)
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
        u_ev={
            "frame_time_ms": u_top_t, "event_time_ms": u_top_ms, "frame_time_error_ms": u_top_err,
            "addr_frame_time_ms": u_addr_t, "aspect_ratio": u_aspect,
            "formula": "|top_spine_iso_deg - addr_spine_iso_deg|"
        },
        r_val=round(r_top_ret, 1) if r_top_ret is not None else None,
        r_conf=min(r_tt_conf, r_at_conf),
        r_ev={
            "frame_time_ms": r_top_t, "event_time_ms": r_top_ms, "frame_time_error_ms": r_top_err,
            "addr_frame_time_ms": r_addr_t, "aspect_ratio": r_aspect,
            "formula": "|top_spine_iso_deg - addr_spine_iso_deg|"
        },
        benchmark="≤ 4.0° (實驗性參考區間，非認證標準)",
        optimal_tol=2.5,
        moderate_tol=5.0,
        unit_suffix="°",
        direction_cue=("前傾維持更佳", "前傾提早流失"),
        is_lower_better=True,
        benchmark_bounds=(None, 4.0),
    ))

    u_top_head, u_th_conf = _compute_head_displacement_pct(u_addr_iso, u_top_iso, u_torso_len or 0.25) if (u_addr_iso and u_top_iso) else (None, 0.0)
    r_top_head, r_th_conf = _compute_head_displacement_pct(r_addr_iso, r_top_iso, r_torso_len or 0.25) if (r_addr_iso and r_top_iso) else (None, 0.0)
    comparisons.append(make_metric(
        id_="top_head_displacement",
        phase="top",
        phase_zh="上桿頂點 (Top)",
        name="頂點頭部相對位移比",
        unit="torso_pct",
        u_val=round(u_top_head, 1) if u_top_head is not None else None,
        u_conf=min(u_th_conf, u_torso_conf),
        u_ev={
            "frame_time_ms": u_top_t, "event_time_ms": u_top_ms, "frame_time_error_ms": u_top_err,
            "addr_frame_time_ms": u_addr_t, "aspect_ratio": u_aspect,
            "formula": "dist(nose_top_iso, nose_addr_iso) / torso_len_iso * 100"
        },
        r_val=round(r_top_head, 1) if r_top_head is not None else None,
        r_conf=min(r_th_conf, r_torso_conf),
        r_ev={
            "frame_time_ms": r_top_t, "event_time_ms": r_top_ms, "frame_time_error_ms": r_top_err,
            "addr_frame_time_ms": r_addr_t, "aspect_ratio": r_aspect,
            "formula": "dist(nose_top_iso, nose_addr_iso) / torso_len_iso * 100"
        },
        benchmark="≤ 8.0% 身長 (實驗性參考區間，非認證標準)",
        optimal_tol=3.0,
        moderate_tol=6.0,
        unit_suffix="%",
        direction_cue=("頭部更為穩定", "頭部浮動過大"),
        is_lower_better=True,
        benchmark_bounds=(None, 8.0),
    ))

    # =========================================================================
    # 階段 3：Impact 擊球瞬間
    # =========================================================================
    u_imp_tilt, u_it_conf = _compute_spine_tilt_deg(u_imp_iso) if u_imp_iso else (None, 0.0)
    r_imp_tilt, r_it_conf = _compute_spine_tilt_deg(r_imp_iso) if r_imp_iso else (None, 0.0)
    u_imp_ret = abs(u_imp_tilt - u_addr_tilt) if (u_imp_tilt is not None and u_addr_tilt is not None) else None
    r_imp_ret = abs(r_imp_tilt - r_addr_tilt) if (r_imp_tilt is not None and r_addr_tilt is not None) else None
    comparisons.append(make_metric(
        id_="impact_spine_delta",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="擊球軀幹前傾維持變化",
        unit="deg_2d",
        u_val=round(u_imp_ret, 1) if u_imp_ret is not None else None,
        u_conf=min(u_it_conf, u_at_conf),
        u_ev={
            "frame_time_ms": u_imp_t, "event_time_ms": u_impact_ms, "frame_time_error_ms": u_imp_err,
            "addr_frame_time_ms": u_addr_t, "aspect_ratio": u_aspect,
            "formula": "|impact_spine_iso_deg - addr_spine_iso_deg|"
        },
        r_val=round(r_imp_ret, 1) if r_imp_ret is not None else None,
        r_conf=min(r_it_conf, r_at_conf),
        r_ev={
            "frame_time_ms": r_imp_t, "event_time_ms": r_impact_ms, "frame_time_error_ms": r_imp_err,
            "addr_frame_time_ms": r_addr_t, "aspect_ratio": r_aspect,
            "formula": "|impact_spine_iso_deg - addr_spine_iso_deg|"
        },
        benchmark="≤ 5.0° (實驗性參考區間，非認證標準)",
        optimal_tol=2.5,
        moderate_tol=5.0,
        unit_suffix="°",
        direction_cue=("前傾維持扎實", "觸球提早起立"),
        is_lower_better=True,
        benchmark_bounds=(None, 5.0),
    ))

    # 上下桿節奏比（Tempo）
    u_tempo = None
    u_tempo_conf = 0.0
    if u_top_ms is not None and u_impact_ms is not None and u_addr_ms is not None:
        u_back_ms = u_top_ms - u_addr_ms
        u_down_ms = u_impact_ms - u_top_ms
        if 300 <= u_back_ms <= 3000 and 120 <= u_down_ms <= 650:
            u_tempo = round(u_back_ms / u_down_ms, 2)
            u_tempo_conf = 0.85

    r_tempo = None
    r_tempo_conf = 0.0
    if not is_ref_slow_mo and r_top_ms is not None and r_impact_ms is not None and r_addr_ms is not None:
        r_back_ms = r_top_ms - r_addr_ms
        r_down_ms = r_impact_ms - r_top_ms
        if 300 <= r_back_ms <= 3000 and 120 <= r_down_ms <= 650:
            r_tempo = round(r_back_ms / r_down_ms, 2)
            r_tempo_conf = 0.85

    comparisons.append(make_metric(
        id_="swing_tempo_ratio",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="上下桿節奏時間比",
        unit="ratio",
        u_val=u_tempo,
        u_conf=u_tempo_conf,
        u_ev={
            "event_top_ms": u_top_ms, "event_impact_ms": u_impact_ms, "event_addr_ms": u_addr_ms,
            "backswing_ms": (u_top_ms - u_addr_ms) if (u_top_ms and u_addr_ms) else None,
            "downswing_ms": (u_impact_ms - u_top_ms) if (u_impact_ms and u_top_ms) else None,
            "formula": "backswing_ms / downswing_ms"
        },
        r_val=r_tempo,
        r_conf=r_tempo_conf,
        r_ev={
            "event_top_ms": r_top_ms, "event_impact_ms": r_impact_ms, "event_addr_ms": r_addr_ms,
            "is_slow_motion": is_ref_slow_mo,
            "formula": "backswing_ms / downswing_ms"
        },
        benchmark="2.7:1 ~ 3.3:1 (實驗性參考區間，非認證標準)",
        optimal_tol=0.35,
        moderate_tol=0.70,
        val_format="{:.2f}",
        unit_suffix=":1",
        is_slow_mo_ref=is_ref_slow_mo,
        slow_mo_note="N/A (慢動作素材不提供假Tempo)",
        direction_cue=("下桿轉換急促", "上桿過度緩慢"),
        requires_geometry=False,  # 時間比不依賴空間座標長寬比
        benchmark_bounds=(2.7, 3.3),
    ))

    # 擊球骨盆2D相對位移比 (第一階段：更名與誠實運動學解釋，移除 is_higher_better)
    u_hip_clear, u_hc_conf = _compute_hip_displacement_pct(u_addr_iso, u_imp_iso, u_torso_len or 0.25) if (u_addr_iso and u_imp_iso) else (None, 0.0)
    r_hip_clear, r_hc_conf = _compute_hip_displacement_pct(r_addr_iso, r_imp_iso, r_torso_len or 0.25) if (r_addr_iso and r_imp_iso) else (None, 0.0)
    comparisons.append(make_metric(
        id_="impact_hip_clearance",
        phase="impact",
        phase_zh="擊球瞬間 (Impact)",
        name="擊球骨盆2D相對位移比",
        unit="torso_pct",
        u_val=round(u_hip_clear, 1) if u_hip_clear is not None else None,
        u_conf=min(u_hc_conf, u_torso_conf),
        u_ev={
            "frame_time_ms": u_imp_t, "event_time_ms": u_impact_ms, "frame_time_error_ms": u_imp_err,
            "addr_frame_time_ms": u_addr_t, "aspect_ratio": u_aspect,
            "formula": "dist(hip_imp_iso, hip_addr_iso) / torso_len_iso * 100"
        },
        r_val=round(r_hip_clear, 1) if r_hip_clear is not None else None,
        r_conf=min(r_hc_conf, r_torso_conf),
        r_ev={
            "frame_time_ms": r_imp_t, "event_time_ms": r_impact_ms, "frame_time_error_ms": r_imp_err,
            "addr_frame_time_ms": r_addr_t, "aspect_ratio": r_aspect,
            "formula": "dist(hip_imp_iso, hip_addr_iso) / torso_len_iso * 100"
        },
        benchmark="8.0% ~ 18.0% 身長 (實驗性參考區間，非認證標準)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="%",
        direction_cue=("平面位移較小", "平面位移較大"),
        is_higher_better=False,
        benchmark_bounds=(8.0, 18.0),
    ))

    # =========================================================================
    # 階段 4：Finish 收桿平衡
    # =========================================================================
    u_fin_tilt, u_ft_conf = _compute_spine_tilt_deg(u_fin_iso) if u_fin_iso else (None, 0.0)
    r_fin_tilt, r_ft_conf = _compute_spine_tilt_deg(r_fin_iso) if r_fin_iso else (None, 0.0)
    comparisons.append(make_metric(
        id_="finish_spine_angle",
        phase="finish",
        phase_zh="收桿平衡 (Finish)",
        name="收桿軀幹直立角",
        unit="deg_2d",
        u_val=round(u_fin_tilt, 1) if u_fin_tilt is not None else None,
        u_conf=u_ft_conf,
        u_ev={
            "frame_time_ms": u_fin_t, "event_time_ms": u_finish_ms, "frame_time_error_ms": u_fin_err,
            "aspect_ratio": u_aspect, "formula": "spine_tilt_iso_deg @ finish frame"
        },
        r_val=round(r_fin_tilt, 1) if r_fin_tilt is not None else None,
        r_conf=r_ft_conf,
        r_ev={
            "frame_time_ms": r_fin_t, "event_time_ms": r_finish_ms, "frame_time_error_ms": r_fin_err,
            "aspect_ratio": r_aspect, "formula": "spine_tilt_iso_deg @ finish frame"
        },
        benchmark="≤ 16.0° (實驗性參考區間，非認證標準)",
        optimal_tol=4.0,
        moderate_tol=8.0,
        unit_suffix="°",
        direction_cue=("更為直立", "身體殘留後傾"),
        is_lower_better=True,
        benchmark_bounds=(None, 16.0),
    ))

    # 7. 可靠度總結與覆蓋率 (P0-B & P1-A)
    comparable_count = sum(1 for c in comparisons if c.is_comparable)
    total_metrics = len(comparisons)
    comparable_ratio = comparable_count / total_metrics if total_metrics > 0 else 0.0

    if not is_angle_compatible:
        overall_status = "not_comparable"
        overall_reliability = "unreliable"
    elif not is_aspect_corrected:
        overall_status = "insufficient_data"
        overall_reliability = "unreliable"
    elif comparable_ratio < 0.35:
        overall_status = "insufficient_data"
        overall_reliability = "unreliable"
    elif comparable_ratio < 0.65:
        overall_status = "ready"
        overall_reliability = "low"
    elif comparable_ratio < 0.85:
        overall_status = "ready"
        overall_reliability = "moderate"
    else:
        overall_status = "ready"
        overall_reliability = "high"

    # 8. Priority Fix 唯一改善重點選擇 (P0-D: 嚴格建立在真實等比例幾何證據上)
    priority_fix_item = _build_priority_fix(
        comparisons=comparisons,
        overall_reliability=overall_reliability,
        is_aspect_corrected=is_aspect_corrected,
        is_angle_compatible=is_angle_compatible,
        comparable_count=comparable_count,
    )
    if priority_fix_item:
        priority_fix_id = priority_fix_item.metric_id
        priority_fix_summary = priority_fix_item.summary
        actionable_drill = priority_fix_item.drill
        retest_metric_target = priority_fix_item.target
        priority_fix_obj = priority_fix_item
    else:
        priority_fix_id = None
        actionable_drill = None
        retest_metric_target = None
        priority_fix_obj = None
        if not is_angle_compatible:
            priority_fix_summary = "相機視角不相容，無法確立可信的動作改善重點。建議更換標準 DTL 示範影片。"
        elif not is_aspect_corrected:
            priority_fix_summary = "缺少影像長寬比幾何資訊，未完成等比例校正，不產生動作改善重點。"
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
        geometry_calibration=geometry_calib_info,
        is_offline_mode=True,
    )
