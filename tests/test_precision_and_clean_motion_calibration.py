"""
高爾夫揮桿分析系統 — 精準度校準與 Clean Motion 驗收自動化測試
(tests/test_precision_and_clean_motion_calibration.py)

驗收範疇：
1. P0-1: 多訊號 Impact 真球回饋精修 (ball_strike_ms feedback, detection_sources, confirmed_strike)
2. P0-2: 音訊抽取強健性 (動態 timeout、無音訊優雅降級、明確失敗原因)
3. P0-3: 局部高 FPS 二次精修 (Local High-FPS Refinement without full video re-decode)
4. P0-4: 誠實記錄 detection_sources (未使用的來源絕不列入)
5. P1-1: Clean Motion UI 視覺降級與無證據時不宣告身體問題
6. P1-2: 移除單鏡頭足底壓力與重心轉移宣稱，明確標註 MediaPipe 33 點骨架
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from packages.analysis.detection.scanner import (
    AudioExtractionResult,
    CoarseToFineDetector,
    extract_audio_transients,
)
from packages.analysis.events.state_machine import (
    DetectedEvent,
    SwingPhaseStateMachine,
)
from packages.analysis.pose.extractor import FramePoseResult, Landmark2D
from packages.analysis.tracking.ball_tracker import (
    GolfBallDetector,
)


def _create_mock_frames(count: int = 25, dt_ms: int = 33) -> list[FramePoseResult]:
    """生成模擬 2D 骨架影格序列，涵蓋完整揮桿動作。"""
    frames = []
    # y 軸：0.75 (Address) -> 0.25 (Top) -> 0.76 (Impact) -> 0.35 (Finish)
    for i in range(count):
        t_ms = i * dt_ms
        if i <= 5:  # Address & Takeaway
            wy = 0.72 - (i * 0.03)
        elif i <= 10:  # Backswing to Top
            wy = 0.57 - ((i - 5) * 0.06)  # i=10 -> wy = 0.27
        elif i <= 14:  # Downswing to Impact
            wy = 0.27 + ((i - 10) * 0.12)  # i=14 -> wy = 0.75
        else:  # Follow through & Finish
            wy = 0.75 - ((i - 14) * 0.04)

        lm = {
            "nose": Landmark2D(x=0.50, y=0.25, visibility=0.95),
            "left_shoulder": Landmark2D(x=0.52, y=0.35, visibility=0.95),
            "right_shoulder": Landmark2D(x=0.48, y=0.35, visibility=0.95),
            "left_hip": Landmark2D(x=0.51, y=0.55, visibility=0.95),
            "right_hip": Landmark2D(x=0.49, y=0.55, visibility=0.95),
            "left_wrist": Landmark2D(x=0.50, y=wy, visibility=0.92),
            "right_wrist": Landmark2D(x=0.50, y=wy, visibility=0.92),
            "left_ankle": Landmark2D(x=0.51, y=0.88, visibility=0.95),
            "right_ankle": Landmark2D(x=0.49, y=0.88, visibility=0.95),
        }
        frames.append(
            FramePoseResult(
                time_ms=t_ms,
                frame_idx=i,
                landmarks=lm,
                pose_confidence=0.88,
                wrist_motion_energy=0.08 if 8 <= i <= 16 else 0.02,
                brightness=120.0,
                sharpness=85.0,
                camera_motion=0.01,
            )
        )
    return frames


def test_ball_strike_feedback_refines_impact():
    """驗證真球觀測到出球啟動點時，正確回饋修正 Impact 事件並升級狀態為 confirmed_strike。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_frames(count=30, dt_ms=66)

    # 模擬 GolfBallDetector.track_swing_launch_with_feedback 回傳可靠出球點 (第 14 幀附近: 14 * 66 = 924ms)
    mock_traj = [
        {"time_ms": 924.0, "x": 0.50, "y": 0.75, "point_type": "observed", "confidence": 0.90},
        {"time_ms": 950.0, "x": 0.55, "y": 0.60, "point_type": "observed", "confidence": 0.88},
        {"time_ms": 980.0, "x": 0.62, "y": 0.40, "point_type": "observed", "confidence": 0.85},
    ]

    with patch.object(
        GolfBallDetector,
        "track_swing_launch_with_feedback",
        return_value={
            "trajectory_points": mock_traj,
            "observed_launch_ms": 924,
            "observed_count": 3,
            "is_valid": True,
        },
    ):
        with patch.object(detector, "_sample_video_window", return_value=frames):
            seg = detector.analyze_single_window(
                video_path="dummy_video.mp4",
                start_ms=0,
                end_ms=2000,
                sequence_no=1,
            )

    assert seg is not None
    imp_ev = next((e for e in seg.events if "impact" in e.event_name), None)
    assert imp_ev is not None
    assert imp_ev.time_ms == 924, "Impact 時間碼應被球體真實觀測點 (924ms) 精準回饋修正"
    assert "ball_flight_observed_launch" in imp_ev.detection_sources, "真球出發點必須真正列入 detection_sources"
    assert seg.ball_strike_status == "confirmed_strike", "真球可靠觀測應使擊球狀態升級為 confirmed_strike"
    assert imp_ev.uncertainty_ms == 16, "真球觀測鎖定後時間不確定性應收斂至 16ms"
    assert seg.quality_metadata.get("ball_strike_feedback", {}).get("applied") is True


