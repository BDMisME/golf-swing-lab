"""
Golf Tracer Studio R4 — Unit Tests for Contracts, Truthfulness Invariants, Coordinate Math & Media Clock.
"""

import numpy as np
import pytest

from packages.analysis.tracer.compositor import verify_preview_export_parity
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    TrackSourceType,
    TrackType,
)
from packages.analysis.tracer.edit_merge import (
    ManualPointEditOp,
    StudioAnchorOverrides,
    apply_manual_edits_copy_on_write,
)
from packages.analysis.tracer.fx_schema import BUILTIN_RENDER_PRESETS, get_preset_recipe
from packages.analysis.tracer.interpolation import (
    catmull_rom_subdivide,
    generate_artistic_ballistic_extension,
    interpolate_pts_gap,
)
from packages.analysis.tracer.media_clock import (
    build_rational_cfr_timeline,
    generate_cfr_output_pts_us,
)
from packages.analysis.tracer.transforms import (
    FrameGeometry,
    coded_px_to_upright_norm,
    compute_output_layout,
    project_upright_norm_to_output_px,
    rotate_coded_frame_to_upright,
    scale_width_at_1080,
    unproject_output_px_to_upright_norm,
    upright_norm_to_coded_px,
)


def test_truthfulness_invariants_reject_wrist_and_unverified_observed() -> None:
    # 1. 禁止將手腕座標作為桿頭點 (wrist-as-head forbidden)
    with pytest.raises(ValueError, match="wrist-as-head forbidden"):
        CanonicalTrackPoint(
            track_id="t1",
            track_type=TrackType.CLUB_HEAD,
            segment_id="seg1",
            source_video_id="vid1",
            source_pts_us=100_000,
            source_frame_index=6,
            x_norm=0.45,
            y_norm=0.55,
            confidence=0.9,
            source_type=TrackSourceType.SHAFT_GEOMETRY_ESTIMATED,
            created_by="wrist",
        )

    # 2. detector_observed 必須包含 raw_observation
    with pytest.raises(ValueError, match="raw_observation"):
        CanonicalTrackPoint(
            track_id="t1",
            track_type=TrackType.BALL,
            segment_id="seg1",
            source_video_id="vid1",
            source_pts_us=100_000,
            source_frame_index=6,
            x_norm=0.45,
            y_norm=0.55,
            confidence=0.9,
            source_type=TrackSourceType.DETECTOR_OBSERVED,
            raw_observation=None,
            created_by="model",
        )

    # 3. 平滑後座標與 raw_observation 不同時，position_role 必須為 display_smoothed
    with pytest.raises(ValueError, match="display_smoothed"):
        CanonicalTrackPoint(
            track_id="t1",
            track_type=TrackType.BALL,
            segment_id="seg1",
            source_video_id="vid1",
            source_pts_us=100_000,
            source_frame_index=6,
            x_norm=0.465,
            y_norm=0.540,
            confidence=0.9,
            source_type=TrackSourceType.DETECTOR_OBSERVED,
            position_role=PositionRole.RAW_OBSERVATION,
            raw_observation={"x_norm": 0.450, "y_norm": 0.550, "bbox": [0.44, 0.54, 0.46, 0.56]},
            created_by="model",
        )

    # 正確標記 display_smoothed 應通過驗證
    valid_pt = CanonicalTrackPoint(
        track_id="t1",
        track_type=TrackType.BALL,
        segment_id="seg1",
        source_video_id="vid1",
        source_pts_us=100_000,
        source_frame_index=6,
        x_norm=0.465,
        y_norm=0.540,
        confidence=0.9,
        source_type=TrackSourceType.DETECTOR_OBSERVED,
        position_role=PositionRole.DISPLAY_SMOOTHED,
        raw_observation={"x_norm": 0.450, "y_norm": 0.550, "bbox": [0.44, 0.54, 0.46, 0.56]},
        created_by="model",
    )
    assert valid_pt.position_role == PositionRole.DISPLAY_SMOOTHED


