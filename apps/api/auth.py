import base64
import hashlib
import hmac
import json
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.models import AuditEvent, User, UserSetting

ph = PasswordHasher()
SESSION_COOKIE_NAME = "gsl_session"


class APIError(Exception):
    """統一 API 錯誤結構，由全域 Exception Handler 轉為標準 JSON。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def hash_password(password: str) -> str:
    return str(ph.hash(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(ph.verify(password_hash, password))
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_session_token(user: User, ttl_seconds: int = 86400 * 7) -> str:
    settings = get_settings()
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{b64_payload}.{sig}"


def decode_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if "." not in token:
        raise APIError(401, "AUTH_INVALID_TOKEN", "無效的登入憑證格式")
    b64_payload, sig = token.split(".", 1)
    expected_sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise APIError(401, "AUTH_INVALID_SIGNATURE", "登入憑證簽章驗證失敗")

    padding = "=" * (-len(b64_payload) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(b64_payload + padding).decode("utf-8"))
    except Exception as exc:
        raise APIError(401, "AUTH_TOKEN_DECODE_ERROR", "無法解析登入憑證") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise APIError(401, "AUTH_TOKEN_EXPIRED", "登入憑證已過期，請重新登入")
    return dict(payload)


def ensure_default_admin(db: Session) -> User:
    """確保系統預設管理員帳戶存在。"""
    settings = get_settings()
    if settings.app_env == "production" and settings.admin_password == "GolfSwingLab!2026":
        raise RuntimeError("生產環境嚴禁使用預設密碼初始化管理員帳戶，請透過 ADMIN_PASSWORD 注入自訂高強度密碼。")
    admin = db.scalar(select(User).where(User.email == settings.admin_email))
    if not admin:
        admin = User(
            email=settings.admin_email,
            username="練習場主理人",
            password_hash=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(admin)
        db.flush()
        db.add(
            UserSetting(
                owner_id=admin.id,
                default_club="7I",
                handedness="right",
                camera_angle="DTL",
                llm_provider=settings.llm_provider,
                llm_base_url=settings.llm_base_url,
                llm_model=settings.llm_model,
            )
        )
        db.commit()
        db.refresh(admin)
    return admin


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """從 HttpOnly Cookie、Authorization Bearer Header 或媒體簽章 Query 驗證當前使用者。"""
    token: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise APIError(401, "AUTH_REQUIRED", "請先登入以存取此資源")

    payload = decode_session_token(token)
    user = db.get(User, str(payload.get("sub")))
    if not user:
        raise APIError(401, "AUTH_USER_NOT_FOUND", "使用者帳戶不存在或已停用")
    return user


def get_optional_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """可選使用者驗證，若未登入則返回 None 而不拋出 401。"""
    try:
        return get_current_user(request, db)
    except APIError:
        return None


def verify_owner(
    db: Session,
    current_user: User,
    resource_owner_id: str,
    object_type: str,
    object_id: str,
) -> None:
    """強制檢查資源擁有權；若跨帳戶越權存取則記錄稽核事件並拋出 403。"""
    if resource_owner_id != current_user.id:
        db.add(
            AuditEvent(
                actor_id=current_user.id,
                object_type=object_type,
                object_id=object_id,
                action="forbidden_access_attempt",
                metadata_json={"resource_owner_id": resource_owner_id},
            )
        )
        db.commit()
        raise APIError(403, "RESOURCE_FORBIDDEN", "您沒有權限存取不屬於您的訓練資料或影片")
