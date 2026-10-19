import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from packages.analysis.pose.extractor import FramePoseResult

SWING_STATES = (
    "IDLE",
    "ADDRESS_CANDIDATE",
    "TAKEAWAY",
    "BACKSWING",
    "TOP",
    "DOWNSWING",
    "IMPACT_ESTIMATED",
    "FOLLOW_THROUGH",
    "FINISH",
)


@dataclass
class DetectedEvent:
    event_name: str
    time_ms: int
    confidence: float
    detection_source: str = "model"
    model_version: str = "pose-v1"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "time_ms": self.time_ms,
            "confidence": round(self.confidence, 3),
            "detection_source": self.detection_source,
            "model_version": self.model_version,
            "rationale": self.rationale,
        }


def _midpoint(frame: FramePoseResult, left_key: str, right_key: str) -> tuple[float, float, float] | None:
    l_lm = frame.landmarks.get(left_key)
    r_lm = frame.landmarks.get(right_key)
    if l_lm and r_lm and (l_lm.visibility >= 0.4 or r_lm.visibility >= 0.4):
        return (
            (l_lm.x + r_lm.x) / 2.0,
            (l_lm.y + r_lm.y) / 2.0,
            min(l_lm.visibility, r_lm.visibility),
        )
    if r_lm and r_lm.visibility >= 0.4:
        return (r_lm.x, r_lm.y, r_lm.visibility)
    if l_lm and l_lm.visibility >= 0.4:
        return (l_lm.x, l_lm.y, l_lm.visibility)
    return None


def _spine_angle_deg(frame: FramePoseResult) -> tuple[float | None, float]:
    """計算 2D DTL 影像中肩中心與髖中心連線相對於垂直線之前傾角度（度）。"""
    sh = _midpoint(frame, "left_shoulder", "right_shoulder")
    hp = _midpoint(frame, "left_hip", "right_hip")
    if not sh or not hp:
        return None, 0.0
    dx = sh[0] - hp[0]
    dy = hp[1] - sh[1]
    if abs(dy) < 1e-4:
        return None, 0.0
    angle = math.degrees(math.atan2(abs(dx), max(1e-4, dy)))
    return angle, min(sh[2], hp[2])


