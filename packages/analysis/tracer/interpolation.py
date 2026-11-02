"""
Golf Tracer Studio R4 — PTS-Aware Trajectory Interpolation & Ballistic Curve Helper (`interpolation.py`).
提供：
1. 以真實 `source_pts_us` 為自變數之分段三次 Hermite / Catmull-Rom 樣條插值，用於：
   - 渲染器在相鄰軌跡點間繪製平滑高密度貝茲曲線（不竄改底層 `CanonicalTrackPoint`）。
   - 使用者於 Studio 新增/移動手動錨點 (`manually_annotated`) 時，局部重算兩錨點間之過渡點 (`interpolated`)。
2. 明確標示為 `artistic_only` 之二次拋物線延伸輔助（僅當使用者開啟 `ARTISTIC_EXTENSION` 或設定落點錨點時啟用）。
"""

import math
from typing import Any

import numpy as np

from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    TrackSourceType,
    TrackType,
)


def catmull_rom_subdivide(
    xy_points: list[tuple[float, float]],
    subdivisions_per_segment: int = 8,
) -> list[tuple[float, float]]:
    """
    對 2D 點序列執行向心 Catmull-Rom 細分，供高解析度抗鋸齒弧線渲染使用。
    輸入與輸出皆保持在相同座標空間（例如 upright normalized 或 output pixel）。
    """
    n = len(xy_points)
    if n <= 2 or subdivisions_per_segment <= 1:
        return list(xy_points)

    result: list[tuple[float, float]] = []
    for i in range(n - 1):
        p0 = xy_points[max(0, i - 1)]
        p1 = xy_points[i]
        p2 = xy_points[i + 1]
        p3 = xy_points[min(n - 1, i + 2)]

        for step in range(subdivisions_per_segment):
            t = step / float(subdivisions_per_segment)
            t2 = t * t
            t3 = t2 * t
            # 標準三次 Catmull-Rom 矩陣權重 (tau = 0.5)
            b0 = -0.5 * t3 + t2 - 0.5 * t
            b1 = 1.5 * t3 - 2.5 * t2 + 1.0
            b2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
            b3 = 0.5 * t3 - 0.5 * t2

            x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
            y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
            result.append((x, y))

    result.append(xy_points[-1])
    return result


def interpolate_pts_gap(
    start_pt: CanonicalTrackPoint,
    end_pt: CanonicalTrackPoint,
    intermediate_frames: list[tuple[int, int, str]],  # (source_pts_us, source_frame_index, phase)
    revision: int = 1,
) -> list[CanonicalTrackPoint]:
    """
    在兩個已知軌跡點 (`start_pt`, `end_pt`) 之間，依真實 `source_pts_us` 比例內插中間幀。
    所有生成的點嚴格標記為 `source_type=TrackSourceType.INTERPOLATED`、`position_role=PositionRole.ESTIMATED_PATH`。
    """
    dt_total = end_pt.source_pts_us - start_pt.source_pts_us
    if dt_total <= 0 or not intermediate_frames:
        return []

    interpolated: list[CanonicalTrackPoint] = []
    for pts_us, frame_idx, phase in intermediate_frames:
        if pts_us <= start_pt.source_pts_us or pts_us >= end_pt.source_pts_us:
            continue
        alpha = float(np.clip((pts_us - start_pt.source_pts_us) / float(dt_total), 0.0, 1.0))
        # 平滑 Hermite 比例權重
        smooth_alpha = alpha * alpha * (3.0 - 2.0 * alpha)
        x_norm = (1.0 - smooth_alpha) * start_pt.x_norm + smooth_alpha * end_pt.x_norm
        y_norm = (1.0 - smooth_alpha) * start_pt.y_norm + smooth_alpha * end_pt.y_norm
        conf = round(max(0.20, min(start_pt.confidence, end_pt.confidence) * 0.72), 4)
        unc = round(max(start_pt.uncertainty_px, end_pt.uncertainty_px) + 4.5, 2)

        interpolated.append(
            CanonicalTrackPoint(
                track_id=start_pt.track_id,
                track_type=start_pt.track_type,
                segment_id=start_pt.segment_id,
                source_video_id=start_pt.source_video_id,
                source_pts_us=pts_us,
                source_frame_index=frame_idx,
                x_norm=round(float(np.clip(x_norm, 0.0, 1.0)), 6),
                y_norm=round(float(np.clip(y_norm, 0.0, 1.0)), 6),
                confidence=conf,
                source_type=TrackSourceType.INTERPOLATED,
                position_role=PositionRole.ESTIMATED_PATH,
                raw_observation=None,
                phase=phase,
                model_id="pts_hermite_interpolator_v1",
                evidence_frame_sha256=None,
                occlusion_state=OcclusionState.OCCLUDED,
                uncertainty_px=unc,
                error_flags=["pts_interpolated_between_anchors"],
                created_by="geometry",
                revision=revision,
            )
        )
    return interpolated


