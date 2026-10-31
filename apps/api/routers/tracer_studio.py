"""
Golf Tracer Studio R4 — FastAPI Router (`apps/api/routers/tracer_studio.py`).
提供完整 18 個 `/api/tracer/*` 端點：
- 嚴格強制 `get_current_user` 身分驗證與 `verify_owner` 跨使用者 IDOR 隔離
- 支援 `GSL_ENABLE_TRACER_STUDIO=false` 功能旗標安全停用
- 支援 Copy-on-Write 逐幀手動編輯、錨點覆寫（與 R3 `SwingEvent` 隔離）、6 種特效風格與 1–10 球批次匯出
"""

from datetime import UTC, datetime
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.auth import APIError, get_current_user, verify_owner
from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.models import (
    SwingEvent,
    SwingSegment,
    TracerAnchorRevision,
    TracerExportJob,
    TracerJob,
    TracerManualEdit,
    TracerProject,
    TracerRenderRecipe,
    TracerTrackRevision,
    User,
    Video,
)
from apps.api.schemas_tracer import (
    TracerAnalyzeRequest,
    TracerAnchorRevisionResponse,
    TracerAnchorUpdateRequest,
    TracerExportCreateRequest,
    TracerExportResponse,
    TracerManualEditsRequest,
    TracerProjectCreateRequest,
    TracerProjectDetailResponse,
    TracerRecipeUpdateRequest,
    TracerTrackRevisionResponse,
)
from apps.worker.tracer_tasks import (
    ensure_tracer_model_registry,
    load_active_track_points,
    run_tracer_analysis_job,
    run_tracer_export_job,
)
from packages.analysis.tracer.artifact_cache import save_track_revision_artifact
from packages.analysis.tracer.contracts import TrackType
from packages.analysis.tracer.edit_merge import (
    ManualPointEditOp,
    StudioAnchorOverrides,
    apply_manual_edits_copy_on_write,
)
from packages.analysis.tracer.fx_schema import (
    BUILTIN_RENDER_PRESETS,
    RenderRecipeV1,
    get_preset_recipe,
)
from packages.analysis.tracer.reliability import recompute_track_quality_summary
from packages.storage.s3_client import get_storage_service


def _require_tracer_studio_enabled() -> None:
    if not get_settings().enable_tracer_studio:
        raise APIError(
            503,
            "TRACER_STUDIO_DISABLED",
            "Golf Tracer Studio (R4) 目前已被環境變數 GSL_ENABLE_TRACER_STUDIO 停用",
        )


router = APIRouter(
    prefix="/api/tracer",
    tags=["tracer-studio"],
    dependencies=[Depends(_require_tracer_studio_enabled)],
)


def _now() -> datetime:
    return datetime.now(UTC)


def _get_owned_project(db: Session, project_id: str, current_user: User) -> TracerProject:
    project = db.get(TracerProject, project_id)
    if project is None:
        raise APIError(404, "TRACER_PROJECT_NOT_FOUND", "找不到指定的 Tracer Studio 專案")
    verify_owner(db, current_user, project.owner_id, "tracer_project", project.id)
    return project


def _build_track_revision_response(
    db: Session,
    project: TracerProject,
    track_type: str,
    revision: int,
) -> TracerTrackRevisionResponse | None:
    pts, summary, row = load_active_track_points(db, project.id, track_type, revision)
    if row is None:
        return None
    return TracerTrackRevisionResponse(
        id=row.id,
        project_id=row.project_id,
        track_type=row.track_type,
        revision=row.revision,
        parent_revision=row.parent_revision,
        status=row.status,
        point_count=len(pts),
        points=pts,
        quality_summary=summary,
        created_by=row.created_by,
        note=row.note,
        created_at=row.created_at,
    )


