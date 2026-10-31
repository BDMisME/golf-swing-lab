"""R4 Real-Media Evaluation & Export Matrix Verification Script."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time

from apps.api.db import SessionLocal
from apps.worker.tracer_tasks import _load_segment_context_from_db
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
from packages.analysis.tracer.shot_tracker import ShotTracerEngine
from packages.analysis.tracer.studio_exporter import (
    ClipExportSpec,
    export_batch_tracer_compilation,
    export_single_tracer_clip,
)
from packages.analysis.tracer.swing_tracker import SwingTracerEngine

DB_SEGMENTS = [
    {
        "segment_id": "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d",
        "label": "11s_iphone.mov (Segment #1, estimated_strike)",
        "category": "real_iphone_60fps_dtl",
    },
    {
        "segment_id": "37c19971-d56d-4592-99a7-a323a3d945ca",
        "label": "video_2min.mov (Segment #1, 9.2s-16.3s, estimated_strike)",
        "category": "real_iphone_long_vfr_dtl",
    },
    {
        "segment_id": "90262dd3-dccc-4b03-9d14-3b6c4e4e1d6b",
        "label": "video_2min.mov (Segment #2, 24.1s-31.0s, estimated_strike)",
        "category": "real_iphone_long_vfr_dtl",
    },
    {
        "segment_id": "810c7517-026d-4b1f-b3d7-6a0dcb257857",
        "label": "IMG_0995.mov (Segment #5, 86.4s-93.7s, confirmed_strike, rotation=270)",
        "category": "real_iphone_11min_rotated270",
    },
    {
        "segment_id": "33da6b35-cc38-49ed-8f92-edd9527f81bd",
        "label": "IMG_0995.mov (Segment #38, 567.0s-574.3s, late-video seek, rotation=270)",
        "category": "real_iphone_11min_rotated270_late",
    },
    {
        "segment_id": "d870c908-6b88-4731-9c71-a0ee55a08f2e",
        "label": "IMG_0995.mov (Segment #4, 0.2s-1.8s, practice_swing / no_ball)",
        "category": "real_iphone_practice_no_ball",
    },
]


def main() -> None:
    swing_engine = SwingTracerEngine()
    shot_engine = ShotTracerEngine()

    eval_results = []
    contexts = {}
    swing_results = {}
    shot_results = {}

    with SessionLocal() as db:
        for item in DB_SEGMENTS:
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

            eval_results.append(
                {
                    "segment_id": sid,
                    "video_id": vid.id,
                    "video_name": vid.original_name,
                    "label": item["label"],
                    "category": item["category"],
                    "ball_strike_status": seg.ball_strike_status,
                    "window_ms": [seg.start_ms, seg.end_ms],
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
                        "total_points": len(sh_res.points),
                        "source_types": {
                            st.value: sum(1 for p in sh_res.points if p.source_type == st)
                            for st in set(p.source_type for p in sh_res.points)
                        },
                    },
                }
            )

    # Export matrix on 11s_iphone.mov (e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d)
    out_dir = Path("/tmp/r4_export_matrix")
    out_dir.mkdir(parents=True, exist_ok=True)
    primary_sid = "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d"
    ctx_primary = contexts[primary_sid]
    sw_primary = swing_results[primary_sid]

    # Build manual-anchored ball trajectory for export rendering parity check (3.8s -> 5.0s)
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

    matrix_configs = [
        ("original", 30, "preserve"),
        ("original", 60, "mute"),
        ("16:9", 30, "preserve"),
        ("16:9", 60, "mute"),
        ("9:16", 30, "preserve"),
        ("9:16", 60, "mute"),
    ]

    export_matrix_results = []
    for aspect, fps, audio_mode in matrix_configs:
        tag = f"{aspect.replace(':', 'x')}_{fps}fps_{audio_mode}"
        mp4_path = out_dir / f"export_{tag}.mp4"
        sidecar_path = out_dir / f"export_{tag}.tracer.json"

        recipe = get_preset_recipe("studio_neon")
        recipe.export_format.aspect_ratio = ExportAspectRatio(aspect)
        recipe.export_format.fps = fps
        recipe.export_format.audio_mode = AudioMode(audio_mode)

        spec = ClipExportSpec(
            project_id="eval-11s-iphone",
            segment_id=ctx_primary.segment_id,
            source_video_id=ctx_primary.video_id,
            source_video_path=ctx_primary.source_video_path,
            source_video_sha256="eval_sha256",
            geometry=ctx_primary.geometry,
            start_pts_us=3_000_000,
            end_pts_us=5_000_000,
            top_pts_us=3_433_000,
            impact_pts_us=3_800_000,
            swing_points=[
                p for p in sw_primary.points if 3_000_000 <= p.source_pts_us <= 5_000_000
            ],
            shot_points=manual_shot_pts,
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

        export_matrix_results.append(
            {
                "config": tag,
                "aspect_ratio": aspect,
                "fps": fps,
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
                "parity_report": asdict(artifact.parity_report),
            }
        )

    # Batch export (2 clips compilation: 11s_iphone.mov + rotated 270 IMG_0995.mov)
    second_sid = "810c7517-026d-4b1f-b3d7-6a0dcb257857"
    ctx_second = contexts[second_sid]
    sw_second = swing_results[second_sid]
    batch_recipe = get_preset_recipe("pro_clean")
    batch_recipe.export_format.aspect_ratio = ExportAspectRatio("9:16")
    batch_recipe.export_format.fps = 30
    batch_recipe.export_format.audio_mode = AudioMode("preserve")

    batch_mp4 = out_dir / "batch_compilation_2clips.mp4"
    batch_sidecar = out_dir / "batch_compilation_2clips.tracer.json"
    t_batch = time.perf_counter()
    batch_art = export_batch_tracer_compilation(
        clip_specs=[
            ClipExportSpec(
                project_id="batch-clip-1",
                segment_id=ctx_primary.segment_id,
                source_video_id=ctx_primary.video_id,
                source_video_path=ctx_primary.source_video_path,
                source_video_sha256="sha1",
                geometry=ctx_primary.geometry,
                start_pts_us=3_200_000,
                end_pts_us=4_950_000,
                top_pts_us=3_433_000,
                impact_pts_us=3_800_000,
                swing_points=[
                    p for p in sw_primary.points if 3_200_000 <= p.source_pts_us <= 4_950_000
                ],
                shot_points=manual_shot_pts,
                swing_quality=sw_primary.quality_summary,
                shot_quality=manual_shot_q,
                recipe=batch_recipe,
                has_audio_stream=True,
            ),
            ClipExportSpec(
                project_id="batch-clip-2",
                segment_id=ctx_second.segment_id,
                source_video_id=ctx_second.video_id,
                source_video_path=ctx_second.source_video_path,
                source_video_sha256="sha2",
                geometry=ctx_second.geometry,
                start_pts_us=87_400_000,
                end_pts_us=89_200_000,
                top_pts_us=87_800_000,
                impact_pts_us=88_200_000,
                swing_points=[
                    p for p in sw_second.points if 87_400_000 <= p.source_pts_us <= 89_200_000
                ],
                shot_points=[],
                swing_quality=sw_second.quality_summary,
                shot_quality=shot_results[second_sid].quality_summary,
                recipe=batch_recipe,
                has_audio_stream=True,
            ),
        ],
        output_mp4_path=batch_mp4,
        sidecar_json_path=batch_sidecar,
    )
    batch_ms = round((time.perf_counter() - t_batch) * 1000.0, 1)
    batch_probe = probe_video_file(batch_mp4)

    report = {
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "clips_evaluated": eval_results,
        "export_matrix": export_matrix_results,
        "batch_export": {
            "runtime_ms": batch_ms,
            "output_width": batch_art.output_width,
            "output_height": batch_art.output_height,
            "frame_count": batch_art.frame_count,
            "duration_ms": batch_art.duration_ms,
            "has_audio_in_output": batch_art.has_audio_in_output,
            "mp4_size_bytes": batch_art.mp4_size_bytes,
            "mp4_sha256": batch_art.mp4_sha256[:16],
            "ffprobe": {
                "codec": batch_probe.codec,
                "width": batch_probe.width,
                "height": batch_probe.height,
                "fps": round(batch_probe.fps_num / max(1, batch_probe.fps_den), 2),
                "has_audio": batch_probe.has_audio,
            },
            "parity_report": asdict(batch_art.parity_report),
        },
    }

    report_path = Path("/tmp/r4_eval_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved report to {report_path}")


if __name__ == "__main__":
    main()
