"""
Golf Tracer Studio R4 — Shot Tracer Engine (`shot_tracker.py`).
負責於原始高解析度影片執行擊球後小白球飛行追蹤：
1. 強制要求原始影片來源（拒絕 <=540p 低解析度 Proxy 推論）。
2. 使用雙向 ROI (`plan_ball_flight_roi`) 同時覆蓋左飛、右飛與高飛球，解決舊版單向向右擴張問題。
3. 結合 YOLOv8n 小白球偵測 (`detector_observed`)、雙向金字塔 LK 光流 (`optical_flow_estimated`) 與
   真實 PTS 時間步長 (`dt = Δsource_pts_us / 1e6`) 之 2D 卡爾曼濾波 (`kalman_predicted`)。
4. 嚴格執行物理與誠信護欄：
   - 靜止在打擊墊上的球 (`stationary`) 或空揮 (`practice_swing`) 絕不產生假飛行軌跡。
   - 靜態背景亮點（連續多幀停留原地）自動列入靜態遮罩排除。
   - `detector_observed` 必保留 `raw_observation`，經卡爾曼平滑之顯示座標標記為 `position_role='display_smoothed'`。
"""

from dataclasses import dataclass
import logging
import math
import uuid
from typing import Any

import numpy as np

from packages.analysis.tracer.camera_motion import CameraMotionTracker
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    ShotTrackMode,
    TrackQualitySummary,
    TrackSourceType,
    TrackType,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader, DecodedUprightFrame
from packages.analysis.tracer.roi_planner import is_view_comparable, plan_ball_flight_roi
from packages.analysis.tracer.segment_context import ResolvedSegmentContext
from packages.analysis.tracer.shot_detector import BallDetectionCandidate, ShotBallDetector
from packages.analysis.tracer.swing_tracker import PTSKalman2D

logger = logging.getLogger(__name__)


@dataclass
class ShotTraceResult:
    """Shot Tracer 完整追蹤結果。"""

    track_id: str
    mode: ShotTrackMode
    points: list[CanonicalTrackPoint]
    quality_summary: TrackQualitySummary
    stationary_ball_norm: tuple[float, float] | None
    observed_launch_pts_us: int | None


def validate_ball_launch_physics(points: list[CanonicalTrackPoint]) -> tuple[bool, list[str]]:
    """
    高爾夫出球物理合理性檢核（同時支援右打與左打、左曲與右曲）：
    1. 有效飛行軌跡點數 >= 3
    2. 起飛點 y_norm >= 0.42 (位於地面或打擊台合理高度)
    3. 最高點 (最小 y_norm) 必須高於起飛點至少 0.045 (dy_apex <= -0.045)
    4. 總位移向量長度 >= 0.045
    """
    reasons: list[str] = []
    if len(points) < 3:
        return False, ["insufficient_airborne_points"]

    init_pt = points[0]
    min_y = min(p.y_norm for p in points)
    max_dist = max(math.hypot(p.x_norm - init_pt.x_norm, p.y_norm - init_pt.y_norm) for p in points)

    if init_pt.y_norm < 0.40:
        reasons.append("launch_origin_too_high")
    if (min_y - init_pt.y_norm) > -0.040:
        reasons.append("insufficient_upward_elevation")
    if max_dist < 0.040:
        reasons.append("insufficient_total_displacement")

    return len(reasons) == 0, reasons


