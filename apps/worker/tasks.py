import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db import SessionLocal
from apps.api.models import (
    AnalysisJob,
    ExportJob,
    PoseArtifact,
    SwingEvent,
    SwingMetric,
    SwingScore,
    SwingSegment,
    UserSetting,
    Video,
)
from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.analysis.exporter import export_swing_compilation
from packages.analysis.probe import (
    extract_thumbnail_fallback,
    generate_proxy_and_thumbnail,
    probe_video_file,
)
from packages.analysis.scoring.engine import compute_swing_score
from packages.storage.s3_client import get_storage_service


def _now() -> datetime:
    return datetime.now(UTC)


def _append_job_log(db: Session, job: AnalysisJob, stage: str, progress: int, message: str) -> bool:
    """更新背景任務階段、進度與 Heartbeat；若任務已被取消則回傳 False。"""
    db.refresh(job)
    if job.status == "cancelled":
        return False
    job.stage = stage
    job.progress = progress
    job.heartbeat_at = _now()
    logs = list(job.logs_json or [])
    logs.append(
        {
            "timestamp": _now().isoformat(),
            "stage": stage,
            "progress": progress,
            "message": message,
        }
    )
    job.logs_json = logs
    db.commit()
    return True


def run_video_analysis_job(job_id: str) -> dict[str, Any]:
    """
    執行完整影片分析 Pipeline：
    1. Ingest & ffprobe 解析真實 PTS / VFR / 旋轉
    2. 生成 Safari H.264 Proxy 預覽與縮圖並上傳 S3
    3. Coarse Scan 低解析度活動視窗掃描
    4. Fine Scan MediaPipe PoseLandmarker + 9 階段事件狀態機
    5. Score v1 可解釋動作評分與 IG 視覺分計算
    （重跑分析時保留 manual_override=True 之人工修訂片段與註記）
    """
    settings = get_settings()
    storage = get_storage_service()

    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return {"status": "not_found", "job_id": job_id}
        if job.status == "cancelled":
            return {"status": "cancelled", "job_id": job_id}
        if job.status == "completed":
            seg_count = len(
                db.scalars(
                    select(SwingSegment).where(SwingSegment.video_id == job.video_id)
                ).all()
            )
            return {"status": "completed", "job_id": job_id, "segments_detected": seg_count}

        video = db.get(Video, job.video_id)
        if not video:
            job.status = "failed"
            job.error_code = "VIDEO_NOT_FOUND"
            job.error_message = "找不到關聯的影片紀錄"
            job.finished_at = _now()
            db.commit()
            return {"status": "failed", "job_id": job_id}

        # 原子性樂觀鎖：只有狀態仍為 queued 的任務才能搶先開始執行
        claim_stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "queued")
            .values(
                status="running",
                attempt_count=AnalysisJob.attempt_count + 1,
                started_at=_now(),
                heartbeat_at=_now(),
            )
        )
        claim_res = db.execute(claim_stmt)
        db.commit()
        if getattr(claim_res, "rowcount", 0) == 0:
            # 任務已被另一個 Worker 或執行緒認領並處理中
            db.refresh(job)
            if job.status == "completed":
                seg_count = len(
                    db.scalars(
                        select(SwingSegment).where(SwingSegment.video_id == job.video_id)
                    ).all()
                )
                return {"status": "completed", "job_id": job_id, "segments_detected": seg_count}
            return {"status": job.status, "job_id": job_id}

        # 重新整理 job 物件
        db.refresh(job)

        try:
            with tempfile.TemporaryDirectory(prefix=f"gsl_job_{job.id[:8]}_") as tmp_dir:
                tmp_root = Path(tmp_dir)
                ext = Path(video.original_name).suffix or ".mp4"
                local_raw = tmp_root / f"raw{ext}"
                local_proxy = tmp_root / "proxy.mp4"
                local_thumb = tmp_root / "thumb.jpg"

                if not _append_job_log(db, job, "probe", 10, "正在從物件儲存下載原始影片並執行 ffprobe 解析"):
                    return {"status": "cancelled", "job_id": job_id}

                storage.download_to_path(video.storage_key, local_raw)
                meta = probe_video_file(local_raw, collect_pts=True)

                video.duration_ms = meta.duration_ms
                video.width = meta.width
                video.height = meta.height
                video.rotation = meta.rotation
                video.fps_num = meta.fps_num
                video.fps_den = meta.fps_den
                video.is_vfr = meta.is_vfr
                video.codec = meta.codec
                video.has_audio = meta.has_audio
                db.commit()

                if not _append_job_log(db, job, "proxy", 18, "正在生成 Safari 相容 H.264 預覽 Proxy 與縮圖"):
                    return {"status": "cancelled", "job_id": job_id}

                try:
                    generate_proxy_and_thumbnail(local_raw, local_proxy, local_thumb)
                    if local_proxy.exists():
                        proxy_key = f"proxies/{video.owner_id}/{video.id}/proxy.mp4"
                        storage.put_file(proxy_key, local_proxy, "video/mp4")
                        video.proxy_storage_key = proxy_key
                    if local_thumb.exists():
                        thumb_key = f"thumbnails/{video.owner_id}/{video.id}/thumb.jpg"
                        storage.put_file(thumb_key, local_thumb, "image/jpeg")
                        video.thumbnail_storage_key = thumb_key
                    db.commit()
                except Exception as proxy_err:
                    _append_job_log(db, job, "proxy", 22, f"預覽轉碼跳過 ({proxy_err})，直接使用原片執行高爾夫分析")
                    if not local_thumb.exists():
                        try:
                            extract_thumbnail_fallback(local_raw, local_thumb)
                            if local_thumb.exists():
                                thumb_key = f"thumbnails/{video.owner_id}/{video.id}/thumb.jpg"
                                storage.put_file(thumb_key, local_thumb, "image/jpeg")
                                video.thumbnail_storage_key = thumb_key
                        except Exception:
                            pass
                    db.commit()

                # 使用正規化旋轉與關鍵幀之 Proxy 或原片執行 Coarse-to-Fine 偵測
                analysis_target = local_proxy if local_proxy.exists() else local_raw
                detector = CoarseToFineDetector(model_version=settings.analysis_model_version)

                def _progress_hook(stage: str, pct: int, msg: str) -> None:
                    _append_job_log(db, job, stage, pct, msg)

                detected_segments, quality_summary = detector.analyze_video(
                    video_path=analysis_target,
                    duration_ms=meta.duration_ms,
                    progress_cb=_progress_hook,
                )

                db.refresh(job)
                if job.status == "cancelled":
                    return {"status": "cancelled", "job_id": job_id}

                video.quality_flags_json = quality_summary
                video.ingest_status = "ready"

                if not _append_job_log(db, job, "scoring", 85, "正在計算可解釋動作評分 (score-v1) 與寫入資料庫"):
                    return {"status": "cancelled", "job_id": job_id}

                # 取得使用者自訂權重（若有）
                user_setting = db.scalar(
                    select(UserSetting).where(UserSetting.owner_id == video.owner_id)
                )
                custom_weights = (
                    user_setting.score_weights_json
                    if (user_setting and user_setting.score_weights_json)
                    else None
                )

                # 僅清除非人工手動鎖定 (manual_override == False) 之舊自動片段，保留人工校正成果
                existing_auto_segments = db.scalars(
                    select(SwingSegment).where(
                        SwingSegment.video_id == video.id,
                        SwingSegment.manual_override.is_(False),
                    )
                ).all()
                for old_seg in existing_auto_segments:
                    db.delete(old_seg)
                db.flush()

                existing_manual_count = len(
                    db.scalars(
                        select(SwingSegment).where(
                            SwingSegment.video_id == video.id,
                            SwingSegment.manual_override.is_(True),
                        )
                    ).all()
                )

                for idx, cand in enumerate(detected_segments, start=existing_manual_count + 1):
                    seg = SwingSegment(
                        owner_id=video.owner_id,
                        video_id=video.id,
                        sequence_no=idx,
                        start_ms=cand.start_ms,
                        end_ms=cand.end_ms,
                        label=cand.label,
                        ball_strike_status=cand.ball_strike_status,
                        confidence=cand.confidence,
                        review_status=cand.review_status,
                        review_flags_json=cand.review_flags,
                        version=settings.analysis_model_version,
                        manual_override=False,
                    )
                    db.add(seg)
                    db.flush()

                    for ev in cand.events:
                        db.add(
                            SwingEvent(
                                segment_id=seg.id,
                                event_name=ev.event_name,
                                time_ms=ev.time_ms,
                                confidence=ev.confidence,
                                detection_source=ev.detection_source,
                                model_version=ev.model_version,
                                rationale=ev.rationale,
                            )
                        )

                    for m in cand.metrics:
                        db.add(
                            SwingMetric(
                                segment_id=seg.id,
                                metric_key=m["metric_key"],
                                value=m["value"],
                                unit=m["unit"],
                                confidence=m["confidence"],
                                source=m["source"],
                                observability=m["observability"],
                            )
                        )

                    db.add(
                        PoseArtifact(
                            segment_id=seg.id,
                            storage_key=None,
                            quality_metadata=cand.quality_metadata,
                            keyframes_json=cand.keyframes,
                        )
                    )

                    score_res = compute_swing_score(
                        metrics=cand.metrics,
                        quality_metadata=cand.quality_metadata,
                        weights=custom_weights,
                        score_version=settings.scoring_version,
                    )
                    db.add(
                        SwingScore(
                            segment_id=seg.id,
                            score_version=score_res.score_version,
                            overall_nullable=score_res.overall_nullable,
                            ig_visual_score=score_res.ig_visual_score,
                            partial_score=score_res.partial_score,
                            subscores_json=score_res.subscores,
                            coverage=score_res.coverage,
                            confidence=score_res.confidence,
                            explanation=score_res.explanation,
                        )
                    )

                job.status = "completed"
                job.stage = "completed"
                job.progress = 100
                job.finished_at = _now()
                job.heartbeat_at = _now()
                logs = list(job.logs_json or [])
                logs.append(
                    {
                        "timestamp": _now().isoformat(),
                        "stage": "completed",
                        "progress": 100,
                        "message": f"分析完成：共偵測 {len(detected_segments)} 個揮桿候選片段",
                    }
                )
                job.logs_json = logs
                db.commit()
                return {
                    "status": "completed",
                    "job_id": job_id,
                    "segments_detected": len(detected_segments),
                }
        except Exception as exc:
            db.rollback()
            job_err = db.get(AnalysisJob, job_id)
            if job_err:
                job_err.status = "failed"
                job_err.stage = "failed"
                job_err.error_code = "ANALYSIS_PIPELINE_ERROR"
                job_err.error_message = str(exc)
                job_err.finished_at = _now()
                job_err.heartbeat_at = _now()
                db.commit()
            return {"status": "failed", "job_id": job_id, "error": str(exc)}


