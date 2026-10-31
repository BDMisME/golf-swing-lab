"""
Golf Tracer Studio R4 — True Swing Tracer Engine (`swing_tracker.py`).
整合：
1. 直接桿頭偵測 (`ClubheadDetector` -> `detector_observed`)
2. 桿身線段端點幾何推算 (`ShaftGeometryEstimator` -> `shaft_geometry_estimated`)
3. 以真實 `source_pts_us` 驅動之有界 Kalman 平滑與短 Gap 插值 (`<= 120ms`)
4. 以 Top / Impact PTS 精準切分 `backswing` / `downswing` / `follow_through`
5. 嚴格品質門檻 (`SwingTrackStatus`)：無直接桿頭模型或覆蓋率不足時絕不偽稱 `AUTO_TRACED`
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from packages.analysis.tracer.camera_motion import CameraMotionTracker
from packages.analysis.tracer.clubhead_detector import ClubheadDetector
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    SwingTrackStatus,
    TrackQualitySummary,
    TrackSourceType,
    TrackType,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader
from packages.analysis.tracer.roi_planner import is_view_comparable, plan_club_roi
from packages.analysis.tracer.segment_context import (
    ResolvedSegmentContext,
    classify_swing_phase_at_pts,
)
from packages.analysis.tracer.shaft_geometry import ShaftGeometryEstimator


@dataclass
class SwingTraceResult:
    track_id: str
    status: SwingTrackStatus
    points: list[CanonicalTrackPoint]
    quality: TrackQualitySummary
    model_status: dict

    @property
    def quality_summary(self) -> TrackQualitySummary:
        return self.quality


class PTSKalman2D:
    """以真實微秒時間差 `dt_sec = (pts_us - prev_pts_us) / 1e6` 更新之 2D 狀態濾波器。"""

    def __init__(
        self,
        process_noise: float = 0.015,
        measurement_noise: float = 0.002,
        damping: float = 0.92,
    ) -> None:
        self.process_noise = float(process_noise)
        self.measurement_noise = float(measurement_noise)
        self.damping = float(damping)
        self.state: np.ndarray | None = None  # [x, y, vx, vy]
        self.cov: np.ndarray = np.eye(4, dtype=np.float64) * 0.05
        self.last_pts_us: int | None = None

    def observe(
        self,
        meas_x: float,
        meas_y: float,
        pts_us: int,
        r_noise: float | None = None,
    ) -> tuple[float, float]:
        return self.update(
            meas_x=meas_x,
            meas_y=meas_y,
            pts_us=pts_us,
            r_noise=r_noise if r_noise is not None else self.measurement_noise,
        )

    def predict_only(self, pts_us: int) -> tuple[float, float] | None:
        if self.state is None or self.last_pts_us is None:
            return None
        dt = max(1e-4, min(0.25, (pts_us - self.last_pts_us) / 1_000_000.0))
        self.last_pts_us = pts_us
        f_mat = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, self.damping, 0.0],
                [0.0, 0.0, 0.0, self.damping],
            ],
            dtype=np.float64,
        )
        q_mat = np.eye(4, dtype=np.float64) * (self.process_noise * dt)
        self.state = f_mat @ self.state
        self.cov = f_mat @ self.cov @ f_mat.T + q_mat
        return (
            float(np.clip(self.state[0], 0.0, 1.0)),
            float(np.clip(self.state[1], 0.0, 1.0)),
        )

    def update(self, meas_x: float, meas_y: float, pts_us: int, r_noise: float = 0.002) -> tuple[float, float]:
        if self.state is None or self.last_pts_us is None:
            self.state = np.array([meas_x, meas_y, 0.0, 0.0], dtype=np.float64)
            self.last_pts_us = pts_us
            return (meas_x, meas_y)

        dt = max(1e-4, min(0.25, (pts_us - self.last_pts_us) / 1_000_000.0))
        self.last_pts_us = pts_us

        f_mat = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, self.damping, 0.0],
                [0.0, 0.0, 0.0, self.damping],
            ],
            dtype=np.float64,
        )
        q_mat = np.eye(4, dtype=np.float64) * (self.process_noise * dt)
        pred_state = f_mat @ self.state
        pred_cov = f_mat @ self.cov @ f_mat.T + q_mat

        h_mat = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
        r_mat = np.eye(2, dtype=np.float64) * r_noise
        z = np.array([meas_x, meas_y], dtype=np.float64)
        y_res = z - (h_mat @ pred_state)
        s_mat = h_mat @ pred_cov @ h_mat.T + r_mat
        k_gain = pred_cov @ h_mat.T @ np.linalg.inv(s_mat)

        self.state = pred_state + (k_gain @ y_res)
        self.cov = (np.eye(4, dtype=np.float64) - k_gain @ h_mat) @ pred_cov
        return (
            float(np.clip(self.state[0], 0.0, 1.0)),
            float(np.clip(self.state[1], 0.0, 1.0)),
        )


def _lookup_nearest_wrist_hint(
    wrist_hints_by_ms: dict[int, tuple[float, float]],
    pts_us: int,
    max_tolerance_ms: int = 160,
) -> tuple[float, float] | None:
    if not wrist_hints_by_ms:
        return None
    target_ms = int(round(pts_us / 1000.0))
    nearest_ms = min(wrist_hints_by_ms.keys(), key=lambda k: abs(k - target_ms))
    if abs(nearest_ms - target_ms) <= max_tolerance_ms:
        return wrist_hints_by_ms[nearest_ms]
    return None


class SwingTracerEngine:
    """高爾夫揮桿桿頭與桿身 2D 軌跡追蹤引擎。"""

    def __init__(
        self,
        clubhead_detector: ClubheadDetector | None = None,
        shaft_estimator: ShaftGeometryEstimator | None = None,
        max_gap_fill_ms: int = 100,
        *,
        club_detector: ClubheadDetector | None = None,
    ) -> None:
        resolved_detector = club_detector if club_detector is not None else clubhead_detector
        self.clubhead_detector = resolved_detector or ClubheadDetector()
        self.shaft_estimator = shaft_estimator or ShaftGeometryEstimator()
        self.max_gap_fill_us = int(max_gap_fill_ms) * 1000

    def trace_segment(
        self,
        context: ResolvedSegmentContext,
        video_path: str | Path | None = None,
        pad_before_ms: int = 200,
        pad_after_ms: int = 200,
    ) -> SwingTraceResult:
        eff_path = video_path or context.source_video_path or context.source_storage_key
        return self.analyze_segment(
            video_path=eff_path,
            context=context,
            pad_before_ms=pad_before_ms,
            pad_after_ms=pad_after_ms,
        )

    def analyze_segment(
        self,
        video_path: str | Path,
        context: ResolvedSegmentContext,
        pad_before_ms: int = 200,
        pad_after_ms: int = 200,
    ) -> SwingTraceResult:
        track_id = str(uuid.uuid4())
        comparable, view_norm = is_view_comparable(context.camera_angle)
        if not comparable:
            summary = TrackQualitySummary(
                track_type=TrackType.CLUB_HEAD,
                status=SwingTrackStatus.NOT_COMPARABLE.value,
                rejection_reasons=["UNSUPPORTED_CAMERA_VIEW"],
                view_angle=view_norm,
                handedness=context.handedness,
                notes=f"拍攝視角 ({context.camera_angle}) 非支援之 DTL/FO 視角，不進行平面揮桿軌跡測量。",
            )
            return SwingTraceResult(
                track_id=track_id,
                status=SwingTrackStatus.NOT_COMPARABLE,
                points=[],
                quality=summary,
                model_status=self.clubhead_detector.get_status_dict(),
            )

        reader = BoundedFrameReader(video_path)
        cam_tracker = CameraMotionTracker()
        kalman = PTSKalman2D()

        raw_points: list[CanonicalTrackPoint] = []
        total_frames = 0
        direct_count = 0
        geom_count = 0
        prev_head_norm: tuple[float, float] | None = None
        cam_scores: list[float] = []
        unstable_frames = 0

        for decoded in reader.iter_window(
            start_pts_us=context.segment_start_pts_us,
            end_pts_us=context.segment_end_pts_us,
            pad_before_us=pad_before_ms * 1000,
            pad_after_us=pad_after_ms * 1000,
        ):
            total_frames += 1
            pts_us = decoded.source_pts_us
            cam_est = cam_tracker.step(decoded.frame_bgr, pts_us)
            cam_scores.append(cam_est.magnitude_norm)
            if cam_est.is_unstable:
                unstable_frames += 1

            wrist_hint = _lookup_nearest_wrist_hint(context.wrist_hints_by_ms, pts_us)
            roi = plan_club_roi(
                display_width=decoded.geometry.display_width,
                display_height=decoded.geometry.display_height,
                handedness=context.handedness,
                wrist_hint_norm=wrist_hint,
                prev_head_norm=prev_head_norm,
            )

            phase = classify_swing_phase_at_pts(
                pts_us=pts_us,
                takeaway_pts_us=context.takeaway_pts_us,
                top_pts_us=context.top_pts_us,
                impact_pts_us=context.impact_pts_us,
                finish_pts_us=context.finish_pts_us,
            )

            # 1. 優先嘗試專用桿頭模型直接偵測
            det = self.clubhead_detector.detect_in_roi(
                frame_bgr=decoded.frame_bgr,
                roi_box=roi.box,
                wrist_hint_norm=wrist_hint,
            )
            if det is not None:
                sx, sy = kalman.update(det.head_x_norm, det.head_y_norm, pts_us, r_noise=0.0015)
                is_smoothed = (abs(sx - det.head_x_norm) > 1e-4) or (abs(sy - det.head_y_norm) > 1e-4)
                pt = CanonicalTrackPoint(
                    track_id=track_id,
                    track_type=TrackType.CLUB_HEAD,
                    segment_id=context.segment_id,
                    source_video_id=context.video_id,
                    source_pts_us=pts_us,
                    source_frame_index=decoded.source_frame_index,
                    x_norm=sx if is_smoothed else det.head_x_norm,
                    y_norm=sy if is_smoothed else det.head_y_norm,
                    confidence=det.confidence,
                    source_type=TrackSourceType.DETECTOR_OBSERVED,
                    position_role=PositionRole.DISPLAY_SMOOTHED if is_smoothed else PositionRole.RAW_OBSERVATION,
                    raw_observation={
                        "x_norm": det.head_x_norm,
                        "y_norm": det.head_y_norm,
                        "bbox": list(det.head_bbox_norm),
                        "uncertainty_px": det.uncertainty_px,
                    },
                    phase=phase,
                    model_id=det.model_id,
                    evidence_frame_sha256=decoded.frame_sha256,
                    occlusion_state=OcclusionState.VISIBLE,
                    uncertainty_px=det.uncertainty_px,
                    error_flags=["camera_motion"] if cam_est.is_unstable else [],
                    created_by="model",
                )
                raw_points.append(pt)
                prev_head_norm = (pt.x_norm, pt.y_norm)
                direct_count += 1
                continue

            # 2. 當桿頭模型缺席或該格模糊漏檢時，嘗試桿身幾何端點推算 (明確標記 shaft_geometry_estimated)
            geom_est = self.shaft_estimator.estimate_from_frame(
                frame_bgr=decoded.frame_bgr,
                roi_box=roi.box,
                wrist_hint_norm=wrist_hint,
                prev_head_norm=prev_head_norm,
            )
            if geom_est is not None:
                sx, sy = kalman.update(geom_est.head_x_norm, geom_est.head_y_norm, pts_us, r_noise=0.006)
                pt = CanonicalTrackPoint(
                    track_id=track_id,
                    track_type=TrackType.CLUB_HEAD,
                    segment_id=context.segment_id,
                    source_video_id=context.video_id,
                    source_pts_us=pts_us,
                    source_frame_index=decoded.source_frame_index,
                    x_norm=sx,
                    y_norm=sy,
                    confidence=geom_est.confidence,
                    source_type=TrackSourceType.SHAFT_GEOMETRY_ESTIMATED,
                    position_role=PositionRole.ESTIMATED_PATH,
                    raw_observation={
                        "x_norm": geom_est.head_x_norm,
                        "y_norm": geom_est.head_y_norm,
                        "grip_x_norm": geom_est.grip_x_norm,
                        "grip_y_norm": geom_est.grip_y_norm,
                        "shaft_length_norm": geom_est.shaft_length_norm,
                        "uncertainty_px": geom_est.uncertainty_px,
                    },
                    phase=phase,
                    model_id="opencv-hough-shaft-v1",
                    evidence_frame_sha256=decoded.frame_sha256,
                    occlusion_state=OcclusionState.BLURRED,
                    uncertainty_px=geom_est.uncertainty_px,
                    error_flags=["shaft_geometry_fallback"] + (["camera_motion"] if cam_est.is_unstable else []),
                    created_by="geometry",
                )
                raw_points.append(pt)
                prev_head_norm = (pt.x_norm, pt.y_norm)
                geom_count += 1

        # 3. 僅對短暫遮擋 (<= max_gap_fill_us) 進行有界插值並明確標記 interpolated；長 gap 絕不連線
        merged_points, interp_count, largest_gap_ms = self._fill_bounded_gaps(raw_points, context)

        total_f = max(1, total_frames)
        direct_cov = round(direct_count / float(total_f), 4)
        geom_cov = round(geom_count / float(total_f), 4)
        mean_conf = round(float(np.mean([p.confidence for p in merged_points])), 3) if merged_points else 0.0
        uncs = [p.uncertainty_px for p in merged_points if p.uncertainty_px > 0]
        p50_unc = round(float(np.percentile(uncs, 50)), 2) if uncs else 0.0
        p95_unc = round(float(np.percentile(uncs, 95)), 2) if uncs else 0.0
        mean_cam = round(float(np.mean(cam_scores)), 4) if cam_scores else 0.0

        rejection_reasons: list[str] = []
        if not self.clubhead_detector.is_available:
            rejection_reasons.append("MODEL_UNAVAILABLE:swingtrace-yolo11m")
        if unstable_frames > max(3, int(total_f * 0.25)):
            rejection_reasons.append("CAMERA_MOVED")
        if direct_cov < 0.50:
            rejection_reasons.append(f"LOW_DIRECT_OBSERVATION_COVERAGE:{direct_cov:.2f}")
        if largest_gap_ms > 250.0:
            rejection_reasons.append(f"LARGE_OCCLUSION_GAP:{largest_gap_ms:.0f}ms")

        if (
            self.clubhead_detector.is_available
            and direct_cov >= 0.50
            and (direct_cov + geom_cov) >= 0.70
            and "CAMERA_MOVED" not in rejection_reasons
        ):
            status = SwingTrackStatus.AUTO_TRACED
            eligible = True
        elif not self.clubhead_detector.is_available and geom_count == 0:
            status = SwingTrackStatus.MODEL_UNAVAILABLE
            eligible = False
        else:
            status = SwingTrackStatus.NEEDS_REVIEW
            eligible = False

        obs_pts = [p.source_pts_us for p in merged_points if p.source_type == TrackSourceType.DETECTOR_OBSERVED]
        obs_range = [min(obs_pts), max(obs_pts)] if obs_pts else []

        summary = TrackQualitySummary(
            track_type=TrackType.CLUB_HEAD,
            status=status.value,
            total_frames=total_frames,
            total_points=len(merged_points),
            direct_observed_count=direct_count,
            geometry_estimated_count=geom_count,
            interpolated_count=interp_count,
            direct_observation_coverage=direct_cov,
            geometry_assisted_coverage=geom_cov,
            largest_gap_ms=round(largest_gap_ms, 1),
            mean_confidence=mean_conf,
            p50_uncertainty_px=p50_unc,
            p95_uncertainty_px=p95_unc,
            observed_range_pts_us=obs_range,
            rejection_reasons=rejection_reasons,
            end_to_end_eligible=eligible,
            view_angle=view_norm,
            handedness=context.handedness,
            camera_motion_score=mean_cam,
            notes=(
                "自動桿頭軌跡通過品質門檻"
                if eligible
                else "直接桿頭模型未安裝或觀測覆蓋率不足，已標記為 NEEDS_REVIEW / MODEL_UNAVAILABLE，請使用 Studio 逐格校正錨點。"
            ),
        )
        return SwingTraceResult(
            track_id=track_id,
            status=status,
            points=merged_points,
            quality=summary,
            model_status=self.clubhead_detector.get_status_dict(),
        )

    def _fill_bounded_gaps(
        self,
        points: list[CanonicalTrackPoint],
        context: ResolvedSegmentContext,
    ) -> tuple[list[CanonicalTrackPoint], int, float]:
        if len(points) < 2:
            return (points, 0, 0.0)

        sorted_pts = sorted(points, key=lambda p: p.source_pts_us)
        out: list[CanonicalTrackPoint] = [sorted_pts[0]]
        interp_count = 0
        largest_gap_us = 0

        for idx in range(1, len(sorted_pts)):
            prev_p = sorted_pts[idx - 1]
            curr_p = sorted_pts[idx]
            gap_us = curr_p.source_pts_us - prev_p.source_pts_us
            largest_gap_us = max(largest_gap_us, gap_us)

            step_dist = float(np.hypot(curr_p.x_norm - prev_p.x_norm, curr_p.y_norm - prev_p.y_norm))
            if 28_000 < gap_us <= self.max_gap_fill_us and step_dist <= 0.14:
                mid_pts_us = (prev_p.source_pts_us + curr_p.source_pts_us) // 2
                mid_idx = (prev_p.source_frame_index + curr_p.source_frame_index) // 2
                if mid_pts_us not in (prev_p.source_pts_us, curr_p.source_pts_us):
                    phase = classify_swing_phase_at_pts(
                        pts_us=mid_pts_us,
                        takeaway_pts_us=context.takeaway_pts_us,
                        top_pts_us=context.top_pts_us,
                        impact_pts_us=context.impact_pts_us,
                        finish_pts_us=context.finish_pts_us,
                    )
                    out.append(
                        CanonicalTrackPoint(
                            track_id=prev_p.track_id,
                            track_type=TrackType.CLUB_HEAD,
                            segment_id=context.segment_id,
                            source_video_id=context.video_id,
                            source_pts_us=mid_pts_us,
                            source_frame_index=mid_idx,
                            x_norm=round((prev_p.x_norm + curr_p.x_norm) / 2.0, 5),
                            y_norm=round((prev_p.y_norm + curr_p.y_norm) / 2.0, 5),
                            confidence=round(min(prev_p.confidence, curr_p.confidence) * 0.75, 3),
                            source_type=TrackSourceType.INTERPOLATED,
                            position_role=PositionRole.ESTIMATED_PATH,
                            raw_observation=None,
                            phase=phase,
                            model_id="linear-gap-interpolator-v1",
                            occlusion_state=OcclusionState.OCCLUDED,
                            uncertainty_px=round(max(prev_p.uncertainty_px, curr_p.uncertainty_px) * 1.35, 2),
                            error_flags=["short_gap_interpolated"],
                            created_by="geometry",
                        )
                    )
                    interp_count += 1
            out.append(curr_p)

        return (out, interp_count, largest_gap_us / 1000.0)
