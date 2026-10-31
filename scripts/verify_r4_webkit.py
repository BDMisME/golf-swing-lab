"""Native macOS WKWebView End-to-End Verification for Golf Tracer Studio R4."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import AppKit
import Foundation
import objc
import WebKit

from apps.api.auth import create_session_token
from apps.api.db import SessionLocal
from apps.api.models import SwingSegment, TracerProject, TracerRenderRecipe, User
from apps.worker.tracer_tasks import ensure_tracer_model_registry, run_tracer_analysis_job
from packages.analysis.tracer.fx_schema import get_preset_recipe
from sqlalchemy import select


def ensure_real_tracer_project() -> tuple[str, str]:
    """Ensure a real TracerProject on 11s_iphone.mov exists and is analyzed, returning (project_id, token)."""
    from fastapi.testclient import TestClient
    from apps.api.main import app

    seg_id = "e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d"
    with SessionLocal() as db:
        ensure_tracer_model_registry(db)
        seg = db.get(SwingSegment, seg_id)
        assert seg is not None
        user = db.get(User, seg.owner_id) or db.scalar(select(User).order_by(User.created_at.asc()))
        assert user is not None
        token = create_session_token(user)
        existing = db.scalar(select(TracerProject).where(TracerProject.segment_id == seg_id))
        if existing is not None:
            return existing.id, token

    client = TestClient(app)
    resp = client.post(
        "/api/tracer/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "segment_id": seg_id,
            "title": "11s_iphone.mov — R4 Tracer Studio 實測",
            "preset_name": "studio_neon",
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


def main() -> None:
    project_id, token = ensure_real_tracer_project()
    print(f"Prepared TracerProject: {project_id}")

    # Clean up any stale R3 processes listening on 28000 or 23000 so R4 code runs cleanly
    subprocess.run("lsof -ti :28000 -ti :23000 | xargs kill -9 2>/dev/null || true", shell=True)
    time.sleep(0.5)

    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["NEXT_PUBLIC_API_BASE_URL"] = "http://localhost:28000"
    env["ALLOWED_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:23000,http://127.0.0.1:23000"

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
        window.setTitle_("Golf Swing Lab — R4 Golf Tracer Studio Native WKWebView Verification")

        config = WebKit.WKWebViewConfiguration.alloc().init()
        user_content = WebKit.WKUserContentController.alloc().init()

        # Inject Bearer token & console error interceptor before page scripts execute
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
        ns_url = Foundation.NSURL.URLWithString_(target_url)
        req = Foundation.NSURLRequest.requestWithURL_(ns_url)
        webview.loadRequest_(req)

        # Pump NSRunLoop for 6.5 seconds to allow Next.js + API + Canvas rendering to complete
        end_time = time.time() + 6.5
        while time.time() < end_time:
            Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1)
            )

        # Evaluate DOM state inside WKWebView
        eval_state = {"done": False, "result": None, "error": None}

        def completion_handler(res: object, err: object) -> None:
            eval_state["result"] = res
            eval_state["error"] = str(err) if err else None
            eval_state["done"] = True

        check_js = """
        JSON.stringify({
            url: window.location.href,
            title: document.title,
            hasCanvas: !!document.querySelector('canvas'),
            canvasCount: document.querySelectorAll('canvas').length,
            buttonCount: document.querySelectorAll('button').length,
            bodyTextSample: (document.body.innerText || '').slice(0, 500),
            jsErrors: window.__GSL_JS_ERRORS__ || []
        })
        """
        webview.evaluateJavaScript_completionHandler_(check_js, completion_handler)
        wait_eval = time.time() + 3.0
        while not eval_state["done"] and time.time() < wait_eval:
            Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05)
            )

        dom_report = json.loads(str(eval_state["result"])) if eval_state["result"] else {}

        # Take native snapshot via WKWebView takeSnapshotWithConfiguration or CGWindowListCreateImage
        snap_state = {"done": False, "saved": False}
        out_png = Path("docs/r4/webkit_tracer_studio.png")
        out_png.parent.mkdir(parents=True, exist_ok=True)

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

        summary = {
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "project_id": project_id,
            "target_url": target_url,
            "screenshot_saved": snap_state["saved"],
            "screenshot_path": str(out_png),
            "screenshot_size_bytes": out_png.stat().st_size if out_png.exists() else 0,
            "dom_report": dom_report,
        }
        Path("/tmp/r4_webkit_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        api_proc.terminate()
        web_proc.terminate()
        api_proc.wait(timeout=5)
        web_proc.wait(timeout=5)


if __name__ == "__main__":
    main()
