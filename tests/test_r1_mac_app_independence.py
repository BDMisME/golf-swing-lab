"""R1: Mac App 獨立化與原生相依性自動化驗收測試 (tests/test_r1_mac_app_independence.py)

驗收範疇：
1. Launcher 二進位架構與無寫死路徑 (Relocatable arm64 Mach-O)
2. 桌面應用啟動器生命週期、Worker 管理與 Sidecar 容錯
3. 本地資料持久化與離線 (LLM_PROVIDER=none) 運作能力
4. 雙球同步播放器 WebKit Autoplay 與時間碼修正
5. 視訊長寬比自適應座標映射 (Aspect Fit) 與純淨教練線驗收
"""

import subprocess
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_launcher_binary_is_arm64_macho():
    """驗證 Launcher 為原生 arm64 Mach-O 且無硬編碼使用者路徑。"""
    launcher_c = REPO_ROOT / "launcher.c"
    assert launcher_c.exists(), "launcher.c 必須存在"
    content = launcher_c.read_text(encoding="utf-8")
    assert "/Users/mathew" not in content, "launcher.c 嚴禁出現寫死的個人絕對路徑 /Users/mathew"
    assert "_NSGetExecutablePath" in content, "launcher.c 必須使用 _NSGetExecutablePath 動態解析"

    binary_path = REPO_ROOT / "dist_mac" / "Golf Swing Lab.app" / "Contents" / "MacOS" / "GolfSwingLab"
    assert binary_path.exists(), "dist_mac 中必須存在編譯後的 GolfSwingLab 執行檔"

    # 使用 file 指令驗證 Mach-O arm64
    res = subprocess.run(["file", str(binary_path)], capture_output=True, text=True, check=True)
    assert "Mach-O 64-bit executable arm64" in res.stdout, f"二進位格式不正確: {res.stdout}"


def test_app_bundle_structure_and_signature():
    """驗證 App Bundle 結構與 Codesign 簽名。"""
    app_dir = REPO_ROOT / "dist_mac" / "Golf Swing Lab.app"
    info_plist = app_dir / "Contents" / "Info.plist"
    assert info_plist.exists(), "Info.plist 必須存在"

    plist_text = info_plist.read_text(encoding="utf-8")
    assert "<string>GolfSwingLab</string>" in plist_text
    assert "<string>com.golfswinglab.desktop</string>" in plist_text

    # 驗證程式碼簽名
    sign_check = subprocess.run(["codesign", "-v", "--deep", str(app_dir)], capture_output=True, text=True)
    assert sign_check.returncode == 0, f"簽名無效: {sign_check.stderr}"


def test_services_health_and_readiness():
    """驗證本地 Docker 基礎設施與核心 API、Web 健康檢查。"""
    # 檢查 API healthz
    with httpx.Client(timeout=3.0) as client:
        r_api = client.get("http://127.0.0.1:28000/healthz")
        assert r_api.status_code == 200, "FastAPI /healthz 必須返回 200"
        data = r_api.json()
        assert data.get("status") == "ok"

        # 檢查 Web
        r_web = client.get("http://127.0.0.1:23000")
        assert r_web.status_code == 200, "Next.js Web 首頁必須返回 200"


def test_offline_coach_provider_none_resilience():
    """驗證無外網或無 API Key 時，規則式教練 (LLM_PROVIDER=none) 完全獨立運作。"""
    import asyncio

    from packages.analysis.coach import RuleBasedCoachProvider

    provider = RuleBasedCoachProvider()

    sample_metrics = {
        "spine_tilt_stability": {"score": 65, "raw_value": 7.5, "unit": "deg_2d"},
        "head_movement": {"score": 55, "raw_value": 0.22, "unit": "torso_ratio"},
        "tempo_consistency": {"score": 85, "raw_value": 2.9, "unit": "ratio"},
    }
    swings_evidence = [
        {
            "sequence_no": 1,
            "label": "valid_swing",
            "overall_score": 68.3,
            "subscores": sample_metrics,
            "events": [{"event_name": "address", "time_ms": 1000}, {"event_name": "impact", "time_ms": 2200}],
        }
    ]

    report = asyncio.run(
        provider.generate_feedback(
            session_summary={"session_id": "test-offline-session", "swing_count": 1},
            swing_evidence=swings_evidence,
        )
    )
    assert report is not None
    assert report.provider == "none"
    assert report.llm_enabled is False
    assert len(report.priority_fixes) >= 1, "必須生成規則式體感口訣與修正建議"


def test_side_by_side_video_fixes_in_code():
    """驗證雙球同步對照頁面已修復 muted、正確綁定影片 ID 與 initial seek。"""
    session_page = REPO_ROOT / "apps" / "web" / "src" / "app" / "sessions" / "[id]" / "page.tsx"
    code = session_page.read_text(encoding="utf-8")

    assert "targetVideo" in code, "必須根據 sw.video_id 動態尋找 targetVideo，不得寫死 primaryVideo"
    assert "muted" in code, "比較視訊元素必須具備 muted 屬性以符合 WebKit 自動播放政策"
    assert "onLoadedMetadata" in code, "必須監聽 onLoadedMetadata 設定 currentTime 避開黑畫面"


def test_canvas_aspect_fit_and_clean_diagnostic_lines():
    """驗證單球播放器 Canvas 具備 Letterbox 座標映射與時間範圍嚴格限制。"""
    swing_page = REPO_ROOT / "apps" / "web" / "src" / "app" / "swings" / "[id]" / "page.tsx"
    code = swing_page.read_text(encoding="utf-8")

    assert "videoAspect" in code, "必須計算 videoAspect"
    assert "offsetX" in code and "offsetY" in code, "必須計算 letterbox 黑邊偏移量 offsetX 與 offsetY"
    assert "toX" in code and "toY" in code, "座標必須透過 toX/toY 進行精準投影"
    assert "Tush Line" in code, "必須提供專業 PGA 鉛線 (Tush Line) 早起檢核"
    assert "proTemplates" not in code, "必須徹底移除僵硬且怪異的外星人骨架模板"
    assert "bufferBefore" in code or "swing.start_ms - " in code, "必須限制繪製時間範圍，擊球結束後自動清空畫布"
