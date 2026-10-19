from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    session_secret: str = "change-me-in-production-at-least-32-bytes-long-secret-key"
    admin_email: str = "golfer@swinglab.local"
    admin_password: str = "GolfSwingLab!2026"
    allowed_origins: str = "http://localhost:23000,http://127.0.0.1:23000,http://localhost:3000,https://golf-swing-lab.zeabur.app"

    max_upload_bytes: int = 8589934592  # 8 GiB
    max_video_duration_sec: int = 1800  # 30 minutes
    worker_concurrency: int = 1
    rq_job_timeout_sec: int = 3600
    analysis_model_version: str = "pose-v1"
    scoring_version: str = "score-v1"
    data_retention_days: int = 30

    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    llm_max_budget_usd: float = 0.0

    # 若為 true，API 在 enqueue 背景任務時同時可在無獨立 worker 測試環境中執行 inline worker
    inline_worker_fallback: bool = False

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        if "https://golf-swing-lab.zeabur.app" not in origins:
            origins.append("https://golf-swing-lab.zeabur.app")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
