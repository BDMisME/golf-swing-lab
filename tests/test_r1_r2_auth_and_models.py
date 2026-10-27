from fastapi.testclient import TestClient

from apps.api.auth import create_session_token, hash_password
from apps.api.config import get_settings
from apps.api.db import SessionLocal
from apps.api.main import app
from apps.api.models import User

client = TestClient(app)


def _get_admin_headers() -> dict[str, str]:
    s = get_settings()
    resp = client.post(
        "/api/auth/login",
        json={"email": s.admin_email, "password": s.admin_password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_second_user_headers() -> dict[str, str]:
    with SessionLocal() as db:
        from sqlalchemy import select

        email = "other_golfer@swinglab.local"
        u = db.scalar(select(User).where(User.email == email))
        if not u:
            u = User(
                email=email,
                username="Other Golfer",
                password_hash=hash_password("OtherPass!2026"),
                role="user",
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        token = create_session_token(u)
        return {"Authorization": f"Bearer {token}"}


def test_healthz_and_readyz() -> None:
    r_health = client.get("/healthz")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert "X-Request-Id" in r_health.headers

    r_ready = client.get("/readyz")
    assert r_ready.status_code == 200, r_ready.text
    body = r_ready.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"] is True
    assert body["checks"]["redis"] is True
    assert body["checks"]["storage"] is True


def test_unauthenticated_access_rejected() -> None:
    unauth_client = TestClient(app)
    for path in ["/api/auth/me", "/api/sessions", "/api/exports", "/api/settings"]:
        resp = unauth_client.get(path)
        assert resp.status_code == 401
        err = resp.json()
        assert "code" in err and "request_id" in err


def test_login_and_cross_user_isolation() -> None:
    # 錯誤密碼必須回傳 401
    bad = client.post(
        "/api/auth/login",
        json={"email": get_settings().admin_email, "password": "wrong-password"},
    )
    assert bad.status_code == 401

    admin_headers = _get_admin_headers()
    other_headers = _create_second_user_headers()

    # Admin 建立場次
    create_resp = client.post(
        "/api/sessions",
        headers=admin_headers,
        json={
            "title": "週六晚間 7 鐵穩定度訓練",
            "date": "2026-10-19",
            "club": "7I",
            "handedness": "right",
            "camera_angle": "DTL",
            "notes": "專注保持前傾角",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    session_id = create_resp.json()["id"]

    # 另一位使用者嘗試讀取、產生報告或刪除 Admin 的場次皆須回傳 403 Forbidden
    r_get = client.get(f"/api/sessions/{session_id}", headers=other_headers)
    assert r_get.status_code == 403
    assert r_get.json()["code"] == "RESOURCE_FORBIDDEN"

    r_rep = client.get(f"/api/sessions/{session_id}/report", headers=other_headers)
    assert r_rep.status_code == 403

    r_del = client.delete(f"/api/sessions/{session_id}", headers=other_headers)
    assert r_del.status_code == 403


def test_security_posture_and_leaked_secret_rejection() -> None:
    """驗證 validate_security_posture 會徹底攔截所有歷史已公開外洩金鑰與預設弱密碼。"""
    import pytest
    from apps.api.config import KNOWN_LEAKED_SECRETS, Settings

    for leaked in KNOWN_LEAKED_SECRETS:
        s_bad = Settings(session_secret=leaked, app_env="production")
        with pytest.raises(RuntimeError, match="已知公開外洩之歷史 session_secret"):
            s_bad.validate_security_posture()

        s_bad_dev = Settings(session_secret=leaked, app_env="development")
        with pytest.raises(RuntimeError, match="已知公開外洩之歷史 session_secret"):
            s_bad_dev.validate_security_posture()

    # 驗證長度過短金鑰
    s_short = Settings(session_secret="too-short", app_env="production")
    with pytest.raises(RuntimeError, match="長度過短"):
        s_short.validate_security_posture()

    # 驗證生產環境預設密碼攔截
    s_default_pwd = Settings(
        session_secret="a-valid-secure-random-secret-key-of-at-least-32-bytes",
        admin_password="GolfSwingLab!2026",
        app_env="production",
    )
    with pytest.raises(RuntimeError, match="生產環境嚴禁使用預設 admin_password"):
        s_default_pwd.validate_security_posture()


def test_session_secret_local_persistence_and_invalidation(tmp_path) -> None:
    """驗證本機金鑰檔案 0600 持久化機制、重啟一致性、寫入失敗 fail-closed 以及舊 Token 失效。"""
    import os
    import pytest
    from apps.api.auth import decode_session_token, APIError
    from apps.api.config import resolve_session_secret

    # 1. 驗證隔離目錄下生成金鑰之 0600 權限與跨呼叫一致性
    isolated_key = tmp_path / "sub" / "secret_key"
    first_secret = resolve_session_secret(key_file_path=isolated_key)
    assert len(first_secret) >= 32
    assert isolated_key.exists()
    mode = oct(os.stat(isolated_key).st_mode & 0o777)
    assert mode == "0o600", f"金鑰檔案權限應為 0600，實際為 {mode}"

    # 再次解析必須讀取相同金鑰（保持登入態一致性）
    second_secret = resolve_session_secret(key_file_path=isolated_key)
    assert second_secret == first_secret, "重新讀取應維持相同金鑰，不可每次更換"

    # 2. 驗證無權限目錄下寫入失敗時嚴格拋出例外（Fail-Closed，杜絕靜默回退）
    readonly_dir = tmp_path / "readonly_dir"
    readonly_dir.mkdir(parents=True)
    readonly_dir.chmod(0o500)  # 可讀可進，但不可寫入
    unwritable_key = readonly_dir / "secret_key"
    try:
        with pytest.raises(RuntimeError, match="無法持久化 session_secret 金鑰檔案"):
            resolve_session_secret(key_file_path=unwritable_key)
    finally:
        readonly_dir.chmod(0o700)  # 復原以便 tmp_path 清理

    # 3. 驗證以舊外洩金鑰簽署的 Token 於當前環境中必然驗證失敗
    import base64
    import hashlib
    import hmac
    import json
    import time

    old_leaked_key = "gsl-rotated-session-secret-7578cfc2fc2e5e4964be15b584741a88e550d330"
    payload = {"sub": "fake-admin", "exp": int(time.time()) + 3600}
    raw = json.dumps(payload).encode("utf-8")
    b64_p = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    old_sig = hmac.new(old_leaked_key.encode("utf-8"), b64_p.encode("ascii"), hashlib.sha256).hexdigest()
    old_token = f"{b64_p}.{old_sig}"

    # 在當前安全密鑰下解析舊 token 必須失敗
    with pytest.raises(APIError) as exc_info:
        decode_session_token(old_token)
    assert exc_info.value.code == "AUTH_INVALID_SIGNATURE"

