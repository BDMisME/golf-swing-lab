"""
Golf Tracer Studio R4 — Upright-to-Output Frame Compositor & Parity Verifier (`compositor.py`).
負責：
1. 將正向 BGR 影格依目標比例 (`original`, `16:9`, `9:16`) 置入 `OutputLayout` 畫布（含 Letterbox / Pillarbox 邊距）。
2. 呼叫 `render_tracer_layers_onto_bgr` 合成 Swing Tracer 與 Shot Tracer 圖層。
3. 提供 Preview 與 Export 座標及時間碼對齊檢驗器 (`verify_preview_export_parity`)，
   強制保證座標差異 `<= 2.0 px` (@1080p) 且時間對齊差異 `<= 1 frame`。
"""

from dataclasses import dataclass
import math

import cv2
import numpy as np

from packages.analysis.tracer.contracts import CanonicalTrackPoint
from packages.analysis.tracer.fx_renderer import (
    project_track_point_to_output_px,
    render_tracer_layers_onto_bgr,
)
from packages.analysis.tracer.fx_schema import RenderRecipeV1
from packages.analysis.tracer.transforms import (
    OutputLayout,
    project_upright_norm_to_output_px,
)


@dataclass(frozen=True)
class ParityCheckReport:
    """Preview 與 Export 數學座標投影與時間格點對齊驗證報告 (`math_projection_parity`)。"""

    aspect_ratio: str
    fps: int
    checked_point_count: int
    max_coordinate_error_px: float
    mean_coordinate_error_px: float
    max_frame_pts_delta_us: int
    max_frame_delta_frames: float
    coordinate_parity_passed: bool
    pts_parity_passed: bool
    parity_kind: str = "math_projection_parity"


@dataclass(frozen=True)
class ActualVisualParityCheckpoint:
    """單一指定 PTS 之 WebKit Canvas 截圖 vs. 匯出 MP4 解碼影格真實像素比對結果。"""

    pts_us: int
    export_frame_index: int
    export_frame_pts_us: int
    frame_delta_frames: float
    active_point_count: int
    max_centerline_offset_px_1080p: float
    mean_centerline_offset_px_1080p: float
    canvas_fx_pixel_count: int
    mp4_fx_pixel_count: int
    phase_color_verified: bool
    artistic_dashed_verified: bool
    passed: bool
    parity_kind: str = "actual_visual_pixel_parity"
    # P0-B: 點位覆蓋率、多維度誤差與詳細跳過診斷
    eligible_point_count: int = 0
    matched_point_count: int = 0
    unmatched_count: int = 0
    match_ratio: float = 0.0
    skipped_reason_breakdown: dict[str, int] = None  # type: ignore
    normal_error_px: float = 0.0
    tangent_error_px: float = 0.0
    full_euclidean_error_px: float = 0.0
    failure_reasons: list[str] = None  # type: ignore


def layout_upright_frame_only(
    upright_bgr: np.ndarray,
    layout: OutputLayout,
    pad_color_bgr: tuple[int, int, int] = (20, 14, 10),
) -> np.ndarray:
    """僅將正向原片影格縮放並置入 OutputLayout（不疊加特效），作為像素差分基準。"""
    uh, uw = upright_bgr.shape[:2]
    scaled_w = int(round(uw * layout.scale))
    scaled_h = int(round(uh * layout.scale))

    if scaled_w == layout.output_width and scaled_h == layout.output_height and layout.pad_x == 0 and layout.pad_y == 0:
        return upright_bgr.copy()

    canvas = np.full((layout.output_height, layout.output_width, 3), pad_color_bgr, dtype=np.uint8)
    resized = cv2.resize(
        upright_bgr,
        (max(1, scaled_w), max(1, scaled_h)),
        interpolation=cv2.INTER_AREA if layout.scale < 1.0 else cv2.INTER_LINEAR,
    )
    x0 = max(0, int(round(layout.pad_x)))
    y0 = max(0, int(round(layout.pad_y)))
    x1 = min(layout.output_width, x0 + resized.shape[1])
    y1 = min(layout.output_height, y0 + resized.shape[0])
    canvas[y0:y1, x0:x1] = resized[: (y1 - y0), : (x1 - x0)]
    return canvas