def _build_project_detail_response(
    db: Session,
    project: TracerProject,
) -> TracerProjectDetailResponse:
    video = db.get(Video, project.video_id)
    segment = db.get(SwingSegment, project.segment_id)

    anchor_row = db.scalar(
        select(TracerAnchorRevision).where(
            TracerAnchorRevision.project_id == project.id,
            TracerAnchorRevision.revision == project.active_anchor_revision,
        )
    )
    anchor_resp = (
        TracerAnchorRevisionResponse(
            id=anchor_row.id,
            project_id=anchor_row.project_id,
            revision=anchor_row.revision,
            address_pts_us=anchor_row.address_pts_us,
            top_pts_us=anchor_row.top_pts_us,
            impact_pts_us=anchor_row.impact_pts_us,
            finish_pts_us=anchor_row.finish_pts_us,
            launch_pts_us=anchor_row.launch_pts_us,
            apex_pts_us=anchor_row.apex_pts_us,
            landing_pts_us=anchor_row.landing_pts_us,
            anchors_json=dict(anchor_row.anchors_json or {}),
            created_by=anchor_row.created_by,
            created_at=anchor_row.created_at,
        )
        if anchor_row
        else None
    )

    recipe = get_preset_recipe("studio_neon")
    if project.active_recipe_id:
        rec_row = db.get(TracerRenderRecipe, project.active_recipe_id)
        if rec_row and rec_row.recipe_json:
            recipe = RenderRecipeV1.model_validate(rec_row.recipe_json)

    swing_resp = _build_track_revision_response(
        db, project, TrackType.CLUB_HEAD.value, project.active_swing_revision
    )
    shot_resp = _build_track_revision_response(
        db, project, TrackType.BALL.value, project.active_shot_revision
    )

    meta = dict(project.metadata_json or {})
    geom = dict(meta.get("geometry") or {})
    if not geom and video is not None:
        rot = int(video.rotation or 0) % 360
        cw = int(video.width or 1080)
        ch = int(video.height or 1920)
        uw, uh = (ch, cw) if rot in (90, 270) else (cw, ch)
        geom = {
            "coded_width": cw,
            "coded_height": ch,
            "rotation_deg": rot,
            "upright_width": uw,
            "upright_height": uh,
            "fps": float(video.fps_num or 60) / float(max(1, video.fps_den or 1)),
            "is_vfr": bool(video.is_vfr),
        }

    clip_start_us = int(meta.get("clip_start_pts_us") or ((segment.start_ms if segment else 0) * 1000))
    clip_end_us = int(meta.get("clip_end_pts_us") or ((segment.end_ms if segment else 3000) * 1000))

    return TracerProjectDetailResponse(
        id=project.id,
        owner_id=project.owner_id,
        session_id=project.session_id,
        video_id=project.video_id,
        segment_id=project.segment_id,
        title=project.title,
        status=project.status,
        swing_status=project.swing_status,
        shot_mode=project.shot_mode,
        active_swing_revision=project.active_swing_revision,
        active_shot_revision=project.active_shot_revision,
        active_anchor_revision=project.active_anchor_revision,
        active_recipe_id=project.active_recipe_id,
        source_video_sha256=project.source_video_sha256,
        coordinate_space_version=project.coordinate_space_version,
        video_stream_url=f"/api/videos/{project.video_id}/stream",
        original_video_stream_url=f"/api/videos/{project.video_id}/stream?source=original",
        clip_start_pts_us=clip_start_us,
        clip_end_pts_us=clip_end_us,
        geometry=geom,
        anchors=anchor_resp,
        recipe=recipe,
        swing_track=swing_resp,
        shot_track=shot_resp,
        metadata_json=meta,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/models")
def list_tracer_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """列出 R4 Tracer Studio 註冊之 CV 模型、SHA256、授權與本機可用狀態。"""
    _ = current_user
    rows = ensure_tracer_model_registry(db)
    return {
        "models": [
            {
                "id": r.id,
                "model_role": r.model_role,
                "display_name": r.display_name,
                "weights_path": r.weights_path,
                "weights_sha256": r.weights_sha256,
                "license_spdx": r.license_spdx,
                "availability_status": r.availability_status,
                "metadata": r.metadata_json,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/presets")
def list_tracer_presets(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """列出 6 組內建 Flight FX 渲染配方預設。"""
    _ = current_user
    return {
        "presets": [
            preset.model_dump(mode="json")
            for preset in BUILTIN_RENDER_PRESETS.values()
        ]
    }


@router.post("/projects", response_model=TracerProjectDetailResponse)
def create_or_get_tracer_project(
    payload: TracerProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """為指定 `segment_id` 建立或取得 Golf Tracer Studio 專案。"""
    segment = db.get(SwingSegment, payload.segment_id)
    if segment is None:
        raise APIError(404, "SEGMENT_NOT_FOUND", "找不到指定的揮桿片段")
    video = db.get(Video, segment.video_id)
    if video is None:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到對應的原始影片")

    verify_owner(db, current_user, video.owner_id, "swing_segment", segment.id)

    existing = db.scalar(
        select(TracerProject).where(
            TracerProject.owner_id == current_user.id,
            TracerProject.segment_id == segment.id,
        )
    )
    if existing is not None:
        return _build_project_detail_response(db, existing)

    title = payload.title or f"球 #{segment.sequence_no} Tracer Studio"
    project = TracerProject(
        owner_id=current_user.id,
        session_id=video.session_id,
        video_id=video.id,
        segment_id=segment.id,
        title=title,
        status="queued" if payload.auto_analyze else "needs_review",
        source_video_sha256=video.sha256 or "",
    )
    db.add(project)
    db.flush()

    preset_recipe = get_preset_recipe(payload.preset_id)
    recipe_row = TracerRenderRecipe(
        project_id=project.id,
        owner_id=current_user.id,
        preset_id=preset_recipe.preset_id,
        name=preset_recipe.name,
        recipe_json=preset_recipe.model_dump(mode="json"),
    )
    db.add(recipe_row)
    db.flush()
    project.active_recipe_id = recipe_row.id

    # 建立初始錨點 Revision 1 (由現有 SwingEvent 初始化，完全獨立儲存)
    events = list(db.scalars(select(SwingEvent).where(SwingEvent.segment_id == segment.id)).all())
    ev_map = {e.event_name.lower(): int(e.time_ms) * 1000 for e in events}
    anchor_row = TracerAnchorRevision(
        project_id=project.id,
        revision=1,
        address_pts_us=ev_map.get("address", segment.start_ms * 1000),
        top_pts_us=ev_map.get("top"),
        impact_pts_us=ev_map.get("impact_estimated") or ev_map.get("impact"),
        finish_pts_us=ev_map.get("finish", segment.end_ms * 1000),
        launch_pts_us=ev_map.get("impact_estimated") or ev_map.get("impact"),
        anchors_json={"artistic_extension_enabled": False},
        created_by="system",
    )
    db.add(anchor_row)
    db.commit()

    if payload.auto_analyze:
        job = TracerJob(
            project_id=project.id,
            owner_id=current_user.id,
            job_type="auto_trace",
            state="queued",
            stage_message="排隊執行自動追蹤",
        )
        db.add(job)
        db.commit()
        run_tracer_analysis_job(job_id=job.id, project_id=project.id)
        db.expire_all()
        project = db.get(TracerProject, project.id) or project

    return _build_project_detail_response(db, project)


@router.get("/projects")
def list_tracer_projects(
    session_id: str | None = Query(default=None),
    segment_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """列出當前使用者擁有之 Tracer Studio 專案。"""
    stmt = select(TracerProject).where(TracerProject.owner_id == current_user.id)
    if session_id:
        stmt = stmt.where(TracerProject.session_id == session_id)
    if segment_id:
        stmt = stmt.where(TracerProject.segment_id == segment_id)
    stmt = stmt.order_by(desc(TracerProject.updated_at))
    rows = list(db.scalars(stmt).all())
    return {
        "projects": [
            {
                "id": p.id,
                "session_id": p.session_id,
                "video_id": p.video_id,
                "segment_id": p.segment_id,
                "title": p.title,
                "status": p.status,
                "swing_status": p.swing_status,
                "shot_mode": p.shot_mode,
                "active_swing_revision": p.active_swing_revision,
                "active_shot_revision": p.active_shot_revision,
                "updated_at": p.updated_at.isoformat(),
            }
            for p in rows
        ]
    }


@router.get("/projects/{project_id}", response_model=TracerProjectDetailResponse)
def get_tracer_project_detail(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """取得單一 Tracer Studio 專案完整詳情、雙軌點位與渲染配方。"""
    project = _get_owned_project(db, project_id, current_user)
    return _build_project_detail_response(db, project)


@router.post("/projects/{project_id}/analyze")
def analyze_tracer_project(
    project_id: str,
    payload: TracerAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """觸發或重新執行原始高解析度影片之 Swing Tracer 與 Shot Tracer 觀測推論。"""
    project = _get_owned_project(db, project_id, current_user)
    job = TracerJob(
        project_id=project.id,
        owner_id=current_user.id,
        job_type="auto_trace",
        state="queued",
        stage_message="排隊執行高解析原片追蹤",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if payload.run_sync:
        res = run_tracer_analysis_job(
            job_id=job.id,
            project_id=project.id,
            run_swing=payload.run_swing_tracer,
            run_shot=payload.run_shot_tracer,
        )
        db.expire_all()
        updated_job = db.get(TracerJob, job.id)
        updated_proj = _get_owned_project(db, project_id, current_user)
        return {
            "job_id": job.id,
            "job_state": updated_job.state if updated_job else res.get("status"),
            "error_code": updated_job.error_code if updated_job else res.get("error_code"),
            "project": _build_project_detail_response(db, updated_proj).model_dump(mode="json"),
        }

    t = threading.Thread(
        target=run_tracer_analysis_job,
        kwargs={
            "job_id": job.id,
            "project_id": project.id,
            "run_swing": payload.run_swing_tracer,
            "run_shot": payload.run_shot_tracer,
        },
        daemon=True,
    )
    t.start()
    return {"job_id": job.id, "job_state": "running"}


@router.get("/projects/{project_id}/jobs")
def list_project_tracer_jobs(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = _get_owned_project(db, project_id, current_user)
    jobs = list(
        db.scalars(
            select(TracerJob)
            .where(TracerJob.project_id == project.id)
            .order_by(desc(TracerJob.created_at))
        ).all()
    )
    return {
        "jobs": [
            {
                "id": j.id,
                "project_id": j.project_id,
                "job_type": j.job_type,
                "state": j.state,
                "progress_pct": j.progress_pct,
                "stage_message": j.stage_message,
                "error_code": j.error_code,
                "error_message": j.error_message,
                "result_summary": j.result_summary_json,
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ]
    }


@router.get("/jobs/{job_id}")
def get_tracer_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(TracerJob, job_id)
    if job is None:
        raise APIError(404, "TRACER_JOB_NOT_FOUND", "找不到指定的 Tracer 任務")
    verify_owner(db, current_user, job.owner_id, "tracer_job", job.id)
    return {
        "id": job.id,
        "project_id": job.project_id,
        "job_type": job.job_type,
        "state": job.state,
        "progress_pct": job.progress_pct,
        "stage_message": job.stage_message,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "result_summary": job.result_summary_json,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@router.get("/projects/{project_id}/tracks")
def list_project_track_revisions(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = _get_owned_project(db, project_id, current_user)
    rows = list(
        db.scalars(
            select(TracerTrackRevision)
            .where(TracerTrackRevision.project_id == project.id)
            .order_by(TracerTrackRevision.track_type, desc(TracerTrackRevision.revision))
        ).all()
    )
    return {
        "active_swing_revision": project.active_swing_revision,
        "active_shot_revision": project.active_shot_revision,
        "revisions": [
            {
                "id": r.id,
                "track_type": r.track_type,
                "revision": r.revision,
                "parent_revision": r.parent_revision,
                "status": r.status,
                "point_count": r.point_count,
                "quality_summary": r.quality_summary_json,
                "created_by": r.created_by,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get(
    "/projects/{project_id}/tracks/{track_type}/revisions/{revision}",
    response_model=TracerTrackRevisionResponse,
)
def get_specific_track_revision(
    project_id: str,
    track_type: str,
    revision: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerTrackRevisionResponse:
    project = _get_owned_project(db, project_id, current_user)
    resp = _build_track_revision_response(db, project, track_type, revision)
    if resp is None:
        raise APIError(404, "TRACK_REVISION_NOT_FOUND", f"找不到 {track_type} 修訂版 {revision}")
    return resp


@router.post("/projects/{project_id}/edits", response_model=TracerProjectDetailResponse)
def apply_manual_track_edits(
    project_id: str,
    payload: TracerManualEditsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """
    以 Copy-on-Write 模式套用逐幀手動編輯 (`add`, `move`, `delete`)，
    產生全新 `revision = base_revision + 1`，絕不覆寫原始 `Revision 1`。
    """
    project = _get_owned_project(db, project_id, current_user)
    t_type = TrackType(payload.track_type)
    base_rev = (
        project.active_swing_revision
        if t_type == TrackType.CLUB_HEAD
        else project.active_shot_revision
    )

    base_pts, prev_summary, _ = load_active_track_points(db, project.id, t_type.value, base_rev)

    # 計算新 revision 編號
    all_revs = list(
        db.scalars(
            select(TracerTrackRevision.revision).where(
                TracerTrackRevision.project_id == project.id,
                TracerTrackRevision.track_type == t_type.value,
            )
        ).all()
    )
    new_rev = (max(all_revs) + 1) if all_revs else 1

    anchor_row = db.scalar(
        select(TracerAnchorRevision).where(
            TracerAnchorRevision.project_id == project.id,
            TracerAnchorRevision.revision == project.active_anchor_revision,
        )
    )
    anchors_extra = dict(anchor_row.anchors_json or {}) if anchor_row else {}
    apex_xy = anchors_extra.get("apex_xy_norm")
    landing_xy = anchors_extra.get("landing_xy_norm")

    anchor_overrides = StudioAnchorOverrides(
        address_pts_us=anchor_row.address_pts_us if anchor_row else None,
        top_pts_us=anchor_row.top_pts_us if anchor_row else None,
        impact_pts_us=anchor_row.impact_pts_us if anchor_row else None,
        finish_pts_us=anchor_row.finish_pts_us if anchor_row else None,
        launch_pts_us=anchor_row.launch_pts_us if anchor_row else None,
        apex_pts_us=anchor_row.apex_pts_us if anchor_row else None,
        landing_pts_us=anchor_row.landing_pts_us if anchor_row else None,
        apex_xy_norm=(float(apex_xy[0]), float(apex_xy[1])) if apex_xy and len(apex_xy) == 2 else None,
        landing_xy_norm=(float(landing_xy[0]), float(landing_xy[1])) if landing_xy and len(landing_xy) == 2 else None,
        artistic_extension_enabled=bool(anchors_extra.get("artistic_extension_enabled", False)),
        recompute_between_manual_anchors=payload.recompute_between_manual_anchors,
    )

    ops = [
        ManualPointEditOp(
            op=item.op,
            source_pts_us=item.source_pts_us,
            source_frame_index=item.source_frame_index,
            x_norm=item.x_norm,
            y_norm=item.y_norm,
            point_role=item.point_role,
            note=item.note,
        )
        for item in payload.edits
    ]

    track_id = (
        base_pts[0].track_id
        if base_pts
        else f"{t_type.value}_{project.segment_id[:12]}_rev{new_rev}"
    )

    try:
        merged_pts = apply_manual_edits_copy_on_write(
            base_points=base_pts,
            track_type=t_type,
            track_id=track_id,
            segment_id=project.segment_id,
            source_video_id=project.video_id,
            new_revision=new_rev,
            edits=ops,
            anchors=anchor_overrides,
        )
    except ValueError as exc:
        raise APIError(422, "INVALID_MANUAL_EDIT", str(exc)) from exc

    new_summary = recompute_track_quality_summary(
        points=merged_pts,
        track_type=t_type,
        total_frames=prev_summary.total_frames or len(merged_pts),
        view_angle=prev_summary.view_angle,
        handedness=prev_summary.handedness,
        camera_motion_score=prev_summary.camera_motion_score,
    )

    s_key, s_sha, _ = save_track_revision_artifact(
        project_id=project.id,
        track_type=t_type.value,
        revision=new_rev,
        points=merged_pts,
    )

    rev_row = TracerTrackRevision(
        project_id=project.id,
        track_type=t_type.value,
        revision=new_rev,
        parent_revision=base_rev,
        status=new_summary.status,
        storage_key=s_key,
        artifact_sha256=s_sha,
        point_count=len(merged_pts),
        points_inline_json=[p.model_dump(mode="json") for p in merged_pts],
        quality_summary_json=new_summary.model_dump(mode="json"),
        created_by="user",
        note=payload.note or f"手動編輯 ({len(ops)} 項操作)",
    )
    db.add(rev_row)

    edit_log = TracerManualEdit(
        project_id=project.id,
        owner_id=current_user.id,
        track_type=t_type.value,
        base_revision=base_rev,
        new_revision=new_rev,
        operations_json=[e.model_dump(mode="json") for e in payload.edits],
        note=payload.note,
    )
    db.add(edit_log)

    if t_type == TrackType.CLUB_HEAD:
        project.active_swing_revision = new_rev
        project.swing_status = new_summary.status
    else:
        project.active_shot_revision = new_rev
        project.shot_mode = new_summary.status

    project.status = "ready"
    project.updated_at = _now()
    db.commit()
    return _build_project_detail_response(db, project)


@router.post(
    "/projects/{project_id}/tracks/{track_type}/rollback/{revision}",
    response_model=TracerProjectDetailResponse,
)
def rollback_track_revision(
    project_id: str,
    track_type: str,
    revision: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """將作用中之 `club_head` 或 `ball` 軌跡版本回滾至指定歷史版本（如 Revision 1）。"""
    project = _get_owned_project(db, project_id, current_user)
    target_row = db.scalar(
        select(TracerTrackRevision).where(
            TracerTrackRevision.project_id == project.id,
            TracerTrackRevision.track_type == track_type,
            TracerTrackRevision.revision == revision,
        )
    )
    if target_row is None:
        raise APIError(404, "TRACK_REVISION_NOT_FOUND", f"找不到 {track_type} 修訂版 {revision}")

    if track_type == TrackType.CLUB_HEAD.value:
        project.active_swing_revision = revision
        project.swing_status = target_row.status
    elif track_type == TrackType.BALL.value:
        project.active_shot_revision = revision
        project.shot_mode = target_row.status
    else:
        raise APIError(400, "INVALID_TRACK_TYPE", f"不支援的 track_type: {track_type}")

    project.updated_at = _now()
    db.commit()
    return _build_project_detail_response(db, project)


@router.put("/projects/{project_id}/anchors", response_model=TracerProjectDetailResponse)
def update_project_anchors(
    project_id: str,
    payload: TracerAnchorUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """
    更新 Studio 專案之時間與空間錨點 (`address`, `top`, `impact`, `finish`, `launch`, `apex`, `landing`)。
    嚴格隔離原則：僅寫入 `tracer_anchor_revisions` 並重算 Tracer 軌跡分段，絕不修改 R3 `swing_events` 或 `swing_scores`。
    """
    project = _get_owned_project(db, project_id, current_user)
    cur_anchor = db.scalar(
        select(TracerAnchorRevision).where(
            TracerAnchorRevision.project_id == project.id,
            TracerAnchorRevision.revision == project.active_anchor_revision,
        )
    )

    all_anchor_revs = list(
        db.scalars(
            select(TracerAnchorRevision.revision).where(TracerAnchorRevision.project_id == project.id)
        ).all()
    )
    next_anchor_rev = (max(all_anchor_revs) + 1) if all_anchor_revs else 1

    address_us = payload.address_pts_us if payload.address_pts_us is not None else (cur_anchor.address_pts_us if cur_anchor else None)
    top_us = payload.top_pts_us if payload.top_pts_us is not None else (cur_anchor.top_pts_us if cur_anchor else None)
    impact_us = payload.impact_pts_us if payload.impact_pts_us is not None else (cur_anchor.impact_pts_us if cur_anchor else None)
    finish_us = payload.finish_pts_us if payload.finish_pts_us is not None else (cur_anchor.finish_pts_us if cur_anchor else None)
    launch_us = payload.launch_pts_us if payload.launch_pts_us is not None else (cur_anchor.launch_pts_us if cur_anchor else impact_us)
    apex_us = payload.apex_pts_us if payload.apex_pts_us is not None else (cur_anchor.apex_pts_us if cur_anchor else None)
    landing_us = payload.landing_pts_us if payload.landing_pts_us is not None else (cur_anchor.landing_pts_us if cur_anchor else None)

    prev_json = dict(cur_anchor.anchors_json or {}) if cur_anchor else {}
    apex_xy = payload.apex_xy_norm if payload.apex_xy_norm is not None else prev_json.get("apex_xy_norm")
    landing_xy = payload.landing_xy_norm if payload.landing_xy_norm is not None else prev_json.get("landing_xy_norm")

    new_anchor = TracerAnchorRevision(
        project_id=project.id,
        revision=next_anchor_rev,
        address_pts_us=address_us,
        top_pts_us=top_us,
        impact_pts_us=impact_us,
        finish_pts_us=finish_us,
        launch_pts_us=launch_us,
        apex_pts_us=apex_us,
        landing_pts_us=landing_us,
        anchors_json={
            "artistic_extension_enabled": payload.artistic_extension_enabled,
            "apex_xy_norm": apex_xy,
            "landing_xy_norm": landing_xy,
        },
        created_by="user",
    )
    db.add(new_anchor)
    project.active_anchor_revision = next_anchor_rev

    if payload.recompute_tracks:
        anchor_overrides = StudioAnchorOverrides(
            address_pts_us=address_us,
            top_pts_us=top_us,
            impact_pts_us=impact_us,
            finish_pts_us=finish_us,
            launch_pts_us=launch_us,
            apex_pts_us=apex_us,
            landing_pts_us=landing_us,
            apex_xy_norm=(float(apex_xy[0]), float(apex_xy[1])) if apex_xy and len(apex_xy) == 2 else None,
            landing_xy_norm=(float(landing_xy[0]), float(landing_xy[1])) if landing_xy and len(landing_xy) == 2 else None,
            artistic_extension_enabled=payload.artistic_extension_enabled,
            recompute_between_manual_anchors=True,
        )

        # 重算 Swing 階段分色 (Top / Impact 切點更新)
        swing_pts, swing_q, _ = load_active_track_points(
            db, project.id, TrackType.CLUB_HEAD.value, project.active_swing_revision
        )
        if swing_pts:
            all_s_revs = list(
                db.scalars(
                    select(TracerTrackRevision.revision).where(
                        TracerTrackRevision.project_id == project.id,
                        TracerTrackRevision.track_type == TrackType.CLUB_HEAD.value,
                    )
                ).all()
            )
            next_s_rev = (max(all_s_revs) + 1) if all_s_revs else 1
            re_swing_pts = apply_manual_edits_copy_on_write(
                base_points=swing_pts,
                track_type=TrackType.CLUB_HEAD,
                track_id=swing_pts[0].track_id,
                segment_id=project.segment_id,
                source_video_id=project.video_id,
                new_revision=next_s_rev,
                edits=[],
                anchors=anchor_overrides,
            )
            re_swing_q = recompute_track_quality_summary(
                points=re_swing_pts,
                track_type=TrackType.CLUB_HEAD,
                total_frames=swing_q.total_frames or len(re_swing_pts),
                view_angle=swing_q.view_angle,
                handedness=swing_q.handedness,
                camera_motion_score=swing_q.camera_motion_score,
            )
            sk, ssha, _ = save_track_revision_artifact(
                project.id, TrackType.CLUB_HEAD.value, next_s_rev, re_swing_pts
            )
            db.add(
                TracerTrackRevision(
                    project_id=project.id,
                    track_type=TrackType.CLUB_HEAD.value,
                    revision=next_s_rev,
                    parent_revision=project.active_swing_revision,
                    status=re_swing_q.status,
                    storage_key=sk,
                    artifact_sha256=ssha,
                    point_count=len(re_swing_pts),
                    points_inline_json=[p.model_dump(mode="json") for p in re_swing_pts],
                    quality_summary_json=re_swing_q.model_dump(mode="json"),
                    created_by="user",
                    note="依更新之 Top/Impact 錨點重算階段分色",
                )
            )
            project.active_swing_revision = next_s_rev
            project.swing_status = re_swing_q.status

        # 若有開啟藝術延伸或更新飛球落點錨點，同步重算 Shot 軌跡
        shot_pts, shot_q, _ = load_active_track_points(
            db, project.id, TrackType.BALL.value, project.active_shot_revision
        )
        if shot_pts and (payload.artistic_extension_enabled or landing_xy is not None):
            all_b_revs = list(
                db.scalars(
                    select(TracerTrackRevision.revision).where(
                        TracerTrackRevision.project_id == project.id,
                        TracerTrackRevision.track_type == TrackType.BALL.value,
                    )
                ).all()
            )
            next_b_rev = (max(all_b_revs) + 1) if all_b_revs else 1
            re_shot_pts = apply_manual_edits_copy_on_write(
                base_points=shot_pts,
                track_type=TrackType.BALL,
                track_id=shot_pts[0].track_id,
                segment_id=project.segment_id,
                source_video_id=project.video_id,
                new_revision=next_b_rev,
                edits=[],
                anchors=anchor_overrides,
            )
            re_shot_q = recompute_track_quality_summary(
                points=re_shot_pts,
                track_type=TrackType.BALL,
                total_frames=shot_q.total_frames or len(re_shot_pts),
                view_angle=shot_q.view_angle,
                handedness=shot_q.handedness,
                camera_motion_score=shot_q.camera_motion_score,
            )
            bk, bsha, _ = save_track_revision_artifact(
                project.id, TrackType.BALL.value, next_b_rev, re_shot_pts
            )
            db.add(
                TracerTrackRevision(
                    project_id=project.id,
                    track_type=TrackType.BALL.value,
                    revision=next_b_rev,
                    parent_revision=project.active_shot_revision,
                    status=re_shot_q.status,
                    storage_key=bk,
                    artifact_sha256=bsha,
                    point_count=len(re_shot_pts),
                    points_inline_json=[p.model_dump(mode="json") for p in re_shot_pts],
                    quality_summary_json=re_shot_q.model_dump(mode="json"),
                    created_by="user",
                    note="依更新之飛球錨點/藝術延伸重算",
                )
            )
            project.active_shot_revision = next_b_rev
            project.shot_mode = re_shot_q.status

    project.updated_at = _now()
    db.commit()
    return _build_project_detail_response(db, project)


@router.put("/projects/{project_id}/recipe", response_model=TracerProjectDetailResponse)
def update_project_render_recipe(
    project_id: str,
    payload: TracerRecipeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerProjectDetailResponse:
    """更新專案之 Flight FX 渲染配方或切換預設風格。"""
    project = _get_owned_project(db, project_id, current_user)
    if payload.recipe is not None:
        recipe_obj = payload.recipe
    elif payload.preset_id:
        recipe_obj = get_preset_recipe(payload.preset_id)
    else:
        raise APIError(400, "MISSING_RECIPE", "必須提供 preset_id 或完整 recipe")

    rec_row = TracerRenderRecipe(
        project_id=project.id,
        owner_id=current_user.id,
        preset_id=recipe_obj.preset_id,
        name=payload.name or recipe_obj.name,
        recipe_json=recipe_obj.model_dump(mode="json"),
    )
    db.add(rec_row)
    db.flush()
    project.active_recipe_id = rec_row.id
    project.updated_at = _now()
    db.commit()
    return _build_project_detail_response(db, project)


def _build_export_response(exp_job: TracerExportJob) -> TracerExportResponse:
    return TracerExportResponse(
        id=exp_job.id,
        owner_id=exp_job.owner_id,
        project_id=exp_job.project_id,
        project_ids=list(exp_job.project_ids_json or []),
        segment_ids=list(exp_job.segment_ids_json or []),
        aspect_ratio=exp_job.aspect_ratio,
        fps=exp_job.fps,
        audio_mode=exp_job.audio_mode,
        state=exp_job.state,
        download_url=f"/api/tracer/exports/{exp_job.id}/download" if exp_job.state == "completed" else None,
        sidecar_url=f"/api/tracer/exports/{exp_job.id}/sidecar" if exp_job.state == "completed" else None,
        mp4_sha256=exp_job.mp4_sha256,
        sidecar_sha256=exp_job.sidecar_sha256,
        size_bytes=exp_job.size_bytes,
        duration_ms=exp_job.duration_ms,
        output_width=exp_job.output_width,
        output_height=exp_job.output_height,
        has_audio_stream=exp_job.has_audio_stream,
        parity_report=dict(exp_job.parity_report_json or {}),
        error_message=exp_job.error_message,
        created_at=exp_job.created_at,
        updated_at=exp_job.updated_at,
    )


@router.post("/exports", response_model=TracerExportResponse)
def create_tracer_export(
    payload: TracerExportCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerExportResponse:
    """
    建立單球或 1–10 球批次特效影片匯出任務 (`original` / `16:9` / `9:16` × `30` / `60` fps × `preserve` / `mute`)。
    """
    if payload.fps not in (30, 60):
        raise APIError(422, "INVALID_EXPORT_FPS", "匯出幀率僅支援 30 或 60 FPS")

    target_project_ids: list[str] = []
    target_segment_ids: list[str] = []

    if payload.project_ids:
        target_project_ids = list(payload.project_ids)
    elif payload.project_id:
        target_project_ids = [payload.project_id]
    elif payload.segment_ids:
        for seg_id in payload.segment_ids:
            seg = db.get(SwingSegment, seg_id)
            if seg is None:
                raise APIError(404, "SEGMENT_NOT_FOUND", f"找不到揮桿片段: {seg_id}")
            vid = db.get(Video, seg.video_id)
            if vid is None:
                raise APIError(404, "VIDEO_NOT_FOUND", f"找不到原始影片: {seg.video_id}")
            verify_owner(db, current_user, vid.owner_id, "swing_segment", seg.id)
            proj_resp = create_or_get_tracer_project(
                TracerProjectCreateRequest(
                    segment_id=seg.id,
                    preset_id=payload.preset_id or "studio_neon",
                    auto_analyze=True,
                ),
                current_user=current_user,
                db=db,
            )
            target_project_ids.append(proj_resp.id)
            target_segment_ids.append(seg.id)

    if not (1 <= len(target_project_ids) <= 10):
        raise APIError(422, "INVALID_BATCH_COUNT", f"匯出球數必須介於 1 至 10 球，收到: {len(target_project_ids)}")

    for pid in target_project_ids:
        proj = _get_owned_project(db, pid, current_user)
        if proj.segment_id not in target_segment_ids:
            target_segment_ids.append(proj.segment_id)

    recipe_snapshot: dict[str, Any] = {}
    if payload.recipe_override is not None:
        recipe_snapshot = payload.recipe_override.model_dump(mode="json")
    elif payload.preset_id:
        recipe_snapshot = get_preset_recipe(payload.preset_id).model_dump(mode="json")

    exp_job = TracerExportJob(
        owner_id=current_user.id,
        project_id=target_project_ids[0] if len(target_project_ids) == 1 else None,
        project_ids_json=target_project_ids,
        segment_ids_json=target_segment_ids,
        aspect_ratio=payload.aspect_ratio.value,
        fps=payload.fps,
        audio_mode=payload.audio_mode.value,
        state="queued",
        recipe_snapshot_json=recipe_snapshot,
    )
    db.add(exp_job)
    db.commit()
    db.refresh(exp_job)

    if payload.run_sync:
        run_tracer_export_job(exp_job.id)
        db.expire_all()
        exp_job = db.get(TracerExportJob, exp_job.id) or exp_job
    else:
        t = threading.Thread(target=run_tracer_export_job, args=(exp_job.id,), daemon=True)
        t.start()

    return _build_export_response(exp_job)


@router.get("/exports")
def list_tracer_exports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(TracerExportJob)
            .where(TracerExportJob.owner_id == current_user.id)
            .order_by(desc(TracerExportJob.created_at))
            .limit(50)
        ).all()
    )
    return {"exports": [_build_export_response(r).model_dump(mode="json") for r in rows]}


@router.get("/exports/{export_id}", response_model=TracerExportResponse)
def get_tracer_export_detail(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TracerExportResponse:
    exp_job = db.get(TracerExportJob, export_id)
    if exp_job is None:
        raise APIError(404, "TRACER_EXPORT_NOT_FOUND", "找不到指定的 Tracer 匯出記錄")
    verify_owner(db, current_user, exp_job.owner_id, "tracer_export", exp_job.id)
    return _build_export_response(exp_job)


@router.get("/exports/{export_id}/download")
def download_tracer_export_mp4(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    exp_job = db.get(TracerExportJob, export_id)
    if exp_job is None:
        raise APIError(404, "TRACER_EXPORT_NOT_FOUND", "找不到指定的 Tracer 匯出記錄")
    verify_owner(db, current_user, exp_job.owner_id, "tracer_export", exp_job.id)
    if exp_job.state != "completed" or not exp_job.mp4_storage_key:
        raise APIError(409, "EXPORT_NOT_READY", "匯出影片尚未完成")

    storage = get_storage_service()
    res = storage.get_object_range(exp_job.mp4_storage_key)
    filename = f"GolfTracerStudio_{exp_job.id[:8]}_{exp_job.aspect_ratio.replace(':', 'x')}_{exp_job.fps}fps.mp4"
    return StreamingResponse(
        res["body"].iter_chunks(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(res["content_length"]),
        },
    )


@router.get("/exports/{export_id}/sidecar")
def download_tracer_export_sidecar(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    exp_job = db.get(TracerExportJob, export_id)
    if exp_job is None:
        raise APIError(404, "TRACER_EXPORT_NOT_FOUND", "找不到指定的 Tracer 匯出記錄")
    verify_owner(db, current_user, exp_job.owner_id, "tracer_export", exp_job.id)
    if exp_job.state != "completed":
        raise APIError(409, "EXPORT_NOT_READY", "匯出 Sidecar 尚未完成")
    return JSONResponse(content=exp_job.sidecar_payload_json or {})
