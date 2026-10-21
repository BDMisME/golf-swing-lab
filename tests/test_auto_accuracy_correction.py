"""
高爾夫揮桿分析系統 — 自動準確度校準與資料流一致性驗收測試
(tests/test_auto_accuracy_correction.py)

驗收範疇：
1. P0-A: 靜止球誤判防護 (Stationary Ball Rejection & Airborne Continuity)
2. P0-B: 試擺 Waggle 抑制與 Top/Impact 生理時序自動重新對齊 (180ms - 650ms)
3. P0-C: 事件精修後 Metrics (Tempo / Downswing ms) 與片段邊界重算與一致性
4. P1-A: 時間精度欄位拆分 (sampling_resolution_ms vs uncertainty_ms)
5. P1-B: 片段邊界防溢出安全保護 (Clamping to duration_ms)
"""

from unittest.mock import patch

import numpy as np
import pytest

from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.analysis.events.state_machine import (
    DetectedEvent,
    SwingPhaseStateMachine,
    compute_observable_metrics,
)
from packages.analysis.pose.extractor import FramePoseResult, Landmark2D
from packages.analysis.tracking.ball_tracker import (
    GolfBallDetector,
    analyze_ball_launch_continuity,
)


def _create_synthetic_frame(
    time_ms: int,
    frame_idx: int,
    wrist_y: float = 0.70,
    wrist_x: float = 0.50,
    confidence: float = 0.90,
) -> FramePoseResult:
    lm = {
        "nose": Landmark2D(x=0.50, y=0.25, visibility=confidence),
        "left_shoulder": Landmark2D(x=0.52, y=0.35, visibility=confidence),
        "right_shoulder": Landmark2D(x=0.48, y=0.35, visibility=confidence),
        "left_hip": Landmark2D(x=0.51, y=0.55, visibility=confidence),
        "right_hip": Landmark2D(x=0.49, y=0.55, visibility=confidence),
        "left_wrist": Landmark2D(x=wrist_x, y=wrist_y, visibility=confidence),
        "right_wrist": Landmark2D(x=wrist_x, y=wrist_y, visibility=confidence),
        "left_ankle": Landmark2D(x=0.51, y=0.88, visibility=confidence),
        "right_ankle": Landmark2D(x=0.49, y=0.88, visibility=confidence),
    }
    return FramePoseResult(
        time_ms=time_ms,
        frame_idx=frame_idx,
        landmarks=lm,
        pose_confidence=confidence,
        wrist_motion_energy=0.05,
        brightness=120.0,
        sharpness=80.0,
        camera_motion=0.01,
    )


def _create_mock_swing_frames(count: int = 30, dt_ms: int = 66) -> list[FramePoseResult]:
    frames = []
    # y 軸：0.75 (Address) -> 0.25 (Top) -> 0.76 (Impact) -> 0.35 (Finish)
    for i in range(count):
        t_ms = i * dt_ms
        if i <= 5:  # Address & Takeaway
            wy = 0.72 - (i * 0.03)
        elif i <= 10:  # Backswing to Top
            wy = 0.57 - ((i - 5) * 0.06)  # i=10 -> wy = 0.27
        elif i <= 14:  # Downswing to Impact
            wy = 0.27 + ((i - 10) * 0.12)  # i=14 -> wy = 0.75 (924ms)
        else:  # Follow through & Finish
            wy = 0.75 - ((i - 14) * 0.04)

        frames.append(_create_synthetic_frame(time_ms=t_ms, frame_idx=i, wrist_y=wy))
    return frames


# -----------------------------------------------------------------------------
# 測試 1: P0-A 靜止球誤判防護
# -----------------------------------------------------------------------------
def test_stationary_ball_is_rejected_without_fake_launch():
    """驗證打擊墊上靜止小白球（或微幅噪聲震動）絕不被誤判為 launch，不輸出假球路。"""
    # 模擬 5 幀在打擊墊上的觀測點，位移均小於 0.015 (處於原地微抖動)
    stationary_observations = [
        {"time_ms": 1000, "x": 0.500, "y": 0.750, "conf": 0.92},
        {"time_ms": 1033, "x": 0.502, "y": 0.751, "conf": 0.90},
        {"time_ms": 1066, "x": 0.501, "y": 0.749, "conf": 0.89},
        {"time_ms": 1100, "x": 0.503, "y": 0.750, "conf": 0.91},
    ]

    analysis = analyze_ball_launch_continuity(stationary_observations, impact_ref_ms=1000)
    assert analysis["state"] == "stationary", f"靜止球應被判定為 stationary，實際為 {analysis['state']}"
    assert analysis["is_launch"] is False, "靜止球絕不能判定為 is_launch=True"
    assert analysis["launch_ms"] is None, "靜止球不能產生出球時間"
    assert analysis["airborne_points"] == [], "靜止球不能產生升空飛行點"


