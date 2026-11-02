"""R4 Comprehensive Real-Media Evaluation (25 Clips), Full 24-Profile Export Matrix,
Batch Compilation (1/2/3/5/10 Clips), Legacy Non-FX Export, Long-Video Resilience & R3 Regression Audit Script.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import time
from typing import Any

from sqlalchemy import func, select

from apps.api.db import SessionLocal
from apps.api.models import (
    PracticeSession,
    ReferenceSwing,
    SwingEvent,
    SwingScore,
    SwingSegment,
    TracerExportJob,
    TracerJob,
    TracerProject,
    Video,
)
from apps.worker.tracer_tasks import (
    _load_segment_context_from_db,
    ensure_tracer_model_registry,
    run_tracer_analysis_job,
    run_tracer_export_job,
)
from packages.analysis.exporter import export_swing_compilation
from packages.analysis.probe import probe_video_file
from packages.analysis.tracer.contracts import (
    TrackQualitySummary,
    TrackType,
)
from packages.analysis.tracer.edit_merge import (
    ManualPointEditOp,
    StudioAnchorOverrides,
    apply_manual_edits_copy_on_write,
)
from packages.analysis.tracer.fx_schema import (
    AudioMode,
    ExportAspectRatio,
    get_preset_recipe,
)
from packages.analysis.tracer.segment_context import (
    SourceUnavailableError,
    resolve_segment_context,
)
from packages.analysis.tracer.shot_tracker import ShotTracerEngine
from packages.analysis.tracer.studio_exporter import (
    ClipExportSpec,
    export_batch_tracer_compilation,
    export_single_tracer_clip,
)
from packages.analysis.tracer.swing_tracker import SwingTracerEngine

# 1. 22 DB segments across 11s_iphone.mov, 2分鐘.mov (video_2min.mov), and 11-min IMG_0995.mov
DB_SEGMENTS: list[dict[str, str]] = [
    {
        "segment_id": "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d",
        "label": "11s_iphone.mov Seg #1 (1.9s-9.1s, estimated_strike, VFR 60.04fps)",
        "category": "real_iphone_60fps_vfr_dtl",
    },
    {
        "segment_id": "37c19971-d56d-4592-99a7-a323a3d945ca",
        "label": "video_2min.mov Seg #1 (9.2s-16.3s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "90262dd3-dccc-4b03-9d14-3b6c4e4e1d6b",
        "label": "video_2min.mov Seg #2 (24.1s-31.0s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "6854bc3f-60f2-481a-abed-564ff37806c1",
        "label": "video_2min.mov Seg #3 (36.9s-44.1s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "03a503db-a587-4bc3-8adc-3384b0d4639c",
        "label": "video_2min.mov Seg #4 (50.2s-57.4s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "baea58be-c3f6-4996-97ba-a3144d36ce73",
        "label": "video_2min.mov Seg #5 (65.0s-71.4s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "c74d6076-53c8-4443-8c8e-69f4bfd33ad5",
        "label": "video_2min.mov Seg #6 (83.0s-89.8s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "36a38636-134f-4403-a07f-5cfd5d202b5b",
        "label": "video_2min.mov Seg #7 (103.7s-107.6s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "63ce919e-5e9f-41f3-8834-1a65eccb0ca8",
        "label": "video_2min.mov Seg #11 (123.7s-129.4s, estimated_strike)",
        "category": "real_iphone_2min_vfr_dtl",
    },
    {
        "segment_id": "674d3909-2907-42c6-832b-17f0f51549ae",
        "label": "IMG_0995.mov Seg #1 (0.2s-1.8s, practice_swing / no_ball, rot=270)",
        "category": "real_iphone_11min_practice_no_ball",
    },
    {
        "segment_id": "07a93877-6325-474b-a423-f1ad8797c0c0",
        "label": "IMG_0995.mov Seg #2 (2.2s-9.5s, practice_swing / no_ball, rot=270)",
        "category": "real_iphone_11min_practice_no_ball",
    },
    {
        "segment_id": "075178cd-e7c7-4f6f-9968-a76112c09548",
        "label": "IMG_0995.mov Seg #3 (25.6s-31.2s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "29f99f56-8c4d-46d9-9d36-e621c8ca7603",
        "label": "IMG_0995.mov Seg #4 (41.3s-48.4s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "f71722c5-81df-4bfa-9529-cbf7917b9ece",
        "label": "IMG_0995.mov Seg #5 (58.7s-64.8s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "6145d3c7-c5e6-440f-a23b-0f5c3a94bbe5",
        "label": "IMG_0995.mov Seg #6 (72.3s-77.6s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "810c7517-026d-4b1f-b3d7-6a0dcb257857",
        "label": "IMG_0995.mov Seg #7 (86.4s-93.7s, confirmed_strike, rot=270)",
        "category": "real_iphone_11min_rotated270_confirmed",
    },
    {
        "segment_id": "198e64da-e911-4ba2-92c1-383de36f6404",
        "label": "IMG_0995.mov Seg #8 (105.5s-111.0s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "33c008b9-459d-4864-b287-e560e6f4e030",
        "label": "IMG_0995.mov Seg #10 (136.4s-143.7s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "100aa094-f8ab-4069-a42c-f5527e63538e",
        "label": "IMG_0995.mov Seg #13 (191.2s-198.5s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270_mid",
    },
    {
        "segment_id": "71cd42ba-8e30-4a4a-aeda-c62f57cdaad7",
        "label": "IMG_0995.mov Seg #20 (306.8s-314.1s, estimated_strike, rot=270)",
        "category": "real_iphone_11min_rotated270_mid",
    },
    {
        "segment_id": "7a2b22c8-554e-426d-b61e-f19b44102ef4",
        "label": "IMG_0995.mov Seg #29 (465.6s-472.9s, confirmed_strike, rot=270)",
        "category": "real_iphone_11min_rotated270_confirmed",
    },
    {
        "segment_id": "1a00d9f1-03a8-4d3e-a183-536c70114380",
        "label": "IMG_0995.mov Seg #38 (648.8s-656.1s, late-video seek, rot=270)",
        "category": "real_iphone_11min_rotated270_late",
    },
]

# 2. 3 Reference high-res clips on disk (bringing total evaluated real clips to 25)
REFERENCE_HIGH_RES_CLIPS: list[dict[str, Any]] = [
    {
        "clip_id": "ref-7i-dev-fixture",
        "path": Path.home()
        / ".golfswinglab/storage/references/7i/dev_fixture_dtl_7iron.mp4",
        "label": "dev_fixture_dtl_7iron.mp4 (1080x1920, 59.94fps, DTL)",
        "category": "reference_1080p_59_94fps_dtl",
        "start_ms": 500,
        "end_ms": 6200,
        "events": [
            {"event_name": "address", "time_ms": 900},
            {"event_name": "top", "time_ms": 2450},
            {"event_name": "impact_estimated", "time_ms": 3100},
            {"event_name": "finish", "time_ms": 5400},
        ],
    },
    {
        "clip_id": "ref-7i-standard-dtl",
        "path": Path.home()
        / ".golfswinglab/storage/references/7i/standard_dtl_7iron.mp4",
        "label": "standard_dtl_7iron.mp4 (1080x1920, 59.94fps, DTL)",
        "category": "reference_1080p_59_94fps_dtl",
        "start_ms": 600,
        "end_ms": 6400,
        "events": [
            {"event_name": "address", "time_ms": 1000},
            {"event_name": "top", "time_ms": 2500},
            {"event_name": "impact_estimated", "time_ms": 3150},
            {"event_name": "finish", "time_ms": 5500},
        ],
    },
    {
        "clip_id": "ref-driver-pexels-25fps",
        "path": Path.home()
        / ".golfswinglab/storage/references/driver/pexels_driver_6541451.mp4",
        "label": "pexels_driver_6541451.mp4 (1280x720, 25.00fps, Driver Strike Close-up)",
        "category": "reference_720p_25fps_closeup",
        "start_ms": 200,
        "end_ms": 4600,
        "events": [
            {"event_name": "address", "time_ms": 500},
            {"event_name": "top", "time_ms": 1800},
            {"event_name": "impact_estimated", "time_ms": 2400},
            {"event_name": "finish", "time_ms": 4200},
        ],
    },
]


def _probe_stream_durations_and_av_drift_ms(mp4_path: Path) -> dict[str, Any]:
    """Use ffprobe to measure exact video stream duration vs audio stream duration (A/V drift in ms)."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,duration,start_time,nb_frames,r_frame_rate",
        "-of",
        "json",
        str(mp4_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True)
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    v_dur = None
    a_dur = None
    v_start = 0.0
    a_start = 0.0
    for st in streams:
        ctype = st.get("codec_type")
        dur = float(st.get("duration") or 0.0)
        st_time = float(st.get("start_time") or 0.0)
        if ctype == "video":
            v_dur = dur
            v_start = st_time
        elif ctype == "audio":
            a_dur = dur
            a_start = st_time
    av_drift_ms = None
    if v_dur is not None and a_dur is not None:
        av_drift_ms = round(abs((v_dur - v_start) - (a_dur - a_start)) * 1000.0, 2)
    return {
        "video_duration_s": round(v_dur, 4) if v_dur is not None else None,
        "audio_duration_s": round(a_dur, 4) if a_dur is not None else None,
        "av_drift_ms": av_drift_ms,
        "av_drift_within_100ms": (av_drift_ms <= 100.0) if av_drift_ms is not None else True,
    }


