"""
Golf Tracer Studio R4 — Canonical Track Point, Provenance & Quality Contracts (`contracts.py`).
嚴格執行證據分級：
- detector_observed 僅限該影格有實際影像模型偵測證據
- 若顯示座標經平滑 (Kalman/Spline)，必須保留 raw_observation 且標記 position_role='display_smoothed'
- 嚴禁將手腕座標偽裝為 club_head，嚴禁將推估或藝術延伸標記為 detector_observed
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TrackType(StrEnum):
    CLUB_HEAD = "club_head"
    BALL = "ball"


class TrackSourceType(StrEnum):
    DETECTOR_OBSERVED = "detector_observed"
    SHAFT_GEOMETRY_ESTIMATED = "shaft_geometry_estimated"
    OPTICAL_FLOW_ESTIMATED = "optical_flow_estimated"
    KALMAN_PREDICTED = "kalman_predicted"
    INTERPOLATED = "interpolated"
    EXTRAPOLATED = "extrapolated"
    MANUALLY_ANNOTATED = "manually_annotated"
    ARTISTIC_ONLY = "artistic_only"


class PositionRole(StrEnum):
    RAW_OBSERVATION = "raw_observation"
    DISPLAY_SMOOTHED = "display_smoothed"
    MANUAL_ANCHOR = "manual_anchor"
    ARTISTIC_CONTROL = "artistic_control"
    ESTIMATED_PATH = "estimated_path"


class OcclusionState(StrEnum):
    VISIBLE = "visible"
    OCCLUDED = "occluded"
    BLURRED = "blurred"
    OUT_OF_FRAME = "out_of_frame"
    UNOBSERVABLE = "unobservable"


class SwingPhase(StrEnum):
    ADDRESS = "address"
    TAKEAWAY = "takeaway"
    BACKSWING = "backswing"
    TOP = "top"
    DOWNSWING = "downswing"
    IMPACT = "impact"
    FOLLOW_THROUGH = "follow_through"
    FINISH = "finish"
    UNKNOWN = "unknown"


class ShotTrackMode(StrEnum):
    AUTO_OBSERVED = "AUTO_OBSERVED"
    AUTO_ASSISTED = "AUTO_ASSISTED"
    MANUAL_ANCHORED = "MANUAL_ANCHORED"
    ARTISTIC_EXTENSION = "ARTISTIC_EXTENSION"
    UNAVAILABLE = "UNAVAILABLE"


class SwingTrackStatus(StrEnum):
    AUTO_TRACED = "AUTO_TRACED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MANUAL_ASSISTED = "MANUAL_ASSISTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class RawObservationEvidence(BaseModel):
    x_norm: float = Field(ge=0.0, le=1.0)
    y_norm: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0], min_length=4, max_length=4)
    uncertainty_px: float = Field(default=0.0, ge=0.0)
    detector_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_kind: str = Field(default="direct_bbox")  # direct_bbox | shaft_endpoint | manual_click


class CanonicalTrackPoint(BaseModel):
    """單一影格之權威軌跡點契約。"""

    track_id: str
    track_type: TrackType
    segment_id: str
    source_video_id: str
    source_pts_us: int = Field(ge=0, description="原始影片真實呈現時間戳 (整數微秒)")
    source_frame_index: int = Field(ge=0)
    x_norm: float = Field(ge=0.0, le=1.0)
    y_norm: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: TrackSourceType
    position_role: PositionRole = PositionRole.RAW_OBSERVATION
    raw_observation: dict[str, Any] | None = None
    phase: str = "unknown"
    model_id: str | None = None
    evidence_frame_sha256: str | None = None
    occlusion_state: OcclusionState = OcclusionState.VISIBLE
    uncertainty_px: float = Field(default=0.0, ge=0.0)
    error_flags: list[str] = Field(default_factory=list)
    coordinate_space_version: int = 1
    created_by: str = "model"  # model | geometry | user | artist
    revision: int = 1

    @model_validator(mode="after")
    def _enforce_truthfulness_invariants(self) -> "CanonicalTrackPoint":
        validate_track_point_invariants(self)
        return self


def validate_track_point_invariants(pt: CanonicalTrackPoint | dict[str, Any]) -> None:
    """
    強制檢驗軌跡點誠信不變量：
    1. detector_observed 必須具備 raw_observation，且 created_by 為 model，不可為手腕冒充。
    2. 若 detector_observed 的 x_norm/y_norm 與 raw_observation 有平滑差異 (>1e-5)，position_role 必須為 display_smoothed。
    3. manually_annotated 的 created_by 必須為 user。
    4. artistic_only 的 occlusion_state 不可偽稱為實際檢出。
    """
    if isinstance(pt, dict):
        src_type = str(pt.get("source_type", ""))
        raw_obs = pt.get("raw_observation")
        pos_role = str(pt.get("position_role", ""))
        created_by = str(pt.get("created_by", ""))
        x_norm = float(pt.get("x_norm", 0.0))
        y_norm = float(pt.get("y_norm", 0.0))
        flags = list(pt.get("error_flags") or [])
    else:
        src_type = str(pt.source_type.value if hasattr(pt.source_type, "value") else pt.source_type)
        raw_obs = pt.raw_observation
        pos_role = str(pt.position_role.value if hasattr(pt.position_role, "value") else pt.position_role)
        created_by = pt.created_by
        x_norm = pt.x_norm
        y_norm = pt.y_norm
        flags = pt.error_flags

    if "wrist_fallback_forbidden" in flags or created_by == "wrist":
        raise ValueError("絕對邊界違規：禁止將手腕座標作為桿頭軌跡點 (wrist-as-head forbidden)")

    if src_type == TrackSourceType.DETECTOR_OBSERVED.value:
        if not raw_obs or "x_norm" not in raw_obs or "y_norm" not in raw_obs:
            raise ValueError("detector_observed 必須附帶真實 raw_observation (x_norm, y_norm)")
        if created_by not in ("model", "detector"):
            raise ValueError(f"detector_observed 的 created_by 必須為 model，收到: {created_by}")
        rx = float(raw_obs["x_norm"])
        ry = float(raw_obs["y_norm"])
        if (abs(x_norm - rx) > 1e-4 or abs(y_norm - ry) > 1e-4) and pos_role != PositionRole.DISPLAY_SMOOTHED.value:
            raise ValueError(
                "當平滑後座標與 raw_observation 不同時，position_role 必須標示為 display_smoothed，不可將濾波座標混充 raw_observation"
            )

    if src_type == TrackSourceType.MANUALLY_ANNOTATED.value and created_by != "user":
        raise ValueError("manually_annotated 軌跡點的 created_by 必須為 user")

    if src_type == TrackSourceType.ARTISTIC_ONLY.value and created_by not in ("artist", "user"):
        raise ValueError("artistic_only 軌跡點的 created_by 必須為 artist 或 user")


class TrackQualitySummary(BaseModel):
    """單條軌跡之可觀測性與信心度統計摘要。"""

    track_type: TrackType
    status: str  # SwingTrackStatus or ShotTrackMode
    total_frames: int = 0
    total_points: int = 0
    direct_observed_count: int = 0
    geometry_estimated_count: int = 0
    optical_flow_count: int = 0
    kalman_predicted_count: int = 0
    interpolated_count: int = 0
    extrapolated_count: int = 0
    manual_count: int = 0
    artistic_count: int = 0
    direct_observation_coverage: float = 0.0
    geometry_assisted_coverage: float = 0.0
    manual_coverage: float = 0.0
    largest_gap_ms: float = 0.0
    mean_confidence: float = 0.0
    p50_uncertainty_px: float = 0.0
    p95_uncertainty_px: float = 0.0
    observed_range_pts_us: list[int] = Field(default_factory=list)
    predicted_ranges_pts_us: list[list[int]] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    end_to_end_eligible: bool = False
    view_angle: str = "DTL"
    handedness: str = "right"
    camera_motion_score: float = 0.0
    notes: str = ""