def compose_output_frame(
    upright_bgr: np.ndarray,
    layout: OutputLayout,
    current_pts_us: int,
    recipe: RenderRecipeV1,
    swing_points: list[CanonicalTrackPoint],
    shot_points: list[CanonicalTrackPoint],
    top_pts_us: int | None = None,
    impact_pts_us: int | None = None,
    pad_color_bgr: tuple[int, int, int] = (20, 14, 10),
) -> np.ndarray:
    """
    將單張正向原片影格 (`upright_bgr`) 縮放並置入 `OutputLayout`，再疊加當下 `current_pts_us` 之雙軌特效。
    """
    canvas = layout_upright_frame_only(upright_bgr, layout, pad_color_bgr=pad_color_bgr)
    return render_tracer_layers_onto_bgr(
        canvas_bgr=canvas,
        layout=layout,
        current_pts_us=current_pts_us,
        recipe=recipe,
        swing_points=swing_points,
        shot_points=shot_points,
        top_pts_us=top_pts_us,
        impact_pts_us=impact_pts_us,
    )


def verify_preview_export_parity(
    points: list[CanonicalTrackPoint],
    layout: OutputLayout,
    fps: int,
    export_output_pts_us: list[int],
) -> ParityCheckReport:
    """
    驗證前端 Preview 投影座標與後端 Export 整數/浮點像素投影誤差 (`math_projection_parity`)，
    以及輸出 CFR 時間格點對齊度。
    注意：此函式僅測量數學投影量化誤差；真實 WebKit Canvas 與 MP4 解碼影格之像素比對請使用 `verify_actual_visual_pixel_parity`。
    """
    coord_errors: list[float] = []
    for pt in points:
        preview_x = layout.pad_x + pt.x_norm * (layout.upright_width * layout.scale)
        preview_y = layout.pad_y + pt.y_norm * (layout.upright_height * layout.scale)
        exp_x, exp_y = project_track_point_to_output_px(pt, layout)
        quant_x, quant_y = float(int(round(exp_x))), float(int(round(exp_y)))
        err = math.hypot(preview_x - quant_x, preview_y - quant_y)
        coord_errors.append(err)

    max_coord_err = round(max(coord_errors) if coord_errors else 0.0, 4)
    mean_coord_err = round(float(np.mean(coord_errors)) if coord_errors else 0.0, 4)

    frame_step_us = 1_000_000.0 / float(max(1, fps))
    pts_deltas: list[int] = []
    if export_output_pts_us and points:
        for pt in points:
            nearest_out = min(export_output_pts_us, key=lambda t: abs(t - pt.source_pts_us))
            pts_deltas.append(abs(nearest_out - pt.source_pts_us))

    max_pts_delta_us = max(pts_deltas) if pts_deltas else 0
    max_frame_delta = round(max_pts_delta_us / frame_step_us, 4)

    return ParityCheckReport(
        aspect_ratio=layout.target_aspect,
        fps=fps,
        checked_point_count=len(points),
        max_coordinate_error_px=max_coord_err,
        mean_coordinate_error_px=mean_coord_err,
        max_frame_pts_delta_us=max_pts_delta_us,
        max_frame_delta_frames=max_frame_delta,
        coordinate_parity_passed=(max_coord_err <= 2.0),
        pts_parity_passed=(max_frame_delta <= 1.0),
        parity_kind="math_projection_parity",
    )


def _compute_patch_color_similarity(
    c_patch: np.ndarray,
    m_patch: np.ndarray,
) -> tuple[bool, float]:
    """以 HSV 色度與灰階容差比對 Canvas 與 MP4 解碼影像之局部軌跡核心像素色彩一致性。"""
    c_mask = c_patch[:, :, 3] > 60 if (c_patch.ndim == 3 and c_patch.shape[2] == 4) else (np.max(c_patch, axis=2) > 40)
    if not np.any(c_mask):
        return True, 1.0

    c_rgb = c_patch[c_mask][:, :3]
    c_mean_bgr = np.mean(c_rgb, axis=0)
    # 取 MP4 解碼幀中對應畫線遮罩區域的前景平均色彩 (避免背景草地/地板顏色污染)
    m_mean_bgr = np.mean(m_patch[c_mask], axis=0)

    c_pix = np.uint8([[c_mean_bgr]])
    m_pix = np.uint8([[m_mean_bgr]])
    c_hsv = cv2.cvtColor(c_pix, cv2.COLOR_BGR2HSV)[0, 0]
    m_hsv = cv2.cvtColor(m_pix, cv2.COLOR_BGR2HSV)[0, 0]

    # 低飽和度（白/灰/黑）比對明度差距
    if c_hsv[1] < 40 and m_hsv[1] < 40:
        val_diff = abs(float(c_hsv[2]) - float(m_hsv[2]))
        return (val_diff <= 90.0), 1.0 - (val_diff / 255.0)

    hue_diff = abs(int(c_hsv[0]) - int(m_hsv[0]))
    if hue_diff > 90:
        hue_diff = 180 - hue_diff

    # Hue diff 在 180 度尺度下，差 35 度以內（即 360 度下差 70 度）視為同色系
    color_ok = (hue_diff <= 35)
    sim = 1.0 - (hue_diff / 90.0)
    return color_ok, sim


