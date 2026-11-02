"""
Golf Swing Lab R4 — Parity Verifier Sabotage & Negative Tests (`test_parity_sabotage_and_guards.py`).
依據《R4 PR #4 第二輪獨立審查指令》P0-B 要求：
對 verify_actual_visual_pixel_parity 執行破壞性負面測試 (Sabotage Fixtures)，
強制證明驗收工具本身具備敏銳且可靠的抓錯能力 (Fail-Closed)，絕不允許在異常狀態下假冒 PASS。
"""

import math
import numpy as np
from pathlib import Path
import pytest

from packages.analysis.tracer.compositor import verify_actual_visual_pixel_parity
from packages.analysis.tracer.contracts import CanonicalTrackPoint, TrackSourceType, TrackType
from packages.analysis.tracer.transforms import OutputLayout


@pytest.fixture
def base_test_environment():
    """建立可重現之合成測試畫布、軌跡點與乾淨原片背景。"""
    w, h = 1080, 1920
    from packages.analysis.tracer.transforms import compute_output_layout
    layout = compute_output_layout(
        display_width=w,
        display_height=h,
        target_aspect="original",
    )
    # 乾淨背景：灰黑練習場背景
    raw_bgr = np.full((h, w, 3), 40, dtype=np.uint8)

    # 建立 10 個測試點 (從 y=1500 向上弧線升至 y=600)
    points: list[CanonicalTrackPoint] = []
    for i in range(10):
        t = i / 9.0
        x = 0.50 + 0.05 * math.sin(t * math.pi)
        y = 0.80 - 0.50 * t
        points.append(
            CanonicalTrackPoint(
                track_id="test_ball",
                track_type=TrackType.BALL,
                segment_id="seg_test",
                source_video_id="vid_test",
                source_pts_us=3_800_000 + i * 33_333,
                source_frame_index=100 + i,
                x_norm=x,
                y_norm=y,
                confidence=0.95,
                source_type=TrackSourceType.INTERPOLATED,
            )
        )

    # 繪製基準 Canvas RGBA (亮青色 #00E5FF，B=255, G=229, R=0, A=255)
    canvas_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for p in points:
        ix, iy = int(round(p.x_norm * w)), int(round(p.y_norm * h))
        cv2_circle_rgba(canvas_rgba, (ix, iy), radius=4, color_bgr=(255, 229, 0), alpha=255)

    # 繪製基準 MP4 BGR (同樣亮青色疊加於 raw_bgr)
    mp4_bgr = raw_bgr.copy()
    for p in points:
        ix, iy = int(round(p.x_norm * w)), int(round(p.y_norm * h))
        cv2_circle_bgr(mp4_bgr, (ix, iy), radius=4, color_bgr=(255, 229, 0))

    return {
        "layout": layout,
        "raw_bgr": raw_bgr,
        "points": points,
        "canvas_rgba": canvas_rgba,
        "mp4_bgr": mp4_bgr,
        "pts_us": points[-1].source_pts_us,
    }


def cv2_circle_rgba(img: np.ndarray, pt: tuple[int, int], radius: int, color_bgr: tuple[int, int, int], alpha: int):
    import cv2
    overlay = img.copy()
    b, g, r = color_bgr
    cv2.circle(overlay, pt, radius, (b, g, r, alpha), -1)
    img[:] = overlay


def cv2_circle_bgr(img: np.ndarray, pt: tuple[int, int], radius: int, color_bgr: tuple[int, int, int]):
    import cv2
    cv2.circle(img, pt, radius, color_bgr, -1)


def test_parity_fails_on_5px_translation(base_test_environment):
    """破壞測試 1：故意將 MP4 影像平移 5px，斷言 verifier 必 FAIL 且抓出 normal_error > 4px。"""
    import cv2
    env = base_test_environment
    h, w = env["raw_bgr"].shape[:2]

    # 故意將 MP4 畫面右移 5px (X 方向平移即是法向偏移)
    M = np.float32([[1, 0, 5], [0, 1, 0]])
    sabotaged_mp4 = cv2.warpAffine(env["mp4_bgr"], M, (w, h))

    res = verify_actual_visual_pixel_parity(
        pts_us=env["pts_us"],
        export_frame_index=10,
        export_frame_pts_us=env["pts_us"],
        fps=30,
        canvas_rgba=env["canvas_rgba"],
        exported_mp4_bgr=sabotaged_mp4,
        raw_upright_bgr=env["raw_bgr"],
        layout=env["layout"],
        active_points=env["points"],
    )

    assert not res.passed, f"平移 5px 應判定為 FAIL，但回傳 passed={res.passed}"
    assert res.normal_error_px > 2.0, f"normal_error_px 應 > 2.0px 門檻，實測: {res.normal_error_px}"
    assert any("中心線法向偏移超出門檻" in r for r in (res.failure_reasons or []))


