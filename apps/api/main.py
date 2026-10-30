import math
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from redis import Redis
from rq import Queue, Worker
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from apps.api.auth import (
    SESSION_COOKIE_NAME,
    APIError,
    create_session_token,
    ensure_default_admin,
    get_current_user,
    verify_owner,
    verify_password,
)
from apps.api.config import get_settings
from apps.api.db import Base, SessionLocal, engine, get_db
from apps.api.models import (
    AnalysisFeedback,
    AnalysisJob,
    AuditEvent,
    ExportJob,
    Favorite,
    PoseArtifact,
    PracticeSession,
    SwingEvent,
    SwingMetric,
    SwingScore,
    SwingSegment,
    Upload,
    UploadPart,
    User,
    UserSetting,
    Video,
    ReferenceSwing,
)
from apps.api.routers.audit import router as audit_router
from apps.api.routers.reference_swings import router as reference_swings_router
from packages.analysis.posture_comparison import compute_quantitative_posture_comparison
from apps.api.schemas import (
    CreateExportRequest,
    CreateManualSwingRequest,
    CreateSessionRequest,
    FavoriteToggleRequest,
    LoginRequest,
    PatchSwingRequest,
    UpdateSettingsRequest,
    UploadCompleteRequest,
    UploadInitiateRequest,
    UploadPartSignRequest,
)
from apps.worker.tasks import run_export_job, run_video_analysis_job
from packages.analysis.coach import (
    ActionDifference,
    GeminiCoachProvider,
    GolfCoachProvider,
    OpenAICompatibleCoachProvider,
    RuleBasedCoachProvider,
    compute_swing_action_differences,
    generate_deep_vision_insight,
)
from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.analysis.probe import VideoProbeError, probe_video_file
from packages.analysis.scoring.engine import (
    DEFAULT_WEIGHTS,
    compute_swing_score,
    rank_session_swings,
)
from packages.storage.s3_client import get_storage_service, sanitize_filename

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
ALLOWED_VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-m4v",
    "application/octet-stream",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _dispatch_analysis_job(job_id: str) -> str | None:
    """將分析任務排入背景處理。若無可用 worker 或啟用 inline_worker_fallback，則自動啟動背景執行緒。"""
    settings = get_settings()
    if settings.inline_worker_fallback:
        t = threading.Thread(target=run_video_analysis_job, args=(job_id,), daemon=True)
        t.start()
        return "inline_thread"

    try:
        redis_conn = Redis.from_url(settings.redis_url)
        workers = Worker.all(connection=redis_conn)
        active_analysis_workers = [w for w in workers if any(q.name == "gsl-analysis" for q in w.queues)]
        if not active_analysis_workers:
            t = threading.Thread(target=run_video_analysis_job, args=(job_id,), daemon=True)
            t.start()
            return "inline_thread_auto"

        q = Queue("gsl-analysis", connection=redis_conn, default_timeout=settings.rq_job_timeout_sec)
        rq_job = q.enqueue(run_video_analysis_job, job_id, job_timeout=settings.rq_job_timeout_sec)
        return str(rq_job.id)
    except Exception:
        t = threading.Thread(target=run_video_analysis_job, args=(job_id,), daemon=True)
        t.start()
        return "inline_fallback"


_COACH_REPORT_CACHE: dict[str, dict[str, Any]] = {}


def _dispatch_export_job(export_id: str) -> None:
    settings = get_settings()
    if settings.inline_worker_fallback:
        t = threading.Thread(target=run_export_job, args=(export_id,), daemon=True)
        t.start()
        return

    try:
        redis_conn = Redis.from_url(settings.redis_url)
        workers = Worker.all(connection=redis_conn)
        active_export_workers = [w for w in workers if any(q.name == "gsl-exports" for q in w.queues)]
        if not active_export_workers:
            t = threading.Thread(target=run_export_job, args=(export_id,), daemon=True)
            t.start()
            return

        q = Queue("gsl-exports", connection=redis_conn, default_timeout=600)
        q.enqueue(run_export_job, export_id, job_timeout=600)
    except Exception:
        t = threading.Thread(target=run_export_job, args=(export_id,), daemon=True)
        t.start()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings().validate_security_posture()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_default_admin(db)
    try:
        get_storage_service().ensure_bucket()
    except Exception:
        pass
    yield


app = FastAPI(
    title="Golf Swing Lab API",
    version="1.0.0",
    description="AI 高爾夫 DTL 練習場長影片自動切球、2D 骨架分析、可解釋評分與 MP4 匯出 API",
    lifespan=lifespan,
)

settings_init = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_init.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "Content-Range", "Accept-Ranges", "Content-Length", "X-Request-Id"],
)

app.include_router(audit_router)
app.include_router(reference_swings_router)



@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Response:
    req_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = req_id
    response: Response = await call_next(request)
    response.headers["X-Request-Id"] = req_id
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:16]}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": req_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:16]}")
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "請求參數格式不正確",
            "details": {"errors": exc.errors()},
            "request_id": req_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:16]}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "伺服器內部發生未預期錯誤，請稍後再試",
            "details": {},
            "request_id": req_id,
        },
    )


# ============================================================================
# 1. Health & Readiness
# ============================================================================


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "service": "gsl-api",
        "version": "1.0.0",
        "analysis_model_version": s.analysis_model_version,
        "scoring_version": s.scoring_version,
    }


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> JSONResponse:
    s = get_settings()
    checks: dict[str, bool] = {"postgres": False, "redis": False, "storage": False}
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    try:
        r = Redis.from_url(s.redis_url, socket_connect_timeout=2)
        checks["redis"] = bool(r.ping())
    except Exception:
        checks["redis"] = False

    try:
        checks["storage"] = get_storage_service().check_health()
    except Exception:
        checks["storage"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


# ============================================================================
# 2. Authentication
# ============================================================================


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_default_admin(db)
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(user.password_hash, payload.password):
        raise APIError(401, "AUTH_INVALID_CREDENTIALS", "電子郵件或密碼錯誤")

    token = create_session_token(user)
    s = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=(s.app_env == "production"),
        max_age=86400 * 7,
        path="/",
    )
    db.add(
        AuditEvent(
            actor_id=user.id,
            object_type="user",
            object_id=user.id,
            action="login_success",
            metadata_json={"email": user.email},
        )
    )
    db.commit()
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
        },
        "access_token": token,
    }


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "role": current_user.role,
        }
    }


# ============================================================================
# 3. Practice Sessions
# ============================================================================


