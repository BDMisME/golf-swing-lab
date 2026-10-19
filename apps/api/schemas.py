from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    role: str


class LoginResponse(BaseModel):
    user: UserOut
    access_token: str


class CreateSessionRequest(BaseModel):
    title: str = Field(default="練習場 DTL 訓練", min_length=1, max_length=200)
    date: str = Field(default="2026-10-19")
    club: str = Field(default="7I")
    handedness: str = Field(default="right", pattern="^(right|left)$")
    camera_angle: str = Field(default="DTL")
    notes: str = Field(default="", max_length=2000)


class UploadInitiateRequest(BaseModel):
    session_id: str
    filename: str
    mime_type: str = Field(default="video/mp4")
    size_bytes: int = Field(gt=0)
    part_size_bytes: int = Field(default=5242880, ge=1024)
    sha256: str | None = None
    idempotency_key: str | None = None


class UploadPartSignRequest(BaseModel):
    part_number: int = Field(ge=1, le=10000)


class CompletedPartInput(BaseModel):
    part_number: int = Field(ge=1)
    etag: str
    sha256: str | None = None
    size_bytes: int | None = None


class UploadCompleteRequest(BaseModel):
    parts: list[CompletedPartInput] = Field(default_factory=list)
    sha256: str | None = None


class CreateManualSwingRequest(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    label: str = Field(default="valid_swing")
    ball_strike_status: str = Field(default="confirmed_strike")
    notes: str = Field(default="")


class PatchSwingRequest(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    label: str | None = None
    ball_strike_status: str | None = None
    review_status: str | None = None
    notes: str | None = None
    feedback_category: str | None = None
    feedback_note: str | None = None


class FavoriteToggleRequest(BaseModel):
    segment_id: str
    category: str = Field(pattern="^(posture|tempo|finish|ig|excluded)$")
    rank_override: int | None = None
    remove: bool = False


class CreateExportRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1, max_length=3)
    layout: str = Field(default="original", pattern="^(original|9:16)$")
    format: str = Field(default="mp4", pattern="^mp4$")
    idempotency_key: str | None = None


class UpdateSettingsRequest(BaseModel):
    default_club: str = Field(default="7I")
    handedness: str = Field(default="right", pattern="^(right|left)$")
    camera_angle: str = Field(default="DTL")
    score_weights: dict[str, float] | None = None
    data_retention_days: int = Field(default=30, ge=1, le=365)
    llm_provider: str = Field(default="none", pattern="^(none|openai-compatible)$")
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_api_key: str | None = None
    llm_consent_frames: bool = False
    recalculate_session_id: str | None = None
