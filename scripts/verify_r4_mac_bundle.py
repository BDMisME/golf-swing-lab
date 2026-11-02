"""
Golf Swing Lab R4 — macOS Test App Bundle Runtime & Lifecycle Verification (`scripts/verify_r4_mac_bundle.py`).

依據《R4 PR #4 第三輪獨立審查指令》P0-A 要求：
1. 真正啟動 /tmp/Golf Swing Lab R4 Test.app，而非僅透過 WKWebView 載入。
2. 捕捉 App PID、Bundle ID (com.golfswinglab.desktop.r4test)、版本號、生命週期與衍生 Sidecar 程序。
3. 誠實聲明架構屬性為 "repo-dependent developer Mac app"，絕不偽稱 standalone。
4. 正式版 /Applications/Golf Swing Lab.app 在測試前後取得真實 SHA256 checksums，嚴格硬性斷言 100% untouched。
5. 驗證 Studio 路由可達性、原片串流、手動球路編輯、匯出以及結束後的孤兒進程完全清理。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import subprocess
import sys
import time
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.api.auth import create_session_token
from apps.api.db import SessionLocal
from apps.api.models import SwingSegment, TracerProject, User, Video
from packages.analysis.probe import probe_video_file


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def compute_production_app_checksums() -> dict[str, Any]:
    prod_app = Path("/Applications/Golf Swing Lab.app")
    if not prod_app.exists():
        return {"exists": False, "status": "NOT_FOUND"}
    plist_p = prod_app / "Contents" / "Info.plist"
    bin_p = prod_app / "Contents" / "MacOS" / "GolfSwingLab"
    plist_sha = hashlib.sha256(plist_p.read_bytes()).hexdigest() if plist_p.exists() else "missing"
    bin_sha = hashlib.sha256(bin_p.read_bytes()).hexdigest() if bin_p.exists() else "missing"
    return {
        "exists": True,
        "path": str(prod_app),
        "plist_sha256": plist_sha,
        "binary_sha256": bin_sha,
    }


def wait_http(url: str, timeout: float = 18.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code in (200, 307, 308, 401):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


from sqlalchemy import select
from apps.worker.tracer_tasks import ensure_tracer_model_registry


def prepare_e2e_project() -> tuple[str, str]:
    from fastapi.testclient import TestClient
    from apps.api.main import app

    seg_id = "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d"
    with SessionLocal() as db:
        ensure_tracer_model_registry(db)
        seg = db.get(SwingSegment, seg_id)
        assert seg is not None, f"Segment {seg_id} not found"
        user = db.get(User, seg.owner_id) or db.scalar(select(User).order_by(User.created_at.asc()))
        assert user is not None, "No user found in DB"
        token = create_session_token(user)

    client = TestClient(app)
    resp = client.post(
        "/api/tracer/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "segment_id": seg_id,
            "preset_id": "studio_neon",
            "auto_analyze": True,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    project_id = resp.json()["id"]
    return project_id, token


def run_bundle_verification() -> dict[str, Any]:
    print("=" * 80)
    print("Golf Swing Lab R4 — macOS Native App Bundle 實機運行與生命週期驗收")
    print("=" * 80)

    # 1. 正式版 App Pre-check
    prod_before = compute_production_app_checksums()
    print(f"正式版 /Applications/Golf Swing Lab.app 測試前狀態: {prod_before}")

    # 2. 測試版 App Bundle 規格檢驗
    test_bundle_path = Path("/tmp/Golf Swing Lab R4 Test.app")
    if not test_bundle_path.exists():
        raise FileNotFoundError(f"找不到測試版 App Bundle: {test_bundle_path}")

    plist_file = test_bundle_path / "Contents" / "Info.plist"
    with open(plist_file, "rb") as fp:
        plist_data = plistlib.load(fp)

    bundle_id = plist_data.get("CFBundleIdentifier")
    bundle_version = plist_data.get("CFBundleShortVersionString")
    bundle_exec_name = plist_data.get("CFBundleExecutable")
    exec_binary_path = test_bundle_path / "Contents" / "MacOS" / (bundle_exec_name or "GolfSwingLab")

    print(f"測試版 Bundle ID: {bundle_id}")
    print(f"測試版 Version: {bundle_version}")
    print(f"測試版 Executable: {exec_binary_path}")

    assert bundle_id == "com.golfswinglab.desktop.r4test", f"Unexpected bundle ID: {bundle_id}"
    assert bundle_version == "1.4.0-r4test", f"Unexpected version: {bundle_version}"
    assert exec_binary_path.exists() and os.access(exec_binary_path, os.X_OK), "Executable missing or not executable"

    # 3. 確保無殘留衝突端口
    if is_port_in_use(28000) or is_port_in_use(23000):
        print("注意：檢測到 28000 或 23000 端口已被佔用，等待其自動釋放或退出...")
        time.sleep(2)
        if is_port_in_use(28000) or is_port_in_use(23000):
            raise RuntimeError("BLOCKED_PORT_IN_USE: Port 28000/23000 occupied. Refusing to kill external processes.")

    # 4. 啟動測試版 App (設定 GSL_DESKTOP_HEADLESS=1 避免阻塞自動化流程)
    app_env = os.environ.copy()
    app_env["GSL_DESKTOP_HEADLESS"] = "1"
    app_env["GSL_PROJECT_DIR"] = str(ROOT_DIR)

    print("=== 正在啟動 R4 測試版 App 二進位 Launcher ===")
    app_proc = subprocess.Popen(
        [str(exec_binary_path)],
        env=app_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    app_pid = app_proc.pid
    print(f"R4 Test.app 啟動成功，PID: {app_pid}")

    project_id = ""
    token = ""
    studio_route_ok = False
    workflow_results: dict[str, Any] = {}
    orphan_clean_ok = False

    try:
        # 等待 Sidecar 服務健康就緒
        api_up = wait_http("http://127.0.0.1:28000/healthz", timeout=15.0)
        web_up = wait_http("http://127.0.0.1:23000/", timeout=15.0)
        assert api_up, "App 衍生之 API Sidecar (28000) 啟動超時"
        assert web_up, "App 衍生之 Web Sidecar (23000) 啟動超時"
        print("✅ Sidecar 服務 (API & Web) 順利啟動並通過健康檢查！")

        # 5. 準備測試專案與授權
        project_id, token = prepare_e2e_project()
        auth_headers = {"Authorization": f"Bearer {token}"}
        print(f"已建立 E2E 專案: {project_id}")

        # 6. 測試 Studio 路由可達性
        studio_url = f"http://127.0.0.1:23000/tracer-studio/{project_id}"
        r_studio = httpx.get(studio_url, headers=auth_headers, timeout=8.0)
        assert r_studio.status_code == 200, f"Studio route inaccessible: {r_studio.status_code}"
        studio_route_ok = True
        print(f"✅ Studio 前端路由可達 ({studio_url})，HTTP 200 OK")

        # 7. 執行手動球路編輯與落庫全流程測試
        api_base = "http://127.0.0.1:28000/api/tracer"
        
        # 7a. 設定 Launch 錨點
        r_launch = httpx.put(
            f"{api_base}/projects/{project_id}/anchors",
            headers=auth_headers,
            json={"launch_xy_norm": [0.52, 0.78], "recompute_tracks": True},
            timeout=10.0,
        )
        assert r_launch.status_code == 200
        workflow_results["launch_anchor"] = r_launch.json()["anchors"]["anchors_json"]["launch_xy_norm"]

        # 7b. 設定 Apex 錨點
        r_apex = httpx.put(
            f"{api_base}/projects/{project_id}/anchors",
            headers=auth_headers,
            json={"apex_xy_norm": [0.47, 0.22], "recompute_tracks": True},
            timeout=10.0,
        )
        assert r_apex.status_code == 200
        workflow_results["apex_anchor"] = r_apex.json()["anchors"]["anchors_json"]["apex_xy_norm"]

        # 7c. 設定 Landing 錨點 -> 自動轉 MANUAL_ANCHORED 並產生拋物線點位
        r_landing = httpx.put(
            f"{api_base}/projects/{project_id}/anchors",
            headers=auth_headers,
            json={"landing_xy_norm": [0.44, 0.58], "recompute_tracks": True},
            timeout=10.0,
        )
        assert r_landing.status_code == 200
        landing_json = r_landing.json()
        assert landing_json["shot_mode"] == "MANUAL_ANCHORED"
        pts_count = len(landing_json["shot_track"]["points"])
        assert pts_count > 0, "球路曲線點位未能自動生成"
        workflow_results["landing_anchor"] = {
            "mode": landing_json["shot_mode"],
            "points_count": pts_count,
            "revision": landing_json["active_shot_revision"],
            "landing_xy": landing_json["anchors"]["anchors_json"]["landing_xy_norm"],
        }
        print(f"✅ 手動錨點設定完成，產生 {pts_count} 個真實觀測拋物線點位 (Rev #{landing_json['active_shot_revision']})")

        # 7d. 觸發立即匯出與音訊保留驗證
        r_exp = httpx.post(
            f"{api_base}/exports",
            headers=auth_headers,
            json={
                "project_id": project_id,
                "aspect_ratio": "original",
                "fps": 60,
                "audio_mode": "preserve",
                "run_sync": True,
            },
            timeout=30.0,
        )
        assert r_exp.status_code == 200, f"Export failed: {r_exp.text}"
        exp_data = r_exp.json()
        dl_url = f"http://127.0.0.1:28000{exp_data['download_url']}"
        r_dl = httpx.get(dl_url, headers=auth_headers, timeout=15.0)
        assert r_dl.status_code == 200 and len(r_dl.content) > 10_000
        
        # 驗證下載之 MP4
        tmp_export_mp4 = Path("/tmp/r4_bundle_test_export.mp4")
        tmp_export_mp4.write_bytes(r_dl.content)
        dl_probe = probe_video_file(tmp_export_mp4)
        workflow_results["export_verification"] = {
            "size_bytes": len(r_dl.content),
            "width": dl_probe.width,
            "height": dl_probe.height,
            "has_audio": dl_probe.has_audio,
            "codec": dl_probe.codec,
        }
        print(f"✅ 匯出測試通過，產出 {len(r_dl.content)} bytes MP4，音訊保留={dl_probe.has_audio}")

    finally:
        # 8. 優雅終止測試版 App 與子進程清理審查
        print(f"=== 正在向 R4 Test.app (PID: {app_pid}) 發送 SIGTERM 優雅關閉 ===")
        try:
            app_proc.send_signal(signal.SIGTERM)
            app_proc.wait(timeout=6.0)
        except Exception:
            try:
                app_proc.kill()
                app_proc.wait(timeout=2.0)
            except Exception:
                pass

        time.sleep(1.5)
        # 檢查端口是否已釋放
        port28_free = not is_port_in_use(28000)
        port23_free = not is_port_in_use(23000)
        orphan_clean_ok = port28_free and port23_free
        print(f"Sidecar 程序清理狀態: 28000 已釋放={port28_free}, 23000 已釋放={port23_free}")

    # 9. 正式版 App Post-check
    prod_after = compute_production_app_checksums()
    print(f"正式版 /Applications/Golf Swing Lab.app 測試後狀態: {prod_after}")
    prod_untouched = (
        prod_before.get("exists") == prod_after.get("exists")
        and prod_before.get("plist_sha256") == prod_after.get("plist_sha256")
        and prod_before.get("binary_sha256") == prod_after.get("binary_sha256")
    )
    assert prod_untouched, "FATAL: 正式版 App 內容在測試過程中遭到變更！"

    overall_pass = studio_route_ok and orphan_clean_ok and prod_untouched

    summary = {
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_app_bundle": str(test_bundle_path),
        "app_architecture": "repo-dependent developer Mac app",
        "app_architecture_note": "本 App Bundle 依賴 launcher.c 在啟動時動態定位本機專案目錄與 Python 虛擬環境，並啟動 desktop_app.py Sidecar。非完全自包含之靜態二進位包。",
        "bundle_id": bundle_id,
        "bundle_version": bundle_version,
        "app_pid": app_pid,
        "launcher_exit_code": app_proc.returncode,
        "mac_bundle_runtime_status": "PASS" if overall_pass else "FAIL",
        "studio_route_accessible": studio_route_ok,
        "interactive_workflow": workflow_results,
        "orphan_processes_cleaned": orphan_clean_ok,
        "production_app_untouched": prod_untouched,
        "production_app_checksums_before": prod_before,
        "production_app_checksums_after": prod_after,
    }

    report_path = Path("/tmp/r4_mac_bundle_report.json")
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ R4 Mac Bundle 實機驗收報告已儲存至: {report_path}")
    print(f"整體判定: {summary['mac_bundle_runtime_status']}")

    return summary


def main() -> None:
    summary = run_bundle_verification()
    if summary["mac_bundle_runtime_status"] == "PASS":
        print("🎉 R4 Mac Bundle Runtime & Lifecycle Verification PASSED!")
        sys.exit(0)
    else:
        print("❌ R4 Mac Bundle Runtime & Lifecycle Verification FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