def _serialize_session(db: Session, sess: PracticeSession) -> dict[str, Any]:
    videos = db.scalars(
        select(Video).where(Video.session_id == sess.id).order_by(Video.created_at.asc())
    ).all()
    video_ids = [v.id for v in videos]
    segments: list[SwingSegment] = []
    if video_ids:
        segments = list(
            db.scalars(
                select(SwingSegment)
                .where(SwingSegment.video_id.in_(video_ids))
                .order_by(SwingSegment.start_ms.asc())
            ).all()
        )
    valid_segments = [s for s in segments if s.label == "valid_swing" and s.review_status != "rejected"]
    scores: list[float] = []
    for seg in valid_segments:
        sc = db.scalar(
            select(SwingScore)
            .where(SwingScore.segment_id == seg.id)
            .order_by(desc(SwingScore.computed_at))
        )
        if sc and sc.overall_nullable is not None:
            scores.append(float(sc.overall_nullable))

    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    best_score = round(max(scores), 1) if scores else None
    needs_review_count = sum(1 for s in segments if s.review_status == "needs_review")

    video_items: list[dict[str, Any]] = []
    for v in videos:
        latest_job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.video_id == v.id)
            .order_by(desc(AnalysisJob.created_at))
        )
        video_items.append(
            {
                "id": v.id,
                "original_name": v.original_name,
                "mime": v.mime,
                "size_bytes": v.size_bytes,
                "duration_ms": v.duration_ms,
                "width": v.width,
                "height": v.height,
                "rotation": v.rotation,
                "fps": round(v.fps_num / max(1, v.fps_den), 2),
                "is_vfr": v.is_vfr,
                "codec": v.codec,
                "ingest_status": v.ingest_status,
                "quality_flags": v.quality_flags_json,
                "latest_job": {
                    "id": latest_job.id,
                    "status": latest_job.status,
                    "stage": latest_job.stage,
                    "progress": latest_job.progress,
                    "progress_pct": latest_job.progress,
                    "message": (latest_job.logs_json[-1].get("message", "") if latest_job.logs_json else ""),
                    "error_code": latest_job.error_code,
                    "error_message": latest_job.error_message,
                }
                if latest_job
                else None,
            }
        )

    return {
        "id": sess.id,
        "owner_id": sess.owner_id,
        "title": sess.title,
        "date": sess.date,
        "club": sess.club,
        "handedness": sess.handedness,
        "camera_angle": sess.camera_angle,
        "notes": sess.notes,
        "status": sess.status,
        "created_at": sess.created_at.isoformat(),
        "video_count": len(videos),
        "total_swings": len(segments),
        "swing_count": len(segments),
        "valid_swings": len(valid_segments),
        "needs_review_count": needs_review_count,
        "average_score": avg_score,
        "average_overall_score": avg_score,
        "best_score": best_score,
        "videos": video_items,
    }


@app.get("/api/sessions")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(PracticeSession)
        .where(PracticeSession.owner_id == current_user.id)
        .order_by(desc(PracticeSession.created_at))
    ).all()
    items = [_serialize_session(db, r) for r in rows]
    return {"items": items, "total": len(items)}


