"""
Golf Tracer Studio R4 — Background & Inline Worker Tasks (`apps/worker/tracer_tasks.py`).
負責執行：
1. `ensure_tracer_model_registry`: 盤點本機模型權重雜湊與可用狀態，寫入 `tracer_model_registry`。
2. `run_tracer_analysis_job`: 對 `TracerProject` 對應之高解析原始影片執行 `SwingTracerEngine` 與 `ShotTracerEngine`。
3. `run_tracer_export_job`: 執行單球或 1–10 球批次特效影片匯出 (`export_single_tracer_clip` / `export_batch_tracer_compilation`) 與 `.tracer.json` Sidecar 驗證。
"""

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import logging
from pathlib import Path
import tempfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.db import SessionLocal
from apps.api.models import (
    PoseArtifact,
    SwingEvent,
    SwingSegment,
    TracerAnchorRevision,
    TracerExportJob,
    TracerJob,
    TracerModelRegistry,
    TracerProject,
    TracerRenderRecipe,
    TracerTrackRevision,
    Video,
)
from packages.analysis.tracer.artifact_cache import (
    load_track_revision_artifact,
    save_track_revision_artifact,
)
from packages.analysis.tracer.clubhead_detector import (
    DEFAULT_CLUBHEAD_MODEL_PATH,
    ClubheadDetector,
)
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    ShotTrackMode,
    SwingTrackStatus,
    TrackQualitySummary,
    TrackType,
)
from packages.analysis.tracer.fx_schema import (
    AudioMode,
    ExportAspectRatio,
    RenderRecipeV1,
    get_preset_recipe,
)
from packages.analysis.tracer.segment_context import (
    ResolvedSegmentContext,
    SourceUnavailableError,
    resolve_segment_context,
)
from packages.analysis.tracer.shot_detector import (
    DEFAULT_GOLF_BALL_MODEL_PATH,
    ShotBallDetector,
)
from packages.analysis.tracer.shot_tracker import ShotTracerEngine
from packages.analysis.tracer.studio_exporter import (
    ClipExportSpec,
    export_batch_tracer_compilation,
    export_single_tracer_clip,
)
from packages.analysis.tracer.swing_tracker import SwingTracerEngine
from packages.storage.s3_client import get_storage_service

logger = logging.getLogger(__name__)

DEFAULT_POSE_MODEL_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "GolfSwingLab"
    / "models"
    / "yolov8x-pose.pt"
)


def _now() -> datetime:
    return datetime.now(UTC)