def test_parity_fails_on_color_inversion(base_test_environment):
    """破壞測試 2：故意將 MP4 顏色由青色置換為純紅色 (顛倒色相)，斷言 phase_color_verified 必 FAIL。"""
    env = base_test_environment
    sabotaged_mp4 = env["raw_bgr"].copy()
    # 故意繪製紅色軌跡 (B=0, G=0, R=255)
    for p in env["points"]:
        ix, iy = int(round(p.x_norm * 1080)), int(round(p.y_norm * 1920))
        cv2_circle_bgr(sabotaged_mp4, (ix, iy), radius=4, color_bgr=(0, 0, 255))

    res = verify_actual_visual_pixel_parity(
        pts_us=env["pts_us"],
        export_frame_index=10,
        export_frame_pts_us=env["pts_us"],
        fps=30,
        canvas_rgba=env["canvas_rgba"],  # 青色
        exported_mp4_bgr=sabotaged_mp4,  # 紅色
        raw_upright_bgr=env["raw_bgr"],
        layout=env["layout"],
        active_points=env["points"],
    )

    assert not res.passed, "顏色顛倒應判定為 FAIL"
    assert not res.phase_color_verified, f"phase_color_verified 應為 False，實測: {res.phase_color_verified}"
    assert any("顏色一致性未達標" in r for r in (res.failure_reasons or []))


def test_parity_fails_on_missing_track_zero_matches(base_test_environment):
    """破壞測試 3：MP4 完全未渲染任何軌跡 (0 匹配點)，斷言 verifier 必 FAIL 且給予 999.0 懲罰。"""
    env = base_test_environment
    # MP4 僅為純原片，完全無軌跡線條
    sabotaged_mp4 = env["raw_bgr"].copy()

    res = verify_actual_visual_pixel_parity(
        pts_us=env["pts_us"],
        export_frame_index=10,
        export_frame_pts_us=env["pts_us"],
        fps=30,
        canvas_rgba=env["canvas_rgba"],
        exported_mp4_bgr=sabotaged_mp4,
        raw_upright_bgr=env["raw_bgr"],
        layout=env["layout"],
        active_points=env["points"],
    )

    assert not res.passed, "零匹配軌跡應判定為 FAIL"
    assert res.matched_point_count == 0
    assert res.max_centerline_offset_px_1080p == 999.0, "零匹配時絕不允許給出 0.0px 偽通過"
    assert any("有效匹配點數不足" in r for r in (res.failure_reasons or []))


def test_parity_fails_on_solid_artistic_line(base_test_environment):
    """破壞測試 4：要求藝術虛線，但 MP4 卻畫成連續實線 (無 Gap 谷底)，斷言 artistic_dashed_verified 必 FAIL。"""
    import cv2
    env = base_test_environment
    h, w = env["raw_bgr"].shape[:2]

    # 將測試點標記為 artistic_only
    art_points = [
        p.model_copy(update={"source_type": TrackSourceType.ARTISTIC_ONLY})
        for p in env["points"]
    ]

    # Canvas 上正確畫虛線 (間隔繪製)
    c_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for idx, p in enumerate(art_points):
        if idx % 2 == 0:
            ix, iy = int(round(p.x_norm * w)), int(round(p.y_norm * h))
            cv2.circle(c_rgba, (ix, iy), 4, (255, 255, 255, 255), -1)

    # 破壞：MP4 故意畫成一條連續無間隔的粗實線
    m_bgr = env["raw_bgr"].copy()
    p0 = (int(round(art_points[0].x_norm * w)), int(round(art_points[0].y_norm * h)))
    p1 = (int(round(art_points[-1].x_norm * w)), int(round(art_points[-1].y_norm * h)))
    cv2.line(m_bgr, p0, p1, (255, 255, 255), 6)

    res = verify_actual_visual_pixel_parity(
        pts_us=env["pts_us"],
        export_frame_index=10,
        export_frame_pts_us=env["pts_us"],
        fps=30,
        canvas_rgba=c_rgba,
        exported_mp4_bgr=m_bgr,
        raw_upright_bgr=env["raw_bgr"],
        layout=env["layout"],
        active_points=art_points,
        expect_artistic_dashed=True,
    )

    assert not res.passed, "實線冒充虛線應判定為 FAIL"
    assert not res.artistic_dashed_verified, "artistic_dashed_verified 應為 False"