def generate_artistic_ballistic_extension(
    observed_points: list[CanonicalTrackPoint],
    apex_xy_norm: tuple[float, float] | None,
    landing_xy_norm: tuple[float, float],
    extension_pts_timeline: list[tuple[int, int]],  # [(source_pts_us, source_frame_index), ...]
    revision: int = 1,
) -> list[CanonicalTrackPoint]:
    """
    當使用者在 Studio 明確啟用 `ARTISTIC_EXTENSION` 或手動標定遠端落點時，
    生成從最後觀測點經頂點 (`apex_xy_norm`) 到落點 (`landing_xy_norm`) 之二次貝茲彈道。
    所有生成的點強制標記為：
    - `source_type = TrackSourceType.ARTISTIC_ONLY`
    - `position_role = PositionRole.ARTISTIC_CONTROL`
    - `occlusion_state = OcclusionState.UNOBSERVABLE`
    - `created_by = "artist"`
    絕不混入 `detector_observed` 統計或宣稱為真實觀測落點。
    """
    if not observed_points or not extension_pts_timeline:
        return []

    last_pt = observed_points[-1]
    p0 = (last_pt.x_norm, last_pt.y_norm)
    p2 = (float(np.clip(landing_xy_norm[0], 0.0, 1.0)), float(np.clip(landing_xy_norm[1], 0.0, 1.0)))

    if apex_xy_norm is not None:
        p1 = (float(np.clip(apex_xy_norm[0], 0.0, 1.0)), float(np.clip(apex_xy_norm[1], 0.0, 1.0)))
    else:
        mid_x = 0.5 * (p0[0] + p2[0])
        top_y = max(0.06, min(p0[1], p2[1]) - max(0.10, 0.32 * abs(p2[0] - p0[0])))
        p1 = (mid_x, top_y)

    n = len(extension_pts_timeline)
    artistic_pts: list[CanonicalTrackPoint] = []
    for idx, (pts_us, frame_idx) in enumerate(extension_pts_timeline):
        if pts_us <= last_pt.source_pts_us:
            continue
        t = (idx + 1) / float(n)
        u = 1.0 - t
        bx = u * u * p0[0] + 2.0 * u * t * p1[0] + t * t * p2[0]
        by = u * u * p0[1] + 2.0 * u * t * p1[1] + t * t * p2[1]

        artistic_pts.append(
            CanonicalTrackPoint(
                track_id=last_pt.track_id,
                track_type=TrackType.BALL,
                segment_id=last_pt.segment_id,
                source_video_id=last_pt.source_video_id,
                source_pts_us=pts_us,
                source_frame_index=frame_idx,
                x_norm=round(float(np.clip(bx, 0.0, 1.0)), 6),
                y_norm=round(float(np.clip(by, 0.0, 1.0)), 6),
                confidence=0.15,
                source_type=TrackSourceType.ARTISTIC_ONLY,
                position_role=PositionRole.ARTISTIC_CONTROL,
                raw_observation=None,
                phase="follow_through",
                model_id="artistic_bezier_arc_v1",
                evidence_frame_sha256=None,
                occlusion_state=OcclusionState.UNOBSERVABLE,
                uncertainty_px=round(25.0 + 35.0 * t, 2),
                error_flags=["artistic_extension_not_observed"],
                created_by="artist",
                revision=revision,
            )
        )
    return artistic_pts