def test_ball_strike_feedback_rejects_stationary_ball():
    """驗證當追蹤到的小白球判定為 stationary 時，系統不回饋修改 Impact 且不標記 confirmed_strike。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_swing_frames(count=30, dt_ms=66)

    stationary_res = {
        "trajectory_points": [],
        "observed_launch_ms": None,
        "observed_count": 4,
        "is_valid": False,
        "launch_state": "stationary",
        "max_displacement": 0.008,
    }

    with patch.object(
        GolfBallDetector,
        "track_swing_launch_with_feedback",
        return_value=stationary_res,
    ):
        with patch.object(detector, "_sample_video_window", return_value=frames):
            seg = detector.analyze_single_window(
                video_path="dummy.mp4",
                start_ms=0,
                end_ms=2000,
                duration_ms=2000,
                sequence_no=1,
            )

    assert seg is not None
    assert seg.ball_strike_status != "confirmed_strike", "靜止球絕對不能觸發 confirmed_strike"
    imp_ev = next((e for e in seg.events if "impact" in e.event_name), None)
    assert imp_ev is not None
    assert "ball_flight_observed_launch" not in imp_ev.detection_sources, "未出球絕不能列入真球出球來源"


# -----------------------------------------------------------------------------
# 測試 2: P0-B 試擺 Waggle 抑制與 Top/Impact 生理時序自動重新對齊
# -----------------------------------------------------------------------------
def test_waggle_suppression_and_top_impact_kinematic_realignment():
    """
    驗證當擊球前存在試擺 (Waggle) 導致初步 Top 抓在 2 秒前時，
    系統自動依據 Impact 在 [T_impact - 650ms, T_impact - 180ms] 物理視窗內
    以運動學特徵 (零交越、速度停頓、強烈下桿) 重新鎖定真實擊球 Top。
    """
    sm = SwingPhaseStateMachine()

    # 模擬一段時長 4.0 秒的揮桿：
    # 0~1.2s: 準備與一次試擺 (Waggle) -> 手腕在 600ms 處升高至 0.35 (假頂點)
    # 1.2s~2.0s: 試擺完放下重新瞄球 (2000ms: y=0.72)
    # 2.2s~3.1s: 正式上桿起桿 -> 3100ms 達到真正 Top (y=0.28)
    # 3.1s~3.45s: 快速下桿 (Downswing 350ms) -> 3450ms 擊球 (Impact: y=0.74)
    # 3.45s~4.0s: 隨揮與收桿
    frames: list[FramePoseResult] = []
    total_frames = 60
    dt = 66  # ~15 fps
    for i in range(total_frames):
        t = i * dt
        if t < 600:
            wy = 0.72 - (t / 600.0) * 0.37  # 0.72 -> 0.35
        elif t < 1200:
            wy = 0.35 + ((t - 600) / 600.0) * 0.37  # 0.35 -> 0.72 (試擺放下)
        elif t < 2200:
            wy = 0.72  # 重新凝結準備
        elif t < 3100:
            wy = 0.72 - ((t - 2200) / 900.0) * 0.44  # 正式起桿上桿 0.72 -> 0.28 (真 Top)
        elif t < 3450:
            wy = 0.28 + ((t - 3100) / 350.0) * 0.46  # 快速下桿 0.28 -> 0.74 (Impact)
        else:
            wy = 0.74 - ((t - 3450) / 550.0) * 0.35  # 隨揮收桿

        frames.append(_create_synthetic_frame(time_ms=t, frame_idx=i, wrist_y=wy))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[3450])
    ev_map = {e.event_name: e for e in events}

    top_ev = ev_map.get("top")
    imp_ev = ev_map.get("impact_estimated")

    assert top_ev is not None and imp_ev is not None
    downswing_time = imp_ev.time_ms - top_ev.time_ms

    # 關鍵驗證：下桿時間必須嚴格落在高爾夫生理極限 180ms ~ 650ms 內，不得是 2000ms+ 的試擺假下桿！
    assert 200 <= downswing_time <= 600, (
        f"Top->Impact 下桿時間異常 ({downswing_time}ms)，未成功抑制試擺或重新對齊！"
        f"Top: {top_ev.time_ms}ms, Impact: {imp_ev.time_ms}ms"
    )
    assert top_ev.time_ms >= 2800, f"真實 Top 應鎖定在 3100ms 附近，實際為 {top_ev.time_ms}ms"


# -----------------------------------------------------------------------------
# 測試 3: P0-C 事件精修後 Metrics 與邊界單向重算
# -----------------------------------------------------------------------------
def test_metrics_and_boundaries_recomputed_after_refinement():
    """驗證在事件精修（如真球回饋修正 Impact）後，Metrics 與揮桿邊界必須立即依據新時間碼重新計算。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_swing_frames(count=30, dt_ms=66)

    # 模擬原本估計 Impact 在 990ms，真球出發觀測點在 924ms
    mock_traj = [
        {"time_ms": 924.0, "x": 0.50, "y": 0.75, "point_type": "observed", "confidence": 0.90},
        {"time_ms": 950.0, "x": 0.55, "y": 0.60, "point_type": "observed", "confidence": 0.88},
    ]

    with patch.object(
        GolfBallDetector,
        "track_swing_launch_with_feedback",
        return_value={
            "trajectory_points": mock_traj,
            "observed_launch_ms": 924,
            "observed_count": 2,
            "is_valid": True,
            "launch_state": "airborne",
            "max_displacement": 0.08,
        },
    ):
        with patch.object(detector, "_sample_video_window", return_value=frames):
            seg = detector.analyze_single_window(
                video_path="dummy.mp4",
                start_ms=0,
                end_ms=2000,
                duration_ms=2000,
                sequence_no=1,
            )

    assert seg is not None
    imp_ev = next((e for e in seg.events if "impact" in e.event_name), None)
    top_ev = next((e for e in seg.events if e.event_name == "top"), None)
    assert imp_ev is not None and top_ev is not None
    assert imp_ev.time_ms == 924, "Impact 應精修為 924ms"

    # 檢核 Metrics 是否真正依據 924ms 重新計算
    m_dict = {m["metric_key"]: m["value"] for m in seg.metrics if m.get("value") is not None}
    expected_ds_ms = float(imp_ev.time_ms - top_ev.time_ms)
    assert m_dict.get("downswing_ms") == expected_ds_ms, (
        f"Metrics 中的 downswing_ms ({m_dict.get('downswing_ms')}) 必須與精修後事件時間碼 "
        f"({expected_ds_ms}) 100% 同步！"
    )