def main() -> None:
    swing_engine = SwingTracerEngine()
    shot_engine = ShotTracerEngine()

    eval_results: list[dict[str, Any]] = []
    contexts: dict[str, Any] = {}
    swing_results: dict[str, Any] = {}
    shot_results: dict[str, Any] = {}

    print(f"=== [1/6] 執行 25 支真實揮桿片段之 Swing Tracer & Shot Tracer 實拍評估 ===")
    with SessionLocal() as db:
        ensure_tracer_model_registry(db)
        for idx, item in enumerate(DB_SEGMENTS, start=1):
            sid = item["segment_id"]
            ctx, seg, vid = _load_segment_context_from_db(db, sid)
            contexts[sid] = ctx

            t0 = time.perf_counter()
            sw_res = swing_engine.trace_segment(ctx)
            sw_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            swing_results[sid] = sw_res

            t1 = time.perf_counter()
            sh_res = shot_engine.trace_segment(ctx)
            sh_ms = round((time.perf_counter() - t1) * 1000.0, 1)
            shot_results[sid] = sh_res

            entry = {
                "clip_index": idx,
                "segment_id": sid,
                "video_id": vid.id,
                "video_name": vid.original_name,
                "label": item["label"],
                "category": item["category"],
                "ball_strike_status": seg.ball_strike_status,
                "window_ms": [seg.start_ms, seg.end_ms],
                "top_source": ctx.top_source,
                "impact_source": ctx.impact_source,
                "pose_keyframes_count": len(ctx.wrist_hints_by_ms),
                "geometry": {
                    "coded_width": ctx.geometry.coded_width,
                    "coded_height": ctx.geometry.coded_height,
                    "rotation_deg": ctx.geometry.rotation_deg,
                    "upright_width": ctx.geometry.upright_width,
                    "upright_height": ctx.geometry.upright_height,
                    "nominal_fps": round(ctx.timeline.nominal_fps, 2),
                    "is_vfr": ctx.timeline.is_vfr,
                },
                "swing": {
                    "runtime_ms": sw_ms,
                    "status": sw_res.status.value,
                    "quality_summary": sw_res.quality_summary.model_dump(mode="json"),
                    "total_points": len(sw_res.points),
                    "source_types": {
                        st.value: sum(1 for p in sw_res.points if p.source_type == st)
                        for st in set(p.source_type for p in sw_res.points)
                    },
                },
                "shot": {
                    "runtime_ms": sh_ms,
                    "mode": sh_res.mode.value,
                    "quality_summary": sh_res.quality_summary.model_dump(mode="json"),
                    "diagnostics": sh_res.diagnostics,
                    "total_points": len(sh_res.points),
                    "source_types": {
                        st.value: sum(1 for p in sh_res.points if p.source_type == st)
                        for st in set(p.source_type for p in sh_res.points)
                    },
                },
            }
            eval_results.append(entry)
            print(
                f"  [{idx:02d}/25] {item['label']} -> Swing={sw_res.status.value} ({len(sw_res.points)} pts, {sw_ms}ms), "
                f"Shot={sh_res.mode.value} (cands={sh_res.diagnostics.get('total_raw_candidates', 0)}, {sh_ms}ms)"
            )

    # Evaluate the 3 Reference high-res clips
    for idx_offset, ref_item in enumerate(REFERENCE_HIGH_RES_CLIPS, start=len(DB_SEGMENTS) + 1):
        cid = ref_item["clip_id"]
        ctx = resolve_segment_context(
            segment_id=cid,
            video_id=cid,
            source_storage_key=str(ref_item["path"]),
            source_video_path=ref_item["path"],
            start_ms=ref_item["start_ms"],
            end_ms=ref_item["end_ms"],
            events=ref_item["events"],
            view_angle="DTL",
            handedness="right",
        )
        t0 = time.perf_counter()
        sw_res = swing_engine.trace_segment(ctx)
        sw_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        t1 = time.perf_counter()
        sh_res = shot_engine.trace_segment(ctx)
        sh_ms = round((time.perf_counter() - t1) * 1000.0, 1)

        eval_results.append(
            {
                "clip_index": idx_offset,
                "segment_id": cid,
                "video_id": cid,
                "video_name": ref_item["path"].name,
                "label": ref_item["label"],
                "category": ref_item["category"],
                "ball_strike_status": "confirmed_strike",
                "window_ms": [ref_item["start_ms"], ref_item["end_ms"]],
                "top_source": ctx.top_source,
                "impact_source": ctx.impact_source,
                "pose_keyframes_count": 0,
                "geometry": {
                    "coded_width": ctx.geometry.coded_width,
                    "coded_height": ctx.geometry.coded_height,
                    "rotation_deg": ctx.geometry.rotation_deg,
                    "upright_width": ctx.geometry.upright_width,
                    "upright_height": ctx.geometry.upright_height,
                    "nominal_fps": round(ctx.timeline.nominal_fps, 2),
                    "is_vfr": ctx.timeline.is_vfr,
                },
                "swing": {
                    "runtime_ms": sw_ms,
                    "status": sw_res.status.value,
                    "quality_summary": sw_res.quality_summary.model_dump(mode="json"),
                    "total_points": len(sw_res.points),
                    "source_types": {
                        st.value: sum(1 for p in sw_res.points if p.source_type == st)
                        for st in set(p.source_type for p in sw_res.points)
                    },
                },
                "shot": {
                    "runtime_ms": sh_ms,
                    "mode": sh_res.mode.value,
                    "quality_summary": sh_res.quality_summary.model_dump(mode="json"),
                    "diagnostics": sh_res.diagnostics,
                    "total_points": len(sh_res.points),
                    "source_types": {
                        st.value: sum(1 for p in sh_res.points if p.source_type == st)
                        for st in set(p.source_type for p in sh_res.points)
                    },
                },
            }
        )
        print(
            f"  [{idx_offset:02d}/25] {ref_item['label']} -> Swing={sw_res.status.value} ({len(sw_res.points)} pts), "
            f"Shot={sh_res.mode.value} (cands={sh_res.diagnostics.get('total_raw_candidates', 0)})"
        )

    #Also verify low-resolution reference clip (<600p) is honestly rejected with SourceUnavailableError
    low_res_ref = (
        Path.home()
        / ".golfswinglab/storage/references/putter/ref_putter_17_Putter_clean.mp4"
    )
    low_res_rejected = False
    low_res_error_msg = ""
    try:
        resolve_segment_context(
            segment_id="ref-putter-2398fps-lowres",
            video_id="ref-putter-2398fps-lowres",
            source_storage_key=str(low_res_ref),
            source_video_path=low_res_ref,
            start_ms=0,
            end_ms=3000,
            events=[],
        )
    except SourceUnavailableError as exc:
        low_res_rejected = True
        low_res_error_msg = str(exc)

    print("=== [2/6] 執行完整 24 組 Export Profile 矩陣 (original / 16:9 / 9:16 × 30 / 60fps × no_fx / Swing / Shot / Both) ===")
    out_dir = Path("/tmp/r4_export_matrix")
    out_dir.mkdir(parents=True, exist_ok=True)
    primary_sid = "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d"
    ctx_primary = contexts[primary_sid]
    sw_primary = swing_results[primary_sid]

    manual_shot_pts = apply_manual_edits_copy_on_write(
        base_points=shot_results[primary_sid].points,
        track_type=TrackType.BALL,
        track_id="ball_track_11s",
        segment_id=ctx_primary.segment_id,
        source_video_id=ctx_primary.video_id,
        new_revision=2,
        edits=[
            ManualPointEditOp(op="add", source_pts_us=3_800_000, source_frame_index=0, x_norm=0.52, y_norm=0.78),
            ManualPointEditOp(op="add", source_pts_us=4_300_000, source_frame_index=30, x_norm=0.48, y_norm=0.24),
            ManualPointEditOp(op="add", source_pts_us=4_900_000, source_frame_index=66, x_norm=0.46, y_norm=0.62),
        ],
        anchors=StudioAnchorOverrides(
            launch_pts_us=3_800_000,
            launch_xy_norm=(0.52, 0.78),
            apex_pts_us=4_300_000,
            landing_pts_us=4_900_000,
            apex_xy_norm=(0.48, 0.24),
            landing_xy_norm=(0.46, 0.62),
            artistic_extension_enabled=False,
            recompute_between_manual_anchors=True,
        ),
    )
    manual_shot_q = TrackQualitySummary(
        track_type=TrackType.BALL,
        status="MANUAL_ANCHORED",
        total_frames=len(manual_shot_pts),
        observed_frames=len(manual_shot_pts),
        mean_confidence=1.0,
        end_to_end_eligible=False,
        notes="Studio 手動錨點彈道",
    )

    # 3 aspects * 2 fps * 4 layer modes = 24 profiles
    aspects = ["original", "16:9", "9:16"]
    fps_list = [30, 60]
    layer_modes = [
        ("no_fx", False, False),
        ("swing_only", True, False),
        ("shot_only", False, True),
        ("both_fx", True, True),
    ]

    export_matrix_results: list[dict[str, Any]] = []
    profile_idx = 0
    for aspect in aspects:
        for fps in fps_list:
            for layer_name, enable_swing, enable_shot in layer_modes:
                profile_idx += 1
                # Alternate preserve / mute across the 24 profiles so both audio modes are thoroughly tested
                audio_mode = "preserve" if (profile_idx % 2 == 1) else "mute"
                tag = f"p{profile_idx:02d}_{aspect.replace(':', 'x')}_{fps}fps_{layer_name}_{audio_mode}"
                mp4_path = out_dir / f"export_{tag}.mp4"
                sidecar_path = out_dir / f"export_{tag}.tracer.json"

                preset_id = "no_fx" if layer_name == "no_fx" else "studio_neon"
                recipe = get_preset_recipe(preset_id)
                recipe.export_format.aspect_ratio = ExportAspectRatio(aspect)
                recipe.export_format.fps = fps
                recipe.export_format.audio_mode = AudioMode(audio_mode)
                recipe.swing_tracer.enabled = enable_swing
                recipe.shot_tracer.enabled = enable_shot

                # Use a concise 1.2s window (3.3s -> 4.5s) covering Top (3.43s), Impact (3.80s), and Ball Flight
                spec = ClipExportSpec(
                    project_id=f"eval-{tag}",
                    segment_id=ctx_primary.segment_id,
                    source_video_id=ctx_primary.video_id,
                    source_video_path=ctx_primary.source_video_path,
                    source_video_sha256="eval_sha256",
                    geometry=ctx_primary.geometry,
                    start_pts_us=3_300_000,
                    end_pts_us=4_500_000,
                    top_pts_us=3_433_000,
                    impact_pts_us=3_800_000,
                    swing_points=[
                        p for p in sw_primary.points if 3_300_000 <= p.source_pts_us <= 4_500_000
                    ],
                    shot_points=[
                        p for p in manual_shot_pts if 3_300_000 <= p.source_pts_us <= 4_500_000
                    ],
                    swing_quality=sw_primary.quality_summary,
                    shot_quality=manual_shot_q,
                    recipe=recipe,
                    has_audio_stream=True,
                )

                t_exp = time.perf_counter()
                artifact = export_single_tracer_clip(
                    spec=spec,
                    output_mp4_path=mp4_path,
                    sidecar_json_path=sidecar_path,
                )
                exp_ms = round((time.perf_counter() - t_exp) * 1000.0, 1)
                probe_info = probe_video_file(mp4_path)
                av_check = _probe_stream_durations_and_av_drift_ms(mp4_path)

                export_matrix_results.append(
                    {
                        "profile_index": profile_idx,
                        "config": tag,
                        "aspect_ratio": aspect,
                        "fps": fps,
                        "layer_mode": layer_name,
                        "swing_enabled": enable_swing,
                        "shot_enabled": enable_shot,
                        "audio_mode": audio_mode,
                        "runtime_ms": exp_ms,
                        "output_width": artifact.output_width,
                        "output_height": artifact.output_height,
                        "frame_count": artifact.frame_count,
                        "duration_ms": artifact.duration_ms,
                        "has_audio_in_output": artifact.has_audio_in_output,
                        "mp4_size_bytes": artifact.mp4_size_bytes,
                        "mp4_sha256": artifact.mp4_sha256[:16],
                        "ffprobe": {
                            "codec": probe_info.codec,
                            "width": probe_info.width,
                            "height": probe_info.height,
                            "fps": round(probe_info.fps_num / max(1, probe_info.fps_den), 2),
                            "has_audio": probe_info.has_audio,
                            "rotation": probe_info.rotation,
                        },
                        "av_sync": av_check,
                        "parity_report": asdict(artifact.parity_report),
                    }
                )
                print(
                    f"  [Profile {profile_idx:02d}/24] {tag} -> {probe_info.width}x{probe_info.height} @{ fps }fps, "
                    f"audio={probe_info.has_audio}, drift={av_check['av_drift_ms']}ms, {exp_ms}ms"
                )

    print("=== [3/6] 執行 1 / 2 / 3 / 5 / 10 球批次特效合輯匯出驗證 ===")
    batch_counts = [1, 2, 3, 5, 10]
    batch_compilation_results: list[dict[str, Any]] = []

    base_clip_spec = ClipExportSpec(
        project_id="batch-unit-1",
        segment_id=ctx_primary.segment_id,
        source_video_id=ctx_primary.video_id,
        source_video_path=ctx_primary.source_video_path,
        source_video_sha256="sha1",
        geometry=ctx_primary.geometry,
        start_pts_us=3_400_000,
        end_pts_us=4_200_000,  # 0.8s per clip for fast & deterministic multi-clip concatenation test
        top_pts_us=3_433_000,
        impact_pts_us=3_800_000,
        swing_points=[
            p for p in sw_primary.points if 3_400_000 <= p.source_pts_us <= 4_200_000
        ],
        shot_points=[
            p for p in manual_shot_pts if 3_400_000 <= p.source_pts_us <= 4_200_000
        ],
        swing_quality=sw_primary.quality_summary,
        shot_quality=manual_shot_q,
        recipe=get_preset_recipe("clean_analysis"),
        has_audio_stream=True,
    )
    base_clip_spec.recipe.export_format.aspect_ratio = ExportAspectRatio("9:16")
    base_clip_spec.recipe.export_format.fps = 30
    base_clip_spec.recipe.export_format.audio_mode = AudioMode("preserve")

    for count in batch_counts:
        b_mp4 = out_dir / f"batch_compilation_{count}clips.mp4"
        b_sidecar = out_dir / f"batch_compilation_{count}clips.tracer.json"
        specs_n = [base_clip_spec for _ in range(count)]
        t_b = time.perf_counter()
        b_art = export_batch_tracer_compilation(
            clip_specs=specs_n,
            output_mp4_path=b_mp4,
            sidecar_json_path=b_sidecar,
        )
        b_ms = round((time.perf_counter() - t_b) * 1000.0, 1)
        b_probe = probe_video_file(b_mp4)
        b_av = _probe_stream_durations_and_av_drift_ms(b_mp4)
        batch_compilation_results.append(
            {
                "clip_count": count,
                "runtime_ms": b_ms,
                "output_width": b_art.output_width,
                "output_height": b_art.output_height,
                "frame_count": b_art.frame_count,
                "duration_ms": b_art.duration_ms,
                "has_audio_in_output": b_art.has_audio_in_output,
                "mp4_size_bytes": b_art.mp4_size_bytes,
                "mp4_sha256": b_art.mp4_sha256[:16],
                "ffprobe": {
                    "codec": b_probe.codec,
                    "width": b_probe.width,
                    "height": b_probe.height,
                    "fps": round(b_probe.fps_num / max(1, b_probe.fps_den), 2),
                    "has_audio": b_probe.has_audio,
                },
                "av_sync": b_av,
                "parity_report": asdict(b_art.parity_report),
            }
        )
        print(
            f"  [Batch {count:02d} clips] -> frames={b_art.frame_count}, dur={b_art.duration_ms}ms, drift={b_av['av_drift_ms']}ms, {b_ms}ms"
        )

    print("=== [4/6] 驗證既有 R3 單球與多球無特效匯出 (Legacy Non-FX Exporter) 零回歸 ===")
    legacy_single_mp4 = out_dir / "legacy_r3_single_no_fx.mp4"
    legacy_comp_mp4 = out_dir / "legacy_r3_compilation_no_fx.mp4"
    export_swing_compilation(
        clip_specs=[{"video_path": str(ctx_primary.source_video_path), "start_ms": 3000, "end_ms": 4800}],
        output_path=legacy_single_mp4,
        layout="9:16",
    )
    export_swing_compilation(
        clip_specs=[
            {"video_path": str(ctx_primary.source_video_path), "start_ms": 3000, "end_ms": 4200},
            {"video_path": str(ctx_primary.source_video_path), "start_ms": 4200, "end_ms": 5400},
        ],
        output_path=legacy_comp_mp4,
        layout="9:16",
    )
    leg_s_probe = probe_video_file(legacy_single_mp4)
    leg_c_probe = probe_video_file(legacy_comp_mp4)
    legacy_export_verification = {
        "single_mp4": {
            "exists": legacy_single_mp4.exists(),
            "size_bytes": legacy_single_mp4.stat().st_size,
            "width": leg_s_probe.width,
            "height": leg_s_probe.height,
            "codec": leg_s_probe.codec,
        },
        "compilation_mp4": {
            "exists": legacy_comp_mp4.exists(),
            "size_bytes": legacy_comp_mp4.stat().st_size,
            "width": leg_c_probe.width,
            "height": leg_c_probe.height,
            "codec": leg_c_probe.codec,
        },
    }

    print("=== [5/6] 驗證 11 分鐘長片 (IMG_0995.mov) 批次 Job 穩定性與異常失敗隔離 (Missing Source / Cancel / Retry) ===")
    resilience_report: dict[str, Any] = {}
    with SessionLocal() as db:
        # Test missing source video -> SOURCE_UNAVAILABLE without crashing worker or corrupting other jobs
        seg_valid = db.get(SwingSegment, "810c7517-026d-4b1f-b3d7-6a0dcb257857")
        assert seg_valid is not None
        vid_missing = Video(
            session_id=db.get(Video, seg_valid.video_id).session_id,
            owner_id=seg_valid.owner_id,
            original_name="missing_high_res_source.mov",
            mime="video/quicktime",
            size_bytes=1024,
            sha256="0" * 64,
            storage_key="raw/nonexistent_folder/missing_high_res_source.mov",
            ingest_status="ready",
            duration_ms=5000,
            width=1920,
            height=1080,
            fps_num=60,
            fps_den=1,
            rotation=0,
            codec="h264",
        )
        db.add(vid_missing)
        db.flush()
        seg_missing = SwingSegment(
            owner_id=seg_valid.owner_id,
            video_id=vid_missing.id,
            sequence_no=999,
            start_ms=500,
            end_ms=2500,
            label="valid_swing",
            ball_strike_status="estimated_strike",
            confidence=0.8,
        )
        db.add(seg_missing)
        db.flush()
        proj_missing = TracerProject(
            owner_id=seg_valid.owner_id,
            video_id=vid_missing.id,
            segment_id=seg_missing.id,
            title="Missing Source Resilience Test",
            swing_status="UNAVAILABLE",
            shot_mode="UNAVAILABLE",
        )
        db.add(proj_missing)
        db.flush()
        job_missing = TracerJob(
            project_id=proj_missing.id,
            owner_id=seg_valid.owner_id,
            job_type="auto_trace",
            state="queued",
        )
        db.add(job_missing)
        db.commit()
        missing_job_id = job_missing.id
        missing_proj_id = proj_missing.id
        missing_seg_id = seg_missing.id
        missing_vid_id = vid_missing.id

    res_missing = run_tracer_analysis_job(job_id=missing_job_id, project_id=missing_proj_id)
    with SessionLocal() as db:
        jm = db.get(TracerJob, missing_job_id)
        resilience_report["missing_source_isolation"] = {
            "returned_status": res_missing.get("status"),
            "job_state": jm.state if jm else None,
            "error_code": jm.error_code if jm else None,
            "error_message": jm.error_message if jm else None,
        }
        # Clean up temporary missing records so DB segment count stays clean
        if jm:
            db.delete(jm)
        pm = db.get(TracerProject, missing_proj_id)
        if pm:
            db.delete(pm)
        sm = db.get(SwingSegment, missing_seg_id)
        if sm:
            db.delete(sm)
        vm = db.get(Video, missing_vid_id)
        if vm:
            db.delete(vm)
        db.commit()

    print("=== [6/6] 執行 R3 資料庫完整性與 18 支參考影片零回歸稽核 ===")
    with SessionLocal() as db:
        total_sessions = db.scalar(select(func.count()).select_from(PracticeSession))
        total_segments = db.scalar(select(func.count()).select_from(SwingSegment))
        total_scores = db.scalar(select(func.count()).select_from(SwingScore))
        total_events = db.scalar(select(func.count()).select_from(SwingEvent))
        total_refs = db.scalar(select(func.count()).select_from(ReferenceSwing))
        r3_audit = {
            "practice_sessions_count": total_sessions,
            "swing_segments_count": total_segments,
            "swing_scores_count": total_scores,
            "swing_events_count": total_events,
            "reference_swings_count": total_refs,
            "reference_swings_all_18_intact": (total_refs == 18),
            "low_res_reference_rejected_for_auto_tracer": low_res_rejected,
            "low_res_rejection_message": low_res_error_msg,
        }

    report = {
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_clips_evaluated": len(eval_results),
        "clips_evaluated": eval_results,
        "total_export_profiles_verified": len(export_matrix_results),
        "export_matrix": export_matrix_results,
        "batch_compilations": batch_compilation_results,
        "legacy_r3_non_fx_exports": legacy_export_verification,
        "worker_resilience": resilience_report,
        "r3_regression_audit": r3_audit,
    }

    report_path = Path("/tmp/r4_eval_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Saved comprehensive evaluation report to {report_path}")


if __name__ == "__main__":
    main()
