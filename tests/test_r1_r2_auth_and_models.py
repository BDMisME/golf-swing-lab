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
