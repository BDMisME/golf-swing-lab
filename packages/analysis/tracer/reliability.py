"""
Golf Tracer Studio R4 — Track Reliability & Quality Calibrator (`reliability.py`).
統一計算 `club_head` 與 `ball` 軌跡之可觀測性覆蓋率、時間間隙 (`largest_gap_ms`)、
不確定度分位數 (`p50_uncertainty_px`, `p95_uncertainty_px`)，以及是否符合自動端到端匯出資格 (`end_to_end_eligible`)。
"""

import numpy as np

from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    ShotTrackMode,
    SwingTrackStatus,
    TrackQualitySummary,
    TrackSourceType,
    TrackType,
)


def recompute_track_quality_summary(
    points: list[CanonicalTrackPoint],
    track_type: TrackType,
    total_frames: int | None = None,
    view_angle: str = "DTL",
    handedness: str = "right",
    camera_motion_score: float = 0.0,
    model_unavailable: bool = False,
) -> TrackQualitySummary:
    """
    針對任意修訂版 (`revision`) 之軌跡點序列重新核算品質摘要與狀態。
    """
    sorted_pts = sorted(points, key=lambda p: p.source_pts_us)
    n_pts = len(sorted_pts)
    n_frames = max(total_frames or n_pts, n_pts, 1)

    direct_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.DETECTOR_OBSERVED]
    geom_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.SHAFT_GEOMETRY_ESTIMATED]
    flow_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.OPTICAL_FLOW_ESTIMATED]
    kalman_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.KALMAN_PREDICTED]
    interp_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.INTERPOLATED]
    extrap_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.EXTRAPOLATED]
    manual_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.MANUALLY_ANNOTATED]
    artistic_pts = [p for p in sorted_pts if p.source_type == TrackSourceType.ARTISTIC_ONLY]

    direct_cov = round(len(direct_pts) / float(n_frames), 4)
    geom_cov = round((len(direct_pts) + len(geom_pts)) / float(n_frames), 4)
    manual_cov = round(len(manual_pts) / float(n_frames), 4)

    # 計算相鄰點最大時間間隙 (毫秒)
    largest_gap_ms = 0.0
    if len(sorted_pts) >= 2:
        for i in range(len(sorted_pts) - 1):
            gap_ms = (sorted_pts[i + 1].source_pts_us - sorted_pts[i].source_pts_us) / 1000.0
            if gap_ms > largest_gap_ms:
                largest_gap_ms = gap_ms

    confs = [p.confidence for p in sorted_pts]
    uncs = [p.uncertainty_px for p in sorted_pts]

    obs_candidates = direct_pts + geom_pts + manual_pts
    obs_range = (
        [obs_candidates[0].source_pts_us, obs_candidates[-1].source_pts_us] if obs_candidates else []
    )
    pred_ranges = [
        [p.source_pts_us, p.source_pts_us]
        for p in (flow_pts + kalman_pts + interp_pts + extrap_pts + artistic_pts)
    ]

    rejection_reasons: list[str] = []
    if track_type == TrackType.CLUB_HEAD:
        if manual_pts:
            status = SwingTrackStatus.MANUAL_ASSISTED.value
            eligible = True
            notes = f"已合併 {len(manual_pts)} 個手動校準點 (Revision {sorted_pts[-1].revision})。"
        elif direct_cov >= 0.65 and largest_gap_ms <= 60.0 and len(direct_pts) >= 8:
            status = SwingTrackStatus.AUTO_TRACED.value
            eligible = True
            notes = "直接桿頭偵測覆蓋率達標 (>=65%)，可自動匯出。"
        elif model_unavailable and len(sorted_pts) == 0:
            status = SwingTrackStatus.MODEL_UNAVAILABLE.value
            eligible = False
            rejection_reasons.append("clubhead_detector_model_unavailable")
            notes = "本機缺少直接桿頭偵測模型，且無足夠桿身幾何端點。"
        else:
            status = SwingTrackStatus.NEEDS_REVIEW.value
            eligible = False
            if model_unavailable:
                rejection_reasons.append("clubhead_detector_model_unavailable_using_shaft_geometry")
            if direct_cov < 0.65:
                rejection_reasons.append(f"direct_coverage_below_threshold:{direct_cov:.2f}<0.65")
            if largest_gap_ms > 60.0:
                rejection_reasons.append(f"largest_gap_exceeded:{largest_gap_ms:.1f}ms>60.0ms")
            notes = "直接桿頭觀測覆蓋率未達 65%，需於 Studio 檢查或補強錨點。"
    else:
        if artistic_pts:
            status = ShotTrackMode.ARTISTIC_EXTENSION.value
            eligible = True
            notes = "包含使用者啟用之藝術延伸彈道 (`artistic_only`)。"
        elif manual_pts:
            status = ShotTrackMode.MANUAL_ANCHORED.value
            eligible = True
            notes = f"已合併 {len(manual_pts)} 個手動飛球錨點。"
        elif len(direct_pts) >= 4:
            status = ShotTrackMode.AUTO_OBSERVED.value
            eligible = True
            notes = "已由原始高解析影格自動觀測飛球初段軌跡。"
        elif (len(direct_pts) + len(flow_pts)) >= 3 and len(sorted_pts) >= 4:
            status = ShotTrackMode.AUTO_ASSISTED.value
            eligible = False
            rejection_reasons.append("shot_requires_review_assisted_mode")
            notes = "飛球初段含光流/卡爾曼輔助補幀，建議於 Studio 確認。"
        else:
            status = ShotTrackMode.UNAVAILABLE.value
            eligible = False
            rejection_reasons.append("insufficient_ball_observations")
            notes = "無足夠飛球觀測點。"

    return TrackQualitySummary(
        track_type=track_type,
        status=status,
        total_frames=n_frames,
        total_points=n_pts,
        direct_observed_count=len(direct_pts),
        geometry_estimated_count=len(geom_pts),
        optical_flow_count=len(flow_pts),
        kalman_predicted_count=len(kalman_pts),
        interpolated_count=len(interp_pts),
        extrapolated_count=len(extrap_pts),
        manual_count=len(manual_pts),
        artistic_count=len(artistic_pts),
        direct_observation_coverage=direct_cov,
        geometry_assisted_coverage=geom_cov,
        manual_coverage=manual_cov,
        largest_gap_ms=round(largest_gap_ms, 2),
        mean_confidence=round(float(np.mean(confs)) if confs else 0.0, 4),
        p50_uncertainty_px=round(float(np.percentile(uncs, 50)) if uncs else 0.0, 2),
        p95_uncertainty_px=round(float(np.percentile(uncs, 95)) if uncs else 0.0, 2),
        observed_range_pts_us=obs_range,
        predicted_ranges_pts_us=pred_ranges,
        rejection_reasons=rejection_reasons,
        end_to_end_eligible=eligible,
        view_angle=view_angle,
        handedness=handedness,
        camera_motion_score=round(camera_motion_score, 4),
        notes=notes,
    )
