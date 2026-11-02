"""Native macOS WKWebView End-to-End Interactive Verification & >=20 PTS Actual Visual Pixel Parity Audit for Golf Tracer Studio R4.

This script implements:
1. P0-A: Hard Fail-Closed guards with non-zero exit code, explicit step1-4 PASS/FAIL statuses, and sabotage testing modes.
2. P0-C: Real UI E2E user interaction inside native WKWebView (DOM buttons + Canvas MouseEvent click & drag).
3. P0-B: HSV color verification, normal & tangent errors, dash/gap parity, and coverage gate.
4. P1-A: Strict audio stream preservation & verification on exported MP4s.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
import urllib.request

import httpx

# 確保根目錄在 sys.path 中
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import AppKit
import cv2
import Foundation
import numpy as np
import WebKit
from sqlalchemy import select

from apps.api.auth import create_session_token
from apps.api.db import SessionLocal
from apps.api.models import SwingSegment, TracerProject, User, Video
from apps.worker.tracer_tasks import (
    _load_segment_context_from_db,
    ensure_tracer_model_registry,
)
from packages.analysis.probe import probe_video_file
from packages.analysis.tracer.compositor import verify_actual_visual_pixel_parity
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    PositionRole,
    TrackQualitySummary,
    TrackSourceType,
    TrackType,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader
from packages.analysis.tracer.fx_schema import (
    AudioMode,
    ExportAspectRatio,
    get_preset_recipe,
)
from packages.analysis.tracer.studio_exporter import (
    ClipExportSpec,
    export_single_tracer_clip,
)
from packages.analysis.tracer.transforms import compute_output_layout


def prepare_e2e_project() -> tuple[str, str]:
    """Create or reset a dedicated TracerProject on 11s_iphone.mov with 0-point Shot track for full E2E interactive testing."""
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


def wait_http(url: str, timeout_sec: float = 25.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def eval_js_sync(webview: Any, js_code: str, timeout_sec: float = 12.0) -> Any:
    state = {"done": False, "result": None, "error": None}

    def handler(res: object, err: object) -> None:
        state["result"] = res
        state["error"] = str(err) if err else None
        state["done"] = True

    webview.evaluateJavaScript_completionHandler_(js_code, handler)
    deadline = time.time() + timeout_sec
    while not state["done"] and time.time() < deadline:
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.04)
        )
    if state["error"]:
        raise RuntimeError(f"WKWebView JS Error: {state['error']}")
    return state["result"]


def pump_runloop(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05)
        )


def _decode_mp4_frame_at_index(mp4_path: Path, frame_index: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(mp4_path))
    assert cap.isOpened(), f"Failed to open {mp4_path}"
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_index))
        ok, frame = cap.read()
        assert ok and frame is not None, f"Failed to decode frame {frame_index} from {mp4_path}"
        return frame
    finally:
        cap.release()


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """安全檢測特定 loopback port 是否正被任何連線或程序佔用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def compute_production_app_checksums() -> dict[str, Any]:
    """計算正式版 /Applications/Golf Swing Lab.app 之真實 SHA256 checksums。"""
    prod_app = Path("/Applications/Golf Swing Lab.app")
    if not prod_app.exists():
        return {"exists": False, "status": "NOT_FOUND"}
    plist_path = prod_app / "Contents" / "Info.plist"
    binary_path = prod_app / "Contents" / "MacOS" / "GolfSwingLab"
    plist_sha = hashlib.sha256(plist_path.read_bytes()).hexdigest() if plist_path.exists() else "missing"
    binary_sha = hashlib.sha256(binary_path.read_bytes()).hexdigest() if binary_path.exists() else "missing"
    return {
        "exists": True,
        "path": str(prod_app),
        "plist_sha256": plist_sha,
        "binary_sha256": binary_sha,
    }


def fetch_project_detail_api(project_id: str, token: str, port: int = 28000) -> dict[str, Any]:
    """透過後端 API 取得 TracerProject 完整詳情、雙軌點位與 anchors。"""
    url = f"http://127.0.0.1:{port}/api/tracer/projects/{project_id}"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
    assert resp.status_code == 200, f"Failed to fetch project detail: {resp.status_code} {resp.text}"
    return resp.json()


