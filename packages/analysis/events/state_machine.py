import math
from dataclasses import dataclass, field
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
    model_version: str = "pose-v2"
    rationale: str = ""
    uncertainty_ms: int = 33
    detection_sources: list[str] = field(default_factory=list)
    sampling_resolution_ms: int = 33
    event_timing_error_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "time_ms": self.time_ms,
            "confidence": round(self.confidence, 3),
            "detection_source": self.detection_source,
            "model_version": self.model_version,
            "rationale": self.rationale,
            "uncertainty_ms": self.uncertainty_ms,
            "detection_sources": self.detection_sources,
            "sampling_resolution_ms": self.sampling_resolution_ms,
            "event_timing_error_ms": self.event_timing_error_ms,
        }


@dataclass
class SwingHypothesis:
    hypothesis_id: str
    top_idx: int
    downswing_idx: int
    impact_idx: int
    addr_idx: int
    takeaway_idx: int
    follow_idx: int
    finish_idx: int
    top_ms: int
    impact_ms: int
    addr_ms: int
    downswing_ms: int
    backswing_ms: int
    stroke_amplitude: float
    downswing_speed_peak: float
    decel_at_impact: float
    follow_amplitude: float
    finish_hold_ms: int
    readdress_calm_ratio: float
    audio_transient_ms: int | None
    audio_diff_ms: float | None
    audio_score: float
    ball_strike_applied: bool
    kinematic_score: float
    follow_through_score: float
    total_score: float
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    is_ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "top_ms": self.top_ms,
            "impact_ms": self.impact_ms,
            "addr_ms": self.addr_ms,
            "downswing_ms": self.downswing_ms,
            "backswing_ms": self.backswing_ms,
            "stroke_amplitude": round(self.stroke_amplitude, 4),
            "downswing_speed_peak": round(self.downswing_speed_peak, 6),
            "decel_at_impact": round(self.decel_at_impact, 6),
            "follow_amplitude": round(self.follow_amplitude, 4),
            "finish_hold_ms": self.finish_hold_ms,
            "readdress_calm_ratio": round(self.readdress_calm_ratio, 4),
            "audio_transient_ms": self.audio_transient_ms,
            "audio_diff_ms": round(self.audio_diff_ms, 1) if self.audio_diff_ms is not None else None,
            "total_score": round(self.total_score, 2),
            "supporting_evidence": self.supporting_evidence,
            "opposing_evidence": self.opposing_evidence,
            "is_ambiguous": self.is_ambiguous,
        }


def _get_lm_xyv(lm: Any) -> tuple[float, float, float] | None:
    if lm is None:
        return None
    if isinstance(lm, dict):
        return (float(lm["x"]), float(lm["y"]), float(lm.get("visibility", 0.0)))
    return (float(lm.x), float(lm.y), float(getattr(lm, "visibility", 0.0)))