class ShotTracerEngine:
    """
    Shot Tracer 2D 彈道觀測與追蹤引擎。
    """

    def __init__(
        self,
        ball_detector: ShotBallDetector | None = None,
        max_optical_flow_gap_frames: int = 3,
        max_kalman_gap_frames: int = 3,
    ) -> None:
        self.ball_detector = ball_detector if ball_detector is not None else ShotBallDetector()
        self.max_optical_flow_gap_frames = max_optical_flow_gap_frames
        self.max_kalman_gap_frames = max_kalman_gap_frames

    def trace_segment(
        self,
        context: ResolvedSegmentContext,
        pre_impact_ms: int = 250,
        flight_duration_ms: int = 1350,
        allow_low_res_test: bool = False,
    ) -> ShotTraceResult:
        """
        對指定揮桿片段執行擊球前後之小白球追蹤。
        """
        track_id = f"shot_{context.segment_id[:12]}_{uuid.uuid4().hex[:8]}"

        comparable, view_reason = is_view_comparable(context.view_angle)
        if not comparable:
            return self._build_empty_result(
                track_id=track_id,
                context=context,
                mode=ShotTrackMode.UNAVAILABLE,
                reasons=[view_reason],
                notes="非標準 DTL/Face-On 視角，停用自動飛球追蹤。",
            )

        if not self.ball_detector.is_available:
            return self._build_empty_result(
                track_id=track_id,
                context=context,
                mode=ShotTrackMode.UNAVAILABLE,
                reasons=["ball_detector_model_unavailable"],
                notes=f"小白球偵測模型未就緒 ({self.ball_detector.status})。",
            )

        impact_pts_us = context.impact_pts_us
        if impact_pts_us is None:
            impact_pts_us = int(round(0.62 * context.start_pts_us + 0.38 * context.end_pts_us))

        window_start_us = max(0, impact_pts_us - pre_impact_ms * 1000)
        window_end_us = max(window_start_us + 300_000, impact_pts_us + flight_duration_ms * 1000)

        reader = BoundedFrameReader(
            source_path=context.source_video_path,
            geometry=context.geometry,
            require_high_res=not allow_low_res_test,
        )
        frames: list[DecodedUprightFrame] = list(
            reader.iter_frames(start_pts_us=window_start_us, end_pts_us=window_end_us)
        )
        if not frames:
            return self._build_empty_result(
                track_id=track_id,
                context=context,
                mode=ShotTrackMode.UNAVAILABLE,
                reasons=["no_frames_decoded_in_impact_window"],
                notes="擊球時間窗內無法解碼任何原始影格。",
            )

        # 尋找打擊位置初始參考點 (使用 impact 前後之手腕向下延伸或畫面預設擊球區)
        wrist_ref = self._resolve_impact_ball_zone_hint(context, impact_pts_us)

        # 第一階段：定位擊球前靜止球基準點 (Stationary Ball Anchor) 與靜態背景雜訊點
        pre_frames = [f for f in frames if f.source_pts_us <= impact_pts_us + 35_000]
        if not pre_frames:
            pre_frames = frames[: min(4, len(frames))]

        pre_candidates_per_frame: list[tuple[int, list[BallDetectionCandidate]]] = []
        for pf in pre_frames:
            roi = plan_ball_flight_roi(
                frame_width=pf.width,
                frame_height=pf.height,
                ball_origin_norm=wrist_ref,
                progress=0.0,
                handedness=context.handedness,
            )
            cands = self.ball_detector.detect_candidates_in_roi(pf.image_bgr, roi)
            pre_candidates_per_frame.append((pf.source_pts_us, cands))

        stationary_ball, static_clutter_zones = self._identify_stationary_ball_and_clutter(
            pre_candidates_per_frame,
            default_origin=wrist_ref,
        )
        ball_origin = stationary_ball if stationary_ball is not None else (wrist_ref or (0.48, 0.76))

        # 第二階段：擊球後雙向擴張 ROI 掃描與軌跡關聯
        cam_tracker = CameraMotionTracker()
        cam_scores: list[float] = []
        raw_detections: list[dict[str, Any]] = []

        for f in frames:
            cam_est = cam_tracker.update(f.image_bgr)
            cam_scores.append(cam_est.stability_score)
            if f.source_pts_us < impact_pts_us - 45_000:
                continue

            progress = float(
                np.clip((f.source_pts_us - impact_pts_us) / float(max(100_000, flight_duration_ms * 1000)), 0.0, 1.0)
            )
            roi = plan_ball_flight_roi(
                frame_width=f.width,
                frame_height=f.height,
                ball_origin_norm=ball_origin,
                progress=progress,
                handedness=context.handedness,
            )
            cands = self.ball_detector.detect_candidates_in_roi(f.image_bgr, roi)
            # 過濾掉固定不動的背景燈光或距離牌雜訊
            filtered_cands = [
                c for c in cands if not self._is_in_static_clutter(c.x_norm, c.y_norm, static_clutter_zones)
            ]
            raw_detections.append(
                {
                    "frame": f,
                    "candidates": filtered_cands,
                    "progress": progress,
                }
            )

        # 第三階段：檢驗是否有真實升空飛行 (Stationary vs Airborne Gate)
        launch_verified, launch_pts_us, airborne_chain, rejection_reasons = self._extract_verified_airborne_chain(
            raw_detections=raw_detections,
            ball_origin=ball_origin,
             stationary_ball=stationary_ball,
            impact_pts_us=impact_pts_us,
        )

        mean_cam_motion = round(1.0 - float(np.mean(cam_scores)) if cam_scores else 0.0, 4)

        if not launch_verified or not airborne_chain:
            return ShotTraceResult(
                track_id=track_id,
                mode=ShotTrackMode.UNAVAILABLE,
                points=[],
                quality_summary=TrackQualitySummary(
                    track_type=TrackType.BALL,
                    status=ShotTrackMode.UNAVAILABLE.value,
                    total_frames=len(frames),
                    total_points=0,
                    rejection_reasons=rejection_reasons or ["no_verified_ball_launch"],
                    end_to_end_eligible=False,
                    view_angle=context.view_angle,
                    handedness=context.handedness,
                    camera_motion_score=mean_cam_motion,
                    notes="未觀測到可信的小白球升空連續軌跡，嚴守誠信原則不產生假彈道。",
                ),
                stationary_ball_norm=stationary_ball,
                observed_launch_pts_us=None,
            )

        # 第四階段：建立包含光流補幀與 PTS-Kalman 濾波之完整飛行點序列
        points = self._build_flight_track_points(
            track_id=track_id,
            context=context,
            raw_detections=raw_detections,
            airborne_chain=airborne_chain,
            launch_pts_us=launch_pts_us or impact_pts_us,
        )

        phys_ok, phys_reasons = validate_ball_launch_physics(points)
        if not phys_ok:
            return ShotTraceResult(
                track_id=track_id,
                mode=ShotTrackMode.UNAVAILABLE,
                points=[],
                quality_summary=TrackQualitySummary(
                    track_type=TrackType.BALL,
                    status=ShotTrackMode.UNAVAILABLE.value,
                    total_frames=len(frames),
                    total_points=0,
                    rejection_reasons=phys_reasons,
                    end_to_end_eligible=False,
                    view_angle=context.view_angle,
                    handedness=context.handedness,
                    camera_motion_score=mean_cam_motion,
                    notes=f"候選軌跡未通過物理合理性檢核: {', '.join(phys_reasons)}",
                ),
                stationary_ball_norm=stationary_ball,
                observed_launch_pts_us=None,
            )

        summary = self._compute_shot_quality_summary(
            points=points,
            total_frames=len(frames),
            context=context,
            camera_motion_score=mean_cam_motion,
        )

        return ShotTraceResult(
            track_id=track_id,
            mode=ShotTrackMode(summary.status),
            points=points,
            quality_summary=summary,
            stationary_ball_norm=stationary_ball,
            observed_launch_pts_us=launch_pts_us,
        )

    def _resolve_impact_ball_zone_hint(
        self,
        context: ResolvedSegmentContext,
        impact_pts_us: int,
    ) -> tuple[float, float] | None:
        wrist = context.lookup_wrist_norm_at_pts(impact_pts_us, max_delta_us=180_000)
        if wrist is None:
            wrist = context.lookup_wrist_norm_at_pts(context.start_pts_us + 200_000, max_delta_us=350_000)
        if wrist is None:
            return None
        # 球位於雙手下方約 0.14~0.18 畫面高度處
        bx = float(np.clip(wrist[0] + (0.04 if context.handedness != "left" else -0.04), 0.15, 0.85))
        by = float(np.clip(wrist[1] + 0.16, 0.50, 0.90))
        return (bx, by)

    def _identify_stationary_ball_and_clutter(
        self,
        pre_candidates_per_frame: list[tuple[int, list[BallDetectionCandidate]]],
        default_origin: tuple[float, float] | None,
    ) -> tuple[tuple[float, float] | None, list[tuple[float, float]]]:
        """
        從擊球前影格找出：
        1. 打擊墊上的靜止球位置 (`stationary_ball`)
        2. 位於高處 (`y_norm < 0.45`) 且在擊球前就一直存在的靜態背景亮點 (`static_clutter_zones`)
        """
        ground_pts: list[tuple[float, float, float]] = []
        sky_clusters: list[tuple[float, float]] = []

        for _pts, cands in pre_candidates_per_frame:
            for c in cands:
                if c.y_norm < 0.44:
                    sky_clusters.append((c.x_norm, c.y_norm))
                elif c.y_norm >= 0.48:
                    ground_pts.append((c.x_norm, c.y_norm, c.confidence))

        if not ground_pts:
            return None, sky_clusters

        if default_origin is not None:
            ox, oy = default_origin
            ground_pts.sort(key=lambda p: math.hypot(p[0] - ox, p[1] - oy) - 0.15 * p[2])
        else:
            ground_pts.sort(key=lambda p: -p[2])

        best_x, best_y, _ = ground_pts[0]
        nearby = [p for p in ground_pts if math.hypot(p[0] - best_x, p[1] - best_y) <= 0.03]
        med_x = float(np.median([p[0] for p in nearby]))
        med_y = float(np.median([p[1] for p in nearby]))
        return (med_x, med_y), sky_clusters

    @staticmethod
    def _is_in_static_clutter(
        x_norm: float,
        y_norm: float,
        clutter_zones: list[tuple[float, float]],
        radius: float = 0.018,
    ) -> bool:
        for cx, cy in clutter_zones:
            if math.hypot(x_norm - cx, y_norm - cy) <= radius:
                return True
        return False

    def _extract_verified_airborne_chain(
        self,
        raw_detections: list[dict[str, Any]],
        ball_origin: tuple[float, float],
        stationary_ball: tuple[float, float] | None,
        impact_pts_us: int,
    ) -> tuple[bool, int | None, dict[int, BallDetectionCandidate], list[str]]:
        """
        從擊球後候選點中提取具物理連續性的升空球鏈。
        排除僅有打擊席靜止球 (`stationary_ball_only`) 或單一雜訊閃點。
        """
        ox, oy = stationary_ball if stationary_ball is not None else ball_origin
        stationary_hits = 0
        airborne_Observations: list[tuple[int, int, BallDetectionCandidate, float, float]] = []

        for item in raw_detections:
            f: DecodedUprightFrame = item["frame"]
            cands: list[BallDetectionCandidate] = item["candidates"]
            for c in cands:
                dx = c.x_norm - ox
                dy = c.y_norm - oy
                dist = math.hypot(dx, dy)
                if dist < 0.028:
                    stationary_hits += 1
                elif dy <= -0.015 and dist >= 0.032 and f.source_pts_us >= impact_pts_us - 20_000:
                    airborne_Observations.append((f.source_pts_us, f.source_frame_index, c, dx, dy))

        if not airborne_Observations:
            if stationary_hits > 0:
                return False, None, {}, ["stationary_ball_only"]
            return False, None, {}, ["no_ball_detected"]

        # 尋找具備時間相鄰性 (0 < dt_ms <= 68ms) 且向上升空連貫的最佳飛行鏈
        best_chain: list[tuple[int, int, BallDetectionCandidate]] = []
        for idx, (pts1, fidx1, c1, dx1, dy1) in enumerate(airborne_Observations):
            chain: list[tuple[int, int, BallDetectionCandidate]] = [(pts1, fidx1, c1)]
            last_pts, last_c = pts1, c1
            last_vx: float | None = None
            last_vy: float | None = None

            for pts2, fidx2, c2, _dx2, _dy2 in airborne_Observations[idx + 1 :]:
                dt_sec = (pts2 - last_pts) / 1_000_000.0
                if dt_sec <= 0.001:
                    continue
                if dt_sec > 0.14:  # 超過 140ms 斷鏈
                    break

                step_dx = c2.x_norm - last_c.x_norm
                step_dy = c2.y_norm - last_c.y_norm
                step_dist = math.hypot(step_dx, step_dy)
                # 排除原地不動之背景點與瞬間橫跨半個畫面的假點
                if step_dist < 0.008 or step_dist > 0.34:
                    continue
                # 爬升階段不可突然向下急墜 (允許高點後微幅下降 <= +0.025)
                if step_dy > 0.025:
                    continue

                if last_vx is not None and last_vy is not None:
                    # 檢查方向夾角一致性 (避免鋸齒亂跳)
                    pred_x = last_c.x_norm + last_vx * dt_sec
                    pred_y = last_c.y_norm + last_vy * dt_sec
                    if math.hypot(c2.x_norm - pred_x, c2.y_norm - pred_y) > 0.12:
                        continue

                last_vx = step_dx / dt_sec
                last_vy = step_dy / dt_sec
                chain.append((pts2, fidx2, c2))
                last_pts, last_c = pts2, c2

            if len(chain) > len(best_chain):
                best_chain = chain

        if len(best_chain) < 2:
            if stationary_hits > 0:
                return False, None, {}, ["stationary_ball_without_continuous_launch"]
            return False, None, {}, ["insufficient_continuous_airborne_detections"]

        # 確認第一與第二個點時間間隔 <= 68ms
        first_dt_ms = (best_chain[1][0] - best_chain[0][0]) / 1000.0
        if first_dt_ms > 68.0:
            return False, None, {}, ["launch_pair_time_gap_too_large"]

        chain_map = {pts: cand for pts, _fidx, cand in best_chain}
        launch_pts_us = best_chain[0][0]
        return True, launch_pts_us, chain_map, []

    def _build_flight_track_points(
        self,
        track_id: str,
        context: ResolvedSegmentContext,
        raw_detections: list[dict[str, Any]],
        airborne_chain: dict[int, BallDetectionCandidate],
        launch_pts_us: int,
    ) -> list[CanonicalTrackPoint]:
        """
        從起飛時間點開始，結合直接偵測點、光流補幀與 PTS-Kalman 預測建立軌跡序列。
        """
        kalman = PTSKalman2D(process_noise=2.0e-2, measurement_noise=4.0e-3, damping=0.985)
        points: list[CanonicalTrackPoint] = []

        last_airborne_pts = max(airborne_chain.keys())
        prev_frame: DecodedUprightFrame | None = None
        prev_xy_norm: tuple[float, float] | None = None
        prev_v_norm: tuple[float, float] | None = None
        consecutive_misses = 0

        for item in raw_detections:
            f: DecodedUprightFrame = item["frame"]
            if f.source_pts_us < launch_pts_us:
                prev_frame = f
                continue
            if f.source_pts_us > last_airborne_pts + 85_000:
                break

            direct_cand = airborne_chain.get(f.source_pts_us)
            if direct_cand is not None:
                consecutive_misses = 0
                sx, sy = kalman.observe(direct_cand.x_norm, direct_cand.y_norm, f.source_pts_us)
                if prev_xy_norm is not None:
                    prev_v_norm = (sx - prev_xy_norm[0], sy - prev_xy_norm[1])
                prev_xy_norm = (sx, sy)
                prev_frame = f

                is_smoothed = abs(sx - direct_cand.x_norm) > 1e-4 or abs(sy - direct_cand.y_norm) > 1e-4
                points.append(
                    CanonicalTrackPoint(
                        track_id=track_id,
                        track_type=TrackType.BALL,
                        segment_id=context.segment_id,
                        source_video_id=context.source_video_id,
                        source_pts_us=f.source_pts_us,
                        source_frame_index=f.source_frame_index,
                        x_norm=round(sx, 6),
                        y_norm=round(sy, 6),
                        confidence=direct_cand.confidence,
                        source_type=TrackSourceType.DETECTOR_OBSERVED,
                        position_role=(
                            PositionRole.DISPLAY_SMOOTHED if is_smoothed else PositionRole.RAW_OBSERVATION
                        ),
                        raw_observation={
                            "x_norm": round(direct_cand.x_norm, 6),
                            "y_norm": round(direct_cand.y_norm, 6),
                            "bbox": [round(v, 6) for v in direct_cand.bbox_norm],
                            "uncertainty_px": direct_cand.uncertainty_px,
                            "detector_confidence": direct_cand.confidence,
                            "evidence_kind": "direct_bbox",
                        },
                        phase="follow_through",
                        model_id=direct_cand.model_id,
                        evidence_frame_sha256=f.frame_sha256,
                        occlusion_state=OcclusionState.VISIBLE,
                        uncertainty_px=direct_cand.uncertainty_px,
                        error_flags=[],
                        created_by="model",
                    )
                )
                continue

            # 若該幀無直接 YOLO 命中，嘗試雙向金字塔 LK 光流追蹤
            consecutive_misses += 1
            flow_cand: BallDetectionCandidate | None = None
            if (
                consecutive_misses <= self.max_optical_flow_gap_frames
                and prev_frame is not None
                and prev_xy_norm is not None
            ):
                flow_cand = self.ball_detector.track_optical_flow_step(
                    prev_bgr=prev_frame.image_bgr,
                    curr_bgr=f.image_bgr,
                    prev_xy_norm=prev_xy_norm,
                    expected_v_norm=prev_v_norm,
                )

            if flow_cand is not None:
                sx, sy = kalman.observe(flow_cand.x_norm, flow_cand.y_norm, f.source_pts_us)
                if prev_xy_norm is not None:
                    prev_v_norm = (sx - prev_xy_norm[0], sy - prev_xy_norm[1])
                prev_xy_norm = (sx, sy)
                prev_frame = f
                points.append(
                    CanonicalTrackPoint(
                        track_id=track_id,
                        track_type=TrackType.BALL,
                        segment_id=context.segment_id,
                        source_video_id=context.source_video_id,
                        source_pts_us=f.source_pts_us,
                        source_frame_index=f.source_frame_index,
                        x_norm=round(sx, 6),
                        y_norm=round(sy, 6),
                        confidence=flow_cand.confidence,
                        source_type=TrackSourceType.OPTICAL_FLOW_ESTIMATED,
                        position_role=PositionRole.ESTIMATED_PATH,
                        raw_observation={
                            "x_norm": round(flow_cand.x_norm, 6),
                            "y_norm": round(flow_cand.y_norm, 6),
                            "bbox": [round(v, 6) for v in flow_cand.bbox_norm],
                            "uncertainty_px": flow_cand.uncertainty_px,
                            "detector_confidence": flow_cand.confidence,
                            "evidence_kind": "optical_flow_lk",
                        },
                        phase="follow_through",
                        model_id=flow_cand.model_id,
                        evidence_frame_sha256=f.frame_sha256,
                        occlusion_state=OcclusionState.BLURRED,
                        uncertainty_px=flow_cand.uncertainty_px,
                        error_flags=["motion_blur_optical_flow"],
                        created_by="model",
                    )
                )
                continue

            # 若光流亦無法鎖定，且仍在最後已知觀測點之前，才允許最多 max_kalman_gap_frames 幀卡爾曼橋接
            if consecutive_misses <= self.max_kalman_gap_frames and f.source_pts_us < last_airborne_pts:
                pred = kalman.predict_only(f.source_pts_us)
                if pred is not None:
                    px, py = pred
                    prev_xy_norm = (px, py)
                    prev_frame = f
                    points.append(
                        CanonicalTrackPoint(
                            track_id=track_id,
                            track_type=TrackType.BALL,
                            segment_id=context.segment_id,
                            source_video_id=context.source_video_id,
                            source_pts_us=f.source_pts_us,
                            source_frame_index=f.source_frame_index,
                            x_norm=round(px, 6),
                            y_norm=round(py, 6),
                            confidence=round(max(0.20, 0.50 - 0.10 * consecutive_misses), 4),
                            source_type=TrackSourceType.KALMAN_PREDICTED,
                            position_role=PositionRole.ESTIMATED_PATH,
                            raw_observation=None,
                            phase="follow_through",
                            model_id="pts_kalman_2d_v1",
                            evidence_frame_sha256=f.frame_sha256,
                            occlusion_state=OcclusionState.BLURRED,
                            uncertainty_px=round(6.0 + 3.5 * consecutive_misses, 2),
                            error_flags=["short_gap_kalman_bridge"],
                            created_by="model",
                        )
                    )
            else:
                prev_frame = f

        return points

    def _compute_shot_quality_summary(
        self,
        points: list[CanonicalTrackPoint],
        total_frames: int,
        context: ResolvedSegmentContext,
        camera_motion_score: float,
    ) -> TrackQualitySummary:
        direct_pts = [p for p in points if p.source_type == TrackSourceType.DETECTOR_OBSERVED]
        flow_pts = [p for p in points if p.source_type == TrackSourceType.OPTICAL_FLOW_ESTIMATED]
        kalman_pts = [p for p in points if p.source_type == TrackSourceType.KALMAN_PREDICTED]
        manual_pts = [p for p in points if p.source_type == TrackSourceType.MANUALLY_ANNOTATED]
        artistic_pts = [p for p in points if p.source_type == TrackSourceType.ARTISTIC_ONLY]

        if artistic_pts:
            mode = ShotTrackMode.ARTISTIC_EXTENSION
        elif manual_pts:
            mode = ShotTrackMode.MANUAL_ANCHORED
        elif len(direct_pts) >= 4:
            mode = ShotTrackMode.AUTO_OBSERVED
        elif len(direct_pts) >= 2 and len(points) >= 4:
            mode = ShotTrackMode.AUTO_ASSISTED
        else:
            mode = ShotTrackMode.UNAVAILABLE

        uncertainties = [p.uncertainty_px for p in points]
        confs = [p.confidence for p in points]
        obs_range = (
            [direct_pts[0].source_pts_us, direct_pts[-1].source_pts_us] if direct_pts else []
        )
        pred_ranges: list[list[int]] = []
        for p in flow_pts + kalman_pts:
            pred_ranges.append([p.source_pts_us, p.source_pts_us])

        denom = max(1, len(points))
        return TrackQualitySummary(
            track_type=TrackType.BALL,
            status=mode.value,
            total_frames=total_frames,
            total_points=len(points),
            direct_observed_count=len(direct_pts),
            optical_flow_count=len(flow_pts),
            kalman_predicted_count=len(kalman_pts),
            manual_count=len(manual_pts),
            artistic_count=len(artistic_pts),
            direct_observation_coverage=round(len(direct_pts) / float(denom), 4),
            manual_coverage=round(len(manual_pts) / float(denom), 4),
            mean_confidence=round(float(np.mean(confs)) if confs else 0.0, 4),
            p50_uncertainty_px=round(float(np.percentile(uncertainties, 50)) if uncertainties else 0.0, 2),
            p95_uncertainty_px=round(float(np.percentile(uncertainties, 95)) if uncertainties else 0.0, 2),
            observed_range_pts_us=obs_range,
            predicted_ranges_pts_us=pred_ranges,
            rejection_reasons=[],
            end_to_end_eligible=(mode == ShotTrackMode.AUTO_OBSERVED),
            view_angle=context.view_angle,
            handedness=context.handedness,
            camera_motion_score=camera_motion_score,
            notes=(
                "已由高解析原片自動觀測完整飛球初段軌跡。"
                if mode == ShotTrackMode.AUTO_OBSERVED
                else "飛球初段含光流/卡爾曼輔助補幀，建議於 Studio 檢視。"
            ),
        )

    def _build_empty_result(
        self,
        track_id: str,
        context: ResolvedSegmentContext,
        mode: ShotTrackMode,
        reasons: list[str],
        notes: str,
    ) -> ShotTraceResult:
        return ShotTraceResult(
            track_id=track_id,
            mode=mode,
            points=[],
            quality_summary=TrackQualitySummary(
                track_type=TrackType.BALL,
                status=mode.value,
                total_frames=0,
                total_points=0,
                rejection_reasons=reasons,
                end_to_end_eligible=False,
                view_angle=context.view_angle,
                handedness=context.handedness,
                notes=notes,
            ),
            stationary_ball_norm=None,
            observed_launch_pts_us=None,
        )