@pytest.mark.parametrize("rot_deg", [0, 90, 180, 270])
def test_rotation_and_coordinate_roundtrip(rot_deg: int) -> None:
    geom = FrameGeometry(coded_width=1920, coded_height=1080, rotation_deg=rot_deg)
    if rot_deg in (90, 270):
        assert geom.upright_width == 1080
        assert geom.upright_height == 1920
    else:
        assert geom.upright_width == 1920
        assert geom.upright_height == 1080

    # 測試 coded <-> upright_norm 雙向可逆
    for cx, cy in [(120.0, 240.0), (960.0, 540.0), (1800.0, 990.0)]:
        ux, uy = coded_px_to_upright_norm(cx, cy, geom)
        assert 0.0 <= ux <= 1.0
        assert 0.0 <= uy <= 1.0
        rcx, rcy = upright_norm_to_coded_px(ux, uy, geom)
        assert abs(rcx - cx) < 1e-4
        assert abs(rcy - cy) < 1e-4

    # 測試影像矩陣旋轉後尺寸一致
    dummy_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
    upright_bgr = rotate_coded_frame_to_upright(dummy_bgr, rot_deg)
    assert upright_bgr.shape[1] == geom.upright_width
    assert upright_bgr.shape[0] == geom.upright_height


@pytest.mark.parametrize("aspect", ["original", "16:9", "9:16"])
@pytest.mark.parametrize("fps", [30, 60])
def test_output_layout_and_preview_export_parity(aspect: str, fps: int) -> None:
    geom = FrameGeometry(coded_width=1920, coded_height=1080, rotation_deg=270)
    layout = compute_output_layout(geom, target_aspect=aspect)

    # 測試投影與反投影
    for xn, yn in [(0.15, 0.82), (0.50, 0.50), (0.88, 0.18)]:
        px, py = project_upright_norm_to_output_px(xn, yn, layout)
        rxn, ryn = unproject_output_px_to_upright_norm(px, py, layout)
        assert abs(rxn - xn) < 1e-6
        assert abs(ryn - yn) < 1e-6

    assert scale_width_at_1080(layout, 6.0) == 6

    # 測試 CFR 時間格點與 Parity 門檻 (<= 2.0 px, <= 1.0 frame)
    cfr_grid = generate_cfr_output_pts_us(1_000_000, 2_500_000, target_fps=fps)
    sample_points = [
        CanonicalTrackPoint(
            track_id="trk_1",
            track_type=TrackType.BALL,
            segment_id="seg_1",
            source_video_id="vid_1",
            source_pts_us=1_000_000 + i * 16_667,
            source_frame_index=60 + i,
            x_norm=0.45 + i * 0.02,
            y_norm=0.75 - i * 0.04,
            confidence=0.85,
            source_type=TrackSourceType.DETECTOR_OBSERVED,
            position_role=PositionRole.RAW_OBSERVATION,
            raw_observation={
                "x_norm": 0.45 + i * 0.02,
                "y_norm": 0.75 - i * 0.04,
                "bbox": [0.44, 0.74, 0.46, 0.76],
            },
            created_by="model",
        )
        for i in range(10)
    ]

    report = verify_preview_export_parity(
        points=sample_points,
        layout=layout,
        fps=fps,
        export_output_pts_us=cfr_grid,
    )
    assert report.coordinate_parity_passed is True
    assert report.pts_parity_passed is True
    assert report.max_coordinate_error_px <= 2.0
    assert report.max_frame_delta_frames <= 1.0


