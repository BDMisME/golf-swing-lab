"""
tests/test_negative_samples_and_classification.py

P0-C: 負樣本基準與分類能力獨立驗證
包含 6 類明確定義之非擊球負樣本：
1. Practice Swing (空揮練習)
2. Waggle (試擺/微動)
3. Walking (練習場橫向走動)
4. Picking Ball (彎腰撿球)
5. Setup Adjustment (調整腳步與握桿站姿)
6. Stepping Out of Frame (球友走出鏡頭)

驗證分類器能精確區分正式擊球 (valid_swing) 與各類負樣本，
絕不將負樣本誤判為 valid_swing。
若無獨立第三方人工金標，明確標註 PROVISIONAL / NOT_VALIDATED。
"""

import math
import numpy as np
import pytest

from packages.analysis.events.state_machine import SwingPhaseStateMachine
from packages.analysis.pose.extractor import FramePoseResult, Landmark2D


def _make_frame(
    time_ms: int,
    frame_idx: int,
    wrist_y: float = 0.70,
    wrist_x: float = 0.50,
    nose_x: float = 0.50,
    nose_y: float = 0.30,
    conf: float = 0.85,
    visible: bool = True,
) -> FramePoseResult:
    """構造合成或模擬人體關鍵點幀。"""
    if not visible:
        return FramePoseResult(
            frame_idx=frame_idx,
            time_ms=time_ms,
            landmarks={},
            pose_confidence=0.0,
        )

    landmarks = {
        "nose": Landmark2D(x=nose_x, y=nose_y, visibility=conf),
        "left_shoulder": Landmark2D(x=0.48, y=0.40, visibility=conf),
        "right_shoulder": Landmark2D(x=0.52, y=0.40, visibility=conf),
        "left_hip": Landmark2D(x=0.49, y=0.60, visibility=conf),
        "right_hip": Landmark2D(x=0.51, y=0.60, visibility=conf),
        "left_wrist": Landmark2D(x=wrist_x - 0.02, y=wrist_y, visibility=conf),
        "right_wrist": Landmark2D(x=wrist_x + 0.02, y=wrist_y, visibility=conf),
        "left_ankle": Landmark2D(x=0.48, y=0.90, visibility=conf),
        "right_ankle": Landmark2D(x=0.52, y=0.90, visibility=conf),
    }
    return FramePoseResult(
        frame_idx=frame_idx,
        time_ms=time_ms,
        landmarks=landmarks,
        pose_confidence=conf,
    )


def test_negative_sample_1_practice_swing():
    """
    負樣本 1: Practice Swing (空揮練習)
    特徵：有完整的上桿與下桿運動，但下桿速度平緩、無爆發衝擊動能，收桿後未停留平衡。
    判定標準：必須被分類為 practice_swing，絕對禁止標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames: list[FramePoseResult] = []
    # 2 秒區間，dt=66ms (30 幀)
    for i in range(30):
        t = i * 66
        if t < 600:
            wy = 0.70 - (t / 600.0) * 0.35  # 慢速上桿 0.70 -> 0.35
        elif t < 1200:
            wy = 0.35 + ((t - 600) / 600.0) * 0.35  # 慢速下桿 0.35 -> 0.70 (無衝擊急煞)
        else:
            wy = 0.70 - ((t - 1200) / 800.0) * 0.20  # 輕輕收桿，未穩固停留
        frames.append(_make_frame(time_ms=t, frame_idx=i, wrist_y=wy))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label == "practice_swing", f"空揮動作應分類為 practice_swing，實際為 {label}"


def test_negative_sample_2_waggle():
    """
    負樣本 2: Waggle (起桿前微幅試擺)
    特徵：手腕在準備位置微幅晃動，垂直幅度極小 (amplitude < 0.065)。
    判定標準：判定為 practice_swing 或 swing_candidate，絕對禁止標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames: list[FramePoseResult] = []
    for i in range(25):
        t = i * 66
        # 在 y=0.70 上下晃動 0.02
        wy = 0.70 + 0.02 * math.sin(t * 0.01)
        frames.append(_make_frame(time_ms=t, frame_idx=i, wrist_y=wy))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label in ("practice_swing", "swing_candidate"), (
        f"Waggle 試擺應被抑制或分類為 practice_swing/swing_candidate，實際為 {label}"
    )


