"""
Golf Tracer Studio R4 — Unit & Integration Tests for Swing Tracer, Shot Tracer, High-Res Frame Reader & Reliability Gates.
驗證：
1. `BoundedFrameReader` 對遺失檔案、Proxy 路徑與低解析度 (<600p) 影片強制拋出 `SourceUnavailableError`。
2. `SwingTracerEngine`：
   - 當 `ClubheadDetector` 無權重時，退回 `shaft_geometry_estimated` 並誠實標記 `NEEDS_REVIEW` / `MODEL_UNAVAILABLE`，且 0 點使用手腕座標冒充桿頭 (`created_by != 'wrist'`, 距離手腕 >= 0.08)。
   - 當注入高覆蓋率 `ClubheadDetector` 時，可達 `AUTO_TRACED` 並正確切分 `backswing` / `downswing` / `follow_through`。
   - 非標準視角 (`OVERHEAD`) 回傳 `NOT_COMPARABLE`。
3. `ShotTracerEngine`：
   - 空揮 (`practice_swing`) 或僅有打擊墊靜止球 (`stationary_ball_only`) 時，嚴格回傳 `UNAVAILABLE` (0 假彈道點)。
   - 右飛與左飛雙向球路 (`handedness='right'` / `'left'`) 皆能透過雙向 ROI 正確擷取升空軌跡 (`AUTO_OBSERVED` / `AUTO_ASSISTED`)。
   - 保留 `raw_observation`，經卡爾曼平滑後標記 `position_role='display_smoothed'`。
"""

import math
from pathlib import Path
import subprocess

import cv2
import numpy as np
import pytest

