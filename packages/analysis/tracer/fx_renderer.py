"""
Golf Tracer Studio R4 — Deterministic Multi-Pass Flight FX Renderer (`fx_renderer.py`).
負責於輸出畫布座標空間 (`OutputLayout`) 繪製 `Swing Tracer` 與 `Shot Tracer` 圖層：
- 支援 6 種風格：`Clean`, `Neon`, `Beam`, `Gradient`, `Tail`, `Pulse`
- 支援 Swing 三階段自動分色 (`backswing`, `downswing`, `follow_through`)
- 支援證據透明度視覺區分：非直接觀測點 (`kalman_predicted`, `optical_flow_estimated`, `interpolated`, `artistic_only`)
  自動以虛線或降透明度呈現，絕不將推估或藝術延伸混充實線實測
- 所有線寬與光暈半徑皆透過 `scale_width_at_1080(layout, width)` 嚴格對齊前端 Canvas 預覽
"""

import math
from typing import Any

import cv2
import numpy as np

from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    TrackSourceType,
)
from packages.analysis.tracer.fx_schema import (
    RenderRecipeV1,
    ShotTracerLayerConfig,
    SwingTracerLayerConfig,
    TracerStyleName,
    blend_bgr,
    parse_hex_to_bgr,
)
from packages.analysis.tracer.interpolation import catmull_rom_subdivide
from packages.analysis.tracer.transforms import (
    OutputLayout,
    project_upright_norm_to_output_px,
    scale_width_at_1080,
)

DIRECT_PROVENANCE_TYPES = {
    TrackSourceType.DETECTOR_OBSERVED,
    TrackSourceType.MANUALLY_ANNOTATED,
}


def project_track_point_to_output_px(
    pt: CanonicalTrackPoint,
    layout: OutputLayout,
) -> tuple[float, float]:
    """將單一 `CanonicalTrackPoint` 投影至輸出畫布像素座標 `(x_px, y_px)`。"""
    return project_upright_norm_to_output_px(pt.x_norm, pt.y_norm, layout)


def render_tracer_layers_onto_bgr(
    canvas_bgr: np.ndarray,
    layout: OutputLayout,
    current_pts_us: int,
    recipe: RenderRecipeV1,
    swing_points: list[CanonicalTrackPoint],
    shot_points: list[CanonicalTrackPoint],
    top_pts_us: int | None = None,
    impact_pts_us: int | None = None,
) -> np.ndarray:
    """
    將當下時間戳 (`current_pts_us`) 可見之 `swing_points` 與 `shot_points`
    依 `RenderRecipeV1` 合成至 `canvas_bgr` 並回傳合成後 BGR 影像。
    """
    out = canvas_bgr.copy()

    if recipe.swing_tracer.enabled and swing_points:
        visible_swing = [p for p in swing_points if p.source_pts_us <= current_pts_us]
        if visible_swing:
            out = _render_swing_tracer_layer(
                canvas_bgr=out,
                layout=layout,
                current_pts_us=current_pts_us,
                cfg=recipe.swing_tracer,
                points=visible_swing,
                top_pts_us=top_pts_us,
                impact_pts_us=impact_pts_us,
            )

    if recipe.shot_tracer.enabled and shot_points:
        visible_shot = [p for p in shot_points if p.source_pts_us <= current_pts_us]
        if visible_shot:
            out = _render_shot_tracer_layer(
                canvas_bgr=out,
                layout=layout,
                current_pts_us=current_pts_us,
                cfg=recipe.shot_tracer,
                points=visible_shot,
                all_shot_points=shot_points,
                impact_pts_us=impact_pts_us,
            )

    return out


def _resolve_swing_phase_bgr(phase: str, cfg: SwingTracerLayerConfig) -> tuple[int, int, int]:
    p = (phase or "").lower()
    if p in ("address", "takeaway", "backswing", "top"):
        return parse_hex_to_bgr(cfg.backswing_color_hex)
    if p in ("downswing", "impact"):
        return parse_hex_to_bgr(cfg.downswing_color_hex)
    return parse_hex_to_bgr(cfg.follow_through_color_hex)