def test_negative_sample_3_walking():
    """
    負樣本 3: Walking (練習場橫向走動)
    特徵：球友在鏡頭前橫向移動，鼻尖與身體水平 X 軸線性改變，手腕垂放身側無垂直揮桿動作。
    判定標準：無有效垂直幅度，絕不標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames: list[FramePoseResult] = []
    for i in range(30):
        t = i * 66
        # 身體與手腕在 X 軸橫移 0.20 -> 0.80，手腕 Y 軸垂直維持在 0.75 垂放
        nx = 0.20 + (t / 2000.0) * 0.60
        wy = 0.75 + 0.01 * math.sin(t * 0.02)  # 僅有腳步微震
        frames.append(_make_frame(time_ms=t, frame_idx=i, wrist_y=wy, wrist_x=nx, nose_x=nx))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label != "valid_swing", f"走動不應被標記為 valid_swing，實際為 {label}"


def test_negative_sample_4_picking_ball():
    """
    負樣本 4: Picking Ball (彎腰撿球)
    特徵：軀幹大幅前傾俯身彎腰 (鼻尖下降，手腕向下伸向地面 y=0.92)，隨後直立起身。
    判定標準：無高爾夫上桿頂點 (手腕向上轉折)，絕不標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames: list[FramePoseResult] = []
    for i in range(30):
        t = i * 66
        if t < 1000:
            wy = 0.70 + (t / 1000.0) * 0.25  # 0.70 -> 0.95 (彎腰手腕觸地撿球)
            ny = 0.30 + (t / 1000.0) * 0.35  # 0.30 -> 0.65 (頭部大幅低下)
        else:
            wy = 0.95 - ((t - 1000) / 1000.0) * 0.25  # 直立起身
            ny = 0.65 - ((t - 1000) / 1000.0) * 0.35
        frames.append(_make_frame(time_ms=t, frame_idx=i, wrist_y=wy, nose_y=ny))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label != "valid_swing", f"撿球不應被標記為 valid_swing，實際為 {label}"


def test_negative_sample_5_setup_adjustment():
    """
    負樣本 5: Setup Adjustment (站姿腳步與握桿微調)
    特徵：球友在球位前調整握桿與雙腳站姿，動作緩慢微小 (速度極低、幅度極低)。
    判定標準：無法形成揮桿能量峰值，絕不標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames: list[FramePoseResult] = []
    for i in range(30):
        t = i * 66
        wy = 0.72 + 0.015 * math.cos(t * 0.005)
        frames.append(_make_frame(time_ms=t, frame_idx=i, wrist_y=wy))

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label != "valid_swing", f"調整站姿不應被標記為 valid_swing，實際為 {label}"


def test_negative_sample_6_stepping_out_of_frame():
    """
    負樣本 6: Stepping Out of Frame (球友走出鏡頭/畫面無人)
    特徵：所有關鍵點丟失，置信度為 0。
    判定標準：回傳空事件或 swing_candidate，絕不標記為 valid_swing！
    """
    sm = SwingPhaseStateMachine(model_version="pose-v2")
    frames = [_make_frame(time_ms=i * 66, frame_idx=i, visible=False) for i in range(20)]

    events, trace, label = sm.extract_events(frames, audio_transients_ms=[])
    assert label != "valid_swing", f"無人畫面不應被標記為 valid_swing，實際為 {label}"
    assert len(events) == 0 or label in ("swing_candidate", "practice_swing")