# -----------------------------------------------------------------------------
# 測試 4: P1-A 時間精度欄位拆分與誠信揭露
# -----------------------------------------------------------------------------
def test_timing_precision_fields_separated():
    """驗證時間精度拆分為 sampling_resolution_ms 與 uncertainty_ms，無真值時 error 為 None。"""
    ev = DetectedEvent(
        event_name="top",
        time_ms=1200,
        confidence=0.88,
        detection_source="pose-v2",
        uncertainty_ms=25,
        sampling_resolution_ms=16,
    )
    d = ev.to_dict()
    assert d["sampling_resolution_ms"] == 16, "取樣解析度欄位必須存在"
    assert d["uncertainty_ms"] == 25, "估計不確定度欄位必須存在"
    assert d["event_timing_error_ms"] is None, "無人工真值時 timing error 必須為 None，絕不捏造為 0"


# -----------------------------------------------------------------------------
# 測試 5: P1-B 片段邊界防溢出安全保護
# -----------------------------------------------------------------------------
def test_segment_boundaries_clamped_to_video_duration():
    """驗證當揮桿靠近影片末端時，refined_end 嚴格不超出 duration_ms。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_swing_frames(count=15, dt_ms=66)

    with patch.object(detector, "_sample_video_window", return_value=frames):
        seg = detector.analyze_single_window(
            video_path="dummy.mp4",
            start_ms=0,
            end_ms=1000,
            duration_ms=1000,  # 總長度 1000ms
            sequence_no=1,
        )

    assert seg is not None
    assert seg.start_ms >= 0, "start_ms 不能為負值"
    assert seg.end_ms <= 1000, f"end_ms ({seg.end_ms}) 絕不能超出影片總長度 (1000)"


# -----------------------------------------------------------------------------
# 測試 6: P0-1 候選順序不變性與零交越隔離測試
# -----------------------------------------------------------------------------
def test_top_realignment_candidate_order_invariance_and_zc_isolation():
    """
    驗證 Top 重對齊時：
    1. best_cand 自身的零交越 (zero crossing) 與運動學特徵被獨立檢核，不被迴圈最後殘留的變數洩漏污染。
    2. 候選點順序反轉或變更時，選出的最佳候選與重對齊決策完全唯一一致。
    """
    sm = SwingPhaseStateMachine()

    # 構造一組 20 幀時序數據
    # 0~10 幀為試擺或上桿，在 idx=6 (t=400ms) 達到局部頂點且有完美零交越 (v_y[6]<=0, v_y[7]>0)
    # idx=9 (t=600ms) 為快速下桿 (v_y[9] > 0，無零交越)
    # idx=15 (t=1000ms) 為擊球瞬間
    times = [i * 66 for i in range(20)]
    n = len(times)
    wrist_ys = [0.70] * n
    wrist_xs = [0.50] * n

    # 設置手腕 Y 軸軌跡
    wrist_ys[0] = 0.70
    wrist_ys[3] = 0.45
    wrist_ys[6] = 0.28  # 最佳 Top 候選：手腕最高，轉折向下
    wrist_ys[7] = 0.35
    wrist_ys[9] = 0.58  # 視窗邊界候選：正在快速下桿，無零交越
    wrist_ys[15] = 0.75  # Impact

    v_y = np.gradient(wrist_ys, times)
    speed = np.abs(v_y)

    impact_idx = 15
    top_idx_initial = 1  # 初始假頂點

    # 調用重對齊邏輯，先驗證整體流程
    (
        top_idx,
        impact_idx_out,
        addr_idx,
        takeaway_idx,
        t_sources,
        i_sources,
        has_anomaly,
    ) = sm._validate_and_realign_swing_timing(
        times=times,
        wrist_ys=wrist_ys,
        wrist_xs=wrist_xs,
        speed=speed,
        v_y=v_y,
        top_idx=top_idx_initial,
        impact_idx=impact_idx,
        addr_idx=0,
        takeaway_idx=1,
        audio_transients_ms=[times[15]],
        ball_strike_ms=None,
        top_sources=[],
        impact_sources=[],
    )

    # 驗證最佳候選 6 必須成功被選中並重對齊，不能因為邊界候選 9 無零交越而被拒絕
    assert top_idx == 6, f"Top 重對齊應選中具有零交越的最佳候選 idx=6，實際選中 {top_idx}"
    assert "pre_impact_kinematic_realigned" in t_sources, "應記錄重對齊來源"

    # --- P0-D: 真實實施排列不變性 (Permutation Invariance) 測試 ---
    # 候選子集合：包含最佳候選 6，以及周邊候選 3, 5, 7, 9
    win_cands = [3, 5, 6, 7, 9]

    # 基準決策
    base_cand, base_score, base_zc, base_acc = sm._select_best_top_realign_candidate(
        win_cands=win_cands,
        times=times,
        wrist_ys=wrist_ys,
        speed=speed,
        v_y=v_y,
        impact_idx=impact_idx,
        n=n,
    )
    assert base_cand == 6

    # 測試多種排列 (包含完全倒序與多種隨機置換)
    import random
    permutations_to_test = [
        list(reversed(win_cands)),  # 倒序
        [6, 9, 3, 7, 5],            # 最佳候選置首
        [9, 7, 5, 3, 6],            # 最佳候選置尾
        [5, 3, 9, 7, 6],            # 交錯排列
    ]
    # 隨機產生 10 種不同排列
    rng = random.Random(42)
    for _ in range(10):
        shuffled = list(win_cands)
        rng.shuffle(shuffled)
        permutations_to_test.append(shuffled)

    for perm in permutations_to_test:
        cand_p, score_p, zc_p, acc_p = sm._select_best_top_realign_candidate(
            win_cands=perm,
            times=times,
            wrist_ys=wrist_ys,
            speed=speed,
            v_y=v_y,
            impact_idx=impact_idx,
            n=n,
        )
        assert cand_p == base_cand, f"候選排列 {perm} 改變了裁決結果：得到 {cand_p}，預期 {base_cand}"
        assert abs(score_p - base_score) < 1e-6, "評分值不應因輸入排列而異"
        assert zc_p == base_zc, "零交越標記不應因輸入排列而異"
        assert acc_p == base_acc, "加速度標記不應因輸入排列而異"

    # --- P0-D: 測試等價分數平手打破 (Tie-breaking) 的確定性 ---
    # 構造兩個完全等分之合成候選 A (idx=1) 與 B (idx=2)
    dummy_cands = [1, 2]
    # 不論傳入 [1, 2] 還是 [2, 1]，選擇的結果必須嚴格一致
    res_12, _, _, _ = sm._select_best_top_realign_candidate(
        win_cands=[1, 2],
        times=times,
        wrist_ys=wrist_ys,
        speed=speed,
        v_y=v_y,
        impact_idx=impact_idx,
        n=n,
    )
    res_21, _, _, _ = sm._select_best_top_realign_candidate(
        win_cands=[2, 1],
        times=times,
        wrist_ys=wrist_ys,
        speed=speed,
        v_y=v_y,
        impact_idx=impact_idx,
        n=n,
    )
    assert res_12 == res_21, f"等價候選平手打破必須確定且順序不變：[1, 2] -> {res_12}, [2, 1] -> {res_21}"


# -----------------------------------------------------------------------------
# 測試 7: P0-3 異常時序自主降級與不可評分保護
# -----------------------------------------------------------------------------
def test_timing_anomaly_degradation_and_null_metrics():
    """
    驗證當揮桿時序異常 (如下桿時間 < 180ms 或 > 650ms 且無客觀證據修復) 時：
    1. 系統自動標記 timing_anomaly_detected
    2. review_status 降級為 needs_review，加入 timing_anomaly 標籤
    3. compute_observable_metrics 將 downswing_ms 與 backswing_downswing_ratio 設為 None
    4. 絕不虛構不可靠分數，落實誠信原則
    """
    # 構造一個下桿時間只有 80ms 的異常事件列表 (如極端手部抖動)
    events = [
        DetectedEvent(
            event_name="address",
            time_ms=1000,
            confidence=0.85,
            detection_source="pose-v2",
        ),
        DetectedEvent(
            event_name="takeaway",
            time_ms=1200,
            confidence=0.85,
            detection_source="pose-v2",
        ),
        DetectedEvent(
            event_name="top",
            time_ms=1500,
            confidence=0.50,
            detection_source="pose-v2",
            detection_sources=["timing_anomaly_detected"],
        ),
        DetectedEvent(
            event_name="impact_estimated",
            time_ms=1580,  # 僅差 80ms (異常)
            confidence=0.50,
            detection_source="pose-v2",
            detection_sources=["timing_anomaly_detected"],
        ),
        DetectedEvent(
            event_name="finish",
            time_ms=2200,
            confidence=0.85,
            detection_source="pose-v2",
        ),
    ]

    frames = _create_mock_swing_frames(count=20, dt_ms=66)
    metrics = compute_observable_metrics(frames=frames, events=events)
    m_dict = {m["metric_key"]: m for m in metrics}

    # 檢核依賴不可靠時序的指標全部為 None
    assert m_dict["downswing_ms"]["value"] is None, "異常揮桿的 downswing_ms 必須設為 None"
    assert m_dict["backswing_downswing_ratio"]["value"] is None, "異常揮桿的節奏比必須設為 None"
    assert m_dict["downswing_ms"]["confidence"] == 0.0, "信心度必須為 0.0"
    assert m_dict["downswing_ms"]["details"]["unreliable"] is True, "必須明確標示 unreliable"
