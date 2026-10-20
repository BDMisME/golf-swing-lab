import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from packages.analysis.events.state_machine import (
    DetectedEvent,
    SwingPhaseStateMachine,
    compute_observable_metrics,
)
from packages.analysis.pose import (
    FramePoseResult,
    PoseExtractor,
    create_pose_extractor,
)

logger = logging.getLogger(__name__)


def compute_time_iou(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    """計算兩個時間區間 [a_start, a_end] 與 [b_start, b_end] 之交集聯集比 (IoU)。"""
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    if inter <= 0:
        return 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    return float(inter) / float(max(1, union))


def merge_overlapping_windows(
    windows: list[tuple[int, int]],
    iou_threshold: float = 0.20,
    min_gap_ms: int = 400,
) -> list[tuple[int, int]]:
    """合併重疊或間距過短之揮桿候選視窗，避免從空揮到正式揮桿重複計數。"""
    if not windows:
        return []
    sorted_wins = sorted(windows, key=lambda w: (w[0], w[1]))
    merged: list[tuple[int, int]] = [sorted_wins[0]]
    for start_ms, end_ms in sorted_wins[1:]:
        prev_start, prev_end = merged[-1]
        iou = compute_time_iou(prev_start, prev_end, start_ms, end_ms)
        if iou >= iou_threshold or (start_ms - prev_end) <= min_gap_ms:
            # 若合併後總長度仍小於 6.0 秒則合併；否則視為兩次連續獨立揮桿
            if (max(prev_end, end_ms) - min(prev_start, start_ms)) <= 6000:
                merged[-1] = (min(prev_start, start_ms), max(prev_end, end_ms))
            else:
                merged.append((start_ms, end_ms))
        else:
            merged.append((start_ms, end_ms))
    return merged


@dataclass
class CandidateSegmentResult:
    sequence_no: int
    start_ms: int
    end_ms: int
    label: str
    ball_strike_status: str
    confidence: float
    review_status: str
    review_flags: list[str]
    events: list[DetectedEvent]
    metrics: list[dict[str, Any]]
    keyframes: list[dict[str, Any]]
    quality_metadata: dict[str, Any] = field(default_factory=dict)


class CoarseToFineDetector:
    """
    長影片 Coarse-to-Fine 自動揮桿偵測器：
    1. Coarse Scan (~5 fps 串流取樣，不載入整部影片至 RAM)：計算手部運動能量與人體存在度。
    2. Event Clustering：聚合運動峰值視窗，套用最短/最長時長與冷卻時間並執行 IoU 去重。
    3. Fine Scan (~15–20 fps 針對候選視窗精細取樣)：透過 MediaPipe PoseLandmarker 與 9 階段狀態機提取階段事件與指標。
    """

    def __init__(
        self,
        model_version: str = "pose-v1",
        coarse_step_ms: int = 200,
        fine_step_ms: int = 66,
        min_swing_duration_ms: int = 1400,
        max_swing_duration_ms: int = 7500,
    ) -> None:
        self.model_version = model_version
        self.coarse_step_ms = coarse_step_ms
        self.fine_step_ms = fine_step_ms
        self.min_swing_duration_ms = min_swing_duration_ms
        self.max_swing_duration_ms = max_swing_duration_ms
        self.state_machine = SwingPhaseStateMachine(model_version=model_version)

    def analyze_video(
        self,
        video_path: str | Path,
        duration_ms: int,
        progress_cb: Callable[[str, int, str], None] | None = None,
    ) -> tuple[list[CandidateSegmentResult], dict[str, Any]]:
        extractor = create_pose_extractor(backend=self.model_version)
        try:
            if progress_cb:
                progress_cb("coarse_scan", 20, "啟動低解析度稀疏掃描 (Coarse Scan)")

            coarse_frames = self._sample_video_window(
                video_path=video_path,
                extractor=extractor,
                start_ms=0,
                end_ms=duration_ms,
                step_ms=self.coarse_step_ms,
            )

            quality_summary = self._summarize_quality(coarse_frames)
            raw_windows = self._cluster_activity_windows(coarse_frames, duration_ms)
            candidate_windows = merge_overlapping_windows(raw_windows)

            if progress_cb:
                progress_cb(
                    "fine_scan",
                    50,
                    f"粗掃定位 {len(candidate_windows)} 個候選視窗，進入高幀率精掃 (Fine Scan)",
                )

            results: list[CandidateSegmentResult] = []
            total_wins = max(1, len(candidate_windows))
            seq_counter = 1
            for idx, (win_start, win_end) in enumerate(candidate_windows, start=1):
                seg = self.analyze_single_window(
                    video_path=video_path,
                    start_ms=win_start,
                    end_ms=win_end,
                    sequence_no=seq_counter,
                    extractor=extractor,
                )
                if seg is not None and len(seg.events) >= 4:
                    seg.sequence_no = seq_counter
                    results.append(seg)
                    seq_counter += 1
                if progress_cb:
                    pct = 50 + int((idx / total_wins) * 30)
                    progress_cb("fine_scan", pct, f"已完成第 {idx}/{len(candidate_windows)} 候選視窗精細分析")

            # 計算同場多球真實手部軌跡重複性偏差 (session_path_repeatability)
            from packages.analysis.scoring.engine import compute_session_wrist_repeatability

            trajs: dict[str, list[dict[str, Any]]] = {
                str(s.sequence_no): s.quality_metadata.get("wrist_trajectory", [])
                for s in results
            }
            repeat_res = compute_session_wrist_repeatability(trajs)
            for s in results:
                r_info = repeat_res.get(str(s.sequence_no), {})
                s.metrics.append(
                    {
                        "metric_key": "session_path_repeatability",
                        "value": r_info.get("deviation"),
                        "unit": "ratio",
                        "confidence": r_info.get("confidence", 0.0),
                        "source": self.model_version,
                        "observability": "observed_2d",
                    }
                )

            return results, quality_summary
        finally:
            extractor.close()

    def analyze_single_window(
        self,
        video_path: str | Path,
        start_ms: int,
        end_ms: int,
        sequence_no: int = 1,
        extractor: PoseExtractor | None = None,
    ) -> CandidateSegmentResult | None:
        own_extractor = extractor is None
        ext = extractor or create_pose_extractor()
        try:
            fine_frames = self._sample_video_window(
                video_path=video_path,
                extractor=ext,
                start_ms=start_ms,
                end_ms=end_ms,
                step_ms=self.fine_step_ms,
            )
            if not fine_frames:
                return None

            events, state_trace, label = self.state_machine.extract_events(fine_frames)

            # 根據偵測到的 address/takeaway 與 finish/follow_through 精細對齊揮桿片段邊界
            refined_start = start_ms
            refined_end = end_ms
            if events:
                ev_map = {e.event_name: e.time_ms for e in events}
                if "address" in ev_map:
                    refined_start = max(start_ms, ev_map["address"] - 300)
                elif "takeaway" in ev_map:
                    refined_start = max(start_ms, ev_map["takeaway"] - 700)

                if "finish" in ev_map:
                    refined_end = min(end_ms, ev_map["finish"] + 450)
                elif "follow_through" in ev_map:
                    refined_end = min(end_ms, ev_map["follow_through"] + 800)
                elif "impact" in ev_map:
                    refined_end = min(end_ms, ev_map["impact"] + 1200)

                if refined_end - refined_start < self.min_swing_duration_ms:
                    refined_start = start_ms
                    refined_end = end_ms

            metrics = compute_observable_metrics(
                frames=fine_frames, events=events, model_version=self.model_version
            )

            flags_set: set[str] = set()
            confs: list[float] = []
            brights: list[float] = []
            sharps: list[float] = []
            cam_motions: list[float] = []
            vis_list: list[float] = []
            oof_flags: set[str] = set()

            for fr in fine_frames:
                confs.append(fr.pose_confidence)
                brights.append(fr.brightness)
                sharps.append(fr.sharpness)
                cam_motions.append(fr.camera_motion)
                if fr.landmarks:
                    l_vis = [lm.visibility for lm in fr.landmarks.values()]
                    vis_list.append(float(np.mean(l_vis)))
                    nose = fr.landmarks.get("nose")
                    if nose and (nose.y < 0.02 or nose.y > 0.98 or nose.x < 0.02 or nose.x > 0.98):
                        oof_flags.add("head_out_of_frame")
                    l_ankle = fr.landmarks.get("left_ankle")
                    r_ankle = fr.landmarks.get("right_ankle")
                    if (l_ankle and (l_ankle.y > 0.98 or l_ankle.y < 0.02)) or (r_ankle and (r_ankle.y > 0.98 or r_ankle.y < 0.02)):
                        oof_flags.add("feet_out_of_frame")
                else:
                    vis_list.append(0.0)

                for fl in fr.flags:
                    if fl != "pose_missing":
                        flags_set.add(fl)

            body_vis_ratio = round(float(np.mean(vis_list)), 3) if vis_list else 0.0
            mean_conf = float(np.mean(confs)) if confs else 0.0
            if not events:
                flags_set.add("incomplete_swing_phases")
                label = "swing_candidate"
                mean_conf = min(mean_conf, 0.45)

            if mean_conf < 0.62:
                flags_set.add("low_confidence")

            review_flags = sorted(flags_set)
            if (
                "low_confidence" in flags_set
                or "multi_person" in flags_set
                or "low_light" in flags_set
                or "incomplete_swing_phases" in flags_set
                or label == "practice_swing"
            ):
                review_status = "needs_review"
            else:
                review_status = "auto_accepted"

            if label == "practice_swing":
                ball_strike_status = "no_ball"
            elif mean_conf >= 0.68 and events:
                ball_strike_status = "estimated_strike"
            else:
                ball_strike_status = "strike_unknown"

            # 僅儲存精簡過之關鍵影格與抽樣點（避免 API 回傳龐大逐幀資料）
            event_times = {e.time_ms for e in events}
            keyframes: list[dict[str, Any]] = []
            for idx_f, fr in enumerate(fine_frames):
                if fr.time_ms in event_times or idx_f % 2 == 0:
                    keyframes.append(fr.to_dict())

            # 若為有效擊球，啟動小白球專用模型與卡爾曼濾波器捕獲出球飛行彈道
            ball_traj: list[dict[str, float]] = []
            imp_ev = next((e for e in events if "impact" in e.event_name), None)
            if imp_ev and label == "valid_swing":
                try:
                    from packages.analysis.tracking.ball_tracker import GolfBallDetector
                    b_det = GolfBallDetector()
                    ref_wrist = None
                    for fr in fine_frames:
                        if abs(fr.time_ms - imp_ev.time_ms) < 150:
                            rw = fr.landmarks.get("right_wrist") or fr.landmarks.get("left_wrist")
                            if rw:
                                ref_wrist = (rw.x, rw.y)
                                break
                    ball_traj = b_det.track_swing_launch(
                        video_path=video_path,
                        impact_ms=imp_ev.time_ms,
                        player_wrist_norm=ref_wrist,
                        duration_ms=1200,
                    )
                except Exception as b_exc:
                    logger.debug(f"小白球彈道追蹤跳過或異常: {b_exc}")

            # 提取手腕 2D 軌跡點序列供多球重複性計算
            wrist_traj: list[dict[str, Any]] = []
            for fr in fine_frames:
                lw = fr.landmarks.get("left_wrist")
                rw = fr.landmarks.get("right_wrist")
                if lw and rw:
                    w_conf = min(lw.visibility, rw.visibility)
                    wrist_traj.append({
                        "time_ms": fr.time_ms,
                        "x": round(float((lw.x + rw.x) / 2.0), 4),
                        "y": round(float((lw.y + rw.y) / 2.0), 4),
                        "conf": round(float(w_conf), 3),
                    })
                elif rw:
                    wrist_traj.append({
                        "time_ms": fr.time_ms,
                        "x": round(float(rw.x), 4),
                        "y": round(float(rw.y), 4),
                        "conf": round(float(rw.visibility), 3),
                    })
                elif lw:
                    wrist_traj.append({
                        "time_ms": fr.time_ms,
                        "x": round(float(lw.x), 4),
                        "y": round(float(lw.y), 4),
                        "conf": round(float(lw.visibility), 3),
                    })

            quality_meta = {
                "mean_brightness": round(float(np.mean(brights or [0.0])), 2),
                "mean_sharpness": round(float(np.mean(sharps or [0.0])), 2),
                "max_camera_motion": round(float(np.max(cam_motions or [0.0])), 4),
                "body_visibility_ratio": body_vis_ratio,
                "out_of_frame_flags": sorted(oof_flags),
                "state_trace": state_trace,
                "sampled_frame_count": len(fine_frames),
                "ball_trajectory": ball_traj,
                "wrist_trajectory": wrist_traj,
            }

            return CandidateSegmentResult(
                sequence_no=sequence_no,
                start_ms=refined_start,
                end_ms=refined_end,
                label=label,
                ball_strike_status=ball_strike_status,
                confidence=round(mean_conf, 3),
                review_status=review_status,
                review_flags=review_flags,
                events=events,
                metrics=metrics,
                keyframes=keyframes,
                quality_metadata=quality_meta,
            )
        finally:
            if own_extractor:
                ext.close()

    def _sample_video_window(
        self,
        video_path: str | Path,
        extractor: PoseExtractor,
        start_ms: int,
        end_ms: int,
        step_ms: int,
    ) -> list[FramePoseResult]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        results: list[FramePoseResult] = []
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(max(0, start_ms)))
            next_target_ms = start_ms
            prev_gray: np.ndarray | None = None
            prev_wrist: tuple[float, float] | None = None
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                actual_pts_ms = int(round(cap.get(cv2.CAP_PROP_POS_MSEC)))
                if actual_pts_ms <= 0 and frame_idx > 0:
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    actual_pts_ms = start_ms + int(round((frame_idx / fps) * 1000))

                if actual_pts_ms > end_ms:
                    break

                if actual_pts_ms >= next_target_ms:
                    pose_res, prev_gray, prev_wrist = extractor.analyze_frame(
                        frame_bgr=frame,
                        time_ms=actual_pts_ms,
                        frame_idx=frame_idx,
                        prev_gray=prev_gray,
                        prev_wrist=prev_wrist,
                    )
                    results.append(pose_res)
                    next_target_ms = actual_pts_ms + step_ms

                frame_idx += 1
        finally:
            cap.release()

        return results

    def _cluster_activity_windows(
        self, coarse_frames: list[FramePoseResult], duration_ms: int
    ) -> list[tuple[int, int]]:
        if not coarse_frames:
            return []

        # 尋找手腕運動峰值（揮桿中上桿→頂點→下桿→隨揮具有顯著能量與垂直位置變化）
        active_indices: list[int] = []
        for i, fr in enumerate(coarse_frames):
            rw = fr.landmarks.get("right_wrist") or fr.landmarks.get("left_wrist")
            sh = fr.landmarks.get("right_shoulder") or fr.landmarks.get("left_shoulder")
            is_hands_raised = bool(rw and sh and rw.y < sh.y + 0.02)
            if fr.wrist_motion_energy >= 0.032 or is_hands_raised:
                active_indices.append(i)

        if not active_indices:
            return []

        # 將相鄰 active 樣本聚類為候選區段
        clusters: list[tuple[int, int]] = []
        cluster_start = active_indices[0]
        prev_idx = active_indices[0]

        for idx in active_indices[1:]:
            gap_ms = coarse_frames[idx].time_ms - coarse_frames[prev_idx].time_ms
            if gap_ms <= 1200:
                prev_idx = idx
            else:
                clusters.append((cluster_start, prev_idx))
                cluster_start = idx
                prev_idx = idx
        clusters.append((cluster_start, prev_idx))

        windows: list[tuple[int, int]] = []
        for s_idx, e_idx in clusters:
            raw_s = coarse_frames[s_idx].time_ms
            raw_e = coarse_frames[e_idx].time_ms
            # 起手前補足 Address 準備時間緩衝 (800ms)，收桿末端補足 Finish 停留緩衝 (800ms)
            win_s = max(0, raw_s - 800)
            win_e = min(duration_ms, raw_e + 800)
            if win_e - win_s < self.min_swing_duration_ms:
                pad = (self.min_swing_duration_ms - (win_e - win_s)) // 2 + 150
                win_s = max(0, win_s - pad)
                win_e = min(duration_ms, win_e + pad)
            if (win_e - win_s) >= 1000:
                windows.append((win_s, min(win_s + self.max_swing_duration_ms, win_e)))

        return windows

    def _summarize_quality(self, frames: list[FramePoseResult]) -> dict[str, Any]:
        if not frames:
            return {
                "mean_brightness": 0.0,
                "mean_sharpness": 0.0,
                "max_camera_motion": 0.0,
                "low_light": True,
                "camera_unstable": False,
                "multi_person_detected": False,
                "flags": ["empty_frames"],
            }
        brights = [f.brightness for f in frames]
        sharps = [f.sharpness for f in frames]
        motions = [f.camera_motion for f in frames]
        multi = sum(1 for f in frames if f.person_count > 1)
        flags: list[str] = []
        if float(np.mean(brights)) < 35.0:
            flags.append("low_light")
        if float(np.max(motions)) > 0.08:
            flags.append("camera_motion")
        if multi > 0:
            flags.append("multi_person")
        return {
            "mean_brightness": round(float(np.mean(brights)), 2),
            "mean_sharpness": round(float(np.mean(sharps)), 2),
            "max_camera_motion": round(float(np.max(motions)), 4),
            "low_light": "low_light" in flags,
            "camera_unstable": "camera_motion" in flags,
            "multi_person_detected": "multi_person" in flags,
            "flags": flags,
        }
