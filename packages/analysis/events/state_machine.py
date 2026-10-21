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

    def extract_events(
        self,
        frames: list[FramePoseResult],
        audio_transients_ms: list[int] | None = None,
        ball_strike_ms: int | None = None,
    ) -> tuple[list[DetectedEvent], list[str], str]:
        """
        從單一候選揮桿區段之細掃影格序列推導階段事件與狀態轉換軌跡。
        只依據可見 2D 關鍵點與多訊號證據轉換，遇跳幀或缺關鍵點則保守降級。
        """
        valid_frames = [
            f
            for f in frames
            if f.pose_confidence >= 0.30
            and ("right_wrist" in f.landmarks or "left_wrist" in f.landmarks)
        ]
        if len(valid_frames) < 5:
            return [], ["IDLE"], "swing_candidate"

        # 1. 抽取多維時間特徵序列
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

            # 估算軀幹參考長度
            t_len = 0.25
            if sh_mid and hp_mid:
                t_len = max(0.08, math.hypot(sh_mid[0] - hp_mid[0], sh_mid[1] - hp_mid[1]))
            torso_lengths.append(t_len)

            # 肩部旋轉指標 (左右肩橫向間距或傾角)
            sh_rot = 0.0
            if l_sh and r_sh and min(l_sh[2], r_sh[2]) >= 0.35:
                sh_rot = math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1])
            shoulder_turns.append(sh_rot)

        n = len(times)
        if n < 5:
            return [], ["IDLE"], "swing_candidate"

        # 計算一階中心差分速度 (像素/ms, y 向上為負)
        dt_arr = np.diff(times).astype(float)
        dt_arr[dt_arr <= 0] = 33.3  # 避免除以零
        mean_dt = float(np.mean(dt_arr)) if len(dt_arr) > 0 else 33.3

        v_y = np.gradient(wrist_ys, times)  # 負值代表向上運動，正值代表向下運動
        v_x = np.gradient(wrist_xs, times)
        speed = np.hypot(v_x, v_y)

        # -------------------------------------------------------------
        # 2. Waggle / Practice Lift 抑制機制 (Settled Address 定位)
        # -------------------------------------------------------------
        min_wrist_y = float(np.min(wrist_ys))
        max_wrist_y = float(np.max(wrist_ys))
        full_amplitude = max_wrist_y - min_wrist_y

        if full_amplitude < 0.06:
            return [], ["IDLE", "ADDRESS_CANDIDATE", "IDLE"], "swing_candidate"

        # 尋找前 30% 區段內手腕高度較低且速度平緩的準備低點
        addr_end_idx = max(2, int(n * 0.30))
        best_addr_score = -1e9
        addr_idx = 0
        mean_spd = float(np.mean(speed)) if len(speed) > 0 else 1e-4

        for i in range(addr_end_idx):
            # y 越大越低 (DTL 站姿地面球位上方)，速度越慢代表身體處於沉靜準備狀態 (抑制微晃動)
            h_s = (wrist_ys[i] - min_wrist_y) / max(1e-3, full_amplitude)
            spd_penalty = speed[i] / max(1e-4, mean_spd)
            score = h_s * 2.5 - spd_penalty * 1.2
            if score > best_addr_score:
                best_addr_score = score
                addr_idx = i

        addr_y = wrist_ys[addr_idx]

        # -------------------------------------------------------------
        # 3. 多訊號 Top of Backswing 頂點判定
        # -------------------------------------------------------------
        peak_speed_idx = int(np.argmax(speed))
        # 搜尋區間：Address 之後至少 2 幀，到前 78% 區間或速度峰值之前
        top_search_start = addr_idx + 1
        top_search_end = max(top_search_start + 2, min(n - 1, int(n * 0.78)))

        # 訊號 1: 手腕垂直速度零交越點 (v_y 由負變正，即向上轉向下)
        zero_crossings: list[int] = []
        for i in range(top_search_start, top_search_end - 1):
            if v_y[i] <= 0 and v_y[i + 1] > 0:
                zero_crossings.append(i)

        # 訊號 2: 手腕速度局部極小值 (Top Pause 頂點轉折停頓)
        pause_candidates: list[int] = []
        for i in range(top_search_start + 1, top_search_end - 1):
            if speed[i] <= speed[i - 1] and speed[i] <= speed[i + 1]:
                pause_candidates.append(i)

        # 訊號 3: 手腕垂直最高點 (y 最小)
        sub_ys = wrist_ys[top_search_start:top_search_end]
        y_min_local = top_search_start + int(np.argmin(sub_ys)) if len(sub_ys) > 0 else top_search_start

        # 多訊號融合評分
        top_candidates = set(zero_crossings + pause_candidates + [y_min_local])
        best_top_score = -1e9
        best_top_idx = y_min_local
        top_sources: list[str] = []

        for cand in top_candidates:
            if cand < top_search_start or cand >= top_search_end:
                continue

            # (1) 高度權重：越靠近最高點得分越高
            h_score = (max_wrist_y - wrist_ys[cand]) / max(1e-3, full_amplitude)

            # (2) 速度停頓權重：轉折處速度越小越可信
            p_score = 1.0 - min(1.0, speed[cand] / max(1e-4, float(np.mean(speed))))

            # (3) 下桿加速驗證：Top 後必須有持續強烈下桿
            sub_post = speed[cand : min(n, cand + 6)]
            post_accel = float(np.max(sub_post)) - speed[cand] if len(sub_post) > 0 else 0.0

            # (4) 全局擊球動能與音訊支持度：Top 後 180~650ms 內是否有全域最大速度峰值或音訊瞬態 (P0-B)
            window_max_spd = float(np.max(speed)) if len(speed) > 0 else 1.0
            ds_end_limit = min(n, cand + max(4, int(650.0 / max(10.0, mean_dt))))
            ds_window = speed[cand + 1 : ds_end_limit]
            ds_max_spd = float(np.max(ds_window)) if len(ds_window) > 0 else 0.0
            kinetic_ratio = ds_max_spd / max(1e-4, window_max_spd)

            has_audio_strike = 0.0
            if audio_transients_ms:
                for a_ms in audio_transients_ms:
                    if 180 <= (a_ms - times[cand]) <= 650:
                        has_audio_strike = 3.5
                        break

            total_s = (
                h_score * 3.0
                + p_score * 2.0
                + post_accel * 35.0
                + kinetic_ratio * 4.5
                + has_audio_strike
            )

            if total_s > best_top_score:
                best_top_score = total_s
                best_top_idx = cand

        top_idx = best_top_idx
        top_y = wrist_ys[top_idx]
        vertical_amplitude = addr_y - top_y

        # 收集 Top 證據來源
        if top_idx in zero_crossings:
            top_sources.append("wrist_velocity_zero_crossing")
        if top_idx in pause_candidates:
            top_sources.append("top_pause_min_speed")
        if abs(top_idx - y_min_local) <= 1:
            top_sources.append("wrist_y_local_minimum")
        if not top_sources:
            top_sources.append("multi_signal_energy_consensus")

        # -------------------------------------------------------------
        # 4. Takeaway & Backswing 判定
        # -------------------------------------------------------------
        takeaway_target_y = addr_y - 0.22 * vertical_amplitude
        takeaway_idx = addr_idx + 1
        for i in range(addr_idx + 1, top_idx):
            if wrist_ys[i] <= takeaway_target_y:
                takeaway_idx = i
                break

        backswing_idx = min(top_idx, max(takeaway_idx, (takeaway_idx + top_idx) // 2))

        # -------------------------------------------------------------
        # 5. 多訊號 Impact 擊球瞬態判定
        # -------------------------------------------------------------
        # 搜尋區間：Top 之後到揮桿後段 (若有音訊或真球，搜尋區間開放到揮桿區段末端；若無亦給予充足餘裕)
        impact_search_start = top_idx + 1
        if audio_transients_ms or ball_strike_ms is not None:
            impact_search_end = max(impact_search_start + 1, n - 2)
        else:
            impact_search_end = min(n - 1, max(top_idx + 4, int(n * 0.88)))

        impact_sources: list[str] = []
        best_imp_idx = min(n - 1, top_idx + 2)
        best_imp_score = -1e9

        # 若有真球觀測，直接作為權威錨點
        if ball_strike_ms is not None:
            closest_idx = int(np.argmin([abs(t - ball_strike_ms) for t in times]))
            if top_idx < closest_idx <= impact_search_end:
                best_imp_idx = closest_idx
                impact_sources.append("ball_flight_observed_launch")

        if not impact_sources:
            for i in range(impact_search_start, impact_search_end + 1):
                # (1) 手腕回到低點程度 (y 越大越低)
                h_weight = (wrist_ys[i] - top_y) / max(1e-3, vertical_amplitude)

                # (2) 下桿速度峰值與減速轉折
                # 擊球時球桿釋放與人體制動會造成速度峰值後急劇減速
                cur_s = speed[i]
                prev_s = speed[i - 1] if i > 0 else cur_s
                decel = max(0.0, prev_s - cur_s) * 30.0

                # (3) 音訊瞬態融合：音訊必須伴隨真實下桿動能，避免收桿靜止時誤採背景雜音
                audio_bonus = 0.0
                max_spd = float(np.max(speed)) if len(speed) > 0 else 1.0
                if audio_transients_ms and cur_s >= 0.30 * max_spd:
                    closest_audio = min(audio_transients_ms, key=lambda a: abs(a - times[i]))
                    audio_diff = abs(closest_audio - times[i])
                    if audio_diff <= 40:
                        audio_bonus = 3.5
                    elif audio_diff <= 80:
                        audio_bonus = 2.0
                    elif audio_diff <= 120:
                        audio_bonus = 1.0

                s = h_weight * 2.5 + cur_s * 60.0 + decel * 40.0 + audio_bonus
                if s > best_imp_score:
                    best_imp_score = s
                    best_imp_idx = i

            impact_sources.append("wrist_kinematic_deceleration")
            if audio_transients_ms:
                closest_audio = min(audio_transients_ms, key=lambda a: abs(a - times[best_imp_idx]))
                if abs(closest_audio - times[best_imp_idx]) <= 60:
                    impact_sources.append("audio_transient_consensus")

        impact_idx = best_imp_idx

        # -------------------------------------------------------------
        # 5.5 高爾夫時序合理性檢核與自動重新對齊 (P0-B)
        # -------------------------------------------------------------
        (
            top_idx,
            impact_idx,
            addr_idx,
            takeaway_idx,
            top_sources,
            impact_sources,
            timing_anomaly,
        ) = self._validate_and_realign_swing_timing(
            times=times,
            wrist_ys=wrist_ys,
            wrist_xs=wrist_xs,
            speed=speed,
            v_y=v_y,
            top_idx=top_idx,
            impact_idx=impact_idx,
            addr_idx=addr_idx,
            takeaway_idx=takeaway_idx,
            audio_transients_ms=audio_transients_ms,
            ball_strike_ms=ball_strike_ms,
            top_sources=top_sources,
            impact_sources=impact_sources,
        )

        backswing_idx = min(top_idx, max(takeaway_idx, (takeaway_idx + top_idx) // 2))
        downswing_idx = max(top_idx, (top_idx + impact_idx) // 2)

        # -------------------------------------------------------------
        # 6. Follow-through & Finish 判定
        # -------------------------------------------------------------
        if impact_idx < n - 2:
            post_impact_ys = wrist_ys[impact_idx + 1 :]
            finish_rel = int(np.argmin(post_impact_ys))
            follow_idx = min(n - 1, impact_idx + 1 + max(0, finish_rel // 2))
            finish_idx = min(n - 1, max(follow_idx, n - 2))
        else:
            follow_idx = impact_idx
            finish_idx = n - 1

        # -------------------------------------------------------------
        # 7. 二次精修與不確定區間估算 (Two-Pass Refinement & P1-A 精度拆分)
        # -------------------------------------------------------------
        # 取樣解析度 (實際影格間隔時間)
        frame_interval_ms = int(round(mean_dt))
        sampling_res = frame_interval_ms

        # 不確定度估計 (根據感測模式與特徵清晰度)
        top_uncertainty = max(24, frame_interval_ms)
        impact_uncertainty = max(24, frame_interval_ms)
        if "audio_transient_consensus" in impact_sources:
            impact_uncertainty = max(16, int(round(frame_interval_ms * 0.6)))
        if "ball_flight_observed_launch" in impact_sources:
            impact_uncertainty = max(16, int(round(frame_interval_ms * 0.5)))

        # 信心度動態加權 (異常時降級)
        top_conf = min(0.96, max(0.60, confs[top_idx] * (0.85 + 0.05 * len(top_sources))))
        impact_conf = min(0.96, max(0.60, confs[impact_idx] * (0.80 + 0.08 * len(impact_sources))))
        if timing_anomaly:
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

        # 判斷是正式揮桿 (valid_swing) 還是空揮練習 (practice_swing)
        finish_hold_ms = max(0, times[-1] - times[follow_idx])
        downswing_peak_energy = max(energies[top_idx : impact_idx + 1] or [0.0])
        max_ds_speed = float(np.max(speed[top_idx : impact_idx + 1])) if impact_idx > top_idx else 0.0

        has_impact_evidence = bool(
            "audio_transient_consensus" in impact_sources
            or "ball_flight_observed_launch" in impact_sources
            or (ball_strike_ms is not None and abs(ball_strike_ms - times[impact_idx]) <= 150)
        )

        is_practice = (
            vertical_amplitude < 0.065
            or (downswing_peak_energy < 0.015 and max_ds_speed < 0.0009)
            or (max_ds_speed < 0.0010 and not has_impact_evidence and finish_hold_ms < 400)
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
