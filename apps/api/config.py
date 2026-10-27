import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWN_LEAKED_SECRETS: set[str] = {
    "change-me-in-production-at-least-32-bytes-long-secret-key",
    "gsl-rotated-session-secret-7578cfc2fc2e5e4964be15b584741a88e550d330",
}


def resolve_session_secret(key_file_path: Path | None = None) -> str:
    """
    動態安全解析 JWT 簽章密鑰，嚴禁在原始碼中存放真實密鑰：
    1. 優先由環境變數 SESSION_SECRET 或 GSL_SESSION_SECRET 載入
    2. 若未設定，檢查個人 Mac App 專屬本機安全持久化金鑰檔 (~/.golfswinglab/session_secret，權限 0600)
    3. 若該金鑰檔不存在或內容在已知外洩清單中，自動生成全新 256-bit 隨機密鑰並寫入（權限 0600）
    4. 嚴格攔截任何歷史外洩金鑰；若無法完成持久化，嚴格安全失敗（Fail-Closed）拋出例外，杜絕靜默回退造成登入態遺失
    """
    # 1. 檢查環境變數
    env_secret = os.environ.get("SESSION_SECRET") or os.environ.get("GSL_SESSION_SECRET")
    if env_secret and env_secret.strip() and env_secret.strip() not in KNOWN_LEAKED_SECRETS:
        return env_secret.strip()

    # 2. 個人 Mac App 本機安全金鑰目錄 (~/.golfswinglab/)
    key_file = key_file_path or (Path.home() / ".golfswinglab" / "session_secret")
    key_dir = key_file.parent

    try:
        if key_file.exists():
            try:
                stored = key_file.read_text(encoding="utf-8").strip()
            except OSError as e:
                raise RuntimeError(f"無法讀取本機 session_secret 金鑰檔案 ({key_file}): {e}，請檢查檔案權限。") from e

            if stored and len(stored) >= 32 and stored not in KNOWN_LEAKED_SECRETS:
                try:
                    os.chmod(key_file, 0o600)
                except OSError:
                    pass
                return stored
    except (PermissionError, OSError) as e:
        raise RuntimeError(
            f"無法持久化或存取本機 session_secret 金鑰檔案 ({key_file}): {e}。請檢查目錄或檔案讀寫權限。"
        ) from e

    # 3. 自動生成本機專屬隨機金鑰並以 0600 權限持久化（Fail-Closed 嚴格安全防護）
    new_secret = secrets.token_hex(32)
    try:
        key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        old_umask = os.umask(0o077)
        try:
            key_file.write_text(new_secret, encoding="utf-8")
            os.chmod(key_file, 0o600)
        finally:
            os.umask(old_umask)
        return new_secret
    except Exception as exc:
        raise RuntimeError(
            f"無法持久化 session_secret 金鑰檔案至 {key_file}: {exc}。"
            f"系統拒絕在未持久化狀態下靜默啟動（避免每次重啟 App 登入態全數失效）。"
            f"請確認該目錄具備寫入權限，或由環境變數 SESSION_SECRET 注入安全金鑰。"
        ) from exc


class Settings(BaseSettings):
    """系統環境變數與組態設定（支援本機開發、測試與 Zeabur 部署）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_base_url: str = "http://localhost:23000"
    api_base_url: str = "http://localhost:28000"

    database_url: str = "postgresql+psycopg://gsl:gsl_dev_password@localhost:25432/golf_swing_lab"
    redis_url: str = "redis://localhost:26379/0"

    storage_provider: str = "s3"
    local_storage_dir: str = "/tmp/gsl_storage"
    s3_endpoint_url: str = "http://localhost:29000"
    s3_internal_endpoint_url: str = "http://localhost:29000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "golf-swing-lab"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin123"
    s3_force_path_style: bool = True
    presigned_url_ttl_seconds: int = 900

    session_secret: str = Field(default_factory=resolve_session_secret)
    admin_email: str = "golfer@swinglab.local"
    admin_password: str = "GolfSwingLab!2026"
    allowed_origins: str = "http://localhost:23000,http://127.0.0.1:23000,http://localhost:3000,https://golf-swing-lab.zeabur.app"

    max_upload_bytes: int = 8589934592  # 8 GiB
    max_video_duration_sec: int = 1800  # 30 minutes
    worker_concurrency: int = 1
    rq_job_timeout_sec: int = 3600
    pose_backend: str = "yolov8x-pose"
    analysis_model_version: str = "pose-v1"
    scoring_version: str = "score-v2.1"
    data_retention_days: int = 30

    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/plan/v3"
    llm_model: str = "doubao-seed-2.1-lite"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    llm_max_budget_usd: float = 100.0

    # 若為 true，API 在無獨立 worker 或單一容器架構中自動於背景線程處理任務
    inline_worker_fallback: bool = True

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        if "https://golf-swing-lab.zeabur.app" not in origins:
            origins.append("https://golf-swing-lab.zeabur.app")
        return origins

    def validate_security_posture(self) -> None:
        """驗證生產環境安全設定，防止預設金鑰洩漏與弱密碼上線。"""
        if self.session_secret in KNOWN_LEAKED_SECRETS:
            raise RuntimeError("系統檢測到已知公開外洩之歷史 session_secret，已被安全機制強制阻擋！請使用未外洩之安全隨機金鑰。")
        if len(self.session_secret) < 32:
            raise RuntimeError("session_secret 長度過短，至少需具備 32 字元（256-bit）。")

        if self.app_env == "production":
            if self.admin_password == "GolfSwingLab!2026":
                raise RuntimeError("生產環境嚴禁使用預設 admin_password，請由環境變數 ADMIN_PASSWORD 注入高強度密碼。")
            if self.s3_access_key_id == "minioadmin" or self.s3_secret_access_key == "minioadmin123":
                raise RuntimeError("生產環境嚴禁使用預設 S3/MinIO 憑證，請由環境變數注入獨立金鑰。")


@lru_cache
def get_settings() -> Settings:
    return Settings()
