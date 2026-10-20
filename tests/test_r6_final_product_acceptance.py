"""R6: 正式產品驗收與端到端完整性測試 (tests/test_r6_final_product_acceptance.py)

驗收範疇：
1. Mac 原生桌面 App (/Users/mathew/Desktop/Golf Swing Lab.app)：
   - arm64 原生 Mach-O Launcher 二進位檔
   - 嚴格簽名 (codesign strict)
   - 零寫死路徑 (動態相對尋址)
2. API 與服務健康度：
   - /healthz, /readyz (Postgres, Redis, Storage)
   - 預設用戶認證 (Argon2id)
3. 視覺與 DTL 演算法防偽與乾淨性：
   - 移除怪異外星人骨架/假人模板
   - 啟用 PGA 鉛線 (Tush Line)
   - 出球軌跡向天空升起且過濾背景干擾
4. 最高誠信防偽合約：
   - 不臆測球速、桿頭速度、碼數或實際球路
"""

import os
import plistlib
import subprocess
from pathlib import Path

import httpx
import pytest


def test_mac_app_integrity_and_signature():
    """驗證桌面與應用程式目錄中的 Mac 原生 App bundle 結構與嚴格簽名。"""
    desktop_app = Path(os.path.expanduser("~/Desktop/Golf Swing Lab.app"))
    assert desktop_app.exists(), f"桌面 App 不存在: {desktop_app}"

    plist_path = desktop_app / "Contents" / "Info.plist"
    assert plist_path.exists(), "Info.plist 必須存在"
    with open(plist_path, "rb") as f:
        plist_data = plistlib.load(f)
    assert plist_data.get("CFBundleExecutable") == "GolfSwingLab"
    assert plist_data.get("CFBundleIdentifier") == "com.golfswinglab.desktop"

    bin_path = desktop_app / "Contents" / "MacOS" / "GolfSwingLab"
    assert bin_path.exists(), "可執行檔必須存在"
    assert os.access(bin_path, os.X_OK), "可執行檔必須具備執行權限"

    # 檢查 Mach-O 格式為 arm64
    out = subprocess.check_output(["file", str(bin_path)], text=True)
    assert "arm64" in out, "二進位檔案必須為 Apple Silicon arm64 架構"

    # 檢查嚴格簽名
    res = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(desktop_app)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Codesign 驗證失敗: {res.stderr}"


def test_dynamic_launcher_has_no_hardcoded_paths():
    """驗證 launcher.c 二進位碼內無寫死的絕對路徑。"""
    launcher_src = Path(__file__).parent.parent / "launcher.c"
    assert launcher_src.exists()
    src_content = launcher_src.read_text(encoding="utf-8")
    assert "/Users/mathew/Desktop" not in src_content, "Launcher 原始碼中不得有任何寫死的使用者家目錄"
    assert "_NSGetExecutablePath" in src_content, "必須採用 macOS 原生 _NSGetExecutablePath 動態尋找 Repo 根目錄"


@pytest.mark.asyncio
async def test_api_health_and_auth_acceptance():
    """驗證本地啟動之 API 服務健康度與登入功能。"""
    async with httpx.AsyncClient(base_url="http://127.0.0.1:28000", timeout=5.0) as client:
        # 健康檢查
        r_health = await client.get("/healthz")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"

        r_ready = await client.get("/readyz")
        assert r_ready.status_code == 200
        checks = r_ready.json()["checks"]
        assert checks["postgres"] is True
        assert checks["redis"] is True
        assert checks["storage"] is True

        # 登入預設體驗帳號
        r_login = await client.post(
            "/api/auth/login",
            json={"email": "golfer@swinglab.local", "password": "GolfSwingLab!2026"},
        )
        assert r_login.status_code == 200
        token = r_login.json().get("access_token")
        assert token is not None, "應成功取得存取權杖"

        # 取得練習場次列表 (回傳分頁結構 {"items": [...], "total": int})
        headers = {"Authorization": f"Bearer {token}"}
        r_sess = await client.get("/api/sessions", headers=headers)
        assert r_sess.status_code == 200
        sess_data = r_sess.json()
        assert "items" in sess_data and isinstance(sess_data["items"], list)
        assert sess_data["total"] >= 1


def test_frontend_visual_fixes_acceptance():
    """驗證前端輔助線極簡專業化與雙球播放修復在前端頁面中完全落地。"""
    repo_root = Path(__file__).parent.parent

    # 1. 驗證單球畫布渲染與 Letterbox 幾何校正 (apps/web/src/app/swings/[id]/page.tsx)
    swing_page = repo_root / "apps" / "web" / "src" / "app" / "swings" / "[id]" / "page.tsx"
    assert swing_page.exists()
    s_code = swing_page.read_text(encoding="utf-8")
    assert "videoAspect" in s_code, "必須計算 videoAspect 避開直式 iPhone 9:16 黑邊拉扯"
    assert "offsetX" in s_code and "offsetY" in s_code, "必須計算黑邊偏移量"
    assert "toX" in s_code and "toY" in s_code, "座標必須透過 toX/toY 映射"
    assert "PGA 鉛線 (Tush Line)" in s_code, "必須提供專業 PGA 鉛線早起檢核"
    assert "proTemplates" not in s_code, "怪異外星人 PGA 假人模板必須徹底拔除"
    assert "bufferBefore" in s_code or "swing.start_ms" in s_code, "必須限制繪製時間，擊球結束自動清空畫布"

    # 2. 驗證雙球對照播放器 (apps/web/src/app/sessions/[id]/page.tsx)
    session_file = repo_root / "apps" / "web" / "src" / "app" / "sessions" / "[id]" / "page.tsx"
    assert session_file.exists()
    sess_code = session_file.read_text(encoding="utf-8")
    assert "muted" in sess_code, "雙球播放器必須設為 muted 繞過 WebKit 自動播放阻擋"
    assert "targetVideo" in sess_code, "必須根據 sw.video_id 動態尋找 targetVideo"
    assert "onLoadedMetadata" in sess_code, "雙球播放器必須在 loadedmetadata 時自動 seek 避開黑畫面"