def verify_actual_visual_pixel_parity(
    *,
    pts_us: int,
    export_frame_index: int,
    export_frame_pts_us: int,
    fps: int,
    canvas_rgba: np.ndarray,
    exported_mp4_bgr: np.ndarray,
    raw_upright_bgr: np.ndarray,
    layout: OutputLayout,
    active_points: list[CanonicalTrackPoint],
    expect_artistic_dashed: bool = False,
) -> ActualVisualParityCheckpoint:
    """
    P0-2 & P0-B 真實像素級視覺一致性驗證 (`actual_visual_pixel_parity`)：
    直接比對 WebKit Canvas 實際渲染之 RGBA 像素圖層與 FFmpeg 解碼後之 MP4 影格，
    嚴格強制：
    1. 軌跡中心線峰值於法向量截面上的真實像素偏移 (`max_centerline_offset_px_1080p <= 2.0 px`)
    2. 切向誤差與全歐幾里得距離監控 (`tangent_error_px`, `full_euclidean_error_px`)
    3. 出現/消失時間差 (`frame_delta_frames <= 1.0`)
    4. 最低覆蓋與有效匹配率防呆 (無有效匹配點或低於門檻時嚴格 FAIL)
    5. HSV 色彩空間真實色系檢驗 (杜絕上下桿色彩顛倒冒充通過)
    6. 雙向虛線斷續特徵檢驗 (Canvas 與 MP4 均需測得 Dash 峰值與 Gap 谷底)
    """
    base_bgr = layout_upright_frame_only(raw_upright_bgr, layout)
    out_h, out_w = exported_mp4_bgr.shape[:2]

    if canvas_rgba.shape[:2] != (out_h, out_w):
        canvas_rgba = cv2.resize(canvas_rgba, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

    # WebKit Canvas 特效強度圖 (Alpha 通道或 RGB 亮度)
    if canvas_rgba.shape[2] == 4:
        canvas_intensity = canvas_rgba[:, :, 3].astype(np.float32)
    else:
        canvas_intensity = np.max(canvas_rgba.astype(np.float32), axis=2)

    # MP4 解碼影格與乾淨原片之像素差分強度圖
    diff_bgr = np.abs(exported_mp4_bgr.astype(np.float32) - base_bgr.astype(np.float32))
    mp4_intensity = np.max(diff_bgr, axis=2)

    canvas_fx_px = int(np.count_nonzero(canvas_intensity > 20.0))
    mp4_fx_px = int(np.count_nonzero(mp4_intensity > 18.0))

    scale_to_1080p = 1080.0 / float(max(1, min(out_w, out_h)))

    visible_pts = [
        p
        for p in active_points
        if p.source_pts_us <= export_frame_pts_us
        and (
            p.track_type.value == "ball"
            or (export_frame_pts_us - p.source_pts_us) <= 950_000
        )
    ]

    coords = [project_upright_norm_to_output_px(p.x_norm, p.y_norm, layout) for p in visible_pts]

    normal_offsets_1080p: list[float] = []
    tangent_offsets_1080p: list[float] = []
    euclidean_offsets_1080p: list[float] = []
    color_matches: list[bool] = []
    fail_reasons: list[str] = []

    skipped_breakdown = {
        "out_of_bounds": 0,
        "low_canvas_energy": 0,
        "low_mp4_energy": 0,
        "artistic_gap": 0,
        "low_weight_sum": 0,
    }

    eligible_count = 0
    r = 4

    for idx in range(len(visible_pts)):
        pt = visible_pts[idx]
        px, py = coords[idx]
        ix, iy = int(round(px)), int(round(py))
        if not (6 <= ix < out_w - 6 and 6 <= iy < out_h - 6):
            skipped_breakdown["out_of_bounds"] += 1
            continue

        eligible_count += 1

        # 局部 9x9 視窗內求取 WebKit Canvas 與 MP4 差分圖之質心/峰值座標
        c_patch = canvas_intensity[iy - r : iy + r + 1, ix - r : ix + r + 1]
        m_patch = mp4_intensity[iy - r : iy + r + 1, ix - r : ix + r + 1]
        c_max = float(np.max(c_patch))
        m_max = float(np.max(m_patch))

        if c_max < 15.0:
            skipped_breakdown["low_canvas_energy"] += 1
            continue
        if m_max < 12.0:
            skipped_breakdown["low_mp4_energy"] += 1
            continue

        # 藝術延伸段為虛線，若該點中心處落在 gap (無直接線條能量)，略過其質心偏移比對
        if pt.source_type.value == "artistic_only":
            c_center = float(np.max(c_patch[r - 1 : r + 2, r - 1 : r + 2]))
            m_center = float(np.max(m_patch[r - 1 : r + 2, r - 1 : r + 2]))
            if c_center < 14.0 or m_center < 10.0:
                skipped_breakdown["artistic_gap"] += 1
                continue

        cy_grid, cx_grid = np.mgrid[-r : r + 1, -r : r + 1]
        c_weights = np.maximum(0.0, c_patch - 12.0)
        m_weights = np.maximum(0.0, m_patch - 10.0)
        c_sum = float(np.sum(c_weights))
        m_sum = float(np.sum(m_weights))
        if c_sum <= 1e-3 or m_sum <= 1e-3:
            skipped_breakdown["low_weight_sum"] += 1
            continue

        c_dx = float(np.sum(cx_grid * c_weights)) / c_sum
        c_dy = float(np.sum(cy_grid * c_weights)) / c_sum
        m_dx = float(np.sum(cx_grid * m_weights)) / m_sum
        m_dy = float(np.sum(cy_grid * m_weights)) / m_sum

        diff_x = c_dx - m_dx
        diff_y = c_dy - m_dy
        euc_dist = math.hypot(diff_x, diff_y) * scale_to_1080p
        euclidean_offsets_1080p.append(euc_dist)

        # 計算局部軌跡切線 T 與法向量 N，將質心位移差向量投影至法向量與切線向量
        prev_c = coords[max(0, idx - 1)]
        next_c = coords[min(len(coords) - 1, idx + 1)]
        tx = next_c[0] - prev_c[0]
        ty = next_c[1] - prev_c[1]
        t_len = math.hypot(tx, ty)
        if t_len > 1e-3:
            unit_tx = tx / t_len
            unit_ty = ty / t_len
            unit_nx = -unit_ty
            unit_ny = unit_tx
            norm_offset = abs(diff_x * unit_nx + diff_y * unit_ny) * scale_to_1080p
            tang_offset = abs(diff_x * unit_tx + diff_y * unit_ty) * scale_to_1080p
        else:
            norm_offset = euc_dist
            tang_offset = 0.0

        normal_offsets_1080p.append(norm_offset)
        tangent_offsets_1080p.append(tang_offset)

        # 色彩檢驗：取 WebKit Canvas 與 MP4 解碼影格之真實像素色彩 (非底圖差分殘差)
        c_patch_color = canvas_rgba[iy - r : iy + r + 1, ix - r : ix + r + 1]
        m_patch_color = exported_mp4_bgr[iy - r : iy + r + 1, ix - r : ix + r + 1]
        c_ok, _ = _compute_patch_color_similarity(c_patch_color, m_patch_color)
        color_matches.append(c_ok)

    matched_count = len(normal_offsets_1080p)
    unmatched_count = max(0, eligible_count - matched_count)
    match_ratio = round(matched_count / float(eligible_count), 4) if eligible_count > 0 else 0.0

    # P0-B 覆蓋率與有效匹配檢驗
    coverage_ok = True
    if eligible_count > 0:
        # 預期有軌跡點：匹配數至少 >= 1；若可測點 >= 4，匹配率需 >= 35% (考慮虛線 gap 等合理排除)
        min_required_matches = 1 if eligible_count < 4 else max(2, int(round(eligible_count * 0.35)))
        if matched_count < min_required_matches:
            coverage_ok = False
            fail_reasons.append(
                f"有效匹配點數不足: matched={matched_count} < min_required={min_required_matches} (eligible={eligible_count}, ratio={match_ratio:.1%})"
            )
    else:
        # 預期無軌跡點：反向驗證畫面不得有偽畫線像素
        if canvas_fx_px > 50 or mp4_fx_px > 50:
            coverage_ok = False
            fail_reasons.append(
                f"預期無軌跡點但檢出偽特效殘留: Canvas={canvas_fx_px}px, MP4={mp4_fx_px}px"
            )

    # 統計最大誤差：若預期有點卻 0 匹配，給予 999.0 懲罰，絕不偽稱 0.0
    if matched_count > 0:
        max_offset = round(max(normal_offsets_1080p), 4)
        mean_offset = round(float(np.mean(normal_offsets_1080p)), 4)
        normal_err = max_offset
        tangent_err = round(max(tangent_offsets_1080p), 4)
        euc_err = round(max(euclidean_offsets_1080p), 4)
    elif eligible_count > 0:
        max_offset = 999.0
        mean_offset = 999.0
        normal_err = 999.0
        tangent_err = 999.0
        euc_err = 999.0
    else:
        max_offset = 0.0
        mean_offset = 0.0
        normal_err = 0.0
        tangent_err = 0.0
        euc_err = 0.0

    frame_step_us = 1_000_000.0 / float(max(1, fps))
    frame_delta = round(abs(export_frame_pts_us - pts_us) / frame_step_us, 4)
    if frame_delta > 1.0:
        fail_reasons.append(f"影格時間差超出門檻: delta={frame_delta:.2f} 幀 > 1.0 幀")

    if max_offset > 2.0:
        fail_reasons.append(f"中心線法向偏移超出門檻: offset={max_offset:.4f}px > 2.0px")

    # 驗證階段顏色一致性
    phase_ok = True
    if eligible_count > 0:
        if not color_matches or (sum(color_matches) / float(len(color_matches))) < 0.60:
            phase_ok = False
            fail_reasons.append("階段顏色一致性未達標: 前後端色系色差過大或色彩顛倒")

    # 驗證藝術延伸段是否呈現虛線 (沿藝術段採樣雙向檢驗亮暗交替)
    artistic_ok = True
    if expect_artistic_dashed:
        expected_art_pts = [p for p in visible_pts if p.source_type.value == "artistic_only"]
        # 僅當當前影格進度已涵蓋藝術延伸段時才執行虛線交替驗證
        if len(expected_art_pts) >= 2:
            p0 = project_upright_norm_to_output_px(expected_art_pts[0].x_norm, expected_art_pts[0].y_norm, layout)
            p1 = project_upright_norm_to_output_px(expected_art_pts[-1].x_norm, expected_art_pts[-1].y_norm, layout)
            c_samples: list[float] = []
            m_samples: list[float] = []
            for s in range(40):
                t = s / 39.0
                sx = int(round(p0[0] + (p1[0] - p0[0]) * t))
                sy = int(round(p0[1] + (p1[1] - p0[1]) * t))
                if 1 <= sx < out_w - 1 and 1 <= sy < out_h - 1:
                    c_samples.append(float(np.max(canvas_intensity[sy - 1 : sy + 2, sx - 1 : sx + 2])))
                    m_samples.append(float(np.max(mp4_intensity[sy - 1 : sy + 2, sx - 1 : sx + 2])))
            p_dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if p_dist >= 150.0:
                c_high = sum(1 for v in c_samples if v > 35.0)
                c_low = sum(1 for v in c_samples if v < 18.0)
                m_high = sum(1 for v in m_samples if v > 25.0)
                m_low = sum(1 for v in m_samples if v < 14.0)
                c_dashed = (c_high >= 2) and (c_low >= 2)
                m_dashed = (m_high >= 2) and (m_low >= 2)
                artistic_ok = c_dashed and m_dashed
                if not artistic_ok:
                    fail_reasons.append(
                        f"藝術段未呈現虛線交替: Canvas(h={c_high},l={c_low}), MP4(h={m_high},l={m_low})"
                    )

    passed = (
        coverage_ok
        and max_offset <= 2.0
        and frame_delta <= 1.0
        and phase_ok
        and artistic_ok
    )

    return ActualVisualParityCheckpoint(
        pts_us=pts_us,
        export_frame_index=export_frame_index,
        export_frame_pts_us=export_frame_pts_us,
        frame_delta_frames=frame_delta,
        active_point_count=len(visible_pts),
        max_centerline_offset_px_1080p=max_offset,
        mean_centerline_offset_px_1080p=mean_offset,
        canvas_fx_pixel_count=canvas_fx_px,
        mp4_fx_pixel_count=mp4_fx_px,
        phase_color_verified=phase_ok,
        artistic_dashed_verified=artistic_ok,
        passed=passed,
        parity_kind="actual_visual_pixel_parity",
        eligible_point_count=eligible_count,
        matched_point_count=matched_count,
        unmatched_count=unmatched_count,
        match_ratio=match_ratio,
        skipped_reason_breakdown=skipped_breakdown,
        normal_error_px=normal_err,
        tangent_error_px=tangent_err,
        full_euclidean_error_px=euc_err,
        failure_reasons=fail_reasons,
    )