def test_copy_on_write_manual_edit_and_artistic_extension() -> None:
    base_pts = [
        CanonicalTrackPoint(
            track_id="ball_1",
            track_type=TrackType.BALL,
            segment_id="seg_1",
            source_video_id="vid_1",
            source_pts_us=1_000_000,
            source_frame_index=60,
            x_norm=0.50,
            y_norm=0.78,
            confidence=0.90,
            source_type=TrackSourceType.DETECTOR_OBSERVED,
            position_role=PositionRole.RAW_OBSERVATION,
            raw_observation={"x_norm": 0.50, "y_norm": 0.78, "bbox": [0.49, 0.77, 0.51, 0.79]},
            created_by="model",
            revision=1,
        ),
        CanonicalTrackPoint(
            track_id="ball_1",
            track_type=TrackType.BALL,
            segment_id="seg_1",
            source_video_id="vid_1",
            source_pts_us=1_050_000,
            source_frame_index=63,
            x_norm=0.53,
            y_norm=0.62,
            confidence=0.88,
            source_type=TrackSourceType.DETECTOR_OBSERVED,
            position_role=PositionRole.RAW_OBSERVATION,
            raw_observation={"x_norm": 0.53, "y_norm": 0.62, "bbox": [0.52, 0.61, 0.54, 0.63]},
            created_by="model",
            revision=1,
        ),
    ]

    edits = [
        ManualPointEditOp(
            op="add",
            source_pts_us=1_100_000,
            source_frame_index=66,
            x_norm=0.56,
            y_norm=0.45,
            point_role="manual_anchor",
        )
    ]
    anchors = StudioAnchorOverrides(
        landing_pts_us=1_300_000,
        apex_xy_norm=(0.58, 0.25),
        landing_xy_norm=(0.64, 0.52),
        artistic_extension_enabled=True,
        recompute_between_manual_anchors=True,
    )

    rev2_pts = apply_manual_edits_copy_on_write(
        base_points=base_pts,
        track_type=TrackType.BALL,
        track_id="ball_1",
        segment_id="seg_1",
        source_video_id="vid_1",
        new_revision=2,
        edits=edits,
        anchors=anchors,
    )

    # 原始 base_pts 絕不可被變更
    assert len(base_pts) == 2
    assert all(p.revision == 1 for p in base_pts)

    # 新修訂版包含手動錨點、局部內插點與標記為 artistic_only 之延伸點
    assert all(p.revision == 2 for p in rev2_pts)
    assert any(p.source_type == TrackSourceType.MANUALLY_ANNOTATED for p in rev2_pts)
    assert any(p.source_type == TrackSourceType.INTERPOLATED for p in rev2_pts)
    artistic_pts = [p for p in rev2_pts if p.source_type == TrackSourceType.ARTISTIC_ONLY]
    assert len(artistic_pts) > 0
    assert all(p.occlusion_state == OcclusionState.UNOBSERVABLE for p in artistic_pts)


def test_builtin_presets_and_cfr_clock() -> None:
    assert len(BUILTIN_RENDER_PRESETS) == 6
    for pid in ["clean_analysis", "studio_neon", "minimal_white", "power_beam", "rainbow_arc", "no_fx"]:
        rec = get_preset_recipe(pid)
        assert rec.preset_id == pid

    tl = build_rational_cfr_timeline(duration_ms=1000, fps_num=60000, fps_den=1001)
    assert len(tl.entries) >= 59
    assert len(catmull_rom_subdivide([(0.1, 0.8), (0.3, 0.5), (0.5, 0.2)], 4)) > 3
    assert len(
        interpolate_pts_gap(
            start_pt=CanonicalTrackPoint(
                track_id="c1",
                track_type=TrackType.CLUB_HEAD,
                segment_id="s1",
                source_video_id="v1",
                source_pts_us=100_000,
                source_frame_index=6,
                x_norm=0.4,
                y_norm=0.7,
                confidence=0.8,
                source_type=TrackSourceType.MANUALLY_ANNOTATED,
                position_role=PositionRole.MANUAL_ANCHOR,
                created_by="user",
            ),
            end_pt=CanonicalTrackPoint(
                track_id="c1",
                track_type=TrackType.CLUB_HEAD,
                segment_id="s1",
                source_video_id="v1",
                source_pts_us=150_000,
                source_frame_index=9,
                x_norm=0.5,
                y_norm=0.5,
                confidence=0.8,
                source_type=TrackSourceType.MANUALLY_ANNOTATED,
                position_role=PositionRole.MANUAL_ANCHOR,
                created_by="user",
            ),
            intermediate_frames=[(116_667, 7, "downswing"), (133_333, 8, "downswing")],
        )
    ) == 2
    assert len(generate_artistic_ballistic_extension([], None, (0.5, 0.5), [])) == 0
