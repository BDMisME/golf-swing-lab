"""R4: DTL 視角專屬演算法與物理過濾自動化測試 (tests/test_r4_dtl_algorithms.py)

驗收範疇：
1. 出球動態軌跡 (Ball Tracer) 高爾夫物理合理性檢核 (濾除水平橫向、倒退與胸腰部假球雜訊)
2. DTL 2D 幾何觀測指標計算 (脊柱傾角、頭部相對位移、節奏比)
3. PGA 鉛線 (Tush Line) 早起檢測邏輯
"""

from packages.analysis.events.state_machine import (
    DetectedEvent,
    FramePoseResult,
    compute_observable_metrics,
)
from packages.analysis.pose.extractor import Landmark2D
from packages.analysis.tracking.ball_tracker import (
    KalmanBallTracker,
    validate_ball_trajectory_physics,
)


def test_kalman_filter_smooth_trajectory():
    """驗證卡爾曼濾波器在正常拋物線下的平滑補全能力。"""
    tracker = KalmanBallTracker(fps=60.0)
    tracker.init_state(x=0.50, y=0.80, vx=0.01, vy=-0.02)

    # 模擬 5 幀上升飛行
    points = []
    for i in range(5):
        # 偶數幀有量測，奇數幀丟失 (模擬快門動態模糊)
        meas_x = 0.50 + i * 0.015 if i % 2 == 0 else None
        meas_y = 0.80 - i * 0.020 if i % 2 == 0 else None
        px, py = tracker.update(meas_x, meas_y, time_ms=1000 + i * 16)
        points.append((px, py))

    assert len(points) == 5
    # 驗證 y 隨時間持續上升 (像素 y 減小)
    assert points[-1][1] < points[0][1], "小白球必須持續向上飛行"
    # 驗證 x 隨時間持續前進 (像素 x 增加)
    assert points[-1][0] > points[0][0], "小白球必須持續向前延伸"


def test_ball_physics_validation():
    """驗證出球物理合理性過濾：拒絕水平穿越身體、向後倒退、起點懸空之雜訊。"""
    # 案例 1: 正常由地面 (y=0.75) 升空 (y=0.30) 向前 (x=0.50 -> 0.70)
    valid_traj = [
        {"time_ms": 1000, "x": 0.50, "y": 0.75},
        {"time_ms": 1050, "x": 0.60, "y": 0.50},
        {"time_ms": 1100, "x": 0.70, "y": 0.30},
    ]
    assert validate_ball_trajectory_physics(valid_traj) is True, "正常出球軌跡應通過"

    # 案例 2: 起點懸空 (y=0.35，在胸腰以上，屬於背景雜訊誤抓)
    sky_start_traj = [
        {"time_ms": 1000, "x": 0.50, "y": 0.35},
        {"time_ms": 1050, "x": 0.60, "y": 0.25},
        {"time_ms": 1100, "x": 0.70, "y": 0.15},
    ]
    assert validate_ball_trajectory_physics(sky_start_traj) is False, "起點懸空之雜訊應被拒絕"

    # 案例 3: 水平穿透身體或倒退 (x 向後倒退)
    backward_traj = [
        {"time_ms": 1000, "x": 0.50, "y": 0.75},
        {"time_ms": 1050, "x": 0.40, "y": 0.75},
        {"time_ms": 1100, "x": 0.30, "y": 0.75},
    ]
    assert validate_ball_trajectory_physics(backward_traj) is False, "倒退水平雜訊應被拒絕"

    # 案例 4: 往下打入地底 (y 變大)
    down_traj = [
        {"time_ms": 1000, "x": 0.50, "y": 0.75},
        {"time_ms": 1050, "x": 0.55, "y": 0.85},
        {"time_ms": 1100, "x": 0.60, "y": 0.95},
    ]
    assert validate_ball_trajectory_physics(down_traj) is False, "向下入地雜訊應被拒絕"

    # 案例 5: 左打者正常由打擊墊向左上方升空 (x 減小，y 減小)
    lefty_traj = [
        {"time_ms": 1000, "x": 0.50, "y": 0.75},
        {"time_ms": 1050, "x": 0.40, "y": 0.50},
        {"time_ms": 1100, "x": 0.30, "y": 0.30},
    ]
    assert validate_ball_trajectory_physics(lefty_traj) is True, "左打者向左上方升空軌跡應被正確接受"


def test_dtl_metrics_computation():
    """驗證 DTL 關鍵幾何指標提取 (前傾角變化、頭部位移、節奏比)。"""
    # 模擬 Address 站姿幀 (使用 Landmark2D 物件)
    addr_lms = {
        "nose": Landmark2D(x=0.50, y=0.25, visibility=0.95),
        "left_shoulder": Landmark2D(x=0.51, y=0.35, visibility=0.95),
        "right_shoulder": Landmark2D(x=0.49, y=0.35, visibility=0.95),
        "left_hip": Landmark2D(x=0.51, y=0.55, visibility=0.95),
        "right_hip": Landmark2D(x=0.49, y=0.55, visibility=0.95),
        "left_ankle": Landmark2D(x=0.51, y=0.88, visibility=0.95),
        "right_ankle": Landmark2D(x=0.49, y=0.88, visibility=0.95),
        "left_wrist": Landmark2D(x=0.50, y=0.65, visibility=0.90),
        "right_wrist": Landmark2D(x=0.50, y=0.65, visibility=0.90),
    }
    # 模擬 Impact 擊球幀 (稍微早起前頂 3 度)
    impact_lms = dict(addr_lms)
    impact_lms["left_hip"] = Landmark2D(x=0.53, y=0.55, visibility=0.95)
    impact_lms["right_hip"] = Landmark2D(x=0.51, y=0.55, visibility=0.95)

    frames = [
        FramePoseResult(time_ms=1000, frame_idx=0, landmarks=addr_lms),
        FramePoseResult(time_ms=1750, frame_idx=45, landmarks=addr_lms),  # Top (750ms 上桿)
        FramePoseResult(time_ms=2000, frame_idx=60, landmarks=impact_lms),  # Impact (250ms 下桿)
        FramePoseResult(time_ms=3000, frame_idx=120, landmarks=impact_lms),  # Finish (1000ms 收桿)
    ]

    events = [
        DetectedEvent(event_name="address", time_ms=1000, confidence=0.9, model_version="v1", rationale=""),
        DetectedEvent(event_name="top", time_ms=1750, confidence=0.9, model_version="v1", rationale=""),
        DetectedEvent(event_name="impact_estimated", time_ms=2000, confidence=0.9, model_version="v1", rationale=""),
        DetectedEvent(event_name="finish", time_ms=3000, confidence=0.9, model_version="v1", rationale=""),
    ]

    metrics = compute_observable_metrics(
        frames=frames,
        events=events,
    )

    m_map = {m["metric_key"]: m for m in metrics}
    assert "spine_tilt_delta_deg" in m_map, "必須包含脊柱前傾差"
    assert "head_displacement_ratio" in m_map, "必須包含頭部相對位移"
    assert "backswing_downswing_ratio" in m_map, "必須包含上下桿節奏比"

    tempo_val = m_map["backswing_downswing_ratio"]["value"]
    assert tempo_val is not None
    assert abs(tempo_val - 3.0) < 0.1, f"節奏比應為 3.0:1, 實際為: {tempo_val}"