from packages.analysis.tracer.clubhead_detector import (
    ClubDetectionResult,
    ClubheadDetector,
)
from packages.analysis.tracer.contracts import (
    PositionRole,
    ShotTrackMode,
    SwingTrackStatus,
    TrackSourceType,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader
from packages.analysis.tracer.roi_planner import plan_ball_flight_roi
from packages.analysis.tracer.segment_context import (
    SourceUnavailableError,
    resolve_segment_context,
)
from packages.analysis.tracer.shot_detector import (
    BallDetectionCandidate,
    ShotBallDetector,
)
from packages.analysis.tracer.shot_tracker import ShotTracerEngine
from packages.analysis.tracer.swing_tracker import SwingTracerEngine


def _create_test_video(
    out_path: Path,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    duration_frames: int = 36,
    draw_shaft: bool = True,
) -> Path:
    """產生合成測試高解析 H.264 影片（含球桿斜線供霍夫幾何端點測試）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps}/1",
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for idx in range(duration_frames):
            img = np.full((height, width, 3), (36, 48, 32), dtype=np.uint8)
            # 畫地面線與背景特徵點（供相機穩定度追蹤）
            cv2.line(img, (0, int(height * 0.82)), (width, int(height * 0.82)), (90, 120, 90), 2)
            for bx in range(40, width - 40, 160):
                cv2.circle(img, (bx, 60), 5, (180, 180, 180), -1)
                cv2.circle(img, (bx, height - 40), 5, (180, 180, 180), -1)

            if draw_shaft:
                # 手腕固定在 (0.48, 0.52)，桿頭沿圓弧揮動 (半徑約 0.22)
                wx, wy = int(width * 0.48), int(height * 0.52)
                angle = -0.8 + (idx / float(max(1, duration_frames - 1))) * 2.4
                hx = int(wx + math.cos(angle) * (width * 0.18))
                hy = int(wy + math.sin(angle) * (height * 0.22))
                cv2.line(img, (wx, wy), (hx, hy), (245, 245, 250), 4, cv2.LINE_AA)
                cv2.circle(img, (hx, hy), 9, (255, 255, 255), -1, cv2.LINE_AA)

            proc.stdin.write(img.tobytes())
    finally:
        proc.stdin.close()
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.read()
        proc.stderr.close()
    proc.wait(timeout=30)
    assert out_path.exists() and out_path.stat().st_size > 512
    return out_path


def test_bounded_frame_reader_rejects_missing_proxy_and_low_res(tmp_path: Path) -> None:
    # 1. 不存在的路徑
    with pytest.raises(SourceUnavailableError):
        BoundedFrameReader(source_path=tmp_path / "missing_original.mp4", require_high_res=True)

    # 2. 檔名帶有 _proxy 的低畫質代理影片
    proxy_file = _create_test_video(tmp_path / "video_123_proxy.mp4", width=1280, height=720, duration_frames=10)
    with pytest.raises(SourceUnavailableError, match="Proxy"):
        BoundedFrameReader(source_path=proxy_file, require_high_res=True)

    # 3. 短邊 < 600px 之低解析度影片
    low_res_file = _create_test_video(tmp_path / "low_res_clip.mp4", width=640, height=360, duration_frames=10)
    with pytest.raises(SourceUnavailableError, match="短邊解析度"):
        BoundedFrameReader(source_path=low_res_file, require_high_res=True)


def test_swing_tracer_without_club_weights_never_uses_wrist_as_head_and_marks_needs_review(
    tmp_path: Path,
) -> None:
    vid = _create_test_video(tmp_path / "hd_swing.mp4", width=1280, height=720, fps=30, duration_frames=36)
    keyframes = [
        {
            "time_ms": int(i * 33.3),
            "landmarks": {
                "right_wrist": {"x": 0.48, "y": 0.52},
                "left_wrist": {"x": 0.47, "y": 0.52},
            },
        }
        for i in range(36)
    ]
    events = [
        {"event_name": "address", "time_ms": 100},
        {"event_name": "top", "time_ms": 480},
        {"event_name": "impact_estimated", "time_ms": 760},
        {"event_name": "finish", "time_ms": 1050},
    ]

    ctx = resolve_segment_context(
        segment_id="seg_swing_fallback",
        video_id="vid_hd_1",
        source_storage_key=str(vid),
        source_video_path=vid,
        start_ms=60,
        end_ms=1100,
        events=events,
        pose_keyframes=keyframes,
        handedness="right",
        view_angle="DTL",
    )

    unavailable_detector = ClubheadDetector(model_path=tmp_path / "nonexistent_swingtrace.pt")
    assert unavailable_detector.is_available is False

    engine = SwingTracerEngine(club_detector=unavailable_detector)
    res = engine.trace_segment(ctx)

    # 缺專用桿頭模型時，狀態必須為 NEEDS_REVIEW 或 MODEL_UNAVAILABLE，絕不可偽稱 AUTO_TRACED
    assert res.status in (SwingTrackStatus.NEEDS_REVIEW, SwingTrackStatus.MODEL_UNAVAILABLE)
    assert res.quality_summary.end_to_end_eligible is False
    assert any("MODEL_UNAVAILABLE" in r for r in res.quality_summary.rejection_reasons)

    # 檢查所有產出點：0 點為 detector_observed，0 點由 wrist 產生，且每個點與手腕 (0.48, 0.52) 保持顯著距離
    for pt in res.points:
        assert pt.source_type in (
            TrackSourceType.SHAFT_GEOMETRY_ESTIMATED,
            TrackSourceType.INTERPOLATED,
        )
        assert pt.created_by != "wrist"
        dist_from_wrist = math.hypot(pt.x_norm - 0.48, pt.y_norm - 0.52)
        assert dist_from_wrist >= 0.08, f"點位過度接近手腕 ({dist_from_wrist:.3f})，疑似誤用手腕座標！"


def test_swing_tracer_with_mock_clubhead_detector_achieves_auto_traced_and_phase_split(
    tmp_path: Path,
) -> None:
    vid = _create_test_video(tmp_path / "hd_swing_mock.mp4", width=1280, height=720, fps=30, duration_frames=36)

    class _MockClubheadDetector(ClubheadDetector):
        def __init__(self) -> None:
            super().__init__(injected_model=object())
            self._step = 0

        def detect_in_roi(self, frame_bgr, roi_box, wrist_hint_norm=None):
            self._step += 1
            angle = -0.9 + (self._step / 36.0) * 2.5
            hx = float(np.clip(0.48 + 0.22 * math.cos(angle), 0.10, 0.90))
            hy = float(np.clip(0.52 + 0.24 * math.sin(angle), 0.10, 0.90))
            return ClubDetectionResult(
                head_x_norm=hx,
                head_y_norm=hy,
                head_bbox_norm=(hx - 0.02, hy - 0.02, 0.04, 0.04),
                confidence=0.88,
                uncertainty_px=3.2,
                model_id="swingtrace-yolo11m:mock",
            )

    ctx = resolve_segment_context(
        segment_id="seg_swing_auto",
        video_id="vid_hd_2",
        source_storage_key=str(vid),
        source_video_path=vid,
        start_ms=60,
        end_ms=1100,
        events=[
            {"event_name": "address", "time_ms": 80},
            {"event_name": "top", "time_ms": 480},
            {"event_name": "impact_estimated", "time_ms": 760},
            {"event_name": "finish", "time_ms": 1080},
        ],
        handedness="right",
        view_angle="DTL",
    )

    engine = SwingTracerEngine(club_detector=_MockClubheadDetector())
    res = engine.trace_segment(ctx)

    assert res.status == SwingTrackStatus.AUTO_TRACED
    assert res.quality_summary.end_to_end_eligible is True
    assert res.quality_summary.direct_observation_coverage >= 0.85

    phases = {p.phase for p in res.points}
    assert "backswing" in phases
    assert "downswing" in phases
    assert "follow_through" in phases

    # 檢查 raw_observation 與 display_smoothed 角色分離
    observed_pts = [p for p in res.points if p.source_type == TrackSourceType.DETECTOR_OBSERVED]
    assert len(observed_pts) >= 20
    assert all(p.raw_observation is not None for p in observed_pts)
    assert any(p.position_role == PositionRole.DISPLAY_SMOOTHED for p in observed_pts)


def test_swing_tracer_rejects_non_comparable_view(tmp_path: Path) -> None:
    vid = _create_test_video(tmp_path / "hd_overhead.mp4", width=1280, height=720, fps=30, duration_frames=15)
    ctx = resolve_segment_context(
        segment_id="seg_overhead",
        video_id="vid_overhead",
        source_storage_key=str(vid),
        source_video_path=vid,
        start_ms=0,
        end_ms=450,
        events=[],
        view_angle="OVERHEAD_DRONE",
    )
    res = SwingTracerEngine().trace_segment(ctx)
    assert res.status == SwingTrackStatus.NOT_COMPARABLE
    assert len(res.points) == 0


def test_shot_tracer_stationary_ball_and_practice_swing_rejection(tmp_path: Path) -> None:
    vid = _create_test_video(tmp_path / "hd_stationary.mp4", width=1280, height=720, fps=30, duration_frames=36)

    class _StationaryOnlyBallDetector(ShotBallDetector):
        def __init__(self) -> None:
            self.model_path = Path("mock")
            self.conf_threshold = 0.2
            self.device = "cpu"
            self.model = object()
            self.model_id = "golf_ball_yolov8n:mock"
            self.weights_sha256 = "mock_sha"
            self.status = "READY"

        def detect_candidates_in_roi(self, upright_bgr, roi):
            # 始終只回傳打擊墊上原地不動的球 (0.52, 0.78) 與高空固定路燈亮點 (0.25, 0.18)
            return [
                BallDetectionCandidate(
                    x_norm=0.52,
                    y_norm=0.78,
                    bbox_norm=(0.51, 0.77, 0.53, 0.79),
                    confidence=0.89,
                    uncertainty_px=2.0,
                    model_id=self.model_id,
                ),
                BallDetectionCandidate(
                    x_norm=0.25,
                    y_norm=0.18,
                    bbox_norm=(0.24, 0.17, 0.26, 0.19),
                    confidence=0.75,
                    uncertainty_px=3.0,
                    model_id=self.model_id,
                ),
            ]

    ctx = resolve_segment_context(
        segment_id="seg_practice",
        video_id="vid_practice",
        source_storage_key=str(vid),
        source_video_path=vid,
        start_ms=50,
        end_ms=1100,
        events=[{"event_name": "impact_estimated", "time_ms": 400}],
    )

    shot_res = ShotTracerEngine(ball_detector=_StationaryOnlyBallDetector()).trace_segment(ctx)
    assert shot_res.mode == ShotTrackMode.UNAVAILABLE
    assert len(shot_res.points) == 0
    assert "stationary_ball_only" in shot_res.quality_summary.rejection_reasons


@pytest.mark.parametrize("direction,handedness", [("rightward", "right"), ("leftward", "left")])
def test_shot_tracer_bidirectional_airborne_tracking(
    tmp_path: Path,
    direction: str,
    handedness: str,
) -> None:
    vid = _create_test_video(
        tmp_path / f"hd_shot_{direction}.mp4",
        width=1280,
        height=720,
        fps=30,
        duration_frames=36,
    )

    # 驗證雙向 ROI 規劃器同時向左右與上方擴展
    roi_mid = plan_ball_flight_roi(
        display_width=1280,
        display_height=720,
        progress=0.6,
        handedness=handedness,
        ball_origin_norm=(0.50, 0.76),
    )
    assert roi_mid.x1 < int(1280 * 0.30)
    assert roi_mid.x2 > int(1280 * 0.70)
    assert roi_mid.y1 < int(720 * 0.25)

    class _BidirectionalFlightDetector(ShotBallDetector):
        def __init__(self) -> None:
            self.model_path = Path("mock")
            self.conf_threshold = 0.2
            self.device = "cpu"
            self.model = object()
            self.model_id = "golf_ball_yolov8n:mock"
            self.weights_sha256 = "mock_sha"
            self.status = "READY"
            self._call_idx = 0

        def detect_candidates_in_roi(self, upright_bgr, roi):
            self._call_idx += 1
            # 前 6 次呼叫 (pre-impact) 為地面靜止球
            if self._call_idx <= 6:
                return [
                    BallDetectionCandidate(
                        x_norm=0.50,
                        y_norm=0.76,
                        bbox_norm=(0.49, 0.75, 0.51, 0.77),
                        confidence=0.91,
                        uncertainty_px=1.8,
                        model_id=self.model_id,
                    )
                ]
            step = self._call_idx - 6
            if step > 11:
                return []
            # 模擬第 6 步高速模糊漏檢 (前段 steps 1..5 與後段 steps 7..11 連續，中間第 6 幀由 Kalman 橋接)
            if step == 6:
                return []
            sign = 1.0 if direction == "rightward" else -1.0
            bx = float(np.clip(0.50 + sign * (0.028 * step), 0.05, 0.95))
            by = float(np.clip(0.76 - (0.052 * step) + (0.002 * step * step), 0.08, 0.90))
            return [
                BallDetectionCandidate(
                    x_norm=bx,
                    y_norm=by,
                    bbox_norm=(bx - 0.01, by - 0.01, bx + 0.01, by + 0.01),
                    confidence=0.84,
                    uncertainty_px=2.4,
                    model_id=self.model_id,
                )
            ]

        def track_optical_flow_step(self, prev_bgr, curr_bgr, prev_xy_norm, expected_v_norm=None):
            return None

    ctx = resolve_segment_context(
        segment_id=f"seg_shot_{direction}",
        video_id=f"vid_shot_{direction}",
        source_storage_key=str(vid),
        source_video_path=vid,
        start_ms=50,
        end_ms=1150,
        events=[{"event_name": "impact_estimated", "time_ms": 300}],
        handedness=handedness,
        view_angle="DTL",
    )

    shot_res = ShotTracerEngine(ball_detector=_BidirectionalFlightDetector()).trace_segment(ctx)
    assert shot_res.mode == ShotTrackMode.AUTO_OBSERVED
    assert shot_res.quality_summary.end_to_end_eligible is True
    assert shot_res.quality_summary.direct_observed_count >= 6
    assert shot_res.quality_summary.kalman_predicted_count >= 1

    # 確認卡爾曼橋接點被誠實標記為 kalman_predicted，而非混充 detector_observed
    kalman_pts = [p for p in shot_res.points if p.source_type == TrackSourceType.KALMAN_PREDICTED]
    assert len(kalman_pts) >= 1
    assert all(p.raw_observation is None for p in kalman_pts)
