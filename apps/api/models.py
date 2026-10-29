import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    """使用者與管理員帳戶 (`users`)。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    sessions: Mapped[list["PracticeSession"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class UserSetting(Base):
    """個人設定與 Server-Side LLM Provider 設定 (`user_settings`)。"""

    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    default_club: Mapped[str] = mapped_column(String(32), default="7I", nullable=False)
    handedness: Mapped[str] = mapped_column(String(16), default="right", nullable=False)
    camera_angle: Mapped[str] = mapped_column(String(16), default="DTL", nullable=False)
    score_weights_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    data_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    llm_base_url: Mapped[str] = mapped_column(String(255), default="https://api.openai.com/v1", nullable=False)
    llm_model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini", nullable=False)
    llm_api_key_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_consent_frames: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PracticeSession(Base):
    """練習場次 (`practice_sessions`)。"""

    __tablename__ = "practice_sessions"
    __table_args__ = (Index("ix_practice_sessions_owner_status", "owner_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="練習場 DTL 訓練")
    date: Mapped[str] = mapped_column(String(32), nullable=False)
    club: Mapped[str] = mapped_column(String(32), nullable=False, default="7I")
    handedness: Mapped[str] = mapped_column(String(16), nullable=False, default="right")
    camera_angle: Mapped[str] = mapped_column(String(16), nullable=False, default="DTL")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="sessions")
    videos: Mapped[list["Video"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Video(Base):
    """原始練習影片與媒體屬性 (`videos`)。"""

    __tablename__ = "videos"
    __table_args__ = (Index("ix_videos_owner_session", "owner_id", "session_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    proxy_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fps_num: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    fps_den: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_vfr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    codec: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    has_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingest_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    quality_flags_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    session: Mapped["PracticeSession"] = relationship(back_populates="videos")
    jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    segments: Mapped[list["SwingSegment"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Upload(Base):
    """大檔案 Multipart Upload 任務 (`uploads`)。"""

    __tablename__ = "uploads"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_uploads_owner_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    s3_upload_id: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="initiated", index=True)
    part_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=5242880)
    total_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    parts: Mapped[list["UploadPart"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan"
    )


class UploadPart(Base):
    """Multipart Upload 分段紀錄 (`upload_parts`)。"""

    __tablename__ = "upload_parts"
    __table_args__ = (
        UniqueConstraint("upload_id", "part_number", name="uq_upload_parts_upload_part_num"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    upload_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    upload: Mapped["Upload"] = relationship(back_populates="parts")


class AnalysisJob(Base):
    """背景影片分析任務 (`analysis_jobs`)。"""

    __tablename__ = "analysis_jobs"
    __table_args__ = (Index("ix_analysis_jobs_video_status", "video_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rq_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False, default="pose-v1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    video: Mapped["Video"] = relationship(back_populates="jobs")


class SwingSegment(Base):
    """偵測或人工建立之單次揮桿片段 (`swing_segments`)。"""

    __tablename__ = "swing_segments"
    __table_args__ = (Index("ix_swing_segments_video_start", "video_id", "start_ms"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(
        String(32), nullable=False, default="valid_swing"
    )  # valid_swing / practice_swing / swing_candidate / rejected
    ball_strike_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="strike_unknown"
    )  # confirmed_strike / estimated_strike / strike_unknown / no_ball
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="auto_accepted", index=True
    )  # auto_accepted / needs_review / confirmed / rejected
    review_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="pose-v1")
    manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    video: Mapped["Video"] = relationship(back_populates="segments")
    events: Mapped[list["SwingEvent"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )
    pose_artifact: Mapped["PoseArtifact | None"] = relationship(
        back_populates="segment", cascade="all, delete-orphan", uselist=False
    )
    metrics: Mapped[list["SwingMetric"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )
    scores: Mapped[list["SwingScore"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )


class SwingEvent(Base):
    """揮桿階段事件 (`swing_events`)：Address / Takeaway / Backswing / Top / Downswing / Impact_Estimated / Follow_Through / Finish。"""

    __tablename__ = "swing_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_name: Mapped[str] = mapped_column(String(48), nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    detection_source: Mapped[str] = mapped_column(String(32), nullable=False, default="model")
    model_version: Mapped[str] = mapped_column(String(32), nullable=False, default="pose-v1")
    rationale: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    segment: Mapped["SwingSegment"] = relationship(back_populates="events")


class PoseArtifact(Base):
    """2D 骨架關鍵點與畫質品質特徵 (`pose_artifacts`)。"""

    __tablename__ = "pose_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quality_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    keyframes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    segment: Mapped["SwingSegment"] = relationship(back_populates="pose_artifact")


class SwingMetric(Base):
    """單球可觀測 2D DTL 指標 (`swing_metrics`)。"""

    __tablename__ = "swing_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="ratio")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="pose-v1")
    observability: Mapped[str] = mapped_column(
        String(32), nullable=False, default="observed_2d"
    )  # observed_2d / estimated / unobservable

    segment: Mapped["SwingSegment"] = relationship(back_populates="metrics")


class SwingScore(Base):
    """單球可解釋評分與 IG 視覺呈現分數 (`swing_scores`)。"""

    __tablename__ = "swing_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score_version: Mapped[str] = mapped_column(String(32), nullable=False, default="score-v1")
    overall_nullable: Mapped[float | None] = mapped_column(Float, nullable=True)
    ig_visual_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    partial_score: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subscores_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    segment: Mapped["SwingSegment"] = relationship(back_populates="scores")


class Favorite(Base):
    """使用者精選球與手動覆寫排序 (`favorites`)。"""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("owner_id", "segment_id", "category", name="uq_favorites_owner_seg_cat"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # posture / tempo / finish / ig / excluded
    rank_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExportJob(Base):
    """MP4 單球與多球合輯匯出任務 (`exports`)。"""

    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    layout: Mapped[str] = mapped_column(String(32), nullable=False, default="original")  # original / 9:16
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="mp4")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class AnalysisFeedback(Base):
    """人工校正與評分誤判回饋紀錄 (`analysis_feedback`)。"""

    __tablename__ = "analysis_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    labeler: Mapped[str] = mapped_column(String(120), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditEvent(Base):
    """安全與操作稽核日誌 (`audit_events`)。"""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReferenceSwing(Base):
    """專業示範揮桿庫 (`reference_swings`)，支援 17 種完整球桿分類與視角比較。"""

    __tablename__ = "reference_swings"
    __table_args__ = (
        Index("ix_ref_swings_club_hand", "club_type", "handedness", "is_default"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    club_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # Driver, 3W, 5W, 3H, 4H, 5H, 4I, 5I, 6I, 7I, 8I, 9I, PW, GW/AW, SW, LW, Putter
    handedness: Mapped[str] = mapped_column(String(16), nullable=False, default="right")  # right / left
    camera_angle: Mapped[str] = mapped_column(String(16), nullable=False, default="DTL")  # DTL / face_on
    shot_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full_swing")  # full_swing, pitch, chip, putt, punch
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reference_author: Mapped[str] = mapped_column(String(120), nullable=False, default="Professional Standard")
    source_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    content_license: Mapped[str] = mapped_column(String(120), nullable=False, default="Educational Reference")
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")  # s3 key or local file path
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verified_club: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_camera_angle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(32), default="pending_analysis", nullable=False)  # completed, missing_reference, pending_analysis, needs_calibration, failed
    reference_category: Mapped[str] = mapped_column(String(32), default="test_fixture", nullable=False)  # professional_standard, community_reference, test_fixture
    is_verified_standard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="local_fixture", nullable=False)  # local_fixture, external_licensed, user_imported
    fps: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    event_timestamps: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    pose_artifact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    calibration_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    analysis_version: Mapped[str] = mapped_column(String(32), default="pose-v1", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