def _midpoint(
    frame: FramePoseResult, left_key: str, right_key: str
) -> tuple[float, float, float] | None:
    l_xyv = _get_lm_xyv(frame.landmarks.get(left_key))
    r_xyv = _get_lm_xyv(frame.landmarks.get(right_key))
    if l_xyv and r_xyv and (l_xyv[2] >= 0.35 or r_xyv[2] >= 0.35):
        return (
            (l_xyv[0] + r_xyv[0]) / 2.0,
            (l_xyv[1] + r_xyv[1]) / 2.0,
            min(l_xyv[2], r_xyv[2]),
        )
    if r_xyv and r_xyv[2] >= 0.35:
        return r_xyv
    if l_xyv and l_xyv[2] >= 0.35:
        return l_xyv
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
    高爾夫多訊號事件狀態機 (Multi-Signal Golf Swing Phase State Machine, pose-v2)：
    整合：
    1. 手腕 2D 軌跡、垂直/水平速度向量、運動能量與加速度零交越
    2. 肩部與骨盆旋轉時序
    3. 試擺與 Waggle / Practice Lift 抑制機制（鎖定正式起桿前最後靜態基準）
    4. 多訊號一致性評估與合理不確定區間 (uncertainty_ms)
    5. 自動二次精修 (Two-Pass Refinement)
    """

    def __init__(self, model_version: str = "pose-v2") -> None:
        self.model_version = model_version
        self.last_hypotheses: list[SwingHypothesis] = []
        self.last_selection_rationale: str = ""
        self.last_is_ambiguous: bool = False

    @staticmethod
    def _select_best_top_realign_candidate(
        win_cands: list[int],
        times: list[int],
        wrist_ys: list[float],
        speed: np.ndarray,
        v_y: np.ndarray,
        impact_idx: int,
        n: int,
    ) -> tuple[int | None, float, bool, bool]:
        """
        在候選集合中評估並選出最佳 Top 重對齊候選。
        實作確定性排序與平手打破規則 (Tie-Breaking)，保證輸入順序或排列不影響裁決結果 (Permutation Invariance)。
        回傳: (best_cand, best_cand_score, best_cand_has_zc, best_cand_has_accel)
        """
        if not win_cands:
            return None, -1e9, False, False

        sub_ys = [wrist_ys[i] for i in win_cands]
        min_sub_y = min(sub_ys)
        max_sub_y = max(sub_ys)
        y_span = max(1e-3, max_sub_y - min_sub_y)

        candidates_evaluated = []
        for c in win_cands:
            h_s = (max_sub_y - wrist_ys[c]) / y_span
            cand_zc = bool(c < n - 1 and v_y[c] <= 0 and v_y[c + 1] > 0)
            zc_bonus = 2.0 if cand_zc else 0.0
            p_s = 1.0 if (0 < c < n - 1 and speed[c] <= speed[c - 1] and speed[c] <= speed[c + 1]) else 0.0
            post_s = speed[c : min(impact_idx + 1, c + 5)]
            acc = float(np.max(post_s)) - speed[c] if len(post_s) > 0 else 0.0

            score = h_s * 3.0 + zc_bonus * 2.5 + p_s * 1.5 + acc * 40.0
            has_accel = bool(acc >= 0.003)

            # 確定性評分元組：(score, -wrist_ys[c], times[c])
            # 當 score 相等時，優先選擇手腕最高者 (-wrist_y 越大)，再選擇靠近 Impact 者 (times 越大)
            candidates_evaluated.append({
                "cand": c,
                "score": score,
                "cand_zc": cand_zc,
                "has_accel": has_accel,
                "tie_key": (round(score, 6), -wrist_ys[c], times[c]),
            })

        # 排序選出最佳候選 (排序鍵不依賴原始列表順序)
        best = max(candidates_evaluated, key=lambda x: x["tie_key"])
        return best["cand"], best["score"], best["cand_zc"], best["has_accel"]

    def _validate_and_realign_swing_timing(
        self,
        times: list[int],
        wrist_ys: list[float],
        wrist_xs: list[float],
        speed: np.ndarray,
        v_y: np.ndarray,
        top_idx: int,
        impact_idx: int,
        addr_idx: int,
        takeaway_idx: int,
        audio_transients_ms: list[int] | None = None,
        ball_strike_ms: int | None = None,
        top_sources: list[str] | None = None,
        impact_sources: list[str] | None = None,
    ) -> tuple[int, int, int, int, list[str], list[str], bool]:
        """
        高爾夫物理時序合理性檢核與自動重新對齊 (Swing Timing Kinematic Validation & Realignment):
        高爾夫全揮桿物理下桿時間 (Downswing: Top -> Impact) 生理極限嚴格落在 180ms ~ 650ms 之間。
        若偵測到下桿時間 > 650ms (通常為擊球前試擺 Waggle 誤導 Top) 或 < 180ms (異常微動):
        1. 依據權威擊球證據 (音訊瞬態、真球觀測或下桿速度峰值急煞) 在 [T_impact - 650ms, T_impact - 180ms]
           物理視窗內，以速度零交越 (v_y <= 0 -> v_y > 0)、頂點停頓 (Top Pause) 與強烈下桿加速度重新鎖定真實擊球 Top。
        2. 依據真實 Top 往前追溯修正 Settled Address 與 Takeaway，排除前面試擺的干擾。
        3. 反向若 Top 訊號強烈而 Impact 落後，在 [T_top + 180ms, T_top + 650ms] 內重新鎖定真實 Impact。
        4. 若經重調後仍不符合物理常態，標記 timing_anomaly_detected 並降級信心度，絕不硬編造或截斷時間碼。
        """
        t_sources = list(top_sources or [])
        i_sources = list(impact_sources or [])
        n = len(times)
        if n < 5 or top_idx >= n or impact_idx >= n:
            return top_idx, impact_idx, addr_idx, takeaway_idx, t_sources, i_sources, False

        ds_ms = times[impact_idx] - times[top_idx]
        has_anomaly = False

        # 下桿時間大於 650ms：最常見的試擺 (Waggle) 假頂點
        if ds_ms > 650:
            has_anomaly = True
            # 判斷 Impact 是否具有高度可信性
            has_audio = False
            if audio_transients_ms:
                closest_a = min(audio_transients_ms, key=lambda a: abs(a - times[impact_idx]))
                if abs(closest_a - times[impact_idx]) <= 90:
                    has_audio = True

            has_ball = bool(ball_strike_ms is not None and abs(ball_strike_ms - times[impact_idx]) <= 180)

            cur_s = speed[impact_idx]
            prev_s = speed[impact_idx - 1] if impact_idx > 0 else cur_s
            has_decel = bool((prev_s - cur_s) > 0.0005)

            imp_is_authoritative = has_audio or has_ball or has_decel or (cur_s >= np.percentile(speed, 60))

            if imp_is_authoritative:
                # 在 [times[impact_idx] - 650ms, times[impact_idx] - 180ms] 窗口內搜尋真實 Top
                win_cands = [
                    i for i in range(impact_idx)
                    if (times[impact_idx] - 650) <= times[i] <= (times[impact_idx] - 180)
                ]
                if win_cands:
                    best_cand, best_cand_score, best_cand_has_zc, best_cand_has_accel = (
                        self._select_best_top_realign_candidate(
                            win_cands=win_cands,
                            times=times,
                            wrist_ys=wrist_ys,
                            speed=speed,
                            v_y=v_y,
                            impact_idx=impact_idx,
                            n=n,
                        )
                    )
                    sub_ys = [wrist_ys[i] for i in win_cands]
                    min_sub_y = min(sub_ys)
                    max_sub_y = max(sub_ys)
                    y_span = max(1e-3, max_sub_y - min_sub_y)

                    stroke_height = wrist_ys[impact_idx] - wrist_ys[best_cand]
                    full_amp = max(wrist_ys) - min(wrist_ys)
                    cand_h_ratio = (max_sub_y - wrist_ys[best_cand]) / y_span
                    kinematic_confirmed = best_cand_has_zc or (cand_h_ratio >= 0.85 and best_cand_has_accel)
                    if (stroke_height >= 0.08 or stroke_height >= 0.35 * full_amp) and (kinematic_confirmed or has_audio or has_ball):
                        top_idx = best_cand
                        if "pre_impact_kinematic_realigned" not in t_sources:
                            t_sources.append("pre_impact_kinematic_realigned")

                        addr_cands = [
                            i for i in range(top_idx)
                            if (times[top_idx] - 1500) <= times[i] <= (times[top_idx] - 250)
                        ]
                        if addr_cands:
                            new_addr = max(addr_cands, key=lambda i: wrist_ys[i] - speed[i] * 50.0)
                            addr_idx = new_addr
                        else:
                            addr_idx = max(0, top_idx - max(2, int(0.20 * n)))

                        amp = wrist_ys[addr_idx] - wrist_ys[top_idx]
                        takeaway_target_y = wrist_ys[addr_idx] - 0.22 * max(0.02, amp)
                        new_take = addr_idx + 1
                        for k in range(addr_idx + 1, top_idx):
                            if wrist_ys[k] <= takeaway_target_y:
                                new_take = k
                                break
                        takeaway_idx = min(top_idx, new_take)
                        has_anomaly = False
            else:
                post_cands = [
                    i for i in range(top_idx + 1, n)
                    if (times[top_idx] + 180) <= times[i] <= (times[top_idx] + 650)
                ]
                if post_cands:
                    best_post = max(post_cands, key=lambda i: wrist_ys[i] * 2.0 + speed[i] * 30.0)
                    impact_idx = best_post
                    if "post_top_kinematic_realigned" not in i_sources:
                        i_sources.append("post_top_kinematic_realigned")
                    has_anomaly = False

        elif ds_ms < 180:
            has_anomaly = True
            if audio_transients_ms and any(abs(a - times[impact_idx]) <= 80 for a in audio_transients_ms):
                earlier_cands = [
                    i for i in range(impact_idx)
                    if (times[impact_idx] - 650) <= times[i] <= (times[impact_idx] - 180)
                ]
                if earlier_cands:
                    top_idx = min(earlier_cands, key=lambda i: wrist_ys[i])
                    if "pre_impact_kinematic_realigned" not in t_sources:
                        t_sources.append("pre_impact_kinematic_realigned")
                    has_anomaly = False
            else:
                later_cands = [
                    i for i in range(top_idx + 1, n)
                    if (times[top_idx] + 180) <= times[i] <= (times[top_idx] + 650)
                ]
                if later_cands:
                    impact_idx = max(later_cands, key=lambda i: wrist_ys[i])
                    if "post_top_kinematic_realigned" not in i_sources:
                        i_sources.append("post_top_kinematic_realigned")
                    has_anomaly = False

        final_ds = times[impact_idx] - times[top_idx]
        if final_ds < 180 or final_ds > 650:
            has_anomaly = True
            if "timing_anomaly_detected" not in t_sources:
                t_sources.append("timing_anomaly_detected")
            if "timing_anomaly_detected" not in i_sources:
                i_sources.append("timing_anomaly_detected")

        return top_idx, impact_idx, addr_idx, takeaway_idx, t_sources, i_sources, has_anomaly

    def _generate_swing_hypotheses(
        self,
        times: list[int],
        wrist_xs: list[float],
        wrist_ys: list[float],
        speed: np.ndarray,
        v_y: np.ndarray,
        confs: list[float],
        energies: list[float],
        audio_transients_ms: list[int] | None,
        ball_strike_ms: int | None,
        mean_dt: float,
        full_amplitude: float,
        min_wrist_y: float,
        max_wrist_y: float,
    ) -> list[SwingHypothesis]:
        n = len(times)
        if n < 5:
            return []

        y_40 = float(np.percentile(wrist_ys, 40))
        spd_40 = float(np.percentile(speed, 40)) if len(speed) > 0 else 0.0005
        max_speed = float(np.max(speed)) if len(speed) > 0 else 1.0

        # 1. 搜尋潛在 Impact 候選點 (Kinematic / Audio / Ball Launch)
        # 1. 搜尋潛在 Impact 候選點 (Kinematic / Audio / Ball Launch / Lowest Wrist Point)
        # 幾何硬性約束：高爾夫球位在地面，擊球瞬間手腕必然位於下半部擊球區 (>= 35% 全振幅)
        # 徹底杜絕將頭頂/胸前高速隨揮誤判為擊球瞬間
        raw_imp_cands: list[int] = []
        for i in range(1, n - 2):
            stroke_depth = wrist_ys[i] - min_wrist_y
            if stroke_depth < 0.35 * full_amplitude:
                continue

            is_speed_peak = bool(speed[i] >= speed[i - 1] and speed[i] >= speed[i + 1] and speed[i] >= spd_40)
            is_decel = bool((speed[i - 1] - speed[i]) >= 0.00015 and speed[i - 1] >= spd_40)
            is_lowest = bool(wrist_ys[i] >= wrist_ys[i - 1] and wrist_ys[i] >= wrist_ys[i + 1])
            has_near_audio = bool(
                audio_transients_ms
                and any(abs(a - times[i]) <= 65 for a in audio_transients_ms)
            )
            has_near_ball = bool(ball_strike_ms is not None and abs(ball_strike_ms - times[i]) <= 90)

            if is_speed_peak or is_decel or is_lowest or has_near_audio or has_near_ball:
                raw_imp_cands.append(i)

        if not raw_imp_cands:
            raw_imp_cands = [int(np.argmax(speed))]

        # 標準 Score-ranked NMS 抑制機制 (修正制動減速方向與幾何深度權重)
        scored_cands: list[tuple[float, int]] = []
        for idx in raw_imp_cands:
            # 撞擊衝擊制動量：前一影格速度減去當前影格速度 (真實擊球手部受阻制動)
            cur_brake = (speed[idx - 1] - speed[idx]) if idx > 0 else 0.0
            aud_dist = min([abs(a - times[idx]) for a in (audio_transients_ms or [])], default=999)
            aud_bonus = 2.0 if aud_dist <= 60 else (1.0 if aud_dist <= 90 else 0.0)
            ball_bonus = 2.5 if (ball_strike_ms is not None and abs(ball_strike_ms - times[idx]) <= 80) else 0.0
            depth_ratio = (wrist_ys[idx] - min_wrist_y) / max(1e-4, full_amplitude)
            is_lowest_pt = bool(wrist_ys[idx] >= wrist_ys[idx - 1] and wrist_ys[idx] >= wrist_ys[idx + 1])
            lowest_bonus = 2.5 if is_lowest_pt else 0.0

            # 物理衝擊強度：垂直深度權重 + 擊球衝擊減速 + 音訊/球體一致性 + 速度峰值能量 + 最低點加分
            s_val = (
                depth_ratio * 4.0
                + max(0.0, cur_brake / max(1e-4, max_speed)) * 3.5
                + (speed[idx] / max(1e-4, max_speed)) * 2.0
                + aud_bonus
                + ball_bonus
                + lowest_bonus
            )
            scored_cands.append((s_val, idx))

        scored_cands.sort(key=lambda x: x[0], reverse=True)
        nms_imps: list[int] = []
        suppressed: set[int] = set()
        for _, idx in scored_cands:
            if idx in suppressed:
                continue
            nms_imps.append(idx)
            for _, other_idx in scored_cands:
                if abs(times[other_idx] - times[idx]) <= 200:
                    suppressed.add(other_idx)

        nms_imps.sort()

        hypotheses: list[SwingHypothesis] = []
        cand_counter = 1


        for imp_idx in nms_imps:
            imp_t = times[imp_idx]
            imp_y = wrist_ys[imp_idx]

            # 2. 為該 Impact 向前搜尋 Top (涵蓋生理下桿時間 150~950ms)
            top_window = [
                i for i in range(imp_idx)
                if (imp_t - 950) <= times[i] <= (imp_t - 150)
            ]
            if not top_window:
                top_window = [
                    i for i in range(imp_idx)
                    if (imp_t - 1300) <= times[i] <= (imp_t - 130)
                ]
            if not top_window:
                continue

            top_cands = []
            for k in top_window:
                stroke_h = imp_y - wrist_ys[k]
                if stroke_h < 0.05 and stroke_h < 0.25 * full_amplitude:
                    continue

                has_zc = bool(k < n - 1 and v_y[k] <= 0 and v_y[k + 1] > 0)
                has_pause = bool(0 < k < n - 1 and speed[k] <= speed[k - 1] and speed[k] <= speed[k + 1])
                sub_ys = [wrist_ys[j] for j in top_window]
                min_w_y = min(sub_ys)
                max_w_y = max(sub_ys)
                h_score = (max_w_y - wrist_ys[k]) / max(1e-3, max_w_y - min_w_y)
                post_s = speed[k : min(imp_idx + 1, k + 5)]
                acc = float(np.max(post_s)) - speed[k] if len(post_s) > 0 else 0.0

                cand_score = h_score * 3.5 + (2.0 if has_zc else 0.0) + (1.5 if has_pause else 0.0) + acc * 35.0
                top_cands.append((cand_score, k))

            if not top_cands:
                continue

            top_cands.sort(key=lambda x: (round(x[0], 5), -wrist_ys[x[1]], times[x[1]]), reverse=True)
            best_top_idx = top_cands[0][1]
            top_t = times[best_top_idx]
            top_y = wrist_ys[best_top_idx]
            stroke_amp = imp_y - top_y
            ds_ms = imp_t - top_t

            # 3. 向前搜尋 Settled Address & Takeaway
            addr_window = [
                i for i in range(best_top_idx)
                if (top_t - 2200) <= times[i] <= (top_t - 220)
            ]
            if addr_window:
                best_addr_idx = max(
                    addr_window,
                    key=lambda i: (wrist_ys[i] * 2.0 - speed[i] * 40.0)
                )
            else:
                best_addr_idx = max(0, best_top_idx - max(2, int(0.18 * n)))

            addr_t = times[best_addr_idx]
            addr_y = wrist_ys[best_addr_idx]
            bs_ms = top_t - addr_t

            takeaway_target = addr_y - 0.22 * max(0.04, addr_y - top_y)
            takeaway_idx = best_addr_idx + 1
            for k in range(best_addr_idx + 1, best_top_idx):
                if wrist_ys[k] <= takeaway_target:
                    takeaway_idx = k
                    break
            takeaway_idx = min(best_top_idx, takeaway_idx)
            downswing_idx = max(best_top_idx, (best_top_idx + imp_idx) // 2)

            # 4. 向後搜尋 Follow-through & Finish (切斷跨動作污染，計算真實連續收桿穩定度)
            # (A) 隨揮頂點搜尋：隨揮上升在擊球後 120ms ~ 700ms 內完成，搜尋此區間內手腕最高點 (y 最小值)
            # 注意：隨揮頂點搜尋絕不受後續放桿干擾，確保完整捕捉真實擊球之隨揮延伸
            post_window = [
                i for i in range(imp_idx + 1, n)
                if times[i] <= imp_t + 700
            ]
            if post_window:
                follow_idx = min(post_window, key=lambda i: wrist_ys[i])
                follow_y = wrist_ys[follow_idx]
                follow_amp = imp_y - follow_y

                # (B) 動作鏈邊界：若存在下一個擊球候選，找出兩次動作間的放桿/重新站定低點
                next_imp_list = [i for i in nms_imps if i > imp_idx]
                motion_end_idx = n
                if next_imp_list:
                    next_imp = next_imp_list[0]
                    # 只有當 next_imp 發生在隨揮頂點之後時，才在兩者之間分割
                    if next_imp > follow_idx:
                        between_window = list(range(follow_idx, next_imp))
                        if between_window:
                            split_idx = max(between_window, key=lambda i: (wrist_ys[i] * 2.0 - speed[i] * 20.0))
                            motion_end_idx = split_idx

                # (C) 真實連續姿態穩定性計算 finish_hold_ms (嚴禁使用 times[-1]！)
                # 從隨揮頂點逐幀檢查姿態是否維持在收桿平衡狀態
                hold_end_idx = follow_idx
                for k in range(follow_idx + 1, min(motion_end_idx, n)):
                    # 姿態維持條件：手腕保持在收桿高度 (<= follow_y + 0.10) 且 運動速度維持平靜
                    if wrist_ys[k] <= follow_y + 0.10 and speed[k] <= max(0.0025, 0.25 * max_speed):
                        hold_end_idx = k
                    else:
                        break
                finish_hold_ms = times[hold_end_idx] - times[follow_idx]
                finish_idx = hold_end_idx
            else:
                follow_idx = imp_idx
                finish_idx = imp_idx
                follow_amp = 0.0
                finish_hold_ms = 0

            # 5. 計算各維度物理特徵與客觀證據
            supporting: list[str] = []
            opposing: list[str] = []

            # (A) 運動學完整度
            ds_spd_peak = float(np.max(speed[best_top_idx : imp_idx + 1])) if imp_idx > best_top_idx else float(speed[imp_idx])
            decel = max(0.0, float(speed[imp_idx - 1] - speed[imp_idx])) if imp_idx > 0 else 0.0

            k_score = 0.0
            # 生理下桿黃金區間：高爾夫真實下桿通常在 200~420ms (爆發加速)
            if 200 <= ds_ms <= 420:
                k_score += 6.0
                supporting.append(f"golden_downswing_tempo ({ds_ms}ms)")
            elif (160 <= ds_ms < 200) or (420 < ds_ms <= 500):
                k_score += 3.0
                supporting.append(f"acceptable_downswing ({ds_ms}ms)")
            elif 500 < ds_ms <= 700:
                k_score -= 2.0
                opposing.append(f"slow_downswing_duration ({ds_ms}ms)")
            else:
                k_score -= 5.0
                opposing.append(f"extreme_downswing_duration ({ds_ms}ms)")

            if stroke_amp >= 0.09:
                k_score += 3.0
                supporting.append("adequate_stroke_amplitude")
            else:
                k_score -= 1.5
                opposing.append("shallow_stroke_amplitude")

            # 下桿動能峰值佔全視窗最大速度比例 (真擊球必然全力加速，放桿假動作速度極低)
            spd_ratio = ds_spd_peak / max(1e-4, max_speed)
            if spd_ratio >= 0.70:
                k_score += 5.0
                supporting.append(f"explosive_impact_speed (ratio={spd_ratio:.2f})")
            elif spd_ratio >= 0.45:
                k_score += 2.0
                supporting.append(f"moderate_impact_speed (ratio={spd_ratio:.2f})")
            else:
                k_score -= 3.0
                opposing.append(f"weak_downswing_speed (ratio={spd_ratio:.2f})")

            if decel >= 0.0003:
                k_score += 2.0
                supporting.append(f"impact_deceleration_brake ({decel:.4f})")

            # (B) 隨揮與收桿延伸 (核心區分試擺與正式擊球)
            f_score = 0.0
            if follow_amp >= 0.08:
                f_score += 4.0
                supporting.append(f"full_follow_through_extension (amp={follow_amp:.3f})")
            elif follow_amp >= 0.03:
                f_score += 1.5
                supporting.append(f"moderate_follow_through (amp={follow_amp:.3f})")
            else:
                f_score -= 3.0
                opposing.append(f"weak_follow_through_waggle_like (amp={follow_amp:.3f})")

            if finish_hold_ms >= 250:
                f_score += 2.0
                supporting.append(f"finish_balance_hold ({finish_hold_ms}ms)")
            elif finish_hold_ms < 60:
                f_score -= 1.0
                opposing.append("abrupt_cutoff_no_finish_hold")

            # (C) 試擺後重新站定沉靜度
            r_score = 0.0
            addr_sub_spd = speed[max(0, best_addr_idx - 2) : min(best_top_idx, best_addr_idx + 3)]
            mean_addr_spd = float(np.mean(addr_sub_spd)) if len(addr_sub_spd) > 0 else 0.001
            calm_ratio = ds_spd_peak / max(1e-4, mean_addr_spd)
            if calm_ratio >= 2.0:
                r_score += 2.0
                supporting.append("settled_readdress_before_takeaway")

            # (D) 音訊瞬態時間與姿態一致性
            aud_score = 0.0
            closest_aud_ms = None
            min_aud_diff = None
            if audio_transients_ms:
                for a in audio_transients_ms:
                    diff = abs(a - imp_t)
                    if min_aud_diff is None or diff < min_aud_diff:
                        min_aud_diff = diff
                        closest_aud_ms = a

                if min_aud_diff is not None:
                    if min_aud_diff <= 60 and speed[imp_idx] >= 0.35 * max_speed:
                        aud_score += 4.5
                        supporting.append(f"audio_aligned_with_strike (diff={min_aud_diff}ms)")
                    elif min_aud_diff <= 90 and speed[imp_idx] >= 0.30 * max_speed:
                        aud_score += 2.0
                        supporting.append(f"audio_near_strike (diff={min_aud_diff}ms)")
                    elif min_aud_diff > 120:
                        opposing.append(f"isolated_background_audio (diff={min_aud_diff}ms)")
            else:
                opposing.append("no_audio_evidence_available")

            # (E) 真球位移觀測
            ball_applied = False
            b_score = 0.0
            if ball_strike_ms is not None and abs(ball_strike_ms - imp_t) <= 75:
                ball_applied = True
                b_score += 5.0
                supporting.append(f"ball_flight_observed_launch (diff={abs(ball_strike_ms - imp_t)}ms)")

            total = k_score + f_score + r_score + aud_score + b_score

            hypotheses.append(
                SwingHypothesis(
                    hypothesis_id=f"cand-{cand_counter}",
                    addr_idx=best_addr_idx,
                    takeaway_idx=takeaway_idx,
                    top_idx=best_top_idx,
                    downswing_idx=downswing_idx,
                    impact_idx=imp_idx,
                    follow_idx=follow_idx,
                    finish_idx=finish_idx,
                    top_ms=top_t,
                    impact_ms=imp_t,
                    addr_ms=addr_t,
                    downswing_ms=ds_ms,
                    backswing_ms=bs_ms,
                    stroke_amplitude=stroke_amp,
                    downswing_speed_peak=ds_spd_peak,
                    decel_at_impact=decel,
                    follow_amplitude=follow_amp,
                    finish_hold_ms=finish_hold_ms,
                    readdress_calm_ratio=calm_ratio,
                    audio_transient_ms=closest_aud_ms,
                    audio_diff_ms=min_aud_diff,
                    audio_score=aud_score,
                    ball_strike_applied=ball_applied,
                    kinematic_score=k_score,
                    follow_through_score=f_score,
                    total_score=total,
                    supporting_evidence=supporting,
                    opposing_evidence=opposing,
                    is_ambiguous=False,
                )
            )
            cand_counter += 1

        hypotheses.sort(
            key=lambda h: (
                round(h.total_score, 4),
                round(h.downswing_speed_peak, 5),
                round(h.follow_amplitude, 4),
                h.impact_ms,
            ),
            reverse=True,
        )
        return hypotheses


    def extract_events(
        self,
        frames: list[FramePoseResult],
        audio_transients_ms: list[int] | None = None,
        ball_strike_ms: int | None = None,
    ) -> tuple[list[DetectedEvent], list[str], str]:
        """
        從單一候選揮桿區段之細掃影格序列推導階段事件與狀態轉換軌跡。
        採用多候選揮桿鏈假設生成與客觀證據裁決架構 (P0-1 ~ P0-3)。
        """
        valid_frames = [
            f
            for f in frames
            if f.pose_confidence >= 0.30
            and ("right_wrist" in f.landmarks or "left_wrist" in f.landmarks)
        ]
        if len(valid_frames) < 5:
            self.last_hypotheses = []
            self.last_selection_rationale = "有效關鍵點不足"
            self.last_is_ambiguous = True
            return [], ["IDLE"], "swing_candidate"

        # 1. 抽取特徵時序
        times: list[int] = []
        wrist_xs: list[float] = []
        wrist_ys: list[float] = []
        confs: list[float] = []
        energies: list[float] = []
        shoulder_turns: list[float] = []
        torso_lengths: list[float] = []

        for f in valid_frames:
            w = _midpoint(f, "left_wrist", "right_wrist")
            sh_mid = _midpoint(f, "left_shoulder", "right_shoulder")
            hp_mid = _midpoint(f, "left_hip", "right_hip")
            l_sh = _get_lm_xyv(f.landmarks.get("left_shoulder"))
            r_sh = _get_lm_xyv(f.landmarks.get("right_shoulder"))

            if w is None:
                continue

            times.append(f.time_ms)
            wrist_xs.append(w[0])
            wrist_ys.append(w[1])
            confs.append(f.pose_confidence)
            energies.append(f.wrist_motion_energy)

            t_len = 0.25
            if sh_mid and hp_mid:
                t_len = max(0.08, math.hypot(sh_mid[0] - hp_mid[0], sh_mid[1] - hp_mid[1]))
            torso_lengths.append(t_len)

            sh_rot = 0.0
            if l_sh and r_sh and min(l_sh[2], r_sh[2]) >= 0.35:
                sh_rot = math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1])
            shoulder_turns.append(sh_rot)

        n = len(times)
        if n < 5:
            self.last_hypotheses = []
            self.last_selection_rationale = "有效時間點不足"
            self.last_is_ambiguous = True
            return [], ["IDLE"], "swing_candidate"

        dt_arr = np.diff(times).astype(float)
        dt_arr[dt_arr <= 0] = 33.3
        mean_dt = float(np.mean(dt_arr)) if len(dt_arr) > 0 else 33.3

        v_y = np.gradient(wrist_ys, times)
        v_x = np.gradient(wrist_xs, times)
        speed = np.hypot(v_x, v_y)

        min_wrist_y = float(np.min(wrist_ys))
        max_wrist_y = float(np.max(wrist_ys))
        full_amplitude = max_wrist_y - min_wrist_y

        if full_amplitude < 0.06:
            self.last_hypotheses = []
            self.last_selection_rationale = "垂直振幅不足"
            self.last_is_ambiguous = False
            return [], ["IDLE", "ADDRESS_CANDIDATE", "IDLE"], "swing_candidate"

        # 2. 多候選假設生成 (Multi-Hypothesis Swing Generation)
        hypotheses = self._generate_swing_hypotheses(
            times=times,
            wrist_xs=wrist_xs,
            wrist_ys=wrist_ys,
            speed=speed,
            v_y=v_y,
            confs=confs,
            energies=energies,
            audio_transients_ms=audio_transients_ms,
            ball_strike_ms=ball_strike_ms,
            mean_dt=mean_dt,
            full_amplitude=full_amplitude,
            min_wrist_y=min_wrist_y,
            max_wrist_y=max_wrist_y,
        )

        if not hypotheses:
            self.last_hypotheses = []
            self.last_selection_rationale = "無有效揮桿假設"
            self.last_is_ambiguous = True
            return [], ["IDLE"], "swing_candidate"

        # 3. 雙峰/多候選比較與裁決 (Resolution & Ambiguity Detection)
        best_h = hypotheses[0]
        is_ambiguous = False
        rationale = ""

        if len(hypotheses) >= 2:
            second_h = hypotheses[1]
            diff_score = best_h.total_score - second_h.total_score

            # 若兩組候選得分極為接近 (< 15%) 且皆具備合理性
            if diff_score < 1.8 and second_h.total_score >= 5.0:
                is_ambiguous = True
                best_h.is_ambiguous = True
                second_h.is_ambiguous = True
                rationale = (
                    f"雙峰爭議：候選1 ({best_h.top_ms}/{best_h.impact_ms}ms, 分數={best_h.total_score:.1f}) "
                    f"與候選2 ({second_h.top_ms}/{second_h.impact_ms}ms, 分數={second_h.total_score:.1f}) "
                    f"得分接近且皆具備揮桿特徵，證據未達絕對優勢，標記爭議保留審核。"
                )
            else:
                rationale = (
                    f"優勢裁決：候選1 (Top={best_h.top_ms}ms, Imp={best_h.impact_ms}ms, 得分={best_h.total_score:.1f}) "
                    f"顯著優於次佳候選 (得分={second_h.total_score:.1f})。"
                    f"關鍵優勢: {', '.join(best_h.supporting_evidence[:2])}。"
                    f"次佳候選反對理由: {', '.join(second_h.opposing_evidence[:2]) if second_h.opposing_evidence else '動能較低'}。"
                )
        else:
            rationale = f"唯一明確候選：Top={best_h.top_ms}ms, Impact={best_h.impact_ms}ms, 得分={best_h.total_score:.1f}。"

        self.last_hypotheses = hypotheses
        self.last_selection_rationale = rationale
        self.last_is_ambiguous = is_ambiguous

        # 4. 提取最終事件
        addr_idx = best_h.addr_idx
        takeaway_idx = best_h.takeaway_idx
        top_idx = best_h.top_idx
        downswing_idx = best_h.downswing_idx
        impact_idx = best_h.impact_idx
        follow_idx = best_h.follow_idx
        finish_idx = best_h.finish_idx

        top_sources = ["multi_signal_hypothesis_consensus"]
        if best_h.stroke_amplitude >= 0.10:
            top_sources.append("wrist_vertical_amplitude")
        if any("physiologically_valid_downswing" in s for s in best_h.supporting_evidence):
            top_sources.append("kinematic_downswing_timing")

        impact_sources = ["wrist_kinematic_deceleration"]
        if best_h.ball_strike_applied:
            impact_sources.append("ball_flight_observed_launch")
        if best_h.audio_diff_ms is not None and best_h.audio_diff_ms <= 60:
            impact_sources.append("audio_transient_consensus")

        frame_interval_ms = int(round(mean_dt))
        sampling_res = frame_interval_ms
        top_uncertainty = max(24, frame_interval_ms)
        impact_uncertainty = max(24, frame_interval_ms)
        if "audio_transient_consensus" in impact_sources:
            impact_uncertainty = max(16, int(round(frame_interval_ms * 0.6)))
        if "ball_flight_observed_launch" in impact_sources:
            impact_uncertainty = max(16, int(round(frame_interval_ms * 0.5)))

        top_conf = min(0.96, max(0.60, confs[top_idx] * (0.85 + 0.05 * len(top_sources))))
        impact_conf = min(0.96, max(0.60, confs[impact_idx] * (0.80 + 0.08 * len(impact_sources))))
        if is_ambiguous:
            top_conf = min(top_conf, 0.55)
            impact_conf = min(impact_conf, 0.55)

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

        backswing_idx = min(top_idx, max(takeaway_idx, (takeaway_idx + top_idx) // 2))

        events: list[DetectedEvent] = [
            DetectedEvent(
                event_name="address",
                time_ms=times[addr_idx],
                confidence=round(float(confs[addr_idx]), 3),
                detection_source="multi_signal_settled_anchor",
                model_version=self.model_version,
                rationale="手腕與軀幹於正式起桿前最後凝結靜止低點 (Waggle 抑制)",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["settled_address_stability", "wrist_low_velocity"],
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="takeaway",
                time_ms=times[takeaway_idx],
                confidence=round(float(confs[takeaway_idx]), 3),
                detection_source="multi_signal_kinematics",
                model_version=self.model_version,
                rationale="手腕離開準備位置並啟動主上桿超過 22% 垂直幅度",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["vertical_displacement_threshold"],
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="backswing",
                time_ms=times[backswing_idx],
                confidence=round(float(confs[backswing_idx]), 3),
                detection_source="multi_signal_kinematics",
                model_version=self.model_version,
                rationale="上桿中段手部持續上升軌跡",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["backswing_mid_interpolation"],
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="top",
                time_ms=times[top_idx],
                confidence=round(float(top_conf), 3),
                detection_source="multi_signal_top_consensus",
                model_version=self.model_version,
                rationale=f"上桿頂點：速度零交越與手部最高轉折點 (依據: {', '.join(top_sources)})",
                uncertainty_ms=top_uncertainty,
                detection_sources=top_sources,
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="downswing",
                time_ms=times[downswing_idx],
                confidence=round(float(confs[downswing_idx]), 3),
                detection_source="multi_signal_kinematics",
                model_version=self.model_version,
                rationale="下桿加速階段：手腕由頂點向擊球區快速下降",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["downswing_acceleration_segment"],
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="impact_estimated",
                time_ms=times[impact_idx],
                confidence=round(float(impact_conf), 3),
                detection_source="multi_signal_impact_consensus",
                model_version=self.model_version,
                rationale=f"疑似擊球瞬間（estimated）：下桿速度制動與手部最低點交會 (依據: {', '.join(impact_sources)})",
                uncertainty_ms=impact_uncertainty,
                detection_sources=impact_sources,
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="follow_through",
                time_ms=times[follow_idx],
                confidence=round(float(confs[follow_idx]), 3),
                detection_source="multi_signal_kinematics",
                model_version=self.model_version,
                rationale="隨揮釋放階段：通過最低點後手臂延伸上升",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["follow_through_extension"],
                sampling_resolution_ms=sampling_res,
            ),
            DetectedEvent(
                event_name="finish",
                time_ms=times[finish_idx],
                confidence=round(float(confs[finish_idx]), 3),
                detection_source="multi_signal_balance",
                model_version=self.model_version,
                rationale="收桿完成與停留平衡階段",
                uncertainty_ms=frame_interval_ms,
                detection_sources=["finish_posture_settlement"],
                sampling_resolution_ms=sampling_res,
            ),
        ]

        downswing_peak_energy = max(energies[top_idx : impact_idx + 1] or [0.0])
        max_ds_speed = best_h.downswing_speed_peak
        has_impact_evidence = bool(
            "audio_transient_consensus" in impact_sources
            or "ball_flight_observed_launch" in impact_sources
            or (best_h.audio_diff_ms is not None and best_h.audio_diff_ms <= 60)
            or (ball_strike_ms is not None and abs(ball_strike_ms - times[impact_idx]) <= 150)
        )

        is_practice = (
            best_h.stroke_amplitude < 0.035
            or (downswing_peak_energy < 0.012 and max_ds_speed < 0.0007)
            or (not has_impact_evidence and max_ds_speed < 0.00085 and best_h.finish_hold_ms < 300)
            or (not has_impact_evidence and best_h.stroke_amplitude < 0.055 and best_h.follow_amplitude < 0.035)
        )
        if is_practice:
            label = "practice_swing"
        else:
            label = "valid_swing"

        return events, state_trace, label


def compute_observable_metrics(
    frames: list[FramePoseResult],
    events: list[DetectedEvent],
    model_version: str = "pose-v2",
    event_frames: dict[str, FramePoseResult] | None = None,
) -> list[dict[str, Any]]:
    """
    依據可見 2D 關鍵點與階段事件計算可追溯之 DTL 動作指標。
    若特定階段關鍵點缺失或信心度 < 0.50，該指標設為 value=None 並誠實標記，絕不捏造數值。
    支援優先使用局部高 FPS 精修之真實影格 (event_frames)。
    若時序存在異常 (unreliable)，節奏與下桿時間明確設為 value=None，絕不虛構分數。
    """
    if not frames or not events:
        return []

    event_map = {e.event_name: e.time_ms for e in events}

    def get_event_frame(ev_name: str) -> tuple[FramePoseResult | None, int]:
        """優先使用精修影格，否則使用最近影格，並回傳影格與時間偏差 (ms)。"""
        if event_frames and ev_name in event_frames:
            ef = event_frames[ev_name]
            target_t = event_map.get(ev_name)
            delta = abs(ef.time_ms - target_t) if target_t is not None else 0
            return ef, delta
        target_t = event_map.get(ev_name)
        if target_t is None:
            return None, 0
        nf = min(frames, key=lambda f: abs(f.time_ms - target_t))
        return nf, abs(nf.time_ms - target_t)

    f_addr, _ = get_event_frame("address")
    f_take, _ = get_event_frame("takeaway")
    f_back, _ = get_event_frame("backswing")
    f_top, _ = get_event_frame("top")
    f_down, _ = get_event_frame("downswing")
    f_imp, _ = get_event_frame("impact_estimated")
    f_fin, _ = get_event_frame("finish")

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
        addr_nose = _get_lm_xyv(f_addr.landmarks.get("nose"))
        if addr_nose:
            max_disp = 0.0
            vis_vals = [addr_nose[2]]
            for fr in frames:
                if f_addr.time_ms <= fr.time_ms <= f_imp.time_ms and "nose" in fr.landmarks:
                    n_lm = _get_lm_xyv(fr.landmarks.get("nose"))
                    if n_lm and n_lm[2] >= 0.50:
                        d = math.hypot(n_lm[0] - addr_nose[0], n_lm[1] - addr_nose[1]) / torso_len
                        max_disp = max(max_disp, d)
                        vis_vals.append(n_lm[2])
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

    # 3. 手部上下桿路徑平面差距 (單球 single_swing_plane_gap_ratio) 與相容指標 (hand_path_deviation_ratio)
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
            "metric_key": "single_swing_plane_gap_ratio",
            "value": plane_gap,
            "unit": "ratio",
            "confidence": plane_conf,
            "source": model_version,
            "observability": "observed_2d",
        }
    )
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

    # 4. 上下桿節奏比 (backswing_downswing_ratio) 與 P0-3 異常時序保護
    top_ev = next((e for e in events if e.event_name == "top"), None)
    imp_ev = next((e for e in events if "impact" in e.event_name), None)
    takeaway_ev = next((e for e in events if e.event_name == "takeaway"), None)
    addr_ev = next((e for e in events if e.event_name == "address"), None)
    start_ev = takeaway_ev or addr_ev

    is_timing_anomalous = False
    if top_ev and imp_ev:
        cur_ds = imp_ev.time_ms - top_ev.time_ms
        if cur_ds < 180 or cur_ds > 650:
            is_timing_anomalous = True
        if "timing_anomaly_detected" in top_ev.detection_sources or "timing_anomaly_detected" in imp_ev.detection_sources:
            is_timing_anomalous = True

    if is_timing_anomalous or not (start_ev and top_ev and imp_ev):
        metrics.append(
            {
                "metric_key": "backswing_ms",
                "value": None,
                "unit": "ms",
                "confidence": 0.0,
                "source": model_version,
                "observability": "estimated",
                "details": {"reason": "揮桿時序異常或不可靠，依誠信原則不予評分", "unreliable": True},
            }
        )
        metrics.append(
            {
                "metric_key": "downswing_ms",
                "value": None,
                "unit": "ms",
                "confidence": 0.0,
                "source": model_version,
                "observability": "estimated",
                "details": {"reason": "揮桿時序異常或不可靠，依誠信原則不予評分", "unreliable": True},
            }
        )
        metrics.append(
            {
                "metric_key": "backswing_downswing_ratio",
                "value": None,
                "unit": "ratio",
                "confidence": 0.0,
                "source": model_version,
                "observability": "estimated",
                "details": {"reason": "揮桿時序異常或不可靠，依誠信原則不予評分", "unreliable": True},
            }
        )
    else:
        # 嚴格以 finalized event timestamps 計算時間型指標 (P0-B: 杜絕混用影格時間產生不同數值)
        bs_ms = max(80, top_ev.time_ms - start_ev.time_ms)
        ds_ms = max(60, imp_ev.time_ms - top_ev.time_ms)
        tempo_ratio = round(bs_ms / float(ds_ms), 2)
        tempo_conf = round(min(start_ev.confidence, top_ev.confidence, imp_ev.confidence), 3)

        _, delta_start = get_event_frame("takeaway" if takeaway_ev else "address")
        _, delta_top = get_event_frame("top")
        _, delta_imp = get_event_frame("impact_estimated")

        metrics.append(
            {
                "metric_key": "backswing_ms",
                "value": float(bs_ms),
                "unit": "ms",
                "confidence": tempo_conf,
                "source": model_version,
                "observability": "estimated",
                "details": {
                    "event_start_ms": start_ev.time_ms,
                    "event_top_ms": top_ev.time_ms,
                    "frame_delta_ms": max(delta_start, delta_top),
                },
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
                "details": {
                    "event_top_ms": top_ev.time_ms,
                    "event_impact_ms": imp_ev.time_ms,
                    "frame_delta_ms": max(delta_top, delta_imp),
                },
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
                "details": {
                    "formula": "backswing_ms / downswing_ms",
                    "backswing_ms": float(bs_ms),
                    "downswing_ms": float(ds_ms),
                },
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