@app.post("/api/sessions", status_code=201)
def create_session(
    payload: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.camera_angle.upper() != "DTL":
        raise APIError(
            400,
            "UNSUPPORTED_CAMERA_ANGLE",
            "初版僅支援後方視角（Down-the-Line, DTL）練習影片分析",
        )
    sess = PracticeSession(
        owner_id=current_user.id,
        title=payload.title.strip(),
        date=payload.date.strip(),
        club=payload.club.strip(),
        handedness=payload.handedness,
        camera_angle="DTL",
        notes=payload.notes.strip(),
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return _serialize_session(db, sess)


@app.get("/api/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sess = db.get(PracticeSession, session_id)
    if not sess:
        raise APIError(404, "SESSION_NOT_FOUND", "找不到指定的練習場次")
    verify_owner(db, current_user, sess.owner_id, "practice_session", sess.id)
    return _serialize_session(db, sess)


@app.delete("/api/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    sess = db.get(PracticeSession, session_id)
    if not sess:
        raise APIError(404, "SESSION_NOT_FOUND", "找不到指定的練習場次")
    verify_owner(db, current_user, sess.owner_id, "practice_session", sess.id)
    db.delete(sess)
    db.commit()
    return {"status": "deleted", "session_id": session_id}


# ============================================================================
# 4. Multipart Upload Lifecycle (Initiate / Sign / Upload Part / Complete / Abort)
# ============================================================================


@app.post("/api/uploads/initiate")
def initiate_upload(
    payload: UploadInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = get_settings()
    sess = db.get(PracticeSession, payload.session_id)
    if not sess:
        raise APIError(404, "SESSION_NOT_FOUND", "找不到所屬的練習場次")
    verify_owner(db, current_user, sess.owner_id, "practice_session", sess.id)

    if payload.size_bytes > s.max_upload_bytes:
        raise APIError(
            413,
            "UPLOAD_TOO_LARGE",
            f"檔案大小超過單檔上限 ({s.max_upload_bytes} bytes)",
        )

    safe_name = sanitize_filename(payload.filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise APIError(
            400,
            "UNSUPPORTED_FILE_EXTENSION",
            f"僅支援上傳 .MOV 或 .MP4 影片格式（收到: {ext or '無副檔名'}）",
        )
    if payload.mime_type.lower() not in ALLOWED_VIDEO_MIMES:
        raise APIError(
            400,
            "UNSUPPORTED_MIME_TYPE",
            f"不支援的 MIME 類型: {payload.mime_type}",
        )

    # 冪等檢查：若相同 owner + idempotency_key 已建立且未中止，直接回傳既有 Upload 與已上傳 Parts
    if payload.idempotency_key:
        existing_up = db.scalar(
            select(Upload).where(
                Upload.owner_id == current_user.id,
                Upload.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_up and existing_up.state != "aborted":
            uploaded_parts = db.scalars(
                select(UploadPart)
                .where(UploadPart.upload_id == existing_up.id)
                .order_by(UploadPart.part_number.asc())
            ).all()
            return {
                "upload_id": existing_up.id,
                "video_id": existing_up.video_id,
                "session_id": existing_up.session_id,
                "storage_key": existing_up.storage_key,
                "state": existing_up.state,
                "part_size_bytes": existing_up.part_size_bytes,
                "total_parts": existing_up.total_parts,
                "uploaded_parts": [
                    {
                        "part_number": p.part_number,
                        "etag": p.etag,
                        "sha256": p.sha256,
                        "size_bytes": p.size_bytes,
                    }
                    for p in uploaded_parts
                ],
                "idempotent_reused": True,
            }

    video = Video(
        owner_id=current_user.id,
        session_id=sess.id,
        storage_key="",
        original_name=safe_name,
        mime=payload.mime_type,
        size_bytes=payload.size_bytes,
        sha256=payload.sha256,
        ingest_status="uploading",
    )
    db.add(video)
    db.flush()

    storage_key = f"raw/{current_user.id}/{sess.id}/{video.id}/{safe_name}"
    video.storage_key = storage_key

    storage = get_storage_service()
    s3_upload_id = storage.create_multipart_upload(storage_key, payload.mime_type)
    total_parts = max(1, math.ceil(payload.size_bytes / payload.part_size_bytes))

    upload = Upload(
        owner_id=current_user.id,
        session_id=sess.id,
        video_id=video.id,
        s3_upload_id=s3_upload_id,
        storage_key=storage_key,
        state="initiated",
        part_size_bytes=payload.part_size_bytes,
        total_parts=total_parts,
        expected_size_bytes=payload.size_bytes,
        expected_sha256=payload.sha256,
        idempotency_key=payload.idempotency_key,
        expires_at=utcnow() + timedelta(hours=24),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    return {
        "upload_id": upload.id,
        "video_id": video.id,
        "session_id": sess.id,
        "storage_key": storage_key,
        "state": upload.state,
        "part_size_bytes": upload.part_size_bytes,
        "total_parts": upload.total_parts,
        "uploaded_parts": [],
        "idempotent_reused": False,
    }


@app.get("/api/uploads/{upload_id}")
def get_upload_status(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    up = db.get(Upload, upload_id)
    if not up:
        raise APIError(404, "UPLOAD_NOT_FOUND", "找不到上傳任務")
    verify_owner(db, current_user, up.owner_id, "upload", up.id)
    parts = db.scalars(
        select(UploadPart).where(UploadPart.upload_id == up.id).order_by(UploadPart.part_number.asc())
    ).all()
    return {
        "upload_id": up.id,
        "video_id": up.video_id,
        "state": up.state,
        "part_size_bytes": up.part_size_bytes,
        "total_parts": up.total_parts,
        "uploaded_parts": [
            {
                "part_number": p.part_number,
                "etag": p.etag,
                "sha256": p.sha256,
                "size_bytes": p.size_bytes,
            }
            for p in parts
        ],
    }


@app.post("/api/uploads/{upload_id}/parts/sign")
def sign_upload_part(
    upload_id: str,
    payload: UploadPartSignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    up = db.get(Upload, upload_id)
    if not up:
        raise APIError(404, "UPLOAD_NOT_FOUND", "找不到上傳任務")
    verify_owner(db, current_user, up.owner_id, "upload", up.id)
    if up.state in ("completed", "aborted"):
        raise APIError(400, "UPLOAD_INVALID_STATE", f"上傳任務狀態為 {up.state}，無法簽發分段 URL")

    storage = get_storage_service()
    presigned_s3_url = storage.sign_upload_part(up.storage_key, up.s3_upload_id, payload.part_number)
    return {
        "upload_id": up.id,
        "part_number": payload.part_number,
        "presigned_url": presigned_s3_url,
        "proxy_upload_path": f"/api/uploads/{up.id}/parts/{payload.part_number}/content",
        "expires_in": get_settings().presigned_url_ttl_seconds,
    }


@app.put("/api/uploads/{upload_id}/parts/{part_number}/content")
async def upload_part_content(
    upload_id: str,
    part_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """支援瀏覽器/測試端分段上傳並寫入 S3 Multipart，同時記錄真實 ETag 與 SHA256 以支援斷點續傳。"""
    up = db.get(Upload, upload_id)
    if not up:
        raise APIError(404, "UPLOAD_NOT_FOUND", "找不到上傳任務")
    verify_owner(db, current_user, up.owner_id, "upload", up.id)
    if up.state in ("completed", "aborted"):
        raise APIError(400, "UPLOAD_INVALID_STATE", f"上傳狀態為 {up.state}，無法寫入分段")

    body = await request.body()
    if not body:
        raise APIError(400, "EMPTY_PART_BODY", "分段內容不可為空")

    storage = get_storage_service()
    try:
        part_info = storage.put_part_bytes(up.storage_key, up.s3_upload_id, part_number, body)
    except Exception as exc:
        err_str = str(exc)
        if "XMinioStorageFull" in err_str or "Storage backend has reached its minimum free drive" in err_str:
            raise APIError(
                507,
                "STORAGE_FULL",
                "儲存空間已滿 (S3/MinIO Storage Full)。請釋放 Docker 容器空間，或於 .env 設定 STORAGE_PROVIDER=local 改用本機大容量硬碟 (享 160GB+ 空間)。",
            ) from exc
        raise APIError(500, "UPLOAD_PART_FAILED", f"寫入分段失敗: {exc}") from exc

    existing_part = db.scalar(
        select(UploadPart).where(
            UploadPart.upload_id == up.id,
            UploadPart.part_number == part_number,
        )
    )
    if existing_part:
        existing_part.etag = part_info["etag"]
        existing_part.sha256 = part_info["sha256"]
        existing_part.size_bytes = part_info["size_bytes"]
        existing_part.uploaded_at = utcnow()
    else:
        db.add(
            UploadPart(
                upload_id=up.id,
                part_number=part_number,
                etag=part_info["etag"],
                sha256=part_info["sha256"],
                size_bytes=part_info["size_bytes"],
            )
        )

    up.state = "uploading"
    db.commit()
    return {
        "upload_id": up.id,
        "part_number": part_number,
        "etag": part_info["etag"],
        "sha256": part_info["sha256"],
        "size_bytes": part_info["size_bytes"],
    }


@app.post("/api/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str,
    payload: UploadCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    up = db.get(Upload, upload_id)
    if not up:
        raise APIError(404, "UPLOAD_NOT_FOUND", "找不到上傳任務")
    verify_owner(db, current_user, up.owner_id, "upload", up.id)

    video = db.get(Video, up.video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到對應影片")

    # 冪等支援：若已完成則直接回傳完成狀態與影片 metadata
    if up.state == "completed":
        return {
            "upload_id": up.id,
            "video_id": video.id,
            "state": "completed",
            "duration_ms": video.duration_ms,
            "width": video.width,
            "height": video.height,
            "rotation": video.rotation,
            "codec": video.codec,
            "is_vfr": video.is_vfr,
            "idempotent_reused": True,
        }

    if up.state == "aborted":
        raise APIError(400, "UPLOAD_ABORTED", "此上傳已被中止，無法完成")

    # 合併客戶端傳入或資料庫已記錄之 Parts
    db_parts = db.scalars(
        select(UploadPart).where(UploadPart.upload_id == up.id).order_by(UploadPart.part_number.asc())
    ).all()
    part_map: dict[int, dict[str, Any]] = {
        p.part_number: {"part_number": p.part_number, "etag": p.etag} for p in db_parts
    }
    for cp in payload.parts:
        part_map[cp.part_number] = {"part_number": cp.part_number, "etag": cp.etag}

    if not part_map:
        raise APIError(400, "UPLOAD_NO_PARTS", "尚未上傳任何分段，無法完成合併")

    storage = get_storage_service()
    try:
        head_info = storage.complete_multipart_upload(
            up.storage_key, up.s3_upload_id, list(part_map.values())
        )
    except Exception as exc:
        err_str = str(exc)
        if "XMinioStorageFull" in err_str or "Storage backend has reached its minimum free drive" in err_str:
            raise APIError(
                507,
                "STORAGE_FULL",
                "儲存空間已滿 (S3/MinIO Storage Full)。請釋放 Docker 容器空間，或於 .env 設定 STORAGE_PROVIDER=local 改用本機大容量硬碟 (享 160GB+ 空間)。",
            ) from exc
        raise APIError(400, "STORAGE_COMPLETE_FAILED", f"分段合併失敗: {exc}") from exc

    # 下載至暫存進行 ffprobe 完整性與時長檢查（拒絕損毀檔、空檔或超過 30 分鐘限制之影片）
    s = get_settings()
    with tempfile.TemporaryDirectory(prefix="gsl_verify_") as tmp_dir:
        ext = Path(video.original_name).suffix or ".mp4"
        local_file = Path(tmp_dir) / f"verify{ext}"
        storage.download_to_path(up.storage_key, local_file)
        try:
            meta = probe_video_file(local_file, collect_pts=False)
        except VideoProbeError as exc:
            video.ingest_status = "corrupt"
            up.state = "failed"
            db.commit()
            raise APIError(422, "INVALID_VIDEO_MEDIA", str(exc)) from exc

        if meta.duration_ms > s.max_video_duration_sec * 1000:
            video.ingest_status = "rejected_duration"
            up.state = "failed"
            db.commit()
            raise APIError(
                422,
                "VIDEO_DURATION_EXCEEDED",
                f"影片時長 ({meta.duration_ms / 1000:.1f}s) 超過系統上限 ({s.max_video_duration_sec}s)",
            )

        video.size_bytes = int(head_info["size_bytes"])
        video.duration_ms = meta.duration_ms
        video.width = meta.width
        video.height = meta.height
        video.rotation = meta.rotation
        video.fps_num = meta.fps_num
        video.fps_den = meta.fps_den
        video.is_vfr = meta.is_vfr
        video.codec = meta.codec
        video.has_audio = meta.has_audio
        if payload.sha256:
            video.sha256 = payload.sha256
        video.ingest_status = "uploaded"
        up.state = "completed"
        db.commit()

    return {
        "upload_id": up.id,
        "video_id": video.id,
        "state": "completed",
        "size_bytes": video.size_bytes,
        "duration_ms": video.duration_ms,
        "width": video.width,
        "height": video.height,
        "rotation": video.rotation,
        "fps": round(video.fps_num / max(1, video.fps_den), 2),
        "codec": video.codec,
        "is_vfr": video.is_vfr,
        "idempotent_reused": False,
    }


@app.post("/api/uploads/{upload_id}/abort")
def abort_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    up = db.get(Upload, upload_id)
    if not up:
        raise APIError(404, "UPLOAD_NOT_FOUND", "找不到上傳任務")
    verify_owner(db, current_user, up.owner_id, "upload", up.id)
    if up.state == "completed":
        raise APIError(400, "UPLOAD_ALREADY_COMPLETED", "已完成的上傳無法中止")

    get_storage_service().abort_multipart_upload(up.storage_key, up.s3_upload_id)
    up.state = "aborted"
    video = db.get(Video, up.video_id)
    if video:
        video.ingest_status = "aborted"
    db.commit()
    return {"status": "aborted", "upload_id": up.id}


# ============================================================================
# 5. Videos & Protected HTTP Range Streaming
# ============================================================================


@app.get("/api/videos/{video_id}")
def get_video_info(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    video = db.get(Video, video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到指定的影片")
    verify_owner(db, current_user, video.owner_id, "video", video.id)

    storage = get_storage_service()
    play_key = video.proxy_storage_key or video.storage_key
    presigned_url = storage.generate_presigned_get_url(play_key)

    return {
        "id": video.id,
        "session_id": video.session_id,
        "original_name": video.original_name,
        "mime": video.mime,
        "size_bytes": video.size_bytes,
        "duration_ms": video.duration_ms,
        "width": video.width,
        "height": video.height,
        "rotation": video.rotation,
        "fps": round(video.fps_num / max(1, video.fps_den), 2),
        "is_vfr": video.is_vfr,
        "codec": video.codec,
        "has_audio": video.has_audio,
        "ingest_status": video.ingest_status,
        "quality_flags": video.quality_flags_json,
        "stream_url": f"/api/videos/{video.id}/stream",
        "presigned_url": presigned_url,
    }


@app.get("/api/videos/{video_id}/stream")
def stream_video(
    video_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """支援 iPhone Safari HTTP Range (206 Partial Content) 的受權限保護串流端點。"""
    video = db.get(Video, video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到指定的影片")
    verify_owner(db, current_user, video.owner_id, "video", video.id)

    storage = get_storage_service()
    candidates = [k for k in [video.proxy_storage_key, video.storage_key] if k]
    head = None
    target_key = None
    for k in candidates:
        try:
            head = storage.head_object(k)
            target_key = k
            break
        except Exception:
            continue

    if not head or not target_key:
        raise APIError(404, "STORAGE_OBJECT_NOT_FOUND", "物件儲存中找不到影片檔案，可能伺服器重新啟動中")

    total_size = int(head["size_bytes"])
    range_header = request.headers.get("range") or request.headers.get("Range")

    if range_header and range_header.startswith("bytes="):
        byte_range = range_header.replace("bytes=", "").strip()
        start_str, end_str = (byte_range.split("-", 1) + [""])[:2]
        start_byte = int(start_str) if start_str else 0
        end_byte = int(end_str) if end_str else min(total_size - 1, start_byte + 4 * 1024 * 1024 - 1)
        end_byte = min(end_byte, total_size - 1)
        if start_byte >= total_size or start_byte > end_byte:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{total_size}"},
            )
        obj = storage.get_object_range(target_key, start_byte, end_byte)
        chunk_len = end_byte - start_byte + 1
        return StreamingResponse(
            obj["body"].iter_chunks(chunk_size=256 * 1024),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start_byte}-{end_byte}/{total_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_len),
                "Cache-Control": "private, max-age=300",
            },
        )

    obj = storage.get_object_range(target_key)
    return StreamingResponse(
        obj["body"].iter_chunks(chunk_size=256 * 1024),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(total_size),
            "Cache-Control": "private, max-age=300",
        },
    )


@app.get("/api/storage/file")
def get_storage_file(
    key: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> Response:
    storage = get_storage_service()
    try:
        head = storage.head_object(key)
        obj = storage.get_object_range(key)
        return StreamingResponse(
            obj["body"].iter_chunks(chunk_size=256 * 1024),
            media_type=head.get("content_type", "application/octet-stream"),
        )
    except Exception as exc:
        raise APIError(404, "STORAGE_FILE_NOT_FOUND", f"找不到指定儲存物件: {exc}") from exc


# ============================================================================
# 6. Background Jobs (Enqueue / Status / Retry / Cancel)
# ============================================================================


@app.post("/api/videos/{video_id}/analyze")
def enqueue_video_analysis(
    video_id: str,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """冪等排入背景分析任務：若該影片已有 queued 或活躍 running 任務且未指定 force，直接回傳既有 Job。"""
    video = db.get(Video, video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到指定的影片")
    verify_owner(db, current_user, video.owner_id, "video", video.id)

    if not force:
        existing_job = db.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.video_id == video.id,
                AnalysisJob.status.in_(["queued", "running", "completed"]),
            )
            .order_by(desc(AnalysisJob.created_at))
        )
        if existing_job:
            # 若為 running 但 heartbeat 逾時超過 180 秒，允許往下建立或重啟
            is_stale = (
                existing_job.status == "running"
                and existing_job.heartbeat_at is not None
                and (utcnow() - existing_job.heartbeat_at).total_seconds() > 180
            )
            if not is_stale:
                return {
                    "job_id": existing_job.id,
                    "video_id": video.id,
                    "status": existing_job.status,
                    "stage": existing_job.stage,
                    "progress": existing_job.progress,
                    "idempotent_reused": True,
                }

    s = get_settings()
    job = AnalysisJob(
        owner_id=current_user.id,
        video_id=video.id,
        status="queued",
        stage="queued",
        progress=0,
        attempt_count=0,
        max_attempts=3,
        analysis_version=s.analysis_model_version,
        logs_json=[
            {
                "timestamp": utcnow().isoformat(),
                "stage": "queued",
                "progress": 0,
                "message": "分析任務已排入佇列",
            }
        ],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    rq_id = _dispatch_analysis_job(job.id)
    if rq_id:
        job.rq_job_id = rq_id
        db.commit()

    return {
        "job_id": job.id,
        "video_id": video.id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "idempotent_reused": False,
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise APIError(404, "JOB_NOT_FOUND", "找不到指定的背景任務")
    verify_owner(db, current_user, job.owner_id, "analysis_job", job.id)

    is_stale = False
    if job.status == "running" and job.heartbeat_at is not None:
        hb = job.heartbeat_at if job.heartbeat_at.tzinfo else job.heartbeat_at.replace(tzinfo=UTC)
        if (utcnow() - hb).total_seconds() > 180:
            is_stale = True

    return {
        "id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "analysis_version": job.analysis_version,
        "is_stale": is_stale,
        "logs": job.logs_json,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
    }


@app.post("/api/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise APIError(404, "JOB_NOT_FOUND", "找不到指定的背景任務")
    verify_owner(db, current_user, job.owner_id, "analysis_job", job.id)

    if job.attempt_count >= job.max_attempts:
        raise APIError(
            400,
            "JOB_MAX_RETRIES_EXCEEDED",
            f"此任務已達最大重試次數上限 ({job.max_attempts} 次)",
        )

    is_stale_running = False
    if job.status == "running" and job.heartbeat_at is not None:
        hb = job.heartbeat_at if job.heartbeat_at.tzinfo else job.heartbeat_at.replace(tzinfo=UTC)
        if (utcnow() - hb).total_seconds() > 60:
            is_stale_running = True

    if job.status not in ("failed", "cancelled") and not is_stale_running:
        raise APIError(400, "JOB_NOT_RETRYABLE", f"目前狀態 ({job.status}) 無需重試")

    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.error_code = None
    job.error_message = None
    logs = list(job.logs_json or [])
    logs.append(
        {
            "timestamp": utcnow().isoformat(),
            "stage": "queued",
            "progress": 0,
            "message": f"使用者觸發安全重試 (目前累計嘗試 {job.attempt_count}/{job.max_attempts})",
        }
    )
    job.logs_json = logs
    db.commit()

    rq_id = _dispatch_analysis_job(job.id)
    if rq_id:
        job.rq_job_id = rq_id
        db.commit()

    return {
        "id": job.id,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise APIError(404, "JOB_NOT_FOUND", "找不到指定的背景任務")
    verify_owner(db, current_user, job.owner_id, "analysis_job", job.id)

    if job.status == "completed":
        raise APIError(400, "JOB_ALREADY_COMPLETED", "已完成的任務無法取消")

    job.status = "cancelled"
    job.stage = "cancelled"
    job.finished_at = utcnow()
    logs = list(job.logs_json or [])
    logs.append(
        {
            "timestamp": utcnow().isoformat(),
            "stage": "cancelled",
            "progress": job.progress,
            "message": "使用者手動取消分析任務",
        }
    )
    job.logs_json = logs
    db.commit()
    return {"id": job.id, "status": "cancelled"}


# ============================================================================
# 7. Swing Segments, Events, Pose, Metrics & Manual Calibration
# ============================================================================


def _serialize_segment(db: Session, seg: SwingSegment, include_detail: bool = False) -> dict[str, Any]:
    events = db.scalars(
        select(SwingEvent).where(SwingEvent.segment_id == seg.id).order_by(SwingEvent.time_ms.asc())
    ).all()
    metrics = db.scalars(select(SwingMetric).where(SwingMetric.segment_id == seg.id)).all()
    score = db.scalar(
        select(SwingScore)
        .where(SwingScore.segment_id == seg.id)
        .order_by(desc(SwingScore.computed_at))
    )
    artifact = db.scalar(select(PoseArtifact).where(PoseArtifact.segment_id == seg.id))
    feedbacks = db.scalars(
        select(AnalysisFeedback)
        .where(AnalysisFeedback.segment_id == seg.id)
        .order_by(desc(AnalysisFeedback.created_at))
    ).all()

    event_map = {e.event_name: e.time_ms for e in events}

    video_row = db.get(Video, seg.video_id)
    cov_val = score.coverage if score else 0.0
    q_meta = (artifact.quality_metadata if artifact and artifact.quality_metadata else {}) or {}
    r_flags = seg.review_flags_json or []
    is_unreliable = bool(
        q_meta.get("unreliable_for_ranking", False)
        or q_meta.get("is_ambiguous", False)
        or "candidate_ambiguous" in r_flags
        or "timing_anomaly" in r_flags
        or seg.review_status == "needs_review"
    )
    base: dict[str, Any] = {
        "id": seg.id,
        "video_id": seg.video_id,
        "session_id": video_row.session_id if video_row else "",
        "sequence_no": seg.sequence_no,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "duration_ms": max(0, seg.end_ms - seg.start_ms),
        "label": seg.label,
        "ball_strike_status": seg.ball_strike_status,
        "confidence": seg.confidence,
        "review_status": seg.review_status,
        "review_flags": seg.review_flags_json,
        "unreliable_for_ranking": is_unreliable,
        "quality_metadata": q_meta,
        "version": seg.version,
        "model_version": seg.version,
        "manual_override": seg.manual_override,
        "notes": seg.notes,
        "top_time_ms": event_map.get("top"),
        "impact_time_ms": event_map.get("impact_estimated"),
        "overall_score": score.overall_nullable if score else None,
        "ig_visual_score": score.ig_visual_score if score else None,
        "partial_score": score.partial_score if score else True,
        "coverage": cov_val,
        "coverage_ratio": cov_val,
        "score_version": score.score_version if score else "score-v1",
        "score_explanation": score.explanation if score else "",
        "subscores": score.subscores_json if score else {},
        "ball_trajectory": (
            q_meta.get("ball_trajectory", [])
            if q_meta
            else []
        ),

        "events": [
            {
                "id": e.id,
                "event_name": e.event_name,
                "time_ms": e.time_ms,
                "confidence": e.confidence,
                "detection_source": e.detection_source,
                "model_version": e.model_version,
                "rationale": e.rationale,
            }
            for e in events
        ],
        "metrics": [
            {
                "id": m.id,
                "metric_key": m.metric_key,
                "value": m.value,
                "unit": m.unit,
                "confidence": m.confidence,
                "source": m.source,
                "observability": m.observability,
            }
            for m in metrics
        ],
        "action_differences": [
            d.model_dump()
            for d in compute_swing_action_differences(
                subscores=score.subscores_json if score else {},
                events=[{"event_name": e.event_name, "time_ms": e.time_ms} for e in events],
                metrics=[{"metric_key": m.metric_key, "value": m.value} for m in metrics],
            )
        ],
    }

    if include_detail:
        kf_list = artifact.keyframes_json if artifact else []
        q_meta = (artifact.quality_metadata if artifact and artifact.quality_metadata else {}) or {}
        base["ball_trajectory"] = q_meta.get("ball_trajectory", [])
        base["keyframes"] = kf_list
        base["pose_artifact"] = {
            "quality_metadata": q_meta,
            "keyframes": kf_list,
        }
        base["feedback_history"] = [
            {
                "id": f.id,
                "category": f.category,
                "before": f.before_json,
                "after": f.after_json,
                "note": f.note,
                "created_at": f.created_at.isoformat(),
            }
            for f in feedbacks
        ]
    return base


@app.get("/api/videos/{video_id}/swings")
def list_video_swings(
    video_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    label: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    video = db.get(Video, video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到指定的影片")
    verify_owner(db, current_user, video.owner_id, "video", video.id)

    stmt = (
        select(SwingSegment)
        .where(SwingSegment.video_id == video.id, SwingSegment.start_ms >= cursor)
        .order_by(SwingSegment.start_ms.asc())
        .limit(limit + 1)
    )
    if label:
        stmt = stmt.where(SwingSegment.label == label)

    rows = list(db.scalars(stmt).all())
    next_cursor: int | None = None
    if len(rows) > limit:
        next_cursor = rows[limit].start_ms
        rows = rows[:limit]

    return {
        "video_id": video.id,
        "items": [_serialize_segment(db, r, include_detail=False) for r in rows],
        "next_cursor": next_cursor,
    }


def _reanalyze_segment_in_place(db: Session, video: Video, seg: SwingSegment) -> None:
    """當使用者手動新增或拉動揮桿邊界時，針對新時間區段重新執行精掃與 Score v1 計算。"""
    s = get_settings()
    storage = get_storage_service()
    user_setting = db.scalar(select(UserSetting).where(UserSetting.owner_id == video.owner_id))
    custom_weights = (
        user_setting.score_weights_json
        if (user_setting and user_setting.score_weights_json)
        else None
    )

    with tempfile.TemporaryDirectory(prefix="gsl_manual_seg_") as tmp_dir:
        src_key = video.proxy_storage_key or video.storage_key
        local_v = Path(tmp_dir) / "video.mp4"
        try:
            storage.download_to_path(src_key, local_v)
            detector = CoarseToFineDetector(model_version=s.analysis_model_version)
            cand = detector.analyze_single_window(
                video_path=local_v,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                sequence_no=seg.sequence_no,
            )
        except Exception:
            cand = None

        if cand:
            for old_ev in list(seg.events):
                db.delete(old_ev)
            for old_m in list(seg.metrics):
                db.delete(old_m)
            for old_sc in list(seg.scores):
                db.delete(old_sc)
            if seg.pose_artifact:
                db.delete(seg.pose_artifact)
            db.flush()

            for ev in cand.events:
                db.add(
                    SwingEvent(
                        segment_id=seg.id,
                        event_name=ev.event_name,
                        time_ms=ev.time_ms,
                        confidence=ev.confidence,
                        detection_source="manual_calibrated",
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
                score_version=s.scoring_version,
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


@app.post("/api/videos/{video_id}/swings", status_code=201)
def create_manual_swing(
    video_id: str,
    payload: CreateManualSwingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    video = db.get(Video, video_id)
    if not video:
        raise APIError(404, "VIDEO_NOT_FOUND", "找不到指定的影片")
    verify_owner(db, current_user, video.owner_id, "video", video.id)

    if payload.end_ms <= payload.start_ms:
        raise APIError(400, "INVALID_TIME_RANGE", "結束時間必須大於開始時間")

    existing_count = len(
        db.scalars(select(SwingSegment).where(SwingSegment.video_id == video.id)).all()
    )
    seg = SwingSegment(
        owner_id=current_user.id,
        video_id=video.id,
        sequence_no=existing_count + 1,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
        label=payload.label,
        ball_strike_status=payload.ball_strike_status,
        confidence=0.95,
        review_status="confirmed",
        review_flags_json=[],
        version=get_settings().analysis_model_version,
        manual_override=True,
        notes=payload.notes,
    )
    db.add(seg)
    db.flush()

    _reanalyze_segment_in_place(db, video, seg)
    db.add(
        AnalysisFeedback(
            owner_id=current_user.id,
            segment_id=seg.id,
            category="manual_create",
            before_json={},
            after_json={
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "label": seg.label,
                "ball_strike_status": seg.ball_strike_status,
            },
            note=payload.notes or "使用者手動新增揮桿片段",
            labeler=current_user.email,
        )
    )
    db.commit()
    db.refresh(seg)
    return _serialize_segment(db, seg, include_detail=True)


@app.get("/api/swings/{swing_id}")
def get_swing_detail(
    swing_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    seg = db.get(SwingSegment, swing_id)
    if not seg:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")
    verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)
    return _serialize_segment(db, seg, include_detail=True)


@app.get("/api/swings/{swing_id}/posture-comparison")
def get_swing_posture_comparison(
    swing_id: str,
    ref_id: str | None = Query(None, description="特定示範揮桿 ID"),
    club_type: str | None = Query(None, description="球桿分類篩選"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    R3: 離線量化姿勢比較端點 (Offline Quantitative Posture Comparison)
    回傳 4 大階段（Address, Top, Impact, Finish）客觀可解釋的 2D 骨架與運動學差異。
    """
    seg = db.get(SwingSegment, swing_id)
    if not seg:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")
    verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)

    ref = None
    target_club = club_type

    if ref_id:
        # 使用者指定特定 Reference ID 時，嚴格依該 ID 檢索，不存在則不 fallback
        ref = db.get(ReferenceSwing, ref_id)
        if ref:
            target_club = ref.club_type
    elif club_type:
        # 使用者指定球桿時，僅在該球桿類別中尋找預設或合格示範，絕不跨球桿 fallback
        ref = db.scalar(
            select(ReferenceSwing)
            .where(ReferenceSwing.club_type == club_type)
            .order_by(desc(ReferenceSwing.is_default), desc(ReferenceSwing.imported_at))
        )
    else:
        # 預設依揮桿所屬場次之球桿尋找
        sess = db.get(PracticeSession, seg.video.session_id) if (seg.video and seg.video.session_id) else None
        target_club = getattr(sess, "club", "7I") or "7I"
        ref = db.scalar(
            select(ReferenceSwing)
            .where(ReferenceSwing.club_type == target_club)
            .order_by(desc(ReferenceSwing.is_default), desc(ReferenceSwing.imported_at))
        )

    ref_dict = {
        "id": ref.id if ref else "",
        "club_type": target_club or "7I",
        "title": ref.title if ref else "",
        "camera_angle": ref.camera_angle if ref else "DTL",
        "event_timestamps": ref.event_timestamps if ref else {},
        "calibration_params": ref.calibration_params if ref else {},
        "pose_artifact": ref.pose_artifact if ref else {},
    }
    user_serialized = _serialize_segment(db, seg, include_detail=True)
    report = compute_quantitative_posture_comparison(user_serialized, ref_dict)
    return report.model_dump()


@app.post("/api/swings/{swing_id}/deep-insight")
def get_swing_deep_insight(
    swing_id: str,
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    seg = db.get(SwingSegment, swing_id)
    if not seg:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")
    verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)

    diff_id = payload.get("diff_id", "")
    serialized = _serialize_segment(db, seg, include_detail=True)
    action_diffs = [ActionDifference(**d) for d in serialized.get("action_differences", [])]
    target_diff = next((d for d in action_diffs if d.id == diff_id), None)
    if not target_diff:
        if action_diffs:
            target_diff = action_diffs[0]
        else:
            target_diff = ActionDifference(
                id="default_diff",
                title="動作協調與穩定性分析",
                phase="top",
                time_ms=seg.start_ms,
                magnitude="基準動作",
                evidence_text="依據可觀測 2D 關節座標分析。",
                suggested_cue="維持體感流暢度。",
                retest_target="完成揮桿穩定平衡。",
                confidence=0.85,
            )

    report = generate_deep_vision_insight(target_diff, serialized)
    return report.model_dump()


@app.patch("/api/swings/{swing_id}")
def patch_swing_segment(
    swing_id: str,
    payload: PatchSwingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    seg = db.get(SwingSegment, swing_id)
    if not seg:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")
    verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)

    before_state = {
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "label": seg.label,
        "ball_strike_status": seg.ball_strike_status,
        "review_status": seg.review_status,
        "notes": seg.notes,
    }

    boundaries_changed = False
    if payload.start_ms is not None and payload.start_ms != seg.start_ms:
        seg.start_ms = payload.start_ms
        boundaries_changed = True
    if payload.end_ms is not None and payload.end_ms != seg.end_ms:
        seg.end_ms = payload.end_ms
        boundaries_changed = True

    if seg.end_ms <= seg.start_ms:
        raise APIError(400, "INVALID_TIME_RANGE", "結束時間必須大於開始時間")

    if payload.label is not None:
        seg.label = payload.label
        if payload.label == "practice_swing" and payload.ball_strike_status is None:
            seg.ball_strike_status = "no_ball"
    if payload.ball_strike_status is not None:
        seg.ball_strike_status = payload.ball_strike_status
    if payload.review_status is not None:
        seg.review_status = payload.review_status
    else:
        seg.review_status = "confirmed"
    if payload.notes is not None:
        seg.notes = payload.notes

    seg.manual_override = True

    video = db.get(Video, seg.video_id)
    if boundaries_changed and video:
        _reanalyze_segment_in_place(db, video, seg)

    after_state = {
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "label": seg.label,
        "ball_strike_status": seg.ball_strike_status,
        "review_status": seg.review_status,
        "notes": seg.notes,
    }

    db.add(
        AnalysisFeedback(
            owner_id=current_user.id,
            segment_id=seg.id,
            category=payload.feedback_category or "manual_calibration",
            before_json=before_state,
            after_json=after_state,
            note=payload.feedback_note or payload.notes or "人工校正時間碼與標籤",
            labeler=current_user.email,
        )
    )
    db.commit()
    db.refresh(seg)
    return _serialize_segment(db, seg, include_detail=True)


@app.delete("/api/swings/{swing_id}")
def delete_swing_segment(
    swing_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    seg = db.get(SwingSegment, swing_id)
    if not seg:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")
    verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)

    db.add(
        AuditEvent(
            actor_id=current_user.id,
            object_type="swing_segment",
            object_id=seg.id,
            action="manual_delete_segment",
            metadata_json={"start_ms": seg.start_ms, "end_ms": seg.end_ms},
        )
    )
    db.delete(seg)
    db.commit()
    return {"status": "deleted", "swing_id": swing_id}


# ============================================================================
# 8. Session Report, Rankings, Favorites & AI Coach
# ============================================================================


@app.post("/api/sessions/{session_id}/favorites")
def toggle_favorite(
    session_id: str,
    payload: FavoriteToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sess = db.get(PracticeSession, session_id)
    if not sess:
        raise APIError(404, "SESSION_NOT_FOUND", "找不到指定的練習場次")
    verify_owner(db, current_user, sess.owner_id, "practice_session", sess.id)

    seg = db.get(SwingSegment, payload.segment_id)
    if not seg or seg.owner_id != current_user.id:
        raise APIError(404, "SWING_NOT_FOUND", "找不到指定的揮桿片段")

    existing = db.scalar(
        select(Favorite).where(
            Favorite.owner_id == current_user.id,
            Favorite.segment_id == seg.id,
            Favorite.category == payload.category,
        )
    )
    if payload.remove:
        if existing:
            db.delete(existing)
            db.commit()
        return {"status": "removed", "segment_id": seg.id, "category": payload.category}

    if existing:
        existing.rank_override = payload.rank_override
    else:
        db.add(
            Favorite(
                owner_id=current_user.id,
                segment_id=seg.id,
                category=payload.category,
                rank_override=payload.rank_override,
            )
        )
    db.commit()
    return {
        "status": "saved",
        "segment_id": seg.id,
        "category": payload.category,
        "rank_override": payload.rank_override,
    }


@app.get("/api/sessions/{session_id}/report")
async def get_session_report(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sess = db.get(PracticeSession, session_id)
    if not sess:
        raise APIError(404, "SESSION_NOT_FOUND", "找不到指定的練習場次")
    verify_owner(db, current_user, sess.owner_id, "practice_session", sess.id)

    videos = db.scalars(
        select(Video).where(Video.session_id == sess.id).order_by(Video.created_at.asc())
    ).all()
    video_ids = [v.id for v in videos]
    segments: list[SwingSegment] = []
    if video_ids:
        segments = list(
            db.scalars(
                select(SwingSegment)
                .where(SwingSegment.video_id.in_(video_ids))
                .order_by(SwingSegment.sequence_no.asc(), SwingSegment.start_ms.asc())
            ).all()
        )

    serialized_swings = [_serialize_segment(db, s, include_detail=False) for s in segments]
    valid_swings = [
        s for s in serialized_swings if s["label"] == "valid_swing" and s["review_status"] != "rejected"
    ]
    practice_swings = [s for s in serialized_swings if s["label"] == "practice_swing"]
    needs_review = [s for s in serialized_swings if s["review_status"] == "needs_review"]
    scorable_swings = [s for s in serialized_swings if s["overall_score"] is not None]

    overall_scores = [float(s["overall_score"]) for s in scorable_swings]
    avg_overall = round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else None

    # 計算前半場 vs 後半場趨勢
    trend_delta: float | None = None
    if len(overall_scores) >= 2:
        mid = len(overall_scores) // 2
        first_half = sum(overall_scores[:mid]) / len(overall_scores[:mid])
        second_half = sum(overall_scores[mid:]) / len(overall_scores[mid:])
        trend_delta = round(second_half - first_half, 1)

    # 各分項平均
    subscore_averages: dict[str, float | None] = {}
    for skey in DEFAULT_WEIGHTS:
        vals = [
            float(s["subscores"][skey]["score"])
            for s in scorable_swings
            if skey in s.get("subscores", {}) and s["subscores"][skey].get("score") is not None
        ]
        subscore_averages[skey] = round(sum(vals) / len(vals), 1) if vals else None

    # 取得使用者手動精選與排除設定
    fav_rows = db.scalars(select(Favorite).where(Favorite.owner_id == current_user.id)).all()
    fav_dicts = [
        {"segment_id": f.segment_id, "category": f.category, "rank_override": f.rank_override}
        for f in fav_rows
    ]
    rankings = rank_session_swings(serialized_swings, favorites=fav_dicts, top_k=5)

    # AI / 規則式教練分析報告
    user_setting = db.scalar(select(UserSetting).where(UserSetting.owner_id == current_user.id))
    s_cfg = get_settings()
    provider_type = (user_setting.llm_provider if user_setting else None) or s_cfg.llm_provider
    api_key = (user_setting.llm_api_key_secret if user_setting else None) or s_cfg.llm_api_key

    summary_dict = {
        "session_id": sess.id,
        "club": sess.club,
        "handedness": sess.handedness,
        "total_swings": len(serialized_swings),
        "valid_swings": len(valid_swings),
        "practice_swings": len(practice_swings),
        "scorable_ratio": round(len(scorable_swings) / max(1, len(valid_swings)), 3),
        "average_overall_score": avg_overall,
        "trend_delta": trend_delta,
        "subscore_averages": subscore_averages,
    }

    coach_provider: GolfCoachProvider
    if s_cfg.enable_external_llm and provider_type == "gemini" and api_key:
        chosen_model = (
            (user_setting.llm_model.strip() if user_setting and user_setting.llm_model else None)
            or s_cfg.gemini_model
            or "gemini-3.8-flash"
        )
        coach_provider = GeminiCoachProvider(
            api_key=api_key,
            model=chosen_model,
        )
    elif s_cfg.enable_external_llm and provider_type == "openai-compatible" and api_key:
        coach_provider = OpenAICompatibleCoachProvider(
            api_key=api_key,
            base_url=(user_setting.llm_base_url if user_setting else s_cfg.llm_base_url),
            model=(user_setting.llm_model if user_setting else s_cfg.llm_model),
            max_budget_usd=max(1.0, s_cfg.llm_max_budget_usd),
        )
    else:
        coach_provider = RuleBasedCoachProvider()

    regenerate = request.query_params.get("regenerate") in ("true", "1")
    active_provider = provider_type if s_cfg.enable_external_llm else "none"
    cache_key = f"{sess.id}:{len(serialized_swings)}:{active_provider}"

    if not regenerate and cache_key in _COACH_REPORT_CACHE:
        coach_report_data = _COACH_REPORT_CACHE[cache_key]
    else:
        coach_report = await coach_provider.generate_feedback(summary_dict, serialized_swings)
        coach_report_data = coach_report.model_dump()
        _COACH_REPORT_CACHE[cache_key] = coach_report_data

    return {
        "session": _serialize_session(db, sess),
        "summary": summary_dict,
        "swings": serialized_swings,
        "needs_review_swings": needs_review,
        "rankings": rankings,
        "favorites": fav_dicts,
        "coach_report": coach_report_data,
    }


# ============================================================================
# 9. Exports (Single & 2-3 Swing Compilation MP4)
# ============================================================================


@app.post("/api/exports", status_code=201)
def create_export(
    payload: CreateExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.idempotency_key:
        existing_exp = db.scalar(
            select(ExportJob).where(
                ExportJob.owner_id == current_user.id,
                ExportJob.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_exp:
            return {
                "id": existing_exp.id,
                "state": existing_exp.state,
                "layout": existing_exp.layout,
                "segment_ids": existing_exp.segment_ids,
                "duration_ms": existing_exp.duration_ms,
                "download_url": f"/api/exports/{existing_exp.id}/download"
                if existing_exp.state == "completed"
                else None,
                "idempotent_reused": True,
            }

    video_ids: list[str] = []
    for seg_id in payload.segment_ids:
        seg = db.get(SwingSegment, seg_id)
        if not seg:
            raise APIError(404, "SWING_NOT_FOUND", f"找不到揮桿片段: {seg_id}")
        verify_owner(db, current_user, seg.owner_id, "swing_segment", seg.id)
        if seg.video_id not in video_ids:
            video_ids.append(seg.video_id)

    exp = ExportJob(
        owner_id=current_user.id,
        video_ids=video_ids,
        segment_ids=payload.segment_ids,
        layout=payload.layout,
        format=payload.format,
        state="queued",
        idempotency_key=payload.idempotency_key,
        expires_at=utcnow() + timedelta(days=get_settings().data_retention_days),
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    _dispatch_export_job(exp.id)
    db.refresh(exp)

    return {
        "id": exp.id,
        "state": exp.state,
        "layout": exp.layout,
        "segment_ids": exp.segment_ids,
        "duration_ms": exp.duration_ms,
        "download_url": f"/api/exports/{exp.id}/download" if exp.state == "completed" else None,
        "idempotent_reused": False,
    }


@app.get("/api/exports")
def list_exports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ExportJob)
        .where(ExportJob.owner_id == current_user.id)
        .order_by(desc(ExportJob.created_at))
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "state": r.state,
                "layout": r.layout,
                "format": r.format,
                "segment_ids": r.segment_ids,
                "duration_ms": r.duration_ms,
                "size_bytes": r.size_bytes,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat(),
                "download_url": f"/api/exports/{r.id}/download" if r.state == "completed" else None,
            }
            for r in rows
        ]
    }


@app.get("/api/exports/{export_id}")
def get_export_detail(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    exp = db.get(ExportJob, export_id)
    if not exp:
        raise APIError(404, "EXPORT_NOT_FOUND", "找不到指定的匯出任務")
    verify_owner(db, current_user, exp.owner_id, "export", exp.id)

    presigned_url = (
        get_storage_service().generate_presigned_get_url(exp.storage_key)
        if (exp.state == "completed" and exp.storage_key)
        else None
    )
    return {
        "id": exp.id,
        "state": exp.state,
        "layout": exp.layout,
        "format": exp.format,
        "segment_ids": exp.segment_ids,
        "duration_ms": exp.duration_ms,
        "size_bytes": exp.size_bytes,
        "error_message": exp.error_message,
        "download_url": f"/api/exports/{exp.id}/download" if exp.state == "completed" else None,
        "presigned_url": presigned_url,
        "expires_at": exp.expires_at.isoformat(),
    }


@app.get("/api/exports/{export_id}/download")
def download_export_mp4(
    export_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    exp = db.get(ExportJob, export_id)
    if not exp:
        raise APIError(404, "EXPORT_NOT_FOUND", "找不到指定的匯出任務")
    verify_owner(db, current_user, exp.owner_id, "export", exp.id)
    if exp.state != "completed" or not exp.storage_key:
        raise APIError(400, "EXPORT_NOT_READY", f"匯出任務狀態為 {exp.state}，尚不可下載")

    storage = get_storage_service()
    obj = storage.get_object_range(exp.storage_key)
    filename = f"golf_swing_{exp.id[:8]}_{exp.layout.replace(':', 'x')}.mp4"
    return StreamingResponse(
        obj["body"].iter_chunks(chunk_size=256 * 1024),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(obj["content_length"]),
        },
    )


# ============================================================================
# 10. Settings & Score Weight Recalculation
# ============================================================================


@app.get("/api/settings")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    st = db.scalar(select(UserSetting).where(UserSetting.owner_id == current_user.id))
    if not st:
        st = UserSetting(owner_id=current_user.id, score_weights_json=dict(DEFAULT_WEIGHTS))
        db.add(st)
        db.commit()
        db.refresh(st)

    weights = dict(DEFAULT_WEIGHTS)
    if st.score_weights_json:
        weights.update(st.score_weights_json)

    # 絕不回傳明文 API Key 至前端
    return {
        "default_club": st.default_club,
        "handedness": st.handedness,
        "camera_angle": st.camera_angle,
        "score_weights": weights,
        "data_retention_days": st.data_retention_days,
        "llm_provider": st.llm_provider,
        "llm_base_url": st.llm_base_url,
        "llm_model": st.llm_model,
        "has_llm_api_key": bool(st.llm_api_key_secret or get_settings().llm_api_key),
        "llm_consent_frames": st.llm_consent_frames,
        "enable_external_llm": get_settings().enable_external_llm,
        "coach_mode": "offline" if not get_settings().enable_external_llm else "external_allowed",
    }


@app.put("/api/settings")
def update_user_settings(
    payload: UpdateSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    st = db.scalar(select(UserSetting).where(UserSetting.owner_id == current_user.id))
    if not st:
        st = UserSetting(owner_id=current_user.id)
        db.add(st)
        db.flush()

    st.default_club = payload.default_club
    st.handedness = payload.handedness
    st.camera_angle = "DTL"
    st.data_retention_days = payload.data_retention_days
    st.llm_provider = payload.llm_provider
    st.llm_base_url = payload.llm_base_url
    st.llm_model = payload.llm_model
    st.llm_consent_frames = payload.llm_consent_frames
    if payload.llm_api_key is not None and payload.llm_api_key.strip() != "":
        st.llm_api_key_secret = payload.llm_api_key.strip()
    if payload.score_weights is not None:
        merged_w = dict(DEFAULT_WEIGHTS)
        for k, v in payload.score_weights.items():
            if k in merged_w and float(v) >= 0:
                merged_w[k] = float(v)
        st.score_weights_json = merged_w

    # 若指定重算或是更新了權重，針對使用者既有揮桿重新計算分數（不覆蓋人工註記與時間碼）
    recalculated_count = 0
    if payload.score_weights is not None or payload.recalculate_session_id:
        segs = db.scalars(
            select(SwingSegment).where(SwingSegment.owner_id == current_user.id)
        ).all()
        for seg in segs:
            metrics = db.scalars(
                select(SwingMetric).where(SwingMetric.segment_id == seg.id)
            ).all()
            art = db.scalar(select(PoseArtifact).where(PoseArtifact.segment_id == seg.id))
            m_dicts = [
                {
                    "metric_key": m.metric_key,
                    "value": m.value,
                    "unit": m.unit,
                    "confidence": m.confidence,
                    "source": m.source,
                    "observability": m.observability,
                }
                for m in metrics
            ]
            score_res = compute_swing_score(
                metrics=m_dicts,
                quality_metadata=art.quality_metadata if art else {},
                weights=st.score_weights_json,
                score_version=f"{get_settings().scoring_version}-calibrated",
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
            recalculated_count += 1

    db.commit()
    return {
        "status": "updated",
        "recalculated_segments": recalculated_count,
        "default_club": st.default_club,
        "handedness": st.handedness,
        "score_weights": st.score_weights_json or DEFAULT_WEIGHTS,
        "llm_provider": st.llm_provider,
        "has_llm_api_key": bool(st.llm_api_key_secret or get_settings().llm_api_key),
    }