def test_audio_preserve_strict_fail_closed_on_mux_error(tmp_path):
    """破壞測試 5 (P1-A)：原片有音訊且 audio_mode=preserve 時，若 FFmpeg mux 失敗，必須嚴格拋出 RuntimeError，絕不靜默退回無聲影片。"""
    from unittest.mock import patch
    from packages.analysis.tracer.studio_exporter import ClipExportSpec, export_single_tracer_clip
    from packages.analysis.tracer.contracts import TrackQualitySummary, TrackType
    from packages.analysis.tracer.fx_schema import get_preset_recipe, AudioMode
    from packages.analysis.tracer.transforms import FrameGeometry

    recipe = get_preset_recipe("studio_neon")
    recipe.export_format.audio_mode = AudioMode("preserve")

    spec = ClipExportSpec(
        project_id="test_proj",
        segment_id="test_seg",
        source_video_id="test_vid",
        source_video_path=Path("/tmp/nonexistent_video.mov"),
        source_video_sha256="dummy_sha",
        geometry=FrameGeometry(
            coded_width=1080,
            coded_height=1920,
            rotation=0,
        ),
        start_pts_us=0,
        end_pts_us=1_000_000,
        top_pts_us=300_000,
        impact_pts_us=500_000,
        swing_points=[],
        shot_points=[],
        swing_quality=TrackQualitySummary(track_type=TrackType.CLUB_HEAD, status="UNAVAILABLE"),
        shot_quality=TrackQualitySummary(track_type=TrackType.BALL, status="UNAVAILABLE"),
        recipe=recipe,
        has_audio_stream=True,
    )

    out_mp4 = tmp_path / "out.mp4"
    out_sidecar = tmp_path / "out.json"

    # 模擬影片寫入成功但 FFmpeg 音軌 mux 失敗
    dummy_proc = patch("subprocess.Popen").start()
    mock_p = dummy_proc.return_value
    mock_p.returncode = 0
    mock_p.stderr.read.return_value = b""
    mock_p.wait.return_value = 0

    # 建立 video_only 虛擬檔案
    def fake_render(*args, **kwargs):
        # 觸發 tempdir 下 video_only.mp4
        pass

    with patch("packages.analysis.tracer.studio_exporter._check_source_has_audio", return_value=True):
        with patch("subprocess.run") as mock_run:
            from subprocess import CompletedProcess
            from packages.analysis.tracer.frame_reader import DecodedUprightFrame
            mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="Simulated FFmpeg audio mux error")
            with patch("packages.analysis.tracer.studio_exporter.BoundedFrameReader") as mock_reader_cls:
                mock_reader = mock_reader_cls.return_value
                fake_frame = DecodedUprightFrame(
                    source_frame_index=0,
                    source_pts_us=0,
                    frame_bgr=np.zeros((1920, 1080, 3), dtype=np.uint8),
                    geometry=spec.geometry,
                    frame_sha256="fake_sha",
                )
                mock_reader.iter_frames.return_value = [fake_frame]
                # 建立虛擬 video_only_mp4
                with patch("pathlib.Path.exists", return_value=True):
                    with pytest.raises(RuntimeError, match="音訊保留模式.*FFmpeg 音軌合成失敗"):
                        export_single_tracer_clip(spec=spec, output_mp4_path=out_mp4, sidecar_json_path=out_sidecar)
    patch.stopall()


def test_verify_r4_webkit_cli_sabotage_exit_semantics(monkeypatch):
    """P1-A: 驗證破壞模式下的 CLI 返回碼語意分離——當驗收檢測出 FAIL 時，CLI 自身必須 exit 1，外部 runner 攔截 exit 1 後判定通過。"""
    import sys
    from unittest.mock import patch
    import scripts.verify_r4_webkit as v_webkit

    # 模擬 run_verification 在 sabotage 模式下檢測出 FAIL
    fake_fail_summary = {
        "overall_status": "FAIL",
        "step1_status": "PASS",
        "step2_status": "PASS",
        "step3_status": "FAIL",
        "step4_status": "PASS",
    }

    with patch.object(v_webkit, "run_verification", return_value=fake_fail_summary):
        monkeypatch.setattr(sys, "argv", ["verify_r4_webkit.py", "--sabotage", "5px"])
        with pytest.raises(SystemExit) as excinfo:
            v_webkit.main()
        # 核心斷言：CLI 本身必須 exit 1 (Fail-Closed 語意)，而非 exit 0
        assert excinfo.value.code == 1, f"Expected exit code 1 under sabotage FAIL, got {excinfo.value.code}"