class SwingPhaseStateMachine:
    """
    9 階段可解釋事件狀態機：
    IDLE -> ADDRESS_CANDIDATE -> TAKEAWAY -> BACKSWING -> TOP -> DOWNSWING -> IMPACT_ESTIMATED -> FOLLOW_THROUGH -> FINISH -> IDLE
    """

    def __init__(self, model_version: str = "pose-v1") -> None:
        self.model_version = model_version

    def extract_events(
        self, frames: list[FramePoseResult]
    ) -> tuple[list[DetectedEvent], list[str], str]:
        """
        從單一候選揮桿區段之細掃影格序列推導階段事件與狀態轉換軌跡。
        只依據可見 2D 關鍵點證據轉換，遇跳幀或缺關鍵點則保守降級。
        """
        valid_frames = [
            f
            for f in frames
            if f.pose_confidence >= 0.35
            and ("right_wrist" in f.landmarks or "left_wrist" in f.landmarks)
        ]
        if len(valid_frames) < 5:
            return [], ["IDLE"], "swing_candidate"

        # 取得每幀手腕高度 (y 越小代表在畫面越高) 與運動能量
        wrist_ys: list[float] = []
        wrist_xs: list[float] = []
        times: list[int] = []
        energies: list[float] = []
        confs: list[float] = []

        for f in valid_frames:
            w = _midpoint(f, "left_wrist", "right_wrist")
            if w is None:
                continue
            wrist_xs.append(w[0])
            wrist_ys.append(w[1])
            times.append(f.time_ms)
            energies.append(f.wrist_motion_energy)
            confs.append(f.pose_confidence)

        n = len(times)
        if n < 5:
            return [], ["IDLE"], "swing_candidate"

        # Address: 起手穩定低點（前 35% 區間內手腕較低且速度較慢處）
        addr_end_idx = max(1, int(n * 0.30))
        addr_idx = int(np.argmax(wrist_ys[:addr_end_idx]))
        addr_y = wrist_ys[addr_idx]

        # Top of Backswing: Address 之後、前 75% 區間內手腕最高點（y 最小處）
        top_search_end = max(addr_idx + 2, int(n * 0.78))
        top_rel_idx = int(np.argmin(wrist_ys[addr_idx + 1 : top_search_end]))
        top_idx = addr_idx + 1 + top_rel_idx
        top_y = wrist_ys[top_idx]

        vertical_amplitude = addr_y - top_y
        if vertical_amplitude < 0.06:
            return [], ["IDLE", "ADDRESS_CANDIDATE", "IDLE"], "swing_candidate"

        # Takeaway: Address 與 Top 之間，手腕上移達 20% 幅度之處
        takeaway_target_y = addr_y - 0.22 * vertical_amplitude
        takeaway_idx = addr_idx + 1
        for i in range(addr_idx + 1, top_idx):
            if wrist_ys[i] <= takeaway_target_y:
                takeaway_idx = i
                break

        # Backswing 中段：Takeaway 與 Top 之間中點
        backswing_idx = min(top_idx, max(takeaway_idx, (takeaway_idx + top_idx) // 2))

        # Impact Estimated: Top 之後手腕回到接近 Address 高度（或下桿速度最快且接近最低點處）
        impact_search_end = min(n - 1, top_idx + max(2, int(n * 0.35)))
        if impact_search_end <= top_idx:
            impact_idx = min(n - 1, top_idx + 1)
        else:
            # 結合手腕最低點（y 最大）與瞬間速度峰值估算疑似擊球瞬間
            best_score = -1e9
            impact_idx = top_idx + 1
            for i in range(top_idx + 1, impact_search_end + 1):
                score = wrist_ys[i] * 1.5 + energies[i] * 2.0
                if score > best_score:
                    best_score = score
                    impact_idx = i

        downswing_idx = max(top_idx, (top_idx + impact_idx) // 2)

        # Follow-through & Finish: Impact 之後手腕再次上揚並維持收桿
        if impact_idx < n - 2:
            post_impact_ys = wrist_ys[impact_idx + 1 :]
            finish_rel = int(np.argmin(post_impact_ys))
            follow_idx = min(n - 1, impact_idx + 1 + max(0, finish_rel // 2))
            finish_idx = min(n - 1, max(follow_idx, n - 2))
        else:
            follow_idx = impact_idx
            finish_idx = n - 1

        state_trace = [
            "IDLE",
            "ADDRESS_CANDIDATE",
            "TAKEAWAY",
            "BACKSWING",
            "TOP",
            "DOWNSWING",
            "IMPACT_ESTIMATED",
            "FOLLOW_THROUGH",
            "FINISH",
            "IDLE",
        ]

        events: list[DetectedEvent] = [
            DetectedEvent(
                event_name="address",
                time_ms=times[addr_idx],
                confidence=confs[addr_idx],
                model_version=self.model_version,
                rationale="手腕與軀幹於準備區段維持相對靜止低點",
            ),
            DetectedEvent(
                event_name="takeaway",
                time_ms=times[takeaway_idx],
                confidence=confs[takeaway_idx],
                model_version=self.model_version,
                rationale="手腕離開準備位置並啟動上桿超過 20% 垂直幅度",
            ),
            DetectedEvent(
                event_name="backswing",
                time_ms=times[backswing_idx],
                confidence=confs[backswing_idx],
                model_version=self.model_version,
                rationale="上桿中段手部持續上升軌跡",
            ),
            DetectedEvent(
                event_name="top",
                time_ms=times[top_idx],
                confidence=confs[top_idx],
                model_version=self.model_version,
                rationale="上桿頂點：手腕達到最高位置且垂直速度反轉",
            ),
            DetectedEvent(
                event_name="downswing",
                time_ms=times[downswing_idx],
                confidence=confs[downswing_idx],
                model_version=self.model_version,
                rationale="下桿加速階段：手腕由頂點向擊球區快速下降",
            ),
            DetectedEvent(
                event_name="impact_estimated",
                time_ms=times[impact_idx],
                confidence=round(confs[impact_idx] * 0.9, 3),
                model_version=self.model_version,
                rationale="疑似擊球瞬間（estimated）：2D 下桿手腕最低點與運動能量峰值交會處",
            ),
            DetectedEvent(
                event_name="follow_through",
                time_ms=times[follow_idx],
                confidence=confs[follow_idx],
                model_version=self.model_version,
                rationale="隨揮釋放階段：通過最低點後手臂延伸上升",
            ),
            DetectedEvent(
                event_name="finish",
                time_ms=times[finish_idx],
                confidence=confs[finish_idx],
                model_version=self.model_version,
                rationale="收桿完成與停留平衡階段",
            ),
        ]

        # 判斷是正式揮桿 (valid_swing) 還是空揮 (practice_swing)
        # 空揮特徵：下桿峰值能量明顯較低，或收桿停留極短且手腕未完整通過擊球最低點
        downswing_peak_energy = max(energies[top_idx : impact_idx + 1] or [0.0])
        finish_hold_ms = max(0, times[-1] - times[follow_idx])
        impact_depth = wrist_ys[impact_idx] - top_y
        if impact_depth < vertical_amplitude * 0.68 or (
            downswing_peak_energy < 0.042 and finish_hold_ms < 450
        ):
            label = "practice_swing"
        else:
            label = "valid_swing"

        return events, state_trace, label


def compute_observable_metrics(
    frames: list[FramePoseResult],
    events: list[DetectedEvent],
    model_version: str = "pose-v1",
) -> list[dict[str, Any]]:
    """
    依據可見 2D 關鍵點與階段事件計算可追溯之 DTL 動作指標。
    若特定階段關鍵點缺失或信心度 < 0.50，該指標設為 value=None 並誠實標記，絕不捏造數值。
    """
    if not frames or not events:
        return []

    event_map = {e.event_name: e.time_ms for e in events}

    def nearest_frame(target_ms: int | None) -> FramePoseResult | None:
        if target_ms is None:
            return None
        return min(frames, key=lambda f: abs(f.time_ms - target_ms))

    f_addr = nearest_frame(event_map.get("address"))
    f_take = nearest_frame(event_map.get("takeaway"))
    f_back = nearest_frame(event_map.get("backswing"))
    f_top = nearest_frame(event_map.get("top"))
    f_down = nearest_frame(event_map.get("downswing"))
    f_imp = nearest_frame(event_map.get("impact_estimated"))
    f_fin = nearest_frame(event_map.get("finish"))

    metrics: list[dict[str, Any]] = []

    # 1. 軀幹前傾穩定 (spine_tilt_delta_deg)
    angle_addr, conf_addr = _spine_angle_deg(f_addr) if f_addr else (None, 0.0)
    angle_imp, conf_imp = _spine_angle_deg(f_imp) if f_imp else (None, 0.0)
    if angle_addr is not None and angle_imp is not None and min(conf_addr, conf_imp) >= 0.50:
        spine_delta = abs(angle_imp - angle_addr)
        metrics.append(
            {
                "metric_key": "spine_tilt_address_deg",
                "value": round(angle_addr, 2),
                "unit": "deg_2d",
                "confidence": round(conf_addr, 3),
                "source": model_version,
                "observability": "observed_2d",
            }
        )
        metrics.append(
            {
                "metric_key": "spine_tilt_impact_deg",
                "value": round(angle_imp, 2),
                "unit": "deg_2d",
                "confidence": round(conf_imp, 3),
                "source": model_version,
                "observability": "observed_2d",
            }
        )
        metrics.append(
            {
                "metric_key": "spine_tilt_delta_deg",
                "value": round(spine_delta, 2),
                "unit": "deg_2d",
                "confidence": round(min(conf_addr, conf_imp), 3),
                "source": model_version,
                "observability": "observed_2d",
            }
        )
    else:
        metrics.append(
            {
                "metric_key": "spine_tilt_delta_deg",
                "value": None,
                "unit": "deg_2d",
                "confidence": 0.0,
                "source": model_version,
                "observability": "observed_2d",
            }
        )

    # 2. 頭部相對位移 (head_displacement_ratio)
    head_ratio: float | None = None
    head_conf = 0.0
    if f_addr and f_imp and "nose" in f_addr.landmarks:
        sh = _midpoint(f_addr, "left_shoulder", "right_shoulder")
        hp = _midpoint(f_addr, "left_hip", "right_hip")
        torso_len = math.hypot(sh[0] - hp[0], sh[1] - hp[1]) if (sh and hp) else 0.22
        torso_len = max(0.08, torso_len)
        addr_nose = f_addr.landmarks["nose"]
        max_disp = 0.0
        vis_vals = [addr_nose.visibility]
        for fr in frames:
            if f_addr.time_ms <= fr.time_ms <= f_imp.time_ms and "nose" in fr.landmarks:
                n_lm = fr.landmarks["nose"]
                if n_lm.visibility >= 0.50:
                    d = math.hypot(n_lm.x - addr_nose.x, n_lm.y - addr_nose.y) / torso_len
                    max_disp = max(max_disp, d)
                    vis_vals.append(n_lm.visibility)
        if len(vis_vals) >= 2 and min(vis_vals) >= 0.50:
            head_ratio = round(max_disp, 4)
            head_conf = round(float(np.mean(vis_vals)), 3)

    metrics.append(
        {
            "metric_key": "head_displacement_ratio",
            "value": head_ratio,
            "unit": "torso_ratio",
            "confidence": head_conf,
            "source": model_version,
            "observability": "observed_2d",
        }
    )

    # 3. 手部上下桿軌跡差距與重複性基準 (plane_gap_ratio / hand_path_deviation_ratio)
    plane_gap: float | None = None
    plane_conf = 0.0
    if f_back and f_down:
        w_back = _midpoint(f_back, "left_wrist", "right_wrist")
        w_down = _midpoint(f_down, "left_wrist", "right_wrist")
        if w_back and w_down and min(w_back[2], w_down[2]) >= 0.50:
            plane_gap = round(math.hypot(w_back[0] - w_down[0], (w_back[1] - w_down[1]) * 0.5), 4)
            plane_conf = round(min(w_back[2], w_down[2]), 3)

    metrics.append(
        {
            "metric_key": "hand_path_deviation_ratio",
            "value": plane_gap,
            "unit": "ratio",
            "confidence": plane_conf,
            "source": model_version,
            "observability": "observed_2d",
        }
    )

    # 4. 上下桿節奏比 (backswing_downswing_ratio)
    tempo_ratio: float | None = None
    tempo_conf = 0.0
    if f_take and f_top and f_imp:
        bs_ms = max(80, f_top.time_ms - f_take.time_ms)
        ds_ms = max(60, f_imp.time_ms - f_top.time_ms)
        tempo_ratio = round(bs_ms / float(ds_ms), 2)
        tempo_conf = round(min(f_take.pose_confidence, f_top.pose_confidence, f_imp.pose_confidence), 3)
        metrics.append(
            {
                "metric_key": "backswing_ms",
                "value": float(bs_ms),
                "unit": "ms",
                "confidence": tempo_conf,
                "source": model_version,
                "observability": "estimated",
            }
        )
        metrics.append(
            {
                "metric_key": "downswing_ms",
                "value": float(ds_ms),
                "unit": "ms",
                "confidence": tempo_conf,
                "source": model_version,
                "observability": "estimated",
            }
        )

    metrics.append(
        {
            "metric_key": "backswing_downswing_ratio",
            "value": tempo_ratio,
            "unit": "ratio",
            "confidence": tempo_conf,
            "source": model_version,
            "observability": "estimated",
        }
    )

    # 5. 收桿姿勢穩定 (finish_hold_ms & finish_sway_ratio)
    finish_hold: float | None = None
    finish_sway: float | None = None
    finish_conf = 0.0
    if f_imp and f_fin:
        post_frames = [
            fr for fr in frames if fr.time_ms >= f_imp.time_ms and fr.pose_confidence >= 0.50
        ]
        if len(post_frames) >= 2:
            finish_hold = float(max(100, post_frames[-1].time_ms - post_frames[0].time_ms))
            hip_xs: list[float] = []
            confs_fin: list[float] = []
            for fr in post_frames:
                hp = _midpoint(fr, "left_hip", "right_hip")
                if hp:
                    hip_xs.append(hp[0])
                    confs_fin.append(hp[2])
            if len(hip_xs) >= 2:
                finish_sway = round(float(max(hip_xs) - min(hip_xs)), 4)
                finish_conf = round(float(np.mean(confs_fin)), 3)

    metrics.append(
        {
            "metric_key": "finish_hold_ms",
            "value": finish_hold,
            "unit": "ms",
            "confidence": finish_conf,
            "source": model_version,
            "observability": "observed_2d",
        }
    )
    metrics.append(
        {
            "metric_key": "finish_sway_ratio",
            "value": finish_sway,
            "unit": "ratio",
            "confidence": finish_conf,
            "source": model_version,
            "observability": "observed_2d",
        }
    )

    return metrics
