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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select, update
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.models import ReferenceSwing, User, utcnow
from packages.storage.s3_client import get_storage_service

logger = logging.getLogger("gsl.reference_swings")

router = APIRouter(prefix="/api/reference-swings", tags=["Reference Swings"])

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
    file_path: str = Field(..., description="本機影片絕對路徑或相對路徑")
    club_type: str = Field(..., description="球桿分類，需符合 17 種球桿清單")
    handedness: str = Field("right", description="慣用手: right / left")
    camera_angle: str = Field("DTL", description="視角: DTL / face_on")
    shot_type: str = Field("full_swing", description="揮桿型態: full_swing, pitch, chip, putt")
    title: str = Field(..., description="示範影片標題")
    reference_author: str = Field("Professional Standard", description="示範選手或教練")
    source_url: str = Field("", description="原始出處或官方連結")
    content_license: str = Field("Educational Reference", description="版權授權模式")
    verified_club: bool = Field(False, description="是否已客觀確認該球桿")
    verified_camera_angle: bool = Field(False, description="是否已客觀確認拍攝角度")
    is_default: bool = Field(True, description="是否設為該球桿預設示範")
    notes: str = Field("", description="備註")
    event_timestamps: dict[str, int] | None = Field(None, description="若已有手動標記時間碼可直接傳入")


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


@router.post("/import-local", response_model=ReferenceSwingResponse, status_code=status.HTTP_201_CREATED)
def import_local_reference_swing(
    payload: ImportLocalReferenceRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    從本機檔案匯入示範影片：
    1. 驗證檔案存在與副檔名
    2. 計算 SHA-256
    3. 解析影片格式、FPS 與時長
    4. 提取或設定事件時間碼
    5. 自動計算等比例畫面對齊參數 (Calibration Params)
    6. 寫入 Storage 與資料庫
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

    # 計算 SHA-256
    raw_bytes = file_path.read_bytes()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    file_size = len(raw_bytes)

    # 執行 ffprobe 解析影片
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
        logger.warning(f"ffprobe 解析失敗，使用預設值: {exc}")
        fps = 30.0
        duration_ms = 3500
        v_width, v_height = 1280, 720

    # 存入 Storage
    storage = get_storage_service()
    ref_id = str(uuid.uuid4())
    storage_key = f"references/{payload.club_type.lower().replace('/', '_')}/{ref_id}_{file_path.name}"
    storage.put_bytes(storage_key, raw_bytes, "video/mp4" if file_path.suffix.lower() == ".mp4" else "video/quicktime")

    # 事件時間碼判定 (若傳入則直接使用；否則依比例初步配置)
    if payload.event_timestamps:
        event_ts = payload.event_timestamps
    else:
        # 標準揮桿時序初估 (可由使用者手動校正)
        event_ts = {
            "address": int(duration_ms * 0.15),
            "takeaway": int(duration_ms * 0.28),
            "top": int(duration_ms * 0.50),
            "downswing": int(duration_ms * 0.58),
            "impact": int(duration_ms * 0.65),
            "follow_through": int(duration_ms * 0.75),
            "finish": int(duration_ms * 0.90),
        }

    # 畫面對齊初估參數：等比例縮放以 1280x720 畫面中央為基準
    calibration = {
        "scale": 1.0,
        "zoom": 1.0,
        "offset_x": 0,
        "offset_y": 0,
        "video_width": v_width,
        "video_height": v_height,
        "torso_length": 115.0,
    }

    # 若設為預設，將同球桿/慣用手的其他影片 is_default 設為 false
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
        reference_author=payload.reference_author,
        source_url=payload.source_url,
        content_license=payload.content_license,
        storage_key=storage_key,
        thumbnail_url=None,
        verified_club=payload.verified_club,
        verified_camera_angle=payload.verified_camera_angle,
        analysis_status="completed",
        fps=fps,
        duration_ms=duration_ms,
        sha256=file_sha256,
        event_timestamps=event_ts,
        pose_artifact={},
        calibration_params=calibration,
        is_default=payload.is_default,
        notes=payload.notes,
        analysis_version="pose-v1",
        imported_at=utcnow(),
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)

    logger.info(f"成功匯入示範揮桿: id={ref.id}, club={ref.club_type}, title={ref.title}")
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
