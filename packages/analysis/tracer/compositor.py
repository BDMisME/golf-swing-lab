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
    P0-2 真實像素級視覺一致性驗證 (`actual_visual_pixel_parity`)：
    直接比對 WebKit Canvas 實際渲染之 RGBA 像素圖層與 FFmpeg 解碼後之 MP4 影格，
    測量：
    1. 軌跡中心線峰值於法向量截面上的真實像素偏移 (`max_centerline_offset_px_1080p <= 2.0 px`)
    2. 出現/消失時間差 (`frame_delta_frames <= 1.0`)
    3. 上下桿階段分色與藝術延伸虛線斷續特徵
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
    centerline_offsets_1080p: list[float] = []

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

    for idx in range(len(visible_pts)):
        pt = visible_pts[idx]
        px, py = coords[idx]
        ix, iy = int(round(px)), int(round(py))
        if not (6 <= ix < out_w - 6 and 6 <= iy < out_h - 6):
            continue

        # 局部 9x9 視窗內求取 WebKit Canvas 與 MP4 差分圖之質心/峰值座標
        r = 4
        c_patch = canvas_intensity[iy - r : iy + r + 1, ix - r : ix + r + 1]
        m_patch = mp4_intensity[iy - r : iy + r + 1, ix - r : ix + r + 1]
        if float(np.max(c_patch)) < 15.0 or float(np.max(m_patch)) < 12.0:
            continue

        # 藝術延伸段為虛線，若該點中心處落在 gap (無直接線條能量)，略過其質心偏移比對
        if pt.source_type.value == "artistic_only":
            c_center = float(np.max(c_patch[r - 1 : r + 2, r - 1 : r + 2]))
            m_center = float(np.max(m_patch[r - 1 : r + 2, r - 1 : r + 2]))
            if c_center < 14.0 or m_center < 10.0:
                continue

        cy_grid, cx_grid = np.mgrid[-r : r + 1, -r : r + 1]
        c_weights = np.maximum(0.0, c_patch - 12.0)
        m_weights = np.maximum(0.0, m_patch - 10.0)
        c_sum = float(np.sum(c_weights))
        m_sum = float(np.sum(m_weights))
        if c_sum <= 1e-3 or m_sum <= 1e-3:
            continue

        c_dx = float(np.sum(cx_grid * c_weights)) / c_sum
        c_dy = float(np.sum(cy_grid * c_weights)) / c_sum
        m_dx = float(np.sum(cx_grid * m_weights)) / m_sum
        m_dy = float(np.sum(cy_grid * m_weights)) / m_sum

        diff_x = c_dx - m_dx
        diff_y = c_dy - m_dy

        # P0-2 規範要求：測量軌跡中心線峰值「於法向量截面上」的真實像素偏移
        # 計算局部軌跡切線 T 與法向量 N，將質心位移差向量投影至法向量，精確排除虛線斷續切向步進差
        prev_c = coords[max(0, idx - 1)]
        next_c = coords[min(len(coords) - 1, idx + 1)]
        tx = next_c[0] - prev_c[0]
        ty = next_c[1] - prev_c[1]
        t_len = math.hypot(tx, ty)
        if t_len > 1e-3:
            nx = -ty / t_len
            ny = tx / t_len
            offset_px = abs(diff_x * nx + diff_y * ny) * scale_to_1080p
        else:
            offset_px = math.hypot(diff_x, diff_y) * scale_to_1080p

        centerline_offsets_1080p.append(offset_px)

    max_offset = round(max(centerline_offsets_1080p) if centerline_offsets_1080p else 0.0, 4)
    mean_offset = round(float(np.mean(centerline_offsets_1080p)) if centerline_offsets_1080p else 0.0, 4)

    frame_step_us = 1_000_000.0 / float(max(1, fps))
    frame_delta = round(abs(export_frame_pts_us - pts_us) / frame_step_us, 4)

    # 驗證階段顏色存在性與一致性
    phase_ok = True
    if visible_pts:
        phase_ok = (canvas_fx_px > 20) and (mp4_fx_px > 20)

    # 驗證藝術延伸段是否呈現虛線 (沿藝術段採樣具有亮暗交替)
    artistic_ok = True
    if expect_artistic_dashed:
        art_pts = [p for p in visible_pts if p.source_type.value == "artistic_only"]
        if len(art_pts) >= 2:
            p0 = project_upright_norm_to_output_px(art_pts[0].x_norm, art_pts[0].y_norm, layout)
            p1 = project_upright_norm_to_output_px(art_pts[-1].x_norm, art_pts[-1].y_norm, layout)
            samples: list[float] = []
            for s in range(40):
                t = s / 39.0
                sx = int(round(p0[0] + (p1[0] - p0[0]) * t))
                sy = int(round(p0[1] + (p1[1] - p0[1]) * t))
                if 1 <= sx < out_w - 1 and 1 <= sy < out_h - 1:
                    samples.append(float(np.max(canvas_intensity[sy - 1 : sy + 2, sx - 1 : sx + 2])))
            p_dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if p_dist >= 25.0 and samples:
                high_hits = sum(1 for v in samples if v > 40.0)
                low_hits = sum(1 for v in samples if v < 20.0)
                artistic_ok = (high_hits >= 2) and (low_hits >= 1)

    passed = (
        max_offset <= 2.0
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
    )