def run_export_job(export_id: str) -> dict[str, Any]:
    """執行單球或多球精選合輯 MP4 匯出任務。"""
    storage = get_storage_service()
    with SessionLocal() as db:
        exp = db.get(ExportJob, export_id)
        if not exp:
            return {"status": "not_found", "export_id": export_id}

        exp.state = "processing"
        db.commit()

        try:
            with tempfile.TemporaryDirectory(prefix=f"gsl_exp_{exp.id[:8]}_") as tmp_dir:
                tmp_root = Path(tmp_dir)
                downloaded_videos: dict[str, Path] = {}
                clip_specs: list[dict[str, Any]] = []

                for seg_id in exp.segment_ids:
                    seg = db.get(SwingSegment, seg_id)
                    if not seg or seg.owner_id != exp.owner_id:
                        continue
                    vid = db.get(Video, seg.video_id)
                    if not vid:
                        continue
                    if vid.id not in downloaded_videos:
                        src_key = vid.proxy_storage_key or vid.storage_key
                        local_v = tmp_root / f"video_{vid.id}.mp4"
                        storage.download_to_path(src_key, local_v)
                        downloaded_videos[vid.id] = local_v

                    clip_specs.append(
                        {
                            "video_path": str(downloaded_videos[vid.id]),
                            "start_ms": seg.start_ms,
                            "end_ms": seg.end_ms,
                            "sequence_no": seg.sequence_no,
                        }
                    )

                if not clip_specs:
                    raise ValueError("找不到任何可匯出之有效揮桿片段")

                out_file = tmp_root / f"export_{exp.id}.mp4"
                export_info = export_swing_compilation(
                    clip_specs=clip_specs,
                    output_path=out_file,
                    layout=exp.layout,
                )
                export_key = f"exports/{exp.owner_id}/{exp.id}/swing_highlight_{exp.layout.replace(':', 'x')}.mp4"
                storage.put_file(export_key, out_file, "video/mp4")

                exp.storage_key = export_key
                exp.duration_ms = int(export_info["duration_ms"])
                exp.size_bytes = int(export_info["size_bytes"])
                exp.state = "completed"
                exp.error_message = None
                db.commit()
                return {
                    "status": "completed",
                    "export_id": export_id,
                    "duration_ms": exp.duration_ms,
                }
        except Exception as exc:
            db.rollback()
            exp_err = db.get(ExportJob, export_id)
            if exp_err:
                exp_err.state = "failed"
                exp_err.error_message = str(exc)
                db.commit()
            return {"status": "failed", "export_id": export_id, "error": str(exc)}
