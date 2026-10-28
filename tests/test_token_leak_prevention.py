import re
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.config import KNOWN_LEAKED_SECRETS, get_settings, resolve_session_secret
from apps.api.main import app


def sanitize_url(url: str) -> str:
    """將 URL 中的敏感參數（token, access_token 等）安全脫敏。"""
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    for sensitive_key in ["token", "access_token", "key", "authorization"]:
        if sensitive_key in qs:
            qs[sensitive_key] = ["[REDACTED]"]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


def test_sanitize_url():
    raw_url = "http://localhost:28000/api/reference-swings/123/stream?token=secret123&club=7I"
    clean = sanitize_url(raw_url)
    assert "secret123" not in clean
    assert "token=%5BREDACTED%5D" in clean or "token=[REDACTED]" in clean
    assert "club=7I" in clean


def test_no_jwts_in_reports_and_docs():
    """掃描 docs/ 內所有報告與 Markdown，嚴禁寫入真實 JWT 憑證。"""
    jwt_pattern = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")
    docs_dir = Path("docs")
    leaked = []

    for file_path in docs_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in [".json", ".md", ".txt"]:
            content = file_path.read_text(encoding="utf-8")
            matches = jwt_pattern.findall(content)
            if matches:
                leaked.append((str(file_path), matches))

    assert not leaked, f"發現 docs 內有未脫敏的 JWT 憑證: {leaked}"


def test_known_leaked_secret_is_blocked(tmp_path: Path):
    """驗證黑名單中的密鑰會被 resolve_session_secret 攔截並自動重新生成。"""
    key_file = tmp_path / "session_secret"
    # 寫入已被外洩的密鑰
    for leaked in KNOWN_LEAKED_SECRETS:
        key_file.write_text(leaked, encoding="utf-8")
        resolved = resolve_session_secret(key_file)
        assert resolved not in KNOWN_LEAKED_SECRETS
        assert len(resolved) >= 32
        # 且檔案已被新密鑰覆蓋
        stored = key_file.read_text(encoding="utf-8").strip()
        assert stored == resolved


def test_revoked_token_returns_401():
    """驗證使用舊密鑰簽署的 Token 會被後端直接以 401 拒絕。"""
    import base64
    import hashlib
    import hmac
    import json
    import time

    old_secret = "c0600f9929e95b8562048f41bc87df58d184681b9de0a304cb131b3d705b2707"
    payload = {
        "sub": "test-user-id",
        "email": "test@swinglab.local",
        "role": "admin",
        "exp": int(time.time()) + 3600,
    }
    raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    old_sig = hmac.new(
        old_secret.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    leaked_token = f"{b64_payload}.{old_sig}"

    client = TestClient(app)
    response = client.get(
        "/api/reference-swings",
        headers={"Authorization": f"Bearer {leaked_token}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_SIGNATURE"
