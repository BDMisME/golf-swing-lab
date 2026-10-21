import logging
import math
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
class AudioExtractionResult:
    transients: list[int] = field(default_factory=list)
    status: str = "ok"  # "ok", "no_audio", "timeout", "error", "too_short"
    error_message: str | None = None

    def __iter__(self):
        return iter(self.transients)

    def __len__(self):
        return len(self.transients)

    def __getitem__(self, index):
        return self.transients[index]


def extract_audio_transients(
    video_path: str | Path,
    start_ms: int | None = None,
    duration_ms: int | None = None,
    timeout: int | None = None,
) -> AudioExtractionResult:
    """
    從影片音訊軌抽取短時能量脈衝時間碼 (ms)。
    支援：
    1. 局部時間區間快速抽取 (start_ms, duration_ms)
    2. 動態逾時機制，避免長影片受固定 timeout 影響中斷
    3. 明確回傳解碼狀態與失敗原因 (no_audio, timeout, ffmpeg_error, ok)
    """
    try:
        import subprocess

        cmd = ["ffmpeg", "-v", "error"]
        if start_ms is not None and start_ms > 0:
            cmd.extend(["-ss", f"{start_ms / 1000.0:.3f}"])
        if duration_ms is not None and duration_ms > 0:
            cmd.extend(["-t", f"{duration_ms / 1000.0:.3f}"])

        cmd.extend([
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ])

        # 動態計算逾時時間：至少 15 秒，若是局部區間則 8 秒，長片則給予充足餘裕
        actual_timeout = timeout
        if actual_timeout is None:
            if duration_ms is not None:
                actual_timeout = max(8, int(duration_ms / 1000.0 * 0.5) + 5)
            else:
                actual_timeout = 25  # 預設長片全量抽取上限提高至 25 秒

        proc = subprocess.run(cmd, capture_output=True, timeout=actual_timeout)
        if proc.returncode != 0:
            stderr_str = proc.stderr.decode("utf-8", errors="ignore")
            if "does not contain any stream" in stderr_str or "matches no streams" in stderr_str:
                return AudioExtractionResult([], status="no_audio", error_message="影片無音訊軌道")
            return AudioExtractionResult([], status="error", error_message=f"FFmpeg 解碼失敗: {stderr_str.strip()[:120]}")

        if not proc.stdout:
            return AudioExtractionResult([], status="no_audio", error_message="未讀取到音訊數據")

        audio_data = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
        if len(audio_data) < 8000 * 0.15:
            return AudioExtractionResult([], status="too_short", error_message="音訊數據長度過短 (<150ms)")

        window_size = int(8000 * 0.05)  # 50ms
        hop_size = int(8000 * 0.02)  # 20ms
        energies: list[float] = []
        timestamps: list[int] = []
        time_offset_ms = start_ms if start_ms is not None else 0

        for i in range(0, len(audio_data) - window_size, hop_size):
            chunk = audio_data[i : i + window_size]
            rms = float(np.sqrt(np.mean(chunk**2)))
            energies.append(rms)
            timestamps.append(time_offset_ms + int(round(i * 1000.0 / 8000.0)))

        if not energies:
            return AudioExtractionResult([], status="ok", error_message=None)

        arr_e = np.array(energies)
        diff_e = np.diff(arr_e, prepend=arr_e[0])
        thresh = float(np.percentile(diff_e, 94))
        transients: list[int] = []
        for k in range(1, len(diff_e) - 1):
            if diff_e[k] > thresh and diff_e[k] > diff_e[k - 1] and diff_e[k] > diff_e[k + 1]:
                transients.append(timestamps[k])

        return AudioExtractionResult(transients, status="ok", error_message=None)
    except subprocess.TimeoutExpired:
        logger.warning(f"音訊抽取逾時 ({actual_timeout}s): {video_path}")
        return AudioExtractionResult([], status="timeout", error_message=f"音訊解碼逾時超過 {actual_timeout} 秒")
    except Exception as exc:
        logger.warning(f"音訊抽取異常: {exc}")
        return AudioExtractionResult([], status="error", error_message=str(exc))




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

            all_audio_transients = extract_audio_transients(video_path)
            quality_summary["audio_status"] = all_audio_transients.status
            quality_summary["audio_error"] = all_audio_transients.error_message
            quality_summary["audio_transients_count"] = len(all_audio_transients.transients)

            results: list[CandidateSegmentResult] = []
            total_wins = max(1, len(candidate_windows))
            seq_counter = 1
            for idx, (win_start, win_end) in enumerate(candidate_windows, start=1):
                win_transients = [
                    t for t in all_audio_transients if (win_start - 400) <= t <= (win_end + 400)
                ]
                seg = self.analyze_single_window(
                    video_path=video_path,
                    start_ms=win_start,
                    end_ms=win_end,
                    sequence_no=seq_counter,
                    extractor=extractor,
                    audio_transients_ms=win_transients,
                    audio_status=all_audio_transients.status,
                    audio_error=all_audio_transients.error_message,
                )
                if seg is not None and len(seg.events) >= 4:
                    seg.sequence_no = seq_counter
                    results.append(seg)
                    seq_counter += 1
                if progress_cb:
                    pct = 50 + int((idx / total_wins) * 30)
                    progress_cb("fine_scan", pct, f"已完成第 {idx}/{len(candidate_windows)} 候選視窗精細分析")

            # 計算同場多球真實手部軌跡重複性偏差 (session_path_repeatability - score-v2.1)
            # 排除空揮 (practice_swing)、人工/系統拒絕 (rejected) 與低信心度 (< 0.60) 揮桿
            from packages.analysis.scoring.engine import compute_session_wrist_repeatability

            eligible_swings = [
                s for s in results
                if s.label == "valid_swing"
                and s.review_status != "rejected"
                and s.confidence >= 0.60
            ]
            trajs: dict[str, list[dict[str, Any]]] = {
                str(s.sequence_no): s.quality_metadata.get("wrist_trajectory", [])
                for s in eligible_swings
            }
            repeat_res = compute_session_wrist_repeatability(trajs)
            for s in results:
                seq_key = str(s.sequence_no)
                if seq_key in repeat_res:
                    r_info = repeat_res[seq_key]
                    s.metrics.append(
                        {
                            "metric_key": "session_path_repeatability",
                            "value": r_info.get("deviation"),
                            "unit": "ratio",
                            "confidence": r_info.get("confidence", 0.0),
                            "source": self.model_version,
                            "observability": "observed_2d",
                            "details": {
                                "normalized_by": r_info.get("normalized_by", "none"),
                                "valid_session_swings": r_info.get("valid_session_swings", 0),
                            },
                        }
                    )
                else:
                    s.metrics.append(
                        {
                            "metric_key": "session_path_repeatability",
                            "value": None,
                            "unit": "ratio",
                            "confidence": 0.0,
                            "source": self.model_version,
                            "observability": "observed_2d",
                            "details": {
                                "reason": "此揮桿為空揮或信心度不足，不計入多球重複性比較",
                            },
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
        audio_transients_ms: list[int] | None = None,
        ball_strike_ms: int | None = None,
        audio_status: str = "ok",
        audio_error: str | None = None,
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

            if audio_transients_ms is None:
                all_aud = extract_audio_transients(video_path)
                audio_transients_ms = [
                    t for t in all_aud if (start_ms - 400) <= t <= (end_ms + 400)
                ]

            events, state_trace, label = self.state_machine.extract_events(
                fine_frames,
                audio_transients_ms=audio_transients_ms,
                ball_strike_ms=ball_strike_ms,
            )

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
            ball_feedback_info: dict[str, Any] = {"applied": False, "observed_count": 0}
            imp_ev = next((e for e in events if "impact" in e.event_name), None)
            top_ev = next((e for e in events if e.event_name == "top"), None)

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
                    ball_res = b_det.track_swing_launch_with_feedback(
                        video_path=video_path,
                        impact_ms=imp_ev.time_ms,
                        player_wrist_norm=ref_wrist,
                        duration_ms=1200,
                    )
                    ball_traj = ball_res.get("trajectory_points", [])
                    obs_launch = ball_res.get("observed_launch_ms")
                    obs_count = ball_res.get("observed_count", 0)
                    ball_feedback_info["observed_count"] = obs_count

                    # 若可靠偵測到真球啟動出球，回饋修正 Impact 事件
                    if ball_res.get("is_valid") and obs_launch is not None:
                        diff = abs(obs_launch - imp_ev.time_ms)
                        if diff <= 180:
                            orig_imp = imp_ev.time_ms
                            imp_ev.time_ms = obs_launch
                            imp_ev.uncertainty_ms = 16
                            imp_ev.confidence = min(0.98, max(imp_ev.confidence, 0.92))
                            if "ball_flight_observed_launch" not in imp_ev.detection_sources:
                                imp_ev.detection_sources.append("ball_flight_observed_launch")
                            imp_ev.rationale = f"真球出發點 (ball_launch_onset @ {obs_launch}ms) 權威觀測定位擊球瞬間"
                            ball_strike_status = "confirmed_strike"
                            ball_feedback_info["applied"] = True
                            ball_feedback_info["original_impact_ms"] = orig_imp
                            ball_feedback_info["refined_impact_ms"] = obs_launch
                            ball_feedback_info["delta_ms"] = obs_launch - orig_imp
                except Exception as b_exc:
                    logger.debug(f"小白球彈道追蹤跳過或異常: {b_exc}")

            # 局部高 FPS 二次精修 (在初步以 ~15 FPS 抽樣後，針對關鍵 Top 與未獲真球鎖定之 Impact，進行前後 ±200ms 的 60 FPS 精修)
            local_refinements: dict[str, Any] = {}
            if top_ev and (top_ev.uncertainty_ms > 20 or top_ev.confidence < 0.95):
                top_ref = self._refine_event_local_high_fps(
                    video_path=video_path,
                    extractor=ext,
                    event_name="top",
                    center_ms=top_ev.time_ms,
                    window_radius_ms=200,
                    high_fps_step_ms=16,
                )
                if top_ref:
                    top_ev.time_ms = top_ref["refined_ms"]
                    top_ev.confidence = top_ref["confidence"]
                    top_ev.uncertainty_ms = top_ref["uncertainty_ms"]
                    for s in top_ref["sources"]:
                        if s not in top_ev.detection_sources:
                            top_ev.detection_sources.append(s)
                    local_refinements["top"] = top_ref

            if imp_ev and not ball_feedback_info.get("applied") and (imp_ev.uncertainty_ms > 20 or imp_ev.confidence < 0.95):
                imp_ref = self._refine_event_local_high_fps(
                    video_path=video_path,
                    extractor=ext,
                    event_name="impact",
                    center_ms=imp_ev.time_ms,
                    window_radius_ms=200,
                    high_fps_step_ms=16,
                )
                if imp_ref:
                    imp_ev.time_ms = imp_ref["refined_ms"]
                    imp_ev.confidence = imp_ref["confidence"]
                    imp_ev.uncertainty_ms = imp_ref["uncertainty_ms"]
                    for s in imp_ref["sources"]:
                        if s not in imp_ev.detection_sources:
                            imp_ev.detection_sources.append(s)
                    local_refinements["impact"] = imp_ref

            # 誠實檢查 detection_sources：未實際發生的來源絕不保留
            if imp_ev:
                if not ball_feedback_info.get("applied") and "ball_flight_observed_launch" in imp_ev.detection_sources:
                    imp_ev.detection_sources.remove("ball_flight_observed_launch")
                if audio_transients_ms:
                    closest_aud = min(audio_transients_ms, key=lambda a: abs(a - imp_ev.time_ms))
                    if abs(closest_aud - imp_ev.time_ms) > 60 and "audio_transient_consensus" in imp_ev.detection_sources:
                        imp_ev.detection_sources.remove("audio_transient_consensus")
                else:
                    if "audio_transient_consensus" in imp_ev.detection_sources:
                        imp_ev.detection_sources.remove("audio_transient_consensus")


            # 提取手腕 2D 軌跡點序列供多球重複性計算
            wrist_traj: list[dict[str, Any]] = []
            for fr in fine_frames:
                lw = fr.landmarks.get("left_wrist")
                rw = fr.landmarks.get("right_wrist")
                lh = fr.landmarks.get("left_hip")
                rh = fr.landmarks.get("right_hip")
                ls = fr.landmarks.get("left_shoulder")
                rs = fr.landmarks.get("right_shoulder")

                hip_x: float | None = None
                hip_y: float | None = None
                torso_len: float | None = None
                if lh and rh:
                    hip_x = round(float((lh.x + rh.x) / 2.0), 4)
                    hip_y = round(float((lh.y + rh.y) / 2.0), 4)
                    if ls and rs:
                        sh_x = (ls.x + rs.x) / 2.0
                        sh_y = (ls.y + rs.y) / 2.0
                        torso_len = round(float(math.hypot(sh_x - hip_x, sh_y - hip_y)), 4)

                point_entry: dict[str, Any] | None = None
                if lw and rw:
                    w_conf = min(lw.visibility, rw.visibility)
                    point_entry = {
                        "time_ms": fr.time_ms,
                        "x": round(float((lw.x + rw.x) / 2.0), 4),
                        "y": round(float((lw.y + rw.y) / 2.0), 4),
                        "conf": round(float(w_conf), 3),
                    }
                elif rw:
                    point_entry = {
                        "time_ms": fr.time_ms,
                        "x": round(float(rw.x), 4),
                        "y": round(float(rw.y), 4),
                        "conf": round(float(rw.visibility), 3),
                    }
                elif lw:
                    point_entry = {
                        "time_ms": fr.time_ms,
                        "x": round(float(lw.x), 4),
                        "y": round(float(lw.y), 4),
                        "conf": round(float(lw.visibility), 3),
                    }

                if point_entry is not None:
                    if hip_x is not None and hip_y is not None:
                        point_entry["hip_x"] = hip_x
                        point_entry["hip_y"] = hip_y
                    if torso_len is not None and torso_len > 0.05:
                        point_entry["torso_len"] = torso_len
                    wrist_traj.append(point_entry)

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
                "ball_strike_feedback": ball_feedback_info,
                "local_refinements": local_refinements,
                "audio_status": audio_status,
                "audio_error": audio_error,
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

    def _refine_event_local_high_fps(
        self,
        video_path: str | Path,
        extractor: PoseExtractor,
        event_name: str,
        center_ms: int,
        window_radius_ms: int = 200,
        high_fps_step_ms: int = 16,
    ) -> dict[str, Any] | None:
        """
        針對特定關鍵事件 (Top 或 Impact) 進行局部高幀率 (~60 FPS) 取樣精修。
        僅讀取 [center_ms - window_radius_ms, center_ms + window_radius_ms] 短暫視窗，
        無需重新解碼整部影片。
        """
        start_ms = max(0, center_ms - window_radius_ms)
        end_ms = center_ms + window_radius_ms
        local_frames = self._sample_video_window(
            video_path=video_path,
            extractor=extractor,
            start_ms=start_ms,
            end_ms=end_ms,
            step_ms=high_fps_step_ms,
        )
        if len(local_frames) < 3:
            return None

        times = [f.time_ms for f in local_frames]
        wrist_ys = []
        wrist_confs = []
        for f in local_frames:
            w = f.landmarks.get("right_wrist") or f.landmarks.get("left_wrist")
            if w:
                wrist_ys.append(float(w.y))
                wrist_confs.append(float(w.visibility))
            else:
                wrist_ys.append(1.0)
                wrist_confs.append(0.0)

        dt_arr = np.diff(times).astype(float)
        dt_arr[dt_arr <= 0] = 16.6
        v_y = np.gradient(wrist_ys, times)

        if event_name == "top":
            # 搜尋手腕最高點與零交越點
            zero_crossings = [i for i in range(len(v_y) - 1) if v_y[i] <= 0 and v_y[i + 1] > 0]
            y_min_idx = int(np.argmin(wrist_ys))
            refined_idx = y_min_idx
            sources = ["wrist_y_local_minimum", "local_high_fps_refinement"]
            if zero_crossings:
                best_zc = min(zero_crossings, key=lambda i: abs(i - y_min_idx))
                refined_idx = best_zc
                sources = ["wrist_velocity_zero_crossing", "local_high_fps_refinement"]

            refined_time_ms = times[refined_idx]
            return {
                "refined_ms": refined_time_ms,
                "confidence": min(0.96, max(0.75, wrist_confs[refined_idx])),
                "uncertainty_ms": 16,
                "sources": sources,
                "delta_ms": refined_time_ms - center_ms,
            }

        elif event_name == "impact":
            # 搜尋下桿速度劇烈制動點 (減速峰值)
            speeds = np.abs(v_y)
            accels = np.diff(speeds, prepend=speeds[0])
            decel_idx = int(np.argmin(accels))
            refined_time_ms = times[decel_idx]
            return {
                "refined_ms": refined_time_ms,
                "confidence": min(0.95, max(0.72, wrist_confs[decel_idx])),
                "uncertainty_ms": 16,
                "sources": ["wrist_kinematic_deceleration", "local_high_fps_refinement"],
                "delta_ms": refined_time_ms - center_ms,
            }

        return None

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