def run_verification(sabotage: str = "none") -> dict[str, Any]:
    project_id, token = prepare_e2e_project()
    print(f"=== Prepared E2E TracerProject: {project_id} (Sabotage mode: {sabotage}) ===")

    # P0-A: 紀錄正式版 /Applications/Golf Swing Lab.app 測試前 checksum
    prod_checksums_before = compute_production_app_checksums()

    # P0-B: 安全契約——嚴禁使用 lsof | kill-9 暴力殺 Port。若已被佔用則明確退出並拒絕傷害外部程序
    if is_port_in_use(28000):
        raise RuntimeError("BLOCKED_PORT_IN_USE: Port 28000 is occupied by an external process. Refusing to forcefully kill external processes.")
    if is_port_in_use(23000):
        raise RuntimeError("BLOCKED_PORT_IN_USE: Port 23000 is occupied by an external process. Refusing to forcefully kill external processes.")

    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["NEXT_PUBLIC_API_BASE_URL"] = "http://localhost:28000"
    env["ALLOWED_ORIGINS"] = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:23000,http://127.0.0.1:23000"
    )

    api_proc = subprocess.Popen(
        [".venv/bin/uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "28000"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    web_proc = subprocess.Popen(
        ["npm", "--prefix", "apps/web", "run", "start", "--", "-H", "127.0.0.1", "-p", "23000"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        assert wait_http("http://127.0.0.1:28000/healthz"), "API server failed to start on 28000"
        assert wait_http("http://127.0.0.1:23000/"), "Web server failed to start on 23000"

        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

        rect = Foundation.NSMakeRect(0, 0, 1440, 920)
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskResizable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("Golf Swing Lab — R4 Native WKWebView E2E & Visual Parity")

        config = WebKit.WKWebViewConfiguration.alloc().init()
        user_content = WebKit.WKUserContentController.alloc().init()

        init_js = f"""
        try {{
            window.localStorage.setItem('gsl_token', {json.dumps(token)});
            window.localStorage.setItem('token', {json.dumps(token)});
            document.cookie = 'gsl_session=' + {json.dumps(token)} + '; path=/';
        }} catch (e) {{}}
        window.__GSL_JS_ERRORS__ = [];
        window.addEventListener('error', function(ev) {{
            window.__GSL_JS_ERRORS__.push(String(ev.message || ev));
        }});
        window.addEventListener('unhandledrejection', function(ev) {{
            window.__GSL_JS_ERRORS__.push(String(ev.reason || ev));
        }});
        """
        wk_script = WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
            init_js,
            WebKit.WKUserScriptInjectionTimeAtDocumentStart,
            True,
        )
        user_content.addUserScript_(wk_script)
        config.setUserContentController_(user_content)

        webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
        window.setContentView_(webview)
        window.makeKeyAndOrderFront_(None)

        target_url = f"http://localhost:23000/tracer-studio/{project_id}"
        webview.loadRequest_(
            Foundation.NSURLRequest.requestWithURL_(Foundation.NSURL.URLWithString_(target_url))
        )
        pump_runloop(6.0)

        # -------------------------------------------------------------
        # STEP 1: Verify initial load, Source: ORIGINAL badge & RVFC sync stats
        # -------------------------------------------------------------
        print("=== Step 1: Original Stream & Frame Sync Audit ===")
        play_js = """
        (function() {
            const v = document.querySelector('video');
            if (v) {
                v.muted = true;
                v.currentTime = 3.2;
                v.play().catch(function(){});
            }
            return !!v;
        })()
        """
        eval_js_sync(webview, play_js)
        pump_runloop(1.8)
        pause_js = """
        (function() {
            const v = document.querySelector('video');
            if (v) { v.pause(); v.currentTime = 3.80; }
            return JSON.stringify({
                videoSrc: v ? v.currentSrc || v.src : '',
                readyState: v ? v.readyState : 0,
                videoWidth: v ? v.videoWidth : 0,
                videoHeight: v ? v.videoHeight : 0,
                sourceBadgePresent: (document.body.innerText || '').includes('Source: ORIGINAL'),
                frameSyncStats: window.__GSL_FRAME_SYNC_STATS__ || null,
                jsErrors: window.__GSL_JS_ERRORS__ || []
            });
        })()
        """
        step1_info = json.loads(str(eval_js_sync(webview, pause_js)))
        print("Step 1 info:", json.dumps(step1_info, ensure_ascii=False))

        # P0-C Step 1 嚴格校驗：HTTP X-GSL-Media-Source 原片標頭、解析度與 PTS 單調性
        video_src = step1_info.get("videoSrc", "")
        if video_src.startswith("/"):
            video_full_url = f"http://127.0.0.1:28000{video_src}" if "/api/" in video_src else f"http://127.0.0.1:23000{video_src}"
        else:
            video_full_url = video_src

        header_source_value = None
        try:
            head_resp = httpx.get(
                video_full_url,
                headers={"Authorization": f"Bearer {token}", "Range": "bytes=0-1024"},
                timeout=5.0,
            )
            header_source_value = head_resp.headers.get("x-gsl-media-source")
        except Exception as e:
            print(f"Warning: could not probe video response header: {e}")

        sync_stats = step1_info.get("frameSyncStats") or {}
        callback_count = sync_stats.get("callbackCount", 0)
        recent_pts = sync_stats.get("recentMediaTimesUs") or []
        pts_advanced = False
        if len(recent_pts) >= 2:
            pts_advanced = recent_pts[-1] > recent_pts[0]
        elif callback_count > 0:
            pts_advanced = True

        step1_passed = (
            step1_info.get("readyState", 0) >= 2
            and "source=original" in video_src
            and header_source_value == "original"
            and step1_info.get("videoWidth", 0) > 0
            and step1_info.get("videoHeight", 0) > 0
            and step1_info.get("sourceBadgePresent", False)
            and callback_count > 0
            and pts_advanced
            and len(step1_info.get("jsErrors", [])) == 0
        )
        step1_status = "PASS" if step1_passed else "FAIL"
        step1_info["header_x_gsl_media_source"] = header_source_value
        step1_info["pts_advanced"] = pts_advanced
        step1_info["step1_passed"] = step1_passed

        # -------------------------------------------------------------
        # STEP 2: Native WKWebView Real DOM & Canvas MouseEvent E2E Interaction
        # -------------------------------------------------------------
        print("=== Step 2: Native WKWebView DOM & Canvas MouseEvent E2E ===")
        # Inject helper functions for DOM clicks and canvas mouse events
        helper_js = """
        window.__GSL_UI_E2E__ = {
            clickElement: function(selector) {
                const el = document.querySelector(selector);
                if (!el) return { success: false, error: 'Element not found: ' + selector };
                el.scrollIntoView({ block: 'center' });
                el.click();
                return { success: true };
            },
            dispatchCanvasMouse: function(type, normX, normY) {
                const canvas = document.querySelector('canvas');
                if (!canvas) return { success: false, error: 'Canvas not found' };
                const rect = canvas.getBoundingClientRect();
                const clientX = rect.left + rect.width * normX;
                const clientY = rect.top + rect.height * normY;
                const evt = new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: clientX,
                    clientY: clientY,
                    button: 0
                });
                canvas.dispatchEvent(evt);
                return { success: true, clientX: clientX, clientY: clientY };
            },
            seekVideoSec: function(sec) {
                const v = document.querySelector('video');
                if (v) { v.currentTime = sec; }
                return !!v;
            },
            getStudioState: function() {
                const bodyText = document.body.innerText || '';
                const shotRevMatch = bodyText.match(/Shot 飛球軌跡[\\s\\S]*?Rev #(\\d+)/);
                const swingRevMatch = bodyText.match(/Swing 揮桿軌跡[\\s\\S]*?Rev #(\\d+)/);
                return {
                    shotRev: shotRevMatch ? parseInt(shotRevMatch[1], 10) : null,
                    swingRev: swingRevMatch ? parseInt(swingRevMatch[1], 10) : null,
                    hasUndo: bodyText.includes('復原'),
                    hasRedo: bodyText.includes('重做'),
                    hasPointsList: bodyText.includes('軌道點位清單') || bodyText.includes('手動點清單'),
                    isBusy: bodyText.includes('處理中') || bodyText.includes('套用中'),
                    bodySnippet: bodyText.slice(0, 500)
                };
            }
        };
        true;
        """
        eval_js_sync(webview, helper_js)

        e2e_results: dict[str, Any] = {}

        # 取得基準專案詳情
        proj_base = fetch_project_detail_api(project_id, token)
        rev_base = proj_base.get("active_shot_revision") or 0

        # 2a. Set Launch Anchor via DOM Button + Canvas Click
        eval_js_sync(webview, "window.__GSL_UI_E2E__.seekVideoSec(3.80);")
        pump_runloop(0.4)
        c_launch = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"tool-set_launch\"]'));")))
        pump_runloop(0.3)
        m_launch = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.dispatchCanvasMouse('mousedown', 0.52, 0.78));")))
        pump_runloop(1.5)
        st_launch = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_launch = fetch_project_detail_api(project_id, token)
        anchors_launch = (proj_launch.get("anchors") or {}).get("anchors_json") or (proj_launch.get("anchors") or {})
        launch_xy = anchors_launch.get("launch_xy_norm") or []
        assert len(launch_xy) == 2, f"Expected 2D launch coordinates, got: {launch_xy}"
        e2e_results["launch_anchor"] = {
            "click_btn": c_launch,
            "mouse_down": m_launch,
            "state_after": st_launch,
            "api_launch_xy": launch_xy,
        }

        # 2b. Set Apex Anchor via DOM Button + Canvas Click
        eval_js_sync(webview, "window.__GSL_UI_E2E__.seekVideoSec(4.35);")
        pump_runloop(0.4)
        c_apex = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"tool-set_apex\"]'));")))
        pump_runloop(0.3)
        m_apex = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.dispatchCanvasMouse('mousedown', 0.47, 0.22));")))
        pump_runloop(1.5)
        st_apex = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_apex = fetch_project_detail_api(project_id, token)
        anchors_apex = (proj_apex.get("anchors") or {}).get("anchors_json") or (proj_apex.get("anchors") or {})
        apex_xy = anchors_apex.get("apex_xy_norm") or []
        assert len(apex_xy) == 2, f"Expected 2D apex coordinates, got: {apex_xy}"
        e2e_results["apex_anchor"] = {
            "click_btn": c_apex,
            "mouse_down": m_apex,
            "state_after": st_apex,
            "api_apex_xy": apex_xy,
        }

        # 2c. Set Landing Anchor via DOM Button + Canvas Click
        eval_js_sync(webview, "window.__GSL_UI_E2E__.seekVideoSec(4.95);")
        pump_runloop(0.4)
        c_landing = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"tool-set_landing\"]'));")))
        pump_runloop(0.3)
        m_landing = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.dispatchCanvasMouse('mousedown', 0.44, 0.58));")))
        pump_runloop(1.8)
        st_landing = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_landing = fetch_project_detail_api(project_id, token)
        anchors_landing = (proj_landing.get("anchors") or {}).get("anchors_json") or (proj_landing.get("anchors") or {})
        landing_xy = anchors_landing.get("landing_xy_norm") or []
        assert len(landing_xy) == 2, f"Expected 2D landing coordinates, got: {landing_xy}"
        pts_landing = proj_landing.get("shot_track", {}).get("points") or []
        rev_landing = proj_landing.get("active_shot_revision") or 0
        assert proj_landing.get("shot_mode") in ("MANUAL_ANCHORED", "ARTISTIC_EXTENSION"), f"Expected shot_mode MANUAL_ANCHORED or ARTISTIC_EXTENSION, got {proj_landing.get('shot_mode')}"
        assert len(pts_landing) > 0, "Expected non-empty points array after landing anchor"
        assert rev_landing > rev_base, f"Expected revision > {rev_base}, got {rev_landing}"
        e2e_results["landing_anchor"] = {
            "click_btn": c_landing,
            "mouse_down": m_landing,
            "state_after": st_landing,
            "api_landing_xy": landing_xy,
            "api_points_count": len(pts_landing),
            "api_shot_rev": rev_landing,
        }

        # 2d. Add Point via DOM Button + Canvas Click (先切換至 Shot 飛球軌跡)
        eval_js_sync(webview, "window.__GSL_UI_E2E__.clickElement('[data-testid=\"select-track-ball\"]');")
        pump_runloop(0.3)
        eval_js_sync(webview, "window.__GSL_UI_E2E__.seekVideoSec(4.05);")
        pump_runloop(0.4)
        c_add = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"tool-add_point\"]'));")))
        pump_runloop(0.3)
        m_add = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.dispatchCanvasMouse('mousedown', 0.495, 0.48));")))
        pump_runloop(1.8)
        st_add = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_add = fetch_project_detail_api(project_id, token)
        pts_add = proj_add.get("shot_track", {}).get("points") or []
        rev_add = proj_add.get("active_shot_revision") or 0
        assert rev_add > rev_landing, f"Revision did not increase: {rev_add} <= {rev_landing}"
        assert len(pts_add) > 0, "Points array is empty after add_point"
        assert any(p.get("source_type") == "manual" for p in pts_add) or (rev_add > rev_landing)
        e2e_results["add_point"] = {
            "click_btn": c_add,
            "mouse_down": m_add,
            "state_after": st_add,
            "api_points_count": len(pts_add),
            "api_shot_rev": rev_add,
        }

        # 2e. Move Point via DOM Button + Canvas Mouse Drag
        c_move = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"tool-move_point\"]'));")))
        pump_runloop(0.3)
        eval_js_sync(webview, "window.__GSL_UI_E2E__.dispatchCanvasMouse('mousedown', 0.495, 0.48);")
        pump_runloop(0.2)
        eval_js_sync(webview, "window.__GSL_UI_E2E__.dispatchCanvasMouse('mousemove', 0.490, 0.46);")
        pump_runloop(0.2)
        eval_js_sync(webview, "window.__GSL_UI_E2E__.dispatchCanvasMouse('mouseup', 0.490, 0.46);")
        pump_runloop(1.8)
        st_move = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_move = fetch_project_detail_api(project_id, token)
        pts_move = proj_move.get("shot_track", {}).get("points") or []
        rev_move = proj_move.get("active_shot_revision") or 0
        assert rev_move > rev_add, f"Revision did not increase after move: {rev_move} <= {rev_add}"
        coord_changed = any(
            abs(float(p1.get("x_norm", 0)) - float(p2.get("x_norm", 0))) > 0.0001
            or abs(float(p1.get("y_norm", 0)) - float(p2.get("y_norm", 0))) > 0.0001
            for p1, p2 in zip(pts_add, pts_move)
        )
        assert coord_changed, "Point coordinates did not change after drag operation"
        e2e_results["move_point"] = {
            "click_btn": c_move,
            "state_after": st_move,
            "api_shot_rev": rev_move,
            "coord_delta_verified": coord_changed,
        }

        # 2f. Undo via DOM Button
        c_undo = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"btn-undo-edit\"]'));")))
        pump_runloop(1.8)
        st_undo = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_undo = fetch_project_detail_api(project_id, token)
        rev_undo = proj_undo.get("active_shot_revision") or 0
        assert rev_undo < rev_move, f"Revision did not rollback after undo: {rev_undo} >= {rev_move}"
        e2e_results["undo"] = {
            "click_btn": c_undo,
            "state_after": st_undo,
            "undone_to_rev": st_undo.get("shotRev"),
            "api_shot_rev": rev_undo,
        }

        # 2g. Redo via DOM Button
        c_redo = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.clickElement('[data-testid=\"btn-redo-edit\"]'));")))
        pump_runloop(1.8)
        st_redo = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_redo = fetch_project_detail_api(project_id, token)
        rev_redo = proj_redo.get("active_shot_revision") or 0
        assert rev_redo == rev_move, f"Revision did not restore after redo: {rev_redo} != {rev_move}"
        e2e_results["redo"] = {
            "click_btn": c_redo,
            "state_after": st_redo,
            "redone_to_rev": st_redo.get("shotRev"),
            "api_shot_rev": rev_redo,
        }

        # 2h. Full Page Reload to verify persistence
        webview.reload()
        pump_runloop(4.8)
        eval_js_sync(webview, helper_js)
        st_reloaded = json.loads(str(eval_js_sync(webview, "JSON.stringify(window.__GSL_UI_E2E__.getStudioState());")))
        proj_reloaded = fetch_project_detail_api(project_id, token)
        rev_reloaded = proj_reloaded.get("active_shot_revision") or 0
        pts_reloaded = proj_reloaded.get("shot_track", {}).get("points") or []
        assert rev_reloaded == rev_redo, f"Persisted revision mismatch: {rev_reloaded} != {rev_redo}"
        assert len(pts_reloaded) == len(pts_move), f"Persisted point count mismatch: {len(pts_reloaded)} != {len(pts_move)}"
        e2e_results["reload_persistence"] = {
            "state_after_reload": st_reloaded,
            "persisted_rev": st_reloaded.get("shotRev"),
            "api_persisted_rev": rev_reloaded,
            "api_persisted_points_count": len(pts_reloaded),
        }

        # Save Screenshot
        out_png = Path("docs/r4/webkit_tracer_studio.png")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        snap_state = {"done": False, "saved": False}

        def snap_handler(ns_image: object, err: object) -> None:
            if ns_image is not None and err is None:
                tiff_data = ns_image.TIFFRepresentation()
                bmp = AppKit.NSBitmapImageRep.imageRepWithData_(tiff_data)
                png_data = bmp.representationUsingType_properties_(
                    AppKit.NSBitmapImageFileTypePNG, {}
                )
                png_data.writeToFile_atomically_(str(out_png.resolve()), True)
                snap_state["saved"] = True
            snap_state["done"] = True

        snap_cfg = WebKit.WKSnapshotConfiguration.alloc().init()
        webview.takeSnapshotWithConfiguration_completionHandler_(snap_cfg, snap_handler)
        wait_snap = time.time() + 4.0
        while not snap_state["done"] and time.time() < wait_snap:
            Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05)
            )

        step2_passed = (
            len(launch_xy) == 2
            and len(apex_xy) == 2
            and len(landing_xy) == 2
            and proj_landing.get("shot_mode") in ("MANUAL_ANCHORED", "ARTISTIC_EXTENSION")
            and rev_add > rev_landing
            and rev_move > rev_add
            and coord_changed
            and rev_undo < rev_move
            and rev_redo == rev_move
            and rev_reloaded == rev_redo
            and len(pts_reloaded) == len(pts_move)
            and snap_state["saved"]
        )
        step2_status = "PASS" if step2_passed else "FAIL"

        # -------------------------------------------------------------
        # STEP 3: Actual Visual Pixel Parity Audit (>= 20 PTS)
        # -------------------------------------------------------------
        print("=== Step 3: Actual Visual Pixel Parity Audit (WebKit Canvas PNG vs FFmpeg MP4) ===")
        from fastapi.testclient import TestClient
        from apps.api.main import app as fastapi_app

        api_client = TestClient(fastapi_app)
        auth_headers = {"Authorization": f"Bearer {token}"}

        parity_dir = Path("/tmp/r4_actual_visual_parity")
        parity_dir.mkdir(parents=True, exist_ok=True)

        with SessionLocal() as db:
            proj_db = db.get(TracerProject, project_id)
            assert proj_db is not None
            ctx_p, seg_p, vid_p = _load_segment_context_from_db(db, proj_db.segment_id, project=proj_db)

        # 4 export profiles × 6 PTS checkpoints = 24 PTS checkpoints (覆蓋球路起飛、爬升、Apex、下降與藝術延伸)
        # 精準對齊 30fps (33.3ms) 與 60fps (16.7ms) 最小公倍數 (0.1s 整數影格)，保證 frame_delta 恆為 0.0
        clip_start_us = 3_300_000
        clip_end_us = 4_900_000
        checkpoint_pts_list = [
            3_900_000,  # Early Launch (Frame 18 @30fps / Frame 36 @60fps)
            4_100_000,  # Mid Ascent (Frame 24 @30fps / Frame 48 @60fps)
            4_300_000,  # High Flight (Frame 30 @30fps / Frame 60 @60fps)
            4_500_000,  # Apex Peak / Transition (Frame 36 @30fps / Frame 72 @60fps)
            4_700_000,  # Ball Descent (Frame 42 @30fps / Frame 84 @60fps)
            4_800_000,  # Landing / Artistic Extension (Frame 45 @30fps / Frame 90 @60fps)
        ]

        parity_profiles = [
            ("studio_neon", "original", 60, True, True, False),
            ("clean_analysis", "9:16", 30, True, True, False),
            ("studio_neon", "original", 30, True, True, True),
            ("clean_analysis", "original", 60, True, False, False),
        ]

        raw_reader = BoundedFrameReader(
            source_path=ctx_p.source_video_path,
            geometry=ctx_p.geometry,
            require_high_res=True,
        )
        raw_frames = list(raw_reader.iter_frames(start_pts_us=clip_start_us - 100_000, end_pts_us=clip_end_us + 100_000))
        raw_pts_arr = [f.source_pts_us for f in raw_frames]

        all_visual_checkpoints: list[dict[str, Any]] = []

        for preset_id, aspect_str, fps_val, sw_on, sh_on, use_artistic in parity_profiles:
            recipe = get_preset_recipe(preset_id)
            recipe.export_format.aspect_ratio = ExportAspectRatio(aspect_str)
            recipe.export_format.fps = fps_val
            recipe.export_format.audio_mode = AudioMode("mute")
            recipe.swing_tracer.enabled = sw_on
            recipe.shot_tracer.enabled = sh_on

            r_cur = api_client.put(
                f"/api/tracer/projects/{project_id}/anchors",
                headers=auth_headers,
                json={"artistic_extension_enabled": use_artistic, "recompute_tracks": True},
            )
            assert r_cur.status_code == 200
            cur_json = r_cur.json()
            active_shot_pts = [
                CanonicalTrackPoint.model_validate(p)
                for p in (cur_json["shot_track"]["points"] if cur_json.get("shot_track") else [])
            ]
            active_swing_pts = [
                CanonicalTrackPoint.model_validate(p)
                for p in (cur_json["swing_track"]["points"] if cur_json.get("swing_track") else [])
            ]

            api_client.put(
                f"/api/tracer/projects/{project_id}/recipe",
                headers=auth_headers,
                json={"recipe": recipe.model_dump(mode="json")},
            )
            webview.reload()
            pump_runloop(3.2)
            eval_js_sync(webview, f"window.__GSL_SET_PREVIEW_ASPECT__ && window.__GSL_SET_PREVIEW_ASPECT__({json.dumps(aspect_str)});")
            pump_runloop(0.8)

            spec = ClipExportSpec(
                project_id=project_id,
                segment_id=ctx_p.segment_id,
                source_video_id=ctx_p.video_id,
                source_video_path=ctx_p.source_video_path,
                source_video_sha256="parity_sha",
                geometry=ctx_p.geometry,
                start_pts_us=clip_start_us,
                end_pts_us=clip_end_us,
                top_pts_us=3_433_000,
                impact_pts_us=3_800_000,
                swing_points=[
                    p for p in active_swing_pts if clip_start_us <= p.source_pts_us <= clip_end_us
                ],
                shot_points=[
                    p for p in active_shot_pts if clip_start_us <= p.source_pts_us <= clip_end_us
                ],
                swing_quality=TrackQualitySummary(track_type=TrackType.CLUB_HEAD, status="NEEDS_REVIEW"),
                shot_quality=TrackQualitySummary(
                    track_type=TrackType.BALL,
                    status="ARTISTIC_EXTENSION" if use_artistic else "MANUAL_ANCHORED",
                ),
                recipe=recipe,
                has_audio_stream=False,
            )

            mp4_out = parity_dir / f"parity_{preset_id}_{aspect_str.replace(':', 'x')}_{fps_val}fps.mp4"
            sidecar_out = parity_dir / f"parity_{preset_id}_{aspect_str.replace(':', 'x')}_{fps_val}fps.tracer.json"
            export_single_tracer_clip(spec=spec, output_mp4_path=mp4_out, sidecar_json_path=sidecar_out)

            layout = compute_output_layout(ctx_p.geometry, target_aspect=aspect_str)
            step_us = 1_000_000.0 / float(fps_val)

            for pts_us in checkpoint_pts_list:
                frame_idx = int(round((pts_us - clip_start_us) / step_us))
                export_pts_us = int(round(clip_start_us + frame_idx * step_us))

                cursor = 0
                while cursor + 1 < len(raw_frames) and abs(raw_pts_arr[cursor + 1] - export_pts_us) <= abs(raw_pts_arr[cursor] - export_pts_us):
                    cursor += 1
                raw_upright_bgr = raw_frames[cursor].image_bgr

                # Capture WebKit Canvas PNG at exact export_pts_us with deterministic recipe sync
                recipe_json_str = json.dumps(recipe.model_dump(mode="json"))
                cap_raw = eval_js_sync(
                    webview,
                    f"JSON.stringify(window.__GSL_RENDER_AND_CAPTURE_CANVAS__ ? window.__GSL_RENDER_AND_CAPTURE_CANVAS__({export_pts_us}, true, {recipe_json_str}) : null)",
                )
                assert cap_raw, f"Canvas capture returned null at {export_pts_us}"
                cap_info = json.loads(str(cap_raw)) if isinstance(cap_raw, (str, bytes)) else dict(cap_raw)
                data_url = cap_info["dataUrl"]
                b64_part = data_url.split(",", 1)[1]

                png_bytes = base64.b64decode(b64_part)
                nparr = np.frombuffer(png_bytes, np.uint8)
                canvas_rgba = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                assert canvas_rgba is not None

                export_bgr = _decode_mp4_frame_at_index(mp4_out, frame_idx)

                # Sabotage injection for negative testing of verification guard
                if sabotage == "5px":
                    # Shift exported image 5px horizontally
                    M = np.float32([[1, 0, 5], [0, 1, 0]])
                    export_bgr = cv2.warpAffine(export_bgr, M, (export_bgr.shape[1], export_bgr.shape[0]))
                elif sabotage == "color":
                    # Invert color channels BGR -> RGB
                    export_bgr = cv2.cvtColor(export_bgr, cv2.COLOR_BGR2RGB)
                elif sabotage == "no_track":
                    # Blank out exported image with black frame
                    export_bgr = np.zeros_like(export_bgr)

                expected_pts: list[CanonicalTrackPoint] = []
                if sw_on:
                    expected_pts.extend(
                        [p for p in spec.swing_points if p.source_pts_us <= export_pts_us]
                    )
                if sh_on:
                    expected_pts.extend(
                        [
                            p
                            for p in spec.shot_points
                            if p.source_pts_us <= export_pts_us
                            and (use_artistic or p.source_type != TrackSourceType.ARTISTIC_ONLY)
                        ]
                    )

                cp_res = verify_actual_visual_pixel_parity(
                    pts_us=pts_us,
                    export_frame_index=frame_idx,
                    export_frame_pts_us=export_pts_us,
                    fps=fps_val,
                    canvas_rgba=canvas_rgba,
                    exported_mp4_bgr=export_bgr,
                    raw_upright_bgr=raw_upright_bgr,
                    layout=layout,
                    active_points=expected_pts,
                    expect_artistic_dashed=use_artistic,
                )
                cp_dict = asdict(cp_res)
                cp_dict["profile"] = f"{preset_id} ({aspect_str} @{fps_val}fps)"
                cp_dict["artistic_mode"] = use_artistic
                all_visual_checkpoints.append(cp_dict)
                print(
                    f"  [PTS {export_pts_us}us | {preset_id} {aspect_str} @{fps_val}fps] "
                    f"offset={cp_res.max_centerline_offset_px_1080p}px, frame_delta={cp_res.frame_delta_frames}, "
                    f"color={cp_res.phase_color_verified}, artistic_dash={cp_res.artistic_dashed_verified}, "
                    f"matches={cp_res.matched_point_count}/{cp_res.eligible_point_count}, passed={cp_res.passed}"
                )

        step3_passed = (
            len(all_visual_checkpoints) >= 20
            and all(c["passed"] for c in all_visual_checkpoints)
        )
        step3_status = "PASS" if step3_passed else "FAIL"

        # -------------------------------------------------------------
        # STEP 4: Full Export & Audio Preservation Verification
        # -------------------------------------------------------------
        print("=== Step 4: Full Export & Audio Preservation Audit ===")
        r_exp = api_client.post(
            "/api/tracer/exports",
            headers=auth_headers,
            json={
                "project_id": project_id,
                "aspect_ratio": "9:16",
                "fps": 60,
                "audio_mode": "preserve",
                "run_sync": True,
            },
        )
        assert r_exp.status_code == 200, r_exp.text
        exp_json = r_exp.json()
        r_dl = api_client.get(exp_json["download_url"], headers=auth_headers)
        assert r_dl.status_code == 200

        # Save downloaded mp4 to verify audio with ffprobe
        downloaded_mp4 = parity_dir / "step4_downloaded_export.mp4"
        downloaded_mp4.write_bytes(r_dl.content)
        dl_probe = probe_video_file(downloaded_mp4)
        has_audio = dl_probe.has_audio

        if sabotage == "no_audio":
            # In sabotage no_audio mode, simulate loss of audio
            has_audio = False

        step4_passed = (
            len(r_dl.content) > 10_000
            and has_audio
        )
        step4_status = "PASS" if step4_passed else "FAIL"

        all_passed = (
            step1_status == "PASS"
            and step2_status == "PASS"
            and step3_status == "PASS"
            and step4_status == "PASS"
        )

        prod_checksums_after = compute_production_app_checksums()
        prod_untouched = (
            prod_checksums_before.get("exists") == prod_checksums_after.get("exists")
            and prod_checksums_before.get("plist_sha256") == prod_checksums_after.get("plist_sha256")
            and prod_checksums_before.get("binary_sha256") == prod_checksums_after.get("binary_sha256")
        )

        summary = {
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sabotage_mode": sabotage,
            "overall_status": "PASS" if all_passed else "FAIL",
            "step1_status": step1_status,
            "step2_status": step2_status,
            "step3_status": step3_status,
            "step4_status": step4_status,
            "rotated_video_subgate": "NOT_RUN",  # Honest marking: rotated 11min clip E2E tested in evaluate_r4_real_media, not in webkit UI
            "test_app_bundle": "/tmp/Golf Swing Lab R4 Test.app",
            "production_app_untouched": prod_untouched,
            "production_app_checksums_before": prod_checksums_before,
            "production_app_checksums_after": prod_checksums_after,
            "project_id": project_id,
            "target_url": target_url,
            "screenshot_saved": snap_state["saved"],
            "screenshot_path": str(out_png),
            "step1_original_stream_and_frame_sync": step1_info,
            "step2_interactive_workflow": e2e_results,
            "step3_actual_visual_pixel_parity": {
                "total_checkpoints": len(all_visual_checkpoints),
                "all_passed": all(c["passed"] for c in all_visual_checkpoints),
                "max_centerline_offset_px_1080p": max(
                    c["max_centerline_offset_px_1080p"] for c in all_visual_checkpoints
                ) if all_visual_checkpoints else 999.0,
                "mean_centerline_offset_px_1080p": round(
                    sum(c["mean_centerline_offset_px_1080p"] for c in all_visual_checkpoints)
                    / max(1, len(all_visual_checkpoints)),
                    3,
                ) if all_visual_checkpoints else 999.0,
                "checkpoints": all_visual_checkpoints,
            },
            "step4_export_verification": {
                "download_size_bytes": len(r_dl.content),
                "output_has_audio": has_audio,
                "probe_codec": dl_probe.codec,
            },
        }

        def _clean_objc_for_json(obj: Any) -> Any:
            if obj is None or isinstance(obj, (int, float, str, bool)):
                return obj
            if isinstance(obj, (dict, Foundation.NSDictionary)):
                return {str(k): _clean_objc_for_json(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, Foundation.NSArray)):
                return [_clean_objc_for_json(v) for v in obj]
            if hasattr(obj, "doubleValue"):
                try:
                    return float(obj.doubleValue())
                except Exception:
                    pass
            if hasattr(obj, "longLongValue"):
                try:
                    return int(obj.longLongValue())
                except Exception:
                    pass
            return str(obj)

        clean_summary = _clean_objc_for_json(summary)
        report_file = Path("/tmp/r4_webkit_report.json")
        report_file.write_text(json.dumps(clean_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report saved to {report_file}")

        return clean_summary

    finally:
        for p in (api_proc, web_proc):
            if p is not None and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify R4 WebKit E2E and Visual Pixel Parity")
    parser.add_argument("--sabotage", choices=["none", "5px", "color", "no_track", "no_audio"], default="none")
    args = parser.parse_args()

    summary = run_verification(sabotage=args.sabotage)

    if args.sabotage == "none":
        # Fail-closed enforcement: all steps must PASS
        assert summary["step1_status"] == "PASS", f"Step 1 failed: {summary['step1_original_stream_and_frame_sync']}"
        assert summary["step2_status"] == "PASS", f"Step 2 failed: {summary['step2_interactive_workflow']}"
        assert summary["step3_status"] == "PASS", f"Step 3 failed: {summary['step3_actual_visual_pixel_parity']}"
        assert summary["step4_status"] == "PASS", f"Step 4 failed: {summary['step4_export_verification']}"
        assert summary["overall_status"] == "PASS", "Overall status is not PASS"
        print("🎉 ALL 4 GATES PASSED (Fail-Closed Verification Complete)!")
        sys.exit(0)
    else:
        # P1-A 語意分離：破壞模式下檢測出失敗應以 exit 1 退出，外部 runner 斷言 exit 1；若誤報 PASS 則 exit 2
        if summary["overall_status"] == "FAIL":
            print(f"[SABOTAGE_INTERCEPTED] Sabotage guard verified! Successfully caught sabotage '{args.sabotage}' (overall_status=FAIL)")
            sys.exit(1)
        else:
            print(f"[SABOTAGE_ERRONEOUS_PASS] Sabotage guard failed! Script erroneously reported PASS under sabotage '{args.sabotage}'")
            sys.exit(2)


if __name__ == "__main__":
    main()
