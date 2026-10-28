"""
apps/api/routers/reference_swings.py — 完整球桿專業示範揮桿資料庫與串流 API
支援 17 種球桿分類、來源與授權追溯、等比例畫面對齊校正、事件時間碼與 HTTP 206 串流。
"""
import hashlib
import json
import logging
import math
import os
import shutil
import uuid
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select, update
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.models import ReferenceSwing, User, utcnow
from packages.analysis.detection.scanner import CoarseToFineDetector
from packages.storage.s3_client import get_storage_service

logger = logging.getLogger("gsl.reference_swings")

router = APIRouter(prefix="/api/reference-swings", tags=["Reference Swings"])


def _analyze_reference_video(
    video_path: Path,
    duration_ms: int,
    v_width: int,
    v_height: int,
    manual_events: dict[str, int] | None = None,
) -> tuple[str, dict[str, int], dict[str, Any], dict[str, Any], str]:
    """
    接入現有影片分析管線：
    1. 優先採用合法手動校準時間碼
    2. 自動啟動 CoarseToFineDetector 抽取真實揮桿事件與骨架
    3. 信心度 >= 0.50 且關鍵事件齊全時標記 completed；否則安全標記 needs_calibration，杜絕百分比偽造
    """
    if manual_events and isinstance(manual_events, dict):
        top = manual_events.get("top", 0)
        impact = manual_events.get("impact", 0)
        if 0 < top < impact <= duration_ms:
            return (
                "completed",
                manual_events,
                {},
                {
                    "scale": 1.0,
                    "zoom": 1.0,
                    "offset_x": 0,
                    "offset_y": 0,
                    "video_width": v_width,
                    "video_height": v_height,
                    "torso_length": 100.0,
                },
                "由使用者手動校正標記時間碼",
            )

    try:
        detector = CoarseToFineDetector()
        detected_segments, _ = detector.analyze_video(video_path, duration_ms)
        if detected_segments:
            best_cand = max(detected_segments, key=lambda s: getattr(s, "confidence", 0))
            ev_map = {ev.event_name: ev.time_ms for ev in best_cand.events}
            
            has_top = "top" in ev_map
            impact_key = "impact" if "impact" in ev_map else "impact_estimated" if "impact_estimated" in ev_map else None
            
            pose_art: dict[str, Any] = {}
            if best_cand.keyframes:
                pose_art = {"landmarks": best_cand.keyframes[0].get("landmarks", [])}

            if has_top and impact_key and (ev_map["top"] < ev_map[impact_key]) and best_cand.confidence >= 0.50:
                normalized_events = {
                    "address": ev_map.get("address", best_cand.start_ms),
                    "takeaway": ev_map.get("takeaway", best_cand.start_ms + 200),
                    "top": ev_map["top"],
                    "downswing": ev_map.get("downswing", (ev_map["top"] + ev_map[impact_key]) // 2),
                    "impact": ev_map[impact_key],
                    "follow_through": ev_map.get("follow_through", ev_map[impact_key] + 300),
                    "finish": ev_map.get("finish", best_cand.end_ms),
                }
                calib = {
                    "scale": 1.0,
                    "zoom": 1.0,
                    "offset_x": 0,
                    "offset_y": 0,
                    "video_width": v_width,
                    "video_height": v_height,
                    "torso_length": 100.0,
                }
                return (
                    "completed",
                    normalized_events,
                    pose_art,
                    calib,
                    f"由自動分析管線偵測 (信心度 {best_cand.confidence:.2f})，已完成同步錨點提取",
                )
    except Exception as exc:
        logger.warning(f"示範影片自動分析管線執行異常: {exc}")

    # 若自動分析不可靠，安全降級為 needs_calibration，絕不捏造固定百分比！
    return (
        "needs_calibration",
        {},
        {},
        {
            "scale": 1.0,
            "zoom": 1.0,
            "offset_x": 0,
            "offset_y": 0,
            "video_width": v_width,
            "video_height": v_height,
            "torso_length": 100.0,
        },
        "⚠️ 自動分析信心度不足或未偵測到完整揮桿，需手動校正時間碼",
    )

ALL_CLUB_TYPES = [
    "Driver",
    "3W",
    "5W",
    "3H",
    "4H",
    "5H",
    "4I",
    "5I",
    "6I",
    "7I",
    "8I",
    "9I",
    "PW",
    "GW/AW",
    "SW",
    "LW",
    "Putter",
]


class ReferenceSwingResponse(BaseModel):
    id: str
    club_type: str
    handedness: str
    camera_angle: str
    shot_type: str
    title: str
    reference_author: str
    source_url: str
    content_license: str
    storage_key: str
    thumbnail_url: str | None
    verified_club: bool
    verified_camera_angle: bool
    analysis_status: str
    reference_category: str
    is_verified_standard: bool
    verification_notes: str
    source_type: str
    fps: float
    duration_ms: int
    sha256: str
    event_timestamps: dict[str, Any]
    pose_artifact: dict[str, Any]
    calibration_params: dict[str, Any]
    is_default: bool
    notes: str
    analysis_version: str
    imported_at: datetime
    stream_url: str


class ReferenceCatalogItem(BaseModel):
    club_type: str
    status: str  # "available" | "missing_reference"
    reference_count: int
    default_reference: ReferenceSwingResponse | None = None


class ReferenceCatalogResponse(BaseModel):
    total_clubs: int
    available_clubs: int
    missing_clubs: int
    clubs: list[ReferenceCatalogItem]
    references: list[ReferenceSwingResponse]


class ImportLocalReferenceRequest(BaseModel):
    file_path: str = Field(..., description="本機影片路徑 (限白名單目錄)")
    club_type: str = Field(..., description="球桿分類，需符合 17 種球桿清單")
    handedness: str = Field("right", description="慣用手: right / left")
    camera_angle: str = Field("DTL", description="視角: DTL / face_on / close_up")
    shot_type: str = Field("full_swing", description="揮桿型態: full_swing, pitch, chip, putt")
    title: str = Field(..., description="示範影片標題")
    reference_author: str = Field("社群參考", description="示範選手或教練")
    source_url: str = Field("", description="原始出處或官方連結")
    content_license: str = Field("個人使用授權", description="版權授權模式")
    is_default: bool = Field(True, description="是否設為該球桿預設示範")
    notes: str = Field("", description="備註")
    event_timestamps: dict[str, int] | None = Field(None, description="若已有手動精確標記時間碼可傳入")


class UpdateReferenceRequest(BaseModel):
    title: str | None = None
    reference_author: str | None = None
    source_url: str | None = None
    content_license: str | None = None
    verified_club: bool | None = None
    verified_camera_angle: bool | None = None
    is_default: bool | None = None
    notes: str | None = None
    event_timestamps: dict[str, Any] | None = None
    calibration_params: dict[str, Any] | None = None


def _to_response_item(item: ReferenceSwing) -> ReferenceSwingResponse:
    return ReferenceSwingResponse(
        id=item.id,
        club_type=item.club_type,
        handedness=item.handedness,
        camera_angle=item.camera_angle,
        shot_type=item.shot_type,
        title=item.title,
        reference_author=item.reference_author,
        source_url=item.source_url,
        content_license=item.content_license,
        storage_key=item.storage_key,
        thumbnail_url=item.thumbnail_url,
        verified_club=item.verified_club,
        verified_camera_angle=item.verified_camera_angle,
        analysis_status=item.analysis_status,
        reference_category=getattr(item, "reference_category", "test_fixture"),
        is_verified_standard=bool(getattr(item, "is_verified_standard", False)),
        verification_notes=getattr(item, "verification_notes", ""),
        source_type=getattr(item, "source_type", "local_fixture"),
        fps=item.fps,
        duration_ms=item.duration_ms,
        sha256=item.sha256,
        event_timestamps=item.event_timestamps or {},
        pose_artifact=item.pose_artifact or {},
        calibration_params=item.calibration_params or {
            "scale": 1.0,
            "offset_x": 0,
            "offset_y": 0,
            "zoom": 1.0,
            "torso_length": 100,
        },
        is_default=item.is_default,
        notes=item.notes,
        analysis_version=item.analysis_version,
        imported_at=item.imported_at,
        stream_url=f"/api/reference-swings/{item.id}/stream",
    )


@router.get("", response_model=ReferenceCatalogResponse)
def list_reference_swings(
    club_type: str | None = Query(None, description="依球桿過濾"),
    handedness: str | None = Query(None, description="依慣用手過濾: right / left"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    列出所有參考示範揮桿影片，並提供完整 17 種球桿分類目錄狀態。
    對尚未有影片的球桿標記 missing_reference，確保透明揭露。
    """
    stmt = select(ReferenceSwing)
    if club_type:
        stmt = stmt.where(ReferenceSwing.club_type == club_type)
    if handedness:
        stmt = stmt.where(ReferenceSwing.handedness == handedness)
    stmt = stmt.order_by(ReferenceSwing.club_type.asc(), ReferenceSwing.imported_at.desc())
    items = db.scalars(stmt).all()

    # 彙總各球桿現狀
    club_map: dict[str, list[ReferenceSwing]] = {c: [] for c in ALL_CLUB_TYPES}
    for item in items:
        if item.club_type in club_map:
            club_map[item.club_type].append(item)

    catalog_items: list[ReferenceCatalogItem] = []
    available_count = 0
    missing_count = 0

    for c in ALL_CLUB_TYPES:
        refs = club_map[c]
        default_ref = next((r for r in refs if r.is_default), refs[0] if refs else None)
        status_str = "available" if (refs and any(r.analysis_status == "completed" for r in refs)) else "missing_reference"
        if status_str == "available":
            available_count += 1
        else:
            missing_count += 1

        catalog_items.append(
            ReferenceCatalogItem(
                club_type=c,
                status=status_str,
                reference_count=len(refs),
                default_reference=_to_response_item(default_ref) if default_ref else None,
            )
        )

    return ReferenceCatalogResponse(
        total_clubs=len(ALL_CLUB_TYPES),
        available_clubs=available_count,
        missing_clubs=missing_count,
        clubs=catalog_items,
        references=[_to_response_item(r) for r in items],
    )


@router.get("/default/{club_type}", response_model=ReferenceSwingResponse)
def get_default_reference_swing(
    club_type: str,
    handedness: str = Query("right", description="慣用手"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """取得指定球桿與慣用手的預設示範揮桿。"""
    stmt = (
        select(ReferenceSwing)
        .where(
            ReferenceSwing.club_type == club_type,
            ReferenceSwing.handedness == handedness,
            ReferenceSwing.is_default.is_(True),
            ReferenceSwing.analysis_status == "completed",
        )
        .order_by(ReferenceSwing.imported_at.desc())
    )
    ref = db.scalar(stmt)
    if not ref:
        # 退回非預設之第一支可用示範
        fallback_stmt = (
            select(ReferenceSwing)
            .where(
                ReferenceSwing.club_type == club_type,
                ReferenceSwing.analysis_status == "completed",
            )
            .order_by(ReferenceSwing.imported_at.desc())
        )
        ref = db.scalar(fallback_stmt)

    if not ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"球桿 {club_type} 目前尚無可用的示範揮桿影片 (missing_reference)。請透過匯入功能新增。",
        )
    return _to_response_item(ref)


@router.get("/{reference_id}", response_model=ReferenceSwingResponse)
def get_reference_swing_by_id(
    reference_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """取得指定示範揮桿詳細資料。"""
    ref = db.get(ReferenceSwing, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的示範揮桿影片")
    return _to_response_item(ref)


@router.get("/{reference_id}/stream")
def stream_reference_swing(
    reference_id: str,
    range: str | None = Header(None),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    示範影片串流端點，完整支援 HTTP 206 Partial Content Range 請求。
    相容 WebKit / Safari 與 Chrome 瀏覽器。
    """
    ref = db.get(ReferenceSwing, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的示範揮桿影片")

    storage = get_storage_service()
    try:
        head = storage.head_object(ref.storage_key)
    except Exception as exc:
        logger.error(f"示範影片儲存讀取失敗: {exc}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示範影片實體檔案不存在") from exc

    total_size = int(head.get("size_bytes") or head.get("ContentLength") or 0)
    content_type = head.get("content_type") or "video/mp4"

    # 處理 HTTP Range 標頭
    start_byte = 0
    end_byte = total_size - 1

    if range and range.startswith("bytes="):
        range_val = range.replace("bytes=", "").strip()
        parts = range_val.split("-")
        if parts[0]:
            start_byte = int(parts[0])
        if len(parts) > 1 and parts[1]:
            end_byte = int(parts[1])

    if start_byte >= total_size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total_size}"})

    end_byte = min(end_byte, total_size - 1)
    chunk_len = end_byte - start_byte + 1

    obj = storage.get_object_range(ref.storage_key, start_byte, end_byte)
    body = obj["body"]
    if hasattr(body, "iter_chunks"):
        stream_generator = body.iter_chunks(chunk_size=256 * 1024)
    elif hasattr(body, "iter_lines"):
        stream_generator = body.iter_lines()
    elif callable(body):
        stream_generator = body()
    else:
        stream_generator = body

    headers = {
        "Content-Range": f"bytes {start_byte}-{end_byte}/{total_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_len),
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=86400",
    }
    status_code = status.HTTP_206_PARTIAL_CONTENT if range else status.HTTP_200_OK
    return StreamingResponse(stream_generator, status_code=status_code, headers=headers)


# 安全允許匯入的目錄白名單
ALLOWED_IMPORT_DIRS = [
    (Path(__file__).resolve().parent.parent.parent.parent / "assets").resolve(),
    (Path(__file__).resolve().parent.parent.parent.parent / "storage_data").resolve(),
    (Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures").resolve(),
    (Path.home() / ".golfswinglab").resolve(),
]


def _is_path_allowed(target_path: Path) -> bool:
    target = target_path.resolve()
    for allowed in ALLOWED_IMPORT_DIRS:
        try:
            if target == allowed or allowed in target.parents:
                return True
        except Exception:
            continue
    return False


@router.post("/import-local", response_model=ReferenceSwingResponse, status_code=status.HTTP_201_CREATED)
def import_local_reference_swing(
    payload: ImportLocalReferenceRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    從本機受信任目錄匯入示範影片：
    1. 驗證白名單目錄、副檔名與大小限制 (<= 500MB)
    2. 分塊串流計算 SHA-256 (避免 OOM)
    3. ffprobe 真實解析寬高、FPS 與時長
    4. 事件時間碼真實性：未提供時標記 needs_calibration，嚴禁百分比捏造
    5. 標註為 community_reference 與 unverified
    """
    if payload.club_type not in ALL_CLUB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無效的球桿分類: {payload.club_type}。支援分類: {ALL_CLUB_TYPES}",
        )

    file_path = Path(payload.file_path).resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"本機影片檔案不存在: {file_path}",
        )

    if not _is_path_allowed(file_path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"安全限制：檔案路徑不在允許的白名單目錄內。允許目錄包含 assets/, storage_data/, ~/.golfswinglab/",
        )

    ext = file_path.suffix.lower()
    if ext not in [".mp4", ".mov", ".m4v"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的影片格式: {ext}，僅支援 .mp4, .mov, .m4v",
        )

    file_size = file_path.stat().st_size
    if file_size > 500 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"影片大小超出上限 500MB (目前: {file_size / (1024 * 1024):.1f}MB)",
        )

    # 分塊計算 SHA-256 與串流讀取
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    file_sha256 = hasher.hexdigest()

    # 執行 ffprobe 解析影片真實屬性
    import subprocess
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,duration,width,height",
            "-of", "json",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        stream_info = probe_data.get("streams", [{}])[0]
        r_fps = stream_info.get("r_frame_rate", "30/1")
        num, den = map(int, r_fps.split("/")) if "/" in r_fps else (30, 1)
        fps = round(num / max(1, den), 2)
        duration_sec = float(stream_info.get("duration", 0))
        duration_ms = int(duration_sec * 1000)
        v_width = int(stream_info.get("width", 1280))
        v_height = int(stream_info.get("height", 720))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"無法使用 ffprobe 解析影片真實元數據: {exc}",
        )

    # 存入 Storage (串流方式，避免 OOM)
    storage = get_storage_service()
    ref_id = str(uuid.uuid4())
    storage_key = f"references/{payload.club_type.lower().replace('/', '_')}/{ref_id}_{file_path.name}"
    storage.put_file(storage_key, file_path, "video/mp4" if ext == ".mp4" else "video/quicktime")

    # 接入現有分析管線執行揮桿偵測、事件提取與骨架分析
    analysis_status_val, event_ts, pose_art, calibration, verif_notes = _analyze_reference_video(
        video_path=file_path,
        duration_ms=duration_ms,
        v_width=v_width,
        v_height=v_height,
        manual_events=payload.event_timestamps,
    )

    if payload.is_default:
        db.execute(
            update(ReferenceSwing)
            .where(
                ReferenceSwing.club_type == payload.club_type,
                ReferenceSwing.handedness == payload.handedness,
            )
            .values(is_default=False)
        )

    ref = ReferenceSwing(
        id=ref_id,
        club_type=payload.club_type,
        handedness=payload.handedness,
        camera_angle=payload.camera_angle,
        shot_type=payload.shot_type,
        title=payload.title,
        reference_author=payload.reference_author or "社群使用者",
        source_url=payload.source_url or f"local://{file_path.name}",
        content_license=payload.content_license or "個人學習參考",
        storage_key=storage_key,
        thumbnail_url=None,
        verified_club=False,  # 使用者自選球桿未經外部認證
        verified_camera_angle=False,  # 未經專業標定視角
        analysis_status=analysis_status_val,
        reference_category="community_reference",
        is_verified_standard=False,
        verification_notes=verif_notes,
        source_type="user_imported",
        fps=fps,
        duration_ms=duration_ms,
        sha256=file_sha256,
        event_timestamps=event_ts,
        pose_artifact=pose_art,
        calibration_params=calibration,
        is_default=payload.is_default,
        notes=payload.notes,
        analysis_version="pose-v1",
        imported_at=utcnow(),
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)

    logger.info(f"成功匯入示範揮桿: id={ref.id}, club={ref.club_type}, status={ref.analysis_status}")
    return _to_response_item(ref)


@router.patch("/{reference_id}", response_model=ReferenceSwingResponse)
def update_reference_swing(
    reference_id: str,
    payload: UpdateReferenceRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """手動更新示範揮桿的時間碼、校正參數、授權或預設設定。"""
    ref = db.get(ReferenceSwing, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的示範揮桿影片")

    if payload.title is not None:
        ref.title = payload.title
    if payload.reference_author is not None:
        ref.reference_author = payload.reference_author
    if payload.source_url is not None:
        ref.source_url = payload.source_url
    if payload.content_license is not None:
        ref.content_license = payload.content_license
    if payload.verified_club is not None:
        ref.verified_club = payload.verified_club
    if payload.verified_camera_angle is not None:
        ref.verified_camera_angle = payload.verified_camera_angle
    if payload.notes is not None:
        ref.notes = payload.notes
    if payload.event_timestamps is not None:
        ref.event_timestamps = payload.event_timestamps
    if payload.calibration_params is not None:
        ref.calibration_params = {**(ref.calibration_params or {}), **payload.calibration_params}

    if payload.is_default is True and not ref.is_default:
        db.execute(
            update(ReferenceSwing)
            .where(
                ReferenceSwing.club_type == ref.club_type,
                ReferenceSwing.handedness == ref.handedness,
            )
            .values(is_default=False)
        )
        ref.is_default = True
    elif payload.is_default is False:
        ref.is_default = False

    ref.updated_at = utcnow()
    db.commit()
    db.refresh(ref)
    return _to_response_item(ref)


@router.delete("/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference_swing(
    reference_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """移除示範揮桿影片。"""
    ref = db.get(ReferenceSwing, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的示範揮桿影片")
    db.delete(ref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/upload", response_model=ReferenceSwingResponse, status_code=status.HTTP_201_CREATED)
async def upload_reference_swing(
    file: UploadFile = File(...),
    club_type: str = Form(...),
    handedness: str = Form("right"),
    camera_angle: str = Form("DTL"),
    title: str = Form(...),
    reference_author: str = Form("社群使用者"),
    source_url: str = Form(""),
    content_license: str = Form("個人學習參考"),
    notes: str = Form(""),
    is_default: bool = Form(True),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    直接上傳示範影片檔案：
    1. 限制格式與大小 (<= 500MB)
    2. 串流分塊儲存至暫存檔與計算 SHA-256
    3. ffprobe 解析影片寬高與時長
    4. 標記 analysis_status='needs_calibration'，嚴禁未標記時捏造時間碼
    """
    if club_type not in ALL_CLUB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無效的球桿分類: {club_type}。支援分類: {ALL_CLUB_TYPES}",
        )

    filename = file.filename or "upload.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in [".mp4", ".mov", ".m4v"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的檔案格式: {ext}，僅支援 .mp4, .mov, .m4v",
        )

    max_size = 500 * 1024 * 1024
    total_bytes = 0
    hasher = hashlib.sha256()

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > max_size:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="上傳檔案超出大小上限 500MB",
                )
            tmp.write(chunk)
            hasher.update(chunk)

    file_sha256 = hasher.hexdigest()

    import subprocess
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,duration,width,height",
            "-of", "json",
            str(tmp_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        stream_info = probe_data.get("streams", [{}])[0]
        r_fps = stream_info.get("r_frame_rate", "30/1")
        num, den = map(int, r_fps.split("/")) if "/" in r_fps else (30, 1)
        fps = round(num / max(1, den), 2)
        duration_sec = float(stream_info.get("duration", 0))
        duration_ms = int(duration_sec * 1000)
        v_width = int(stream_info.get("width", 1280))
        v_height = int(stream_info.get("height", 720))
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"無法使用 ffprobe 解析上傳影片元數據: {exc}",
        )

    storage = get_storage_service()
    ref_id = str(uuid.uuid4())
    storage_key = f"references/{club_type.lower().replace('/', '_')}/{ref_id}_{Path(filename).name}"
    storage.put_file(storage_key, tmp_path, "video/mp4" if ext == ".mp4" else "video/quicktime")

    # 接入現有分析管線執行揮桿偵測、事件提取與骨架分析
    analysis_status_val, event_ts, pose_art, calibration, verif_notes = _analyze_reference_video(
        video_path=tmp_path,
        duration_ms=duration_ms,
        v_width=v_width,
        v_height=v_height,
        manual_events=None,
    )
    tmp_path.unlink(missing_ok=True)

    if is_default:
        db.execute(
            update(ReferenceSwing)
            .where(
                ReferenceSwing.club_type == club_type,
                ReferenceSwing.handedness == handedness,
            )
            .values(is_default=False)
        )

    ref = ReferenceSwing(
        id=ref_id,
        club_type=club_type,
        handedness=handedness,
        camera_angle=camera_angle,
        shot_type="full_swing",
        title=title,
        reference_author=reference_author or "社群使用者",
        source_url=source_url or "uploaded://direct",
        content_license=content_license or "個人學習參考",
        storage_key=storage_key,
        thumbnail_url=None,
        verified_club=False,
        verified_camera_angle=False,
        analysis_status=analysis_status_val,
        reference_category="community_reference",
        is_verified_standard=False,
        verification_notes=verif_notes,
        source_type="user_imported",
        fps=fps,
        duration_ms=duration_ms,
        sha256=file_sha256,
        event_timestamps=event_ts,
        pose_artifact=pose_art,
        calibration_params=calibration,
        is_default=is_default,
        notes=notes,
        analysis_version="pose-v1",
        imported_at=utcnow(),
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return _to_response_item(ref)