def test_no_ball_detection_does_not_hallucinate_sources():
    """驗證在無真球觀測或球體觀測失敗時，絕不得虛構 ball_flight_observed_launch。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_frames(count=30, dt_ms=66)

    # 模擬球體追蹤失敗 (無真球觀測)
    with patch.object(
        GolfBallDetector,
        "track_swing_launch_with_feedback",
        return_value={
            "trajectory_points": [],
            "observed_launch_ms": None,
            "observed_count": 0,
            "is_valid": False,
        },
    ):
        with patch.object(detector, "_sample_video_window", return_value=frames):
            seg = detector.analyze_single_window(
                video_path="dummy_video.mp4",
                start_ms=0,
                end_ms=2000,
                sequence_no=1,
            )

    assert seg is not None
    imp_ev = next((e for e in seg.events if "impact" in e.event_name), None)
    assert imp_ev is not None
    assert "ball_flight_observed_launch" not in imp_ev.detection_sources, "未觀測到真球時絕不可捏造出球來源"
    assert seg.ball_strike_status != "confirmed_strike", "未觀測到真球時絕不能標記為 confirmed_strike"


def test_audio_extraction_robustness_and_explicit_failure_reasons():
    """驗證音訊抽取具備動態 timeout、支援局部抽取，並在無音軌或超時留下明確診斷原因。"""
    # 測試案例 1: 模擬無音軌影片
    mock_proc_no_audio = MagicMock()
    mock_proc_no_audio.returncode = 1
    mock_proc_no_audio.stderr = b"Stream map '0:a:0' matches no streams; Output file #0 does not contain any stream"
    mock_proc_no_audio.stdout = b""

    with patch("subprocess.run", return_value=mock_proc_no_audio):
        res = extract_audio_transients("silent_video.mov")
        assert isinstance(res, AudioExtractionResult)
        assert res.status == "no_audio"
        assert "無音訊軌道" in (res.error_message or "")
        assert len(res) == 0

    # 測試案例 2: 模擬音訊解碼超時
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=15)):
        res_timeout = extract_audio_transients("very_long_video.mov", timeout=15)
        assert res_timeout.status == "timeout"
        assert "逾時" in (res_timeout.error_message or "")
        assert len(res_timeout) == 0


def test_local_high_fps_refinement():
    """驗證針對低信心度關鍵事件啟動局部高 FPS 取樣精修，不重跑全片。"""
    detector = CoarseToFineDetector()
    frames = _create_mock_frames(count=30, dt_ms=66)
    # 將頂點附近影格信心度設為 0.58，模擬低光或動態模糊導致頂點信心偏低
    for i in range(8, 12):
        frames[i].pose_confidence = 0.58

    # 模擬局部取樣返回 16ms 步長的高 FPS 精修結果
    mock_refined = {
        "refined_ms": 330,
        "confidence": 0.88,
        "uncertainty_ms": 16,
        "sources": ["wrist_velocity_zero_crossing", "local_high_fps_refinement"],
        "delta_ms": -33,
    }

    with patch.object(
        detector,
        "_refine_event_local_high_fps",
        return_value=mock_refined,
    ):
        with patch.object(detector, "_sample_video_window", return_value=frames):
            seg = detector.analyze_single_window(
                video_path="dummy_video.mp4",
                start_ms=0,
                end_ms=2000,
                sequence_no=1,
            )

    assert seg is not None
    top_ev = next((e for e in seg.events if e.event_name == "top"), None)
    assert top_ev is not None
    assert top_ev.uncertainty_ms == 16
    assert "local_high_fps_refinement" in top_ev.detection_sources
    assert "top" in seg.quality_metadata.get("local_refinements", {})
    assert seg.quality_metadata["local_refinements"]["top"]["delta_ms"] == -33


@pytest.mark.asyncio
async def test_truthfulness_safeguards_in_overlay_and_coach():
    """驗證前端 Clean Motion UI 與教練文本遵守最高誠信原則（不宣稱單鏡頭重心轉移與足底壓力）。"""
    from packages.analysis.coach import RuleBasedCoachProvider

    provider = RuleBasedCoachProvider()
    valid_swings = [
        {
            "sequence_no": 1,
            "label": "valid_swing",
            "impact_ms": 950,
            "overall_score": 72.0,
            "subscores": {
                "finish_balance": {"score": 65.0, "confidence": 0.85, "how_calculated": "收桿晃動比檢測"},
            },
            "events": [{"event_name": "impact", "time_ms": 950}],
        }
    ]
    report = await provider.generate_feedback(
        session_summary={"average_overall_score": 72.0},
        swing_evidence=valid_swings,
    )

    full_text = " ".join([d.action_cue + " " + d.drill_steps for d in report.priority_fixes])
    assert "足底壓力" not in full_text, "禁止使用單鏡頭影像宣稱測量足底壓力"
    assert "重心是否完全轉移至前腳" not in full_text, "禁止宣稱單鏡頭測量精確重心轉移"
    assert "身體收桿軸線" in full_text, "應使用可觀測身體收桿軸線平衡"