def _file_sha256_or_none(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_tracer_model_registry(db: Session) -> list[TracerModelRegistry]:
    """盤點並更新本機 3 個核心 CV 模型之 SHA256 與可用狀態。"""
    specs = [
        {
            "id": "golf_ball_yolov8n",
            "model_role": "ball_detector",
            "display_name": "Golf Ball YOLOv8n Detector (Shot Tracer)",
            "path": DEFAULT_GOLF_BALL_MODEL_PATH,
            "license_spdx": "AGPL-3.0-or-later",
            "missing_status": "MODEL_UNAVAILABLE",
            "notes": "專用於高解析度原片之小白球偵測 (classes={0: 'golf_ball'})",
        },
        {
            "id": "yolov8x_pose",
            "model_role": "pose_detector",
            "display_name": "YOLOv8x-Pose 2D Keypoints (ROI & Anchor Prior)",
            "path": DEFAULT_POSE_MODEL_PATH,
            "license_spdx": "AGPL-3.0-or-later",
            "missing_status": "MODEL_UNAVAILABLE",
            "notes": "用於雙手 ROI 引導與揮桿事件定位（絕不直接以手腕冒充桿頭）",
        },
        {
            "id": "swingtrace_yolo11m",
            "model_role": "clubhead_detector",
            "display_name": "SwingTrace YOLO11m Clubhead & Grip Detector",
            "path": DEFAULT_CLUBHEAD_MODEL_PATH,
            "license_spdx": "AGPL-3.0-or-later",
            "missing_status": "BLOCKED_GATED_WEIGHTS",
            "notes": "HuggingFace nishsm/golf-club-detection-swingtrace 處於 Gated 狀態 (HTTP 401)，缺權重時退回桿身幾何端點估算並標記 NEEDS_REVIEW",
        },
    ]

    entries: list[TracerModelRegistry] = []
    for sp in specs:
        p: Path = sp["path"]
        sha = _file_sha256_or_none(p)
        status = "READY" if sha is not None else sp["missing_status"]
        rec = db.get(TracerModelRegistry, sp["id"])
        meta = {
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else 0,
            "notes": sp["notes"],
        }
        if rec is None:
            rec = TracerModelRegistry(
                id=sp["id"],
                model_role=sp["model_role"],
                display_name=sp["display_name"],
                weights_path=str(p),
                weights_sha256=sha,
                license_spdx=sp["license_spdx"],
                availability_status=status,
                metadata_json=meta,
            )
            db.add(rec)
        else:
            rec.weights_path = str(p)
            rec.weights_sha256 = sha
            rec.availability_status = status
            rec.metadata_json = meta
            rec.updated_at = _now()
        entries.append(rec)

    db.commit()
    return entries


def _load_segment_context_from_db(db: Session, segment_id: str) -> tuple[ResolvedSegmentContext, SwingSegment, Video]:
    segment = db.get(SwingSegment, segment_id)
    if segment is None:
        raise ValueError(f"找不到揮桿片段: {segment_id}")
    video = db.get(Video, segment.video_id)
    if video is None:
        raise ValueError(f"找不到原始影片記錄: {segment.video_id}")

    events = list(
        db.scalars(select(SwingEvent).where(SwingEvent.segment_id == segment.id)).all()
    )
    event_dicts = [
        {"event_name": ev.event_name, "time_ms": ev.time_ms, "confidence": ev.confidence}
        for ev in events
    ]
    pose_art = db.scalar(select(PoseArtifact).where(PoseArtifact.segment_id == segment.id))
    keyframes = list(pose_art.keyframes_json) if (pose_art and pose_art.keyframes_json) else []
    q_meta = dict(pose_art.quality_metadata) if (pose_art and pose_art.quality_metadata) else {}
    raw_info = dict(video.raw_info_json) if getattr(video, "raw_info_json", None) else {}

    view_angle = str(q_meta.get("view_angle") or raw_info.get("camera_angle") or "DTL")
    handedness = str(q_meta.get("handedness") or raw_info.get("handedness") or "right")

    ctx = resolve_segment_context(
        segment_id=segment.id,
        video_id=video.id,
        source_storage_key=video.storage_key,
        proxy_storage_key=video.proxy_storage_key,
        source_sha256=video.sha256,
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        events=event_dicts,
        pose_keyframes=keyframes,
        view_angle=view_angle,
        handedness=handedness,
    )
    return ctx, segment, video


def run_tracer_analysis_job(
    job_id: str,
    project_id: str,
    run_swing: bool = True,
    run_shot: bool = True,
    club_detector: ClubheadDetector | None = None,
    ball_detector: ShotBallDetector | None = None,
) -> dict[str, Any]:
    """
    執行單一 `TracerProject` 之自動 Swing Tracer 與 Shot Tracer 觀測推論。
    """
    with SessionLocal() as db:
        ensure_tracer_model_registry(db)
        job = db.get(TracerJob, job_id)
        project = db.get(TracerProject, project_id)
        if project is None:
            if job is not None:
                job.state = "failed"
                job.error_code = "PROJECT_NOT_FOUND"
                job.error_message = f"找不到 TracerProject: {project_id}"
                db.commit()
            return {"status": "failed", "error": "PROJECT_NOT_FOUND"}

        if job is not None:
            job.state = "running"
            job.progress_pct = 10.0
            job.stage_message = "正在檢驗原始高解析影片與解碼時鐘..."
            db.commit()

        project.status = "analyzing"
        db.commit()

        try:
            ctx, _seg, video = _load_segment_context_from_db(db, project.segment_id)
        except SourceUnavailableError as exc:
            project.status = "source_unavailable"
            project.swing_status = SwingTrackStatus.MODEL_UNAVAILABLE.value
            project.shot_mode = ShotTrackMode.UNAVAILABLE.value
            if job is not None:
                job.state = "failed"
                job.error_code = exc.code
                job.error_message = str(exc)
                job.stage_message = str(exc)
            db.commit()
            return {"status": "source_unavailable", "error_code": exc.code, "message": str(exc)}
        except Exception as exc:
            project.status = "failed"
            if job is not None:
                job.state = "failed"
                job.error_code = "CONTEXT_RESOLVE_ERROR"
                job.error_message = str(exc)
            db.commit()
            return {"status": "failed", "error": str(exc)}

        project.source_video_sha256 = ctx.source_sha256 or video.sha256 or ""
        project.metadata_json = {
            **(project.metadata_json or {}),
            "geometry": {
                "coded_width": ctx.geometry.coded_width,
                "coded_height": ctx.geometry.coded_height,
                "rotation_deg": ctx.geometry.rotation_deg,
                "upright_width": ctx.geometry.upright_width,
                "upright_height": ctx.geometry.upright_height,
                "fps": ctx.timeline.nominal_fps,
                "is_vfr": ctx.timeline.is_vfr,
            },
            "clip_start_pts_us": ctx.start_pts_us,
            "clip_end_pts_us": ctx.end_pts_us,
            "view_angle": ctx.view_angle,
            "handedness": ctx.handedness,
        }

        # 確保有初始錨點修訂版 (Revision 1)
        anchor_rev1 = db.scalar(
            select(TracerAnchorRevision).where(
                TracerAnchorRevision.project_id == project.id,
                TracerAnchorRevision.revision == 1,
            )
        )
        if anchor_rev1 is None:
            anchor_rev1 = TracerAnchorRevision(
                project_id=project.id,
                revision=1,
                address_pts_us=ctx.address_pts_us,
                top_pts_us=ctx.top_pts_us,
                impact_pts_us=ctx.impact_pts_us,
                finish_pts_us=ctx.finish_pts_us,
                launch_pts_us=ctx.impact_pts_us,
                apex_pts_us=None,
                landing_pts_us=None,
                anchors_json={
                    "artistic_extension_enabled": False,
                    "apex_xy_norm": None,
                    "landing_xy_norm": None,
                },
                created_by="system",
            )
            db.add(anchor_rev1)
            project.active_anchor_revision = 1
            db.commit()

        # 1. 執行 Swing Tracer
        swing_summary_dict: dict[str, Any] = {}
        if run_swing:
            if job is not None:
                job.progress_pct = 35.0
                job.stage_message = "正在執行 Swing Tracer 桿頭/桿身幾何追蹤..."
                db.commit()

            swing_engine = SwingTracerEngine(club_detector=club_detector)
            swing_res = swing_engine.trace_segment(ctx)
            next_swing_rev = _get_next_track_revision_num(db, project.id, TrackType.CLUB_HEAD.value)
            pts_for_rev = [
                p.model_copy(update={"revision": next_swing_rev}) for p in swing_res.points
            ]
            s_key, s_sha, _s_size = save_track_revision_artifact(
                project_id=project.id,
                track_type=TrackType.CLUB_HEAD.value,
                revision=next_swing_rev,
                points=pts_for_rev,
            )
            swing_summary_dict = swing_res.quality_summary.model_dump(mode="json")
            swing_rev_row = TracerTrackRevision(
                project_id=project.id,
                track_type=TrackType.CLUB_HEAD.value,
                revision=next_swing_rev,
                parent_revision=None,
                status=swing_res.status.value,
                storage_key=s_key,
                artifact_sha256=s_sha,
                point_count=len(pts_for_rev),
                points_inline_json=[p.model_dump(mode="json") for p in pts_for_rev],
                quality_summary_json=swing_summary_dict,
                created_by="model",
                note=swing_res.quality_summary.notes,
            )
            db.add(swing_rev_row)
            project.active_swing_revision = next_swing_rev
            project.swing_status = swing_res.status.value
            db.commit()

        # 2. 執行 Shot Tracer
        shot_summary_dict: dict[str, Any] = {}
        if run_shot:
            if job is not None:
                job.progress_pct = 70.0
                job.stage_message = "正在執行高解析度原片 Shot Tracer 飛球初段偵測與光流追蹤..."
                db.commit()

            shot_engine = ShotTracerEngine(ball_detector=ball_detector)
            shot_res = shot_engine.trace_segment(ctx)
            next_shot_rev = _get_next_track_revision_num(db, project.id, TrackType.BALL.value)
            ball_pts_for_rev = [
                p.model_copy(update={"revision": next_shot_rev}) for p in shot_res.points
            ]
            b_key, b_sha, _b_size = save_track_revision_artifact(
                project_id=project.id,
                track_type=TrackType.BALL.value,
                revision=next_shot_rev,
                points=ball_pts_for_rev,
            )
            shot_summary_dict = shot_res.quality_summary.model_dump(mode="json")
            shot_rev_row = TracerTrackRevision(
                project_id=project.id,
                track_type=TrackType.BALL.value,
                revision=next_shot_rev,
                parent_revision=None,
                status=shot_res.mode.value,
                storage_key=b_key,
                artifact_sha256=b_sha,
                point_count=len(ball_pts_for_rev),
                points_inline_json=[p.model_dump(mode="json") for p in ball_pts_for_rev],
                quality_summary_json=shot_summary_dict,
                created_by="model",
                note=shot_res.quality_summary.notes,
            )
            db.add(shot_rev_row)
            project.active_shot_revision = next_shot_rev
            project.shot_mode = shot_res.mode.value
            if shot_res.observed_launch_pts_us is not None and anchor_rev1 is not None:
                anchor_rev1.launch_pts_us = shot_res.observed_launch_pts_us
            db.commit()

        # 更新專案與任務最終狀態
        if (
            project.swing_status == SwingTrackStatus.AUTO_TRACED.value
            and project.shot_mode == ShotTrackMode.AUTO_OBSERVED.value
        ):
            project.status = "ready"
        else:
            project.status = "needs_review"

        if job is not None:
            job.state = "completed"
            job.progress_pct = 100.0
            job.stage_message = "自動追蹤分析完成"
            job.result_summary_json = {
                "swing_status": project.swing_status,
                "shot_mode": project.shot_mode,
                "swing_quality": swing_summary_dict,
                "shot_quality": shot_summary_dict,
            }
        db.commit()
        return {
            "status": project.status,
            "swing_status": project.swing_status,
            "shot_mode": project.shot_mode,
        }


def _get_next_track_revision_num(db: Session, project_id: str, track_type: str) -> int:
    revs = list(
        db.scalars(
            select(TracerTrackRevision.revision).where(
                TracerTrackRevision.project_id == project_id,
                TracerTrackRevision.track_type == track_type,
            )
        ).all()
    )
    return (max(revs) + 1) if revs else 1


def load_active_track_points(
    db: Session,
    project_id: str,
    track_type: str,
    revision: int,
) -> tuple[list[CanonicalTrackPoint], TrackQualitySummary, TracerTrackRevision | None]:
    row = db.scalar(
        select(TracerTrackRevision).where(
            TracerTrackRevision.project_id == project_id,
            TracerTrackRevision.track_type == track_type,
            TracerTrackRevision.revision == revision,
        )
    )
    if row is None:
        empty_summary = TrackQualitySummary(
            track_type=TrackType(track_type),
            status="UNAVAILABLE" if track_type == TrackType.BALL.value else "NEEDS_REVIEW",
        )
        return [], empty_summary, None

    points: list[CanonicalTrackPoint] = []
    if row.points_inline_json:
        points = [CanonicalTrackPoint.model_validate(item) for item in row.points_inline_json]
    elif row.storage_key:
        points = load_track_revision_artifact(row.storage_key, expected_sha256=row.artifact_sha256)

    q_summary = (
        TrackQualitySummary.model_validate(row.quality_summary_json)
        if row.quality_summary_json
        else TrackQualitySummary(track_type=TrackType(track_type), status=row.status)
    )
    return points, q_summary, row


def run_tracer_export_job(export_id: str) -> dict[str, Any]:
    """
    執行單一或批次 (1–10 球) `TracerExportJob` 渲染匯出任務。
    """
    with SessionLocal() as db:
        exp_job = db.get(TracerExportJob, export_id)
        if exp_job is None:
            return {"status": "failed", "error": "EXPORT_JOB_NOT_FOUND"}

        exp_job.state = "running"
        db.commit()

        try:
            proj_ids = list(exp_job.project_ids_json or [])
            if not proj_ids and exp_job.project_id:
                proj_ids = [exp_job.project_id]

            if not proj_ids or len(proj_ids) > 10:
                raise ValueError(f"匯出專案數量必須介於 1 至 10，收到: {len(proj_ids)}")

            clip_specs: list[ClipExportSpec] = []
            override_recipe_dict = dict(exp_job.recipe_snapshot_json or {})

            for pid in proj_ids:
                project = db.get(TracerProject, pid)
                if project is None:
                    raise ValueError(f"找不到匯出目標專案: {pid}")
                ctx, _seg, video = _load_segment_context_from_db(db, project.segment_id)

                swing_pts, swing_q, _ = load_active_track_points(
                    db, project.id, TrackType.CLUB_HEAD.value, project.active_swing_revision
                )
                shot_pts, shot_q, _ = load_active_track_points(
                    db, project.id, TrackType.BALL.value, project.active_shot_revision
                )

                anchor_row = db.scalar(
                    select(TracerAnchorRevision).where(
                        TracerAnchorRevision.project_id == project.id,
                        TracerAnchorRevision.revision == project.active_anchor_revision,
                    )
                )
                top_pts_us = anchor_row.top_pts_us if anchor_row else ctx.top_pts_us
                impact_pts_us = anchor_row.impact_pts_us if anchor_row else ctx.impact_pts_us

                if override_recipe_dict and "swing_tracer" in override_recipe_dict:
                    recipe = RenderRecipeV1.model_validate(override_recipe_dict)
                elif project.active_recipe_id:
                    rec_row = db.get(TracerRenderRecipe, project.active_recipe_id)
                    recipe = (
                        RenderRecipeV1.model_validate(rec_row.recipe_json)
                        if (rec_row and rec_row.recipe_json)
                        else get_preset_recipe("studio_neon")
                    )
                else:
                    recipe = get_preset_recipe("studio_neon")

                recipe.export_format.aspect_ratio = ExportAspectRatio(exp_job.aspect_ratio)
                recipe.export_format.fps = 30 if exp_job.fps == 30 else 60
                recipe.export_format.audio_mode = AudioMode(exp_job.audio_mode)

                clip_specs.append(
                    ClipExportSpec(
                        project_id=project.id,
                        segment_id=project.segment_id,
                        source_video_id=project.video_id,
                        source_video_path=ctx.source_video_path,
                        source_video_sha256=ctx.source_sha256 or video.sha256,
                        geometry=ctx.geometry,
                        start_pts_us=ctx.start_pts_us,
                        end_pts_us=ctx.end_pts_us,
                        top_pts_us=top_pts_us,
                        impact_pts_us=impact_pts_us,
                        swing_points=swing_pts,
                        shot_points=shot_pts,
                        swing_quality=swing_q,
                        shot_quality=shot_q,
                        recipe=recipe,
                        has_audio_stream=bool(getattr(video, "has_audio", True)),
                    )
                )

            with tempfile.TemporaryDirectory(prefix="gsl_tracer_export_out_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)
                local_mp4 = tmp_dir / f"tracer_export_{exp_job.id}.mp4"
                local_sidecar = tmp_dir / f"tracer_export_{exp_job.id}.tracer.json"

                if len(clip_specs) == 1:
                    artifact = export_single_tracer_clip(
                        spec=clip_specs[0],
                        output_mp4_path=local_mp4,
                        sidecar_json_path=local_sidecar,
                    )
                else:
                    artifact = export_batch_tracer_compilation(
                        clip_specs=clip_specs,
                        output_mp4_path=local_mp4,
                        sidecar_json_path=local_sidecar,
                    )

                storage = get_storage_service()
                mp4_key = f"exports/tracer/{exp_job.owner_id}/{exp_job.id}.mp4"
                sidecar_key = f"exports/tracer/{exp_job.owner_id}/{exp_job.id}.tracer.json"

                storage.put_file(mp4_key, local_mp4, content_type="video/mp4")
                storage.put_file(sidecar_key, local_sidecar, content_type="application/json")

                exp_job.state = "completed"
                exp_job.mp4_storage_key = mp4_key
                exp_job.sidecar_storage_key = sidecar_key
                exp_job.mp4_sha256 = artifact.mp4_sha256
                exp_job.sidecar_sha256 = artifact.sidecar_sha256
                exp_job.size_bytes = artifact.mp4_size_bytes
                exp_job.duration_ms = artifact.duration_ms
                exp_job.output_width = artifact.output_width
                exp_job.output_height = artifact.output_height
                exp_job.has_audio_stream = artifact.has_audio_in_output
                exp_job.parity_report_json = asdict(artifact.parity_report)
                exp_job.sidecar_payload_json = artifact.sidecar_payload
                exp_job.updated_at = _now()
                db.commit()

                return {
                    "status": "completed",
                    "export_id": exp_job.id,
                    "mp4_sha256": artifact.mp4_sha256,
                    "parity": asdict(artifact.parity_report),
                }
        except Exception as exc:
            logger.exception("Tracer 匯出任務失敗 (%s): %s", export_id, exc)
            exp_job.state = "failed"
            exp_job.error_message = str(exc)
            exp_job.updated_at = _now()
            db.commit()
            return {"status": "failed", "error": str(exc)}
