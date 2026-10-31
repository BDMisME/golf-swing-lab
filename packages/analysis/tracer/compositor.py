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
    """Preview 與 Export 對齊驗證報告。"""

    aspect_ratio: str
    fps: int
    checked_point_count: int
    max_coordinate_error_px: float
    mean_coordinate_error_px: float
    max_frame_pts_delta_us: int
    max_frame_delta_frames: float
    coordinate_parity_passed: bool
    pts_parity_passed: bool


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
    uh, uw = upright_bgr.shape[:2]
    scaled_w = int(round(uw * layout.scale))
    scaled_h = int(round(uh * layout.scale))

    if scaled_w == layout.output_width and scaled_h == layout.output_height and layout.pad_x == 0 and layout.pad_y == 0:
        canvas = upright_bgr.copy()
    else:
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
    驗證前端 Preview 投影座標與後端 Export 整數/浮點像素投影誤差，以及輸出 CFR 時間格點對齊度。
    契約門檻：
    - `max_coordinate_error_px <= 2.0`
    - `max_frame_delta_frames <= 1.0`
    """
    coord_errors: list[float] = []
    for pt in points:
        # 前端 Canvas 浮點投影公式
        preview_x = layout.pad_x + pt.x_norm * (layout.upright_width * layout.scale)
        preview_y = layout.pad_y + pt.y_norm * (layout.upright_height * layout.scale)
        # 後端渲染器投影公式 (連同 OpenCV 整數像素量化誤差)
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
    )
