"""
Golf Tracer Studio R4 — FastAPI Request & Response Schemas (`apps/api/schemas_tracer.py`).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    TrackQualitySummary,
)
from packages.analysis.tracer.fx_schema import (
    AudioMode,
    ExportAspectRatio,
    RenderRecipeV1,
)


class TracerProjectCreateRequest(BaseModel):
    segment_id: str = Field(..., min_length=1)
    title: str | None = None
    preset_id: str = "studio_neon"
    auto_analyze: bool = True


class TracerAnalyzeRequest(BaseModel):
    run_swing_tracer: bool = True
    run_shot_tracer: bool = True
    force_recompute: bool = True
    run_sync: bool = True


class ManualEditPointPayload(BaseModel):
    op: str = Field(..., pattern="^(add|move|delete)$")
    source_pts_us: int = Field(..., ge=0)
    source_frame_index: int = Field(default=0, ge=0)
    x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    point_role: str = Field(default="manual_anchor", pattern="^(manual_anchor|artistic_control)$")
    note: str = ""


class TracerManualEditsRequest(BaseModel):
    track_type: str = Field(..., pattern="^(club_head|ball)$")
    edits: list[ManualEditPointPayload] = Field(..., min_length=1)
    recompute_between_manual_anchors: bool = True
    note: str = ""


class TracerAnchorUpdateRequest(BaseModel):
    address_pts_us: int | None = Field(default=None, ge=0)
    top_pts_us: int | None = Field(default=None, ge=0)
    impact_pts_us: int | None = Field(default=None, ge=0)
    finish_pts_us: int | None = Field(default=None, ge=0)
    launch_pts_us: int | None = Field(default=None, ge=0)
    apex_pts_us: int | None = Field(default=None, ge=0)
    landing_pts_us: int | None = Field(default=None, ge=0)
    apex_xy_norm: list[float] | None = Field(default=None, min_length=2, max_length=2)
    landing_xy_norm: list[float] | None = Field(default=None, min_length=2, max_length=2)
    artistic_extension_enabled: bool = False
    recompute_tracks: bool = True


class TracerRecipeUpdateRequest(BaseModel):
    preset_id: str | None = None
    name: str | None = None
    recipe: RenderRecipeV1 | None = None


class TracerExportCreateRequest(BaseModel):
    project_id: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    segment_ids: list[str] = Field(default_factory=list)
    aspect_ratio: ExportAspectRatio = ExportAspectRatio.ORIGINAL
    fps: int = Field(default=60, description="支援 30 或 60")
    audio_mode: AudioMode = AudioMode.PRESERVE
    preset_id: str | None = None
    recipe_override: RenderRecipeV1 | None = None
    run_sync: bool = True


class TracerTrackRevisionResponse(BaseModel):
    id: str
    project_id: str
    track_type: str
    revision: int
    parent_revision: int | None = None
    status: str
    point_count: int
    points: list[CanonicalTrackPoint] = Field(default_factory=list)
    quality_summary: TrackQualitySummary | dict[str, Any] = Field(default_factory=dict)
    created_by: str
    note: str = ""
    created_at: datetime


class TracerAnchorRevisionResponse(BaseModel):
    id: str
    project_id: str
    revision: int
    address_pts_us: int | None = None
    top_pts_us: int | None = None
    impact_pts_us: int | None = None
    finish_pts_us: int | None = None
    launch_pts_us: int | None = None
    apex_pts_us: int | None = None
    landing_pts_us: int | None = None
    anchors_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime


class TracerProjectDetailResponse(BaseModel):
    id: str
    owner_id: str
    session_id: str | None = None
    video_id: str
    segment_id: str
    title: str
    status: str
    swing_status: str
    shot_mode: str
    active_swing_revision: int
    active_shot_revision: int
    active_anchor_revision: int
    active_recipe_id: str | None = None
    source_video_sha256: str
    coordinate_space_version: int = 1
    video_stream_url: str
    original_video_stream_url: str
    clip_start_pts_us: int
    clip_end_pts_us: int
    geometry: dict[str, Any] = Field(default_factory=dict)
    anchors: TracerAnchorRevisionResponse | None = None
    recipe: RenderRecipeV1
    swing_track: TracerTrackRevisionResponse | None = None
    shot_track: TracerTrackRevisionResponse | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TracerExportResponse(BaseModel):
    id: str
    owner_id: str
    project_id: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    segment_ids: list[str] = Field(default_factory=list)
    aspect_ratio: str
    fps: int
    audio_mode: str
    state: str
    download_url: str | None = None
    sidecar_url: str | None = None
    mp4_sha256: str | None = None
    sidecar_sha256: str | None = None
    size_bytes: int = 0
    duration_ms: int = 0
    output_width: int = 0
    output_height: int = 0
    has_audio_stream: bool = False
    parity_report: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
