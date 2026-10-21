"""Golden Set 人工校核與真實基準 API 路由 (apps/api/routers/audit.py).

遵循 R13-A & R13-C 規範：
1. 作為前端 /audit 單一真實來源 (Single Source of Truth)。
2. 每筆標註嚴格綁定特定影片 SHA-256，拒絕使用隨機影片。
3. 嚴格防呆校驗：時間碼或影格超出影片長度時拒絕儲存並返回 422 錯誤。
4. 支援 machine_suggested, human_verified, uncertain 狀態轉換與歷史追蹤。
5. 提供 48kHz 音訊脈衝能量峰值供前端對照。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user, get_optional_current_user
from apps.api.db import get_db
from apps.api.models import User, Video
from packages.analysis.evaluation.golden_registry import (
    GoldenSetRegistry,
    get_golden_registry,
    golden_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["Golden Set Audit"])

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def get_audit_registry() -> GoldenSetRegistry:
    """提供可被測試依賴覆寫 (dependency_overrides) 的 GoldenSetRegistry 單例 (P0-2)."""
    return get_golden_registry()


class UpdateEventRequest(BaseModel):
    time_ms: int = Field(..., ge=0, description="新時間碼 (ms)")
    frame: int | None = Field(default=None, ge=0, description="新影格號（可選，若無則按 FPS 自動計算）")
    status: Literal["human_verified", "uncertain", "machine_suggested"] = "human_verified"
    rationale: str = Field(default="", max_length=500, description="修改依據或說明")


@router.get("/golden-sets")
def list_golden_sets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    registry: GoldenSetRegistry = Depends(get_audit_registry),
) -> list[dict[str, Any]]:
    """列出所有註冊的 Golden Set 資料集，並依據目前登入者權限比對資料庫影片 (P1-5)."""
    datasets = registry.list_datasets()
    enriched: list[dict[str, Any]] = []

    for ds in datasets:
        ds_id = ds.get("dataset_id", "")
        ds_model = registry.get_dataset(ds_id)
        sha = ds.get("video_sha256")
        matched_video: Video | None = None
        if sha:
            # 優先依 Owner 權限過濾影片
            matched_video = db.scalar(
                select(Video)
                .where(Video.sha256 == sha, Video.owner_id == current_user.id)
                .order_by(Video.created_at.desc())
            )
            if not matched_video:
                # 兼容個人自用預設影片
                matched_video = db.scalar(
                    select(Video).where(Video.sha256 == sha).order_by(Video.created_at.desc())
                )

        # 檢查本機實體檔案是否存在，但嚴禁向客戶端回傳本機絕對路徑 (P1-5)
        filename = ds.get("video_filename", "")
        local_raw = REPO_ROOT / "測試影片" / filename
        local_exists = local_raw.exists()

        item = dict(ds)
        # 移除可能包含敏感檔案路徑的欄位
        item.pop("file_path", None)
        item["golden_set_id"] = ds_id
        item["name"] = ds_model.note if ds_model and ds_model.note else ds.get("dataset_version", ds_id)
        item["video_duration_ms"] = ds_model.duration_ms if ds_model else ds.get("duration_ms", 0)
        item["matched_video_id"] = matched_video.id if matched_video else None
        item["matched_session_id"] = matched_video.session_id if matched_video else None
        item["local_file_exists"] = local_exists
        if ds_model:
            item["swings"] = [s.model_dump(mode="json") for s in ds_model.ground_truth_swings]
        else:
            item["swings"] = []
        enriched.append(item)

    return enriched


@router.get("/golden-sets/{dataset_id}")
def get_golden_set(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    registry: GoldenSetRegistry = Depends(get_audit_registry),
) -> dict[str, Any]:
    """獲取指定 Golden Set 完整標註資料與影片綁定資訊 (P1-5)."""
    ds = registry.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到指定的 Golden Set: {dataset_id}",
        )

    # 依 Owner 權限比對 SHA-256 關聯之 Video
    matched_video = db.scalar(
        select(Video)
        .where(Video.sha256 == ds.video_sha256, Video.owner_id == current_user.id)
        .order_by(Video.created_at.desc())
    )
    if not matched_video:
        matched_video = db.scalar(
            select(Video).where(Video.sha256 == ds.video_sha256).order_by(Video.created_at.desc())
        )

    data = ds.model_dump(mode="json")
    data["golden_set_id"] = ds.dataset_id
    data["video_duration_ms"] = ds.duration_ms
    data["swings"] = data.get("ground_truth_swings", [])
    data["matched_video_id"] = matched_video.id if matched_video else None
    data["matched_session_id"] = matched_video.session_id if matched_video else None
    return data


@router.put("/golden-sets/{dataset_id}/swings/{swing_id}/events/{event_name}")
def update_golden_event(
    dataset_id: str,
    swing_id: str,
    event_name: str,
    payload: UpdateEventRequest,
    current_user: User = Depends(get_current_user),
    registry: GoldenSetRegistry = Depends(get_audit_registry),
) -> dict[str, Any]:
    """人工精確校核關鍵事件影格與時間碼。

    嚴格檢驗：超出影片時長 (duration_ms) 或影格時直接拋出 422 錯誤。
    """
    if event_name not in {"address", "takeaway", "top", "impact", "finish"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的事件名稱: {event_name}。合法值為: address, takeaway, top, impact, finish",
        )

    ds = registry.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到指定的 Golden Set: {dataset_id}",
        )

    calc_frame = (
        payload.frame
        if payload.frame is not None
        else int(round(payload.time_ms * ds.fps / 1000.0))
    )

    try:
        updated_swing = registry.update_swing_event(
            dataset_id=dataset_id,
            swing_id=swing_id,
            event_name=event_name,
            new_time_ms=payload.time_ms,
            new_frame=calc_frame,
            status=payload.status,
            rationale=payload.rationale,
            user=current_user.email,
        )
        ev = updated_swing.events.get(event_name)
        return {
            "swing": updated_swing.model_dump(mode="json"),
            "event": ev.model_dump(mode="json") if ev else None,
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        ) from val_err
    except KeyError as key_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(key_err),
        ) from key_err


@router.post("/golden-sets/{dataset_id}/swings/{swing_id}/reset")
def reset_golden_swing(
    dataset_id: str,
    swing_id: str,
    current_user: User = Depends(get_current_user),
    registry: GoldenSetRegistry = Depends(get_audit_registry),
) -> dict[str, Any]:
    """撤回人工修改，將該球所有事件還原為初始機器建議。"""
    try:
        res = registry.reset_swing_to_machine(dataset_id=dataset_id, swing_id=swing_id)
        return {"swing": res.model_dump(mode="json")}
    except KeyError as key_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(key_err),
        ) from key_err


@router.get("/golden-sets/{dataset_id}/audio-peaks")
def get_dataset_audio_peaks(
    dataset_id: str,
    threshold: float = Query(97.0, ge=80.0, le=99.9),
    current_user: User = Depends(get_current_user),
    registry: GoldenSetRegistry = Depends(get_audit_registry),
) -> list[dict[str, Any]]:
    """提取對應影片之 48kHz PCM 音訊瞬態能量峰值供前端波形與候選 Impact 對照。"""
    ds = registry.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到指定的 Golden Set: {dataset_id}",
        )

    local_path = REPO_ROOT / "測試影片" / ds.video_filename
    if not local_path.exists():
        return []

    peaks = registry.extract_audio_peaks(local_path, threshold_pct=threshold)
    return peaks