def _render_swing_tracer_layer(
    canvas_bgr: np.ndarray,
    layout: OutputLayout,
    current_pts_us: int,
    cfg: SwingTracerLayerConfig,
    points: list[CanonicalTrackPoint],
    top_pts_us: int | None,
    impact_pts_us: int | None,
) -> np.ndarray:
    h, w = canvas_bgr.shape[:2]
    core_layer = np.zeros((h, w, 3), dtype=np.float32)
    alpha_layer = np.zeros((h, w), dtype=np.float32)
    glow_layer = np.zeros((h, w, 3), dtype=np.float32)

    base_core_w = max(1, scale_width_at_1080(layout, cfg.core_width_px_at_1080))
    base_glow_r = scale_width_at_1080(layout, cfg.glow_radius_px_at_1080)
    tail_decay_us = max(100_000, cfg.tail_decay_ms * 1000)

    projected = [project_track_point_to_output_px(p, layout) for p in points]

    # 1. 若啟用不確定度帶，先繪製半透明誤差圈
    if cfg.show_uncertainty_band:
        for pt, (px, py) in zip(points, projected):
            rad = max(2, scale_width_at_1080(layout, min(28.0, pt.uncertainty_px)))
            col = _resolve_swing_phase_bgr(pt.phase, cfg)
            cv2.circle(glow_layer, (int(round(px)), int(round(py))), rad, col, -1, cv2.LINE_AA)

    # 2. 逐段繪製軌跡線段
    n = len(points)
    for i in range(n - 1):
        p1, p2 = points[i], points[i + 1]
        xy1, xy2 = projected[i], projected[i + 1]

        age_us = max(0, current_pts_us - p2.source_pts_us)
        if cfg.style == TracerStyleName.TAIL and age_us > tail_decay_us:
            continue

        tail_factor = (
            max(0.08, 1.0 - (age_us / float(tail_decay_us)))
            if cfg.style == TracerStyleName.TAIL
            else max(0.28, 1.0 - 0.55 * (age_us / float(max(tail_decay_us, 1_500_000))))
        )

        col1 = _resolve_swing_phase_bgr(p1.phase, cfg)
        col2 = _resolve_swing_phase_bgr(p2.phase, cfg)
        seg_col = blend_bgr(col1, col2, 0.5)
        if cfg.style == TracerStyleName.GRADIENT:
            prog = i / float(max(1, n - 1))
            seg_col = blend_bgr(parse_hex_to_bgr(cfg.backswing_color_hex), parse_hex_to_bgr(cfg.downswing_color_hex), prog)

        is_predicted = (
            p1.source_type not in DIRECT_PROVENANCE_TYPES
            or p2.source_type not in DIRECT_PROVENANCE_TYPES
        )
        if cfg.show_predicted_dashed and is_predicted and (i % 2 == 1):
            continue

        seg_alpha = cfg.opacity * tail_factor * (0.68 if is_predicted else 1.0)
        seg_width = max(1, int(round(base_core_w * (0.55 + 0.45 * tail_factor))))

        pt1_i = (int(round(xy1[0])), int(round(xy1[1])))
        pt2_i = (int(round(xy2[0])), int(round(xy2[1])))

        cv2.line(core_layer, pt1_i, pt2_i, seg_col, seg_width, cv2.LINE_AA)
        cv2.line(alpha_layer, pt1_i, pt2_i, float(seg_alpha), seg_width, cv2.LINE_AA)

        if cfg.style in (TracerStyleName.NEON, TracerStyleName.BEAM, TracerStyleName.PULSE) and base_glow_r > 0:
            glow_w = max(seg_width + 2, int(round(seg_width * 2.2)))
            cv2.line(glow_layer, pt1_i, pt2_i, seg_col, glow_w, cv2.LINE_AA)
            if cfg.style == TracerStyleName.BEAM:
                inner_w = max(1, seg_width // 2)
                cv2.line(core_layer, pt1_i, pt2_i, (255, 255, 255), inner_w, cv2.LINE_AA)

    # 3. 繪製 Top 與 Impact 關鍵節點標記
    if cfg.show_top_marker and top_pts_us is not None:
        top_pt = _find_closest_point(points, top_pts_us, max_delta_us=65_000)
        if top_pt is not None:
            tx, ty = project_track_point_to_output_px(top_pt, layout)
            r_top = max(5, scale_width_at_1080(layout, 9.0))
            col_top = parse_hex_to_bgr(cfg.backswing_color_hex)
            cv2.circle(core_layer, (int(round(tx)), int(round(ty))), r_top, col_top, 2, cv2.LINE_AA)
            cv2.circle(alpha_layer, (int(round(tx)), int(round(ty))), r_top + 2, float(cfg.opacity), -1, cv2.LINE_AA)

    if cfg.show_impact_marker and impact_pts_us is not None:
        imp_pt = _find_closest_point(points, impact_pts_us, max_delta_us=65_000)
        if imp_pt is not None:
            ix, iy = project_track_point_to_output_px(imp_pt, layout)
            r_imp = max(6, scale_width_at_1080(layout, 11.0))
            col_imp = parse_hex_to_bgr(cfg.downswing_color_hex)
            cv2.circle(core_layer, (int(round(ix)), int(round(iy))), r_imp, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(glow_layer, (int(round(ix)), int(round(iy))), r_imp * 2, col_imp, -1, cv2.LINE_AA)
            cv2.circle(alpha_layer, (int(round(ix)), int(round(iy))), r_imp + 2, float(cfg.opacity), -1, cv2.LINE_AA)

    return _composite_glow_and_core(
        base_bgr=canvas_bgr,
        core_layer=core_layer,
        alpha_layer=alpha_layer,
        glow_layer=glow_layer,
        glow_radius_px=base_glow_r if cfg.style != TracerStyleName.CLEAN else 0,
        glow_intensity=cfg.glow_intensity if cfg.style != TracerStyleName.CLEAN else 0.0,
    )


def _render_shot_tracer_layer(
    canvas_bgr: np.ndarray,
    layout: OutputLayout,
    current_pts_us: int,
    cfg: ShotTracerLayerConfig,
    points: list[CanonicalTrackPoint],
    all_shot_points: list[CanonicalTrackPoint],
    impact_pts_us: int | None,
) -> np.ndarray:
    h, w = canvas_bgr.shape[:2]
    core_layer = np.zeros((h, w, 3), dtype=np.float32)
    alpha_layer = np.zeros((h, w), dtype=np.float32)
    glow_layer = np.zeros((h, w, 3), dtype=np.float32)

    base_core_w = max(1, scale_width_at_1080(layout, cfg.core_width_px_at_1080))
    base_glow_r = scale_width_at_1080(layout, cfg.glow_radius_px_at_1080)
    tail_decay_us = max(150_000, cfg.tail_decay_ms * 1000)

    col_primary = parse_hex_to_bgr(cfg.primary_color_hex)
    col_secondary = parse_hex_to_bgr(cfg.secondary_color_hex)

    # 將實測/估算點與藝術延伸點拆開渲染，確保藝術延伸段永遠為虛線標示
    non_artistic = [p for p in points if p.source_type != TrackSourceType.ARTISTIC_ONLY]
    artistic_only = [p for p in points if p.source_type == TrackSourceType.ARTISTIC_ONLY]

    if len(non_artistic) >= 2:
        raw_xy = [project_track_point_to_output_px(p, layout) for p in non_artistic]
        smooth_xy = catmull_rom_subdivide(raw_xy, subdivisions_per_segment=6)
        m = len(smooth_xy)
        t_sec = current_pts_us / 1_000_000.0

        for j in range(m - 1):
            prog = j / float(max(1, m - 1))
            orig_idx = min(len(non_artistic) - 1, int(prog * len(non_artistic)))
            ref_pt = non_artistic[orig_idx]

            age_us = max(0, current_pts_us - ref_pt.source_pts_us)
            if cfg.style == TracerStyleName.TAIL and age_us > tail_decay_us:
                continue

            is_pred = ref_pt.source_type not in DIRECT_PROVENANCE_TYPES
            if cfg.show_predicted_dashed and is_pred and (j % 3 == 1):
                continue

            # 錐度 (Taper): 起飛端略細 -> 中段飽滿 -> 飛行前端收尖
            taper = cfg.taper_start_ratio + (1.0 - cfg.taper_start_ratio) * math.sin(prog * math.pi)
            if prog > 0.85:
                taper *= cfg.taper_end_ratio + (1.0 - cfg.taper_end_ratio) * ((1.0 - prog) / 0.15)

            seg_w = max(1, int(round(base_core_w * max(0.35, taper))))
            seg_col = blend_bgr(col_primary, col_secondary, prog)

            pulse_boost = 1.0
            if cfg.style == TracerStyleName.PULSE:
                wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * (prog * 3.0 - cfg.pulse_speed_hz * t_sec))
                pulse_boost = 0.65 + 0.55 * wave
                seg_col = blend_bgr(seg_col, (255, 255, 255), 0.35 * wave)

            p1_i = (int(round(smooth_xy[j][0])), int(round(smooth_xy[j][1])))
            p2_i = (int(round(smooth_xy[j + 1][0])), int(round(smooth_xy[j + 1][1])))

            seg_alpha = min(1.0, cfg.opacity * pulse_boost * (0.72 if is_pred else 1.0))
            cv2.line(core_layer, p1_i, p2_i, seg_col, seg_w, cv2.LINE_AA)
            cv2.line(alpha_layer, p1_i, p2_i, float(seg_alpha), seg_w, cv2.LINE_AA)

            if cfg.style != TracerStyleName.CLEAN and base_glow_r > 0:
                cv2.line(glow_layer, p1_i, p2_i, seg_col, max(seg_w + 2, int(round(seg_w * 2.4))), cv2.LINE_AA)
                if cfg.style == TracerStyleName.BEAM:
                    cv2.line(core_layer, p1_i, p2_i, (255, 255, 255), max(1, seg_w // 2), cv2.LINE_AA)

    # 若有藝術延伸段 (`artistic_only`)，強制以半透明虛線繪製
    if artistic_only:
        chain_pts = ([non_artistic[-1]] if non_artistic else []) + artistic_only
        art_xy = [project_track_point_to_output_px(p, layout) for p in chain_pts]
        for k in range(len(art_xy) - 1):
            if k % 2 == 1:
                continue
            p1_i = (int(round(art_xy[k][0])), int(round(art_xy[k][1])))
            p2_i = (int(round(art_xy[k + 1][0])), int(round(art_xy[k + 1][1])))
            art_w = max(1, int(round(base_core_w * 0.65)))
            cv2.line(core_layer, p1_i, p2_i, col_secondary, art_w, cv2.LINE_AA)
            cv2.line(alpha_layer, p1_i, p2_i, float(cfg.opacity * 0.55), art_w, cv2.LINE_AA)

    # 繪製起飛擊球閃光 (Impact Flash)
    if cfg.show_impact_flash and points:
        launch_pt = points[0]
        if abs(current_pts_us - launch_pt.source_pts_us) <= 180_000:
            lx, ly = project_track_point_to_output_px(launch_pt, layout)
            flash_r = max(6, scale_width_at_1080(layout, 14.0))
            cv2.circle(glow_layer, (int(round(lx)), int(round(ly))), flash_r * 2, col_primary, -1, cv2.LINE_AA)
            cv2.circle(core_layer, (int(round(lx)), int(round(ly))), flash_r // 2, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(alpha_layer, (int(round(lx)), int(round(ly))), flash_r, float(cfg.opacity), -1, cv2.LINE_AA)

    # 繪製最高點標記 (Apex Marker)
    if cfg.show_apex_marker and len(all_shot_points) >= 3:
        apex_pt = min(all_shot_points, key=lambda p: p.y_norm)
        if current_pts_us >= apex_pt.source_pts_us:
            ax, ay = project_track_point_to_output_px(apex_pt, layout)
            apex_r = max(5, scale_width_at_1080(layout, 8.0))
            cv2.circle(core_layer, (int(round(ax)), int(round(ay))), apex_r, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(alpha_layer, (int(round(ax)), int(round(ay))), apex_r + 2, float(cfg.opacity), -1, cv2.LINE_AA)

    # 繪製落點光環 (Landing Ring — 僅在已抵達最後點時顯示)
    if cfg.show_landing_ring and all_shot_points and current_pts_us >= all_shot_points[-1].source_pts_us:
        end_pt = all_shot_points[-1]
        ex, ey = project_track_point_to_output_px(end_pt, layout)
        ring_w = max(8, scale_width_at_1080(layout, 16.0))
        ring_h = max(4, scale_width_at_1080(layout, 7.0))
        cv2.ellipse(
            core_layer,
            (int(round(ex)), int(round(ey))),
            (ring_w, ring_h),
            0.0,
            0.0,
            360.0,
            col_secondary,
            2,
            cv2.LINE_AA,
        )
        cv2.ellipse(
            alpha_layer,
            (int(round(ex)), int(round(ey))),
            (ring_w + 2, ring_h + 2),
            0.0,
            0.0,
            360.0,
            float(cfg.opacity * 0.85),
            2,
            cv2.LINE_AA,
        )

    return _composite_glow_and_core(
        base_bgr=canvas_bgr,
        core_layer=core_layer,
        alpha_layer=alpha_layer,
        glow_layer=glow_layer,
        glow_radius_px=base_glow_r if cfg.style != TracerStyleName.CLEAN else 0,
        glow_intensity=cfg.glow_intensity if cfg.style != TracerStyleName.CLEAN else 0.0,
    )


def _find_closest_point(
    points: list[CanonicalTrackPoint],
    target_pts_us: int,
    max_delta_us: int = 65_000,
) -> CanonicalTrackPoint | None:
    if not points:
        return None
    best = min(points, key=lambda p: abs(p.source_pts_us - target_pts_us))
    if abs(best.source_pts_us - target_pts_us) <= max_delta_us:
        return best
    return None


def _composite_glow_and_core(
    base_bgr: np.ndarray,
    core_layer: np.ndarray,
    alpha_layer: np.ndarray,
    glow_layer: np.ndarray,
    glow_radius_px: int,
    glow_intensity: float,
) -> np.ndarray:
    out_f = base_bgr.astype(np.float32)

    if glow_radius_px > 0 and glow_intensity > 0.01 and np.any(glow_layer > 0):
        ksize = int(glow_radius_px) * 2 + 1
        if ksize % 2 == 0:
            ksize += 1
        blurred_glow = cv2.GaussianBlur(glow_layer, (ksize, ksize), sigmaX=0.0)
        out_f = np.clip(out_f + blurred_glow * float(glow_intensity), 0.0, 255.0)

    mask_3d = np.clip(alpha_layer[:, :, None], 0.0, 1.0)
    out_f = out_f * (1.0 - mask_3d) + core_layer * mask_3d
    return np.clip(out_f, 0.0, 255.0).astype(np.uint8)
