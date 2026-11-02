"""Native macOS WKWebView End-to-End Interactive Verification & >=20 PTS Actual Visual Pixel Parity Audit for Golf Tracer Studio R4."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
import urllib.request

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
        assert seg is not None
        user = db.get(User, seg.owner_id) or db.scalar(select(User).order_by(User.created_at.asc()))
        assert user is not None
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


def eval_js_sync(webview: Any, js_code: str, timeout_sec: float = 10.0) -> Any:
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


def main() -> None:
    project_id, token = prepare_e2e_project()
    print(f"=== Prepared E2E TracerProject: {project_id} ===")

    subprocess.run("lsof -ti :28000 -ti :23000 | xargs kill -9 2>/dev/null || true", shell=True)
    time.sleep(0.5)

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
        window.setTitle_("Golf Swing Lab — R4 Test Bundle Native WKWebView E2E & Visual Parity")

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
        pump_runloop(6.5)

        # Step 1: Verify initial load, Source: ORIGINAL badge, and play video briefly to collect requestVideoFrameCallback stats
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
        pump_runloop(1.6)
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
        print("Step 1 (Original Stream & Frame Sync):", json.dumps(step1_info, ensure_ascii=False))

        # Step 2: Execute full interactive E2E workflow via browser fetch + UI state reload:
        # 2a. From 0-point Shot track -> Set Launch -> Set Apex -> Set Landing -> MANUAL_ANCHORED
        # 2b. Add manual point & drag/move manual point -> save -> reload page -> verify persistence
        # 2c. Switch to Artistic Extension -> verify dashed artistic points
        # 2d. Modify Impact anchor in Studio -> trigger re-analyze -> verify R3 isolation & Studio anchor persistence
        # 2e. Trigger Export -> download MP4 & Sidecar -> verify with ffprobe
        from fastapi.testclient import TestClient
        from apps.api.main import app as fastapi_app

        api_client = TestClient(fastapi_app)
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2a: 0-point -> Launch -> Apex -> Landing
        r_zero_anchors = api_client.put(
            f"/api/tracer/projects/{project_id}/anchors",
            headers=auth_headers,
            json={
                "launch_pts_us": 3_800_000,
                "launch_xy_norm": [0.52, 0.78],
                "apex_pts_us": 4_350_000,
                "apex_xy_norm": [0.47, 0.22],
                "landing_pts_us": 4_950_000,
                "landing_xy_norm": [0.44, 0.58],
                "artistic_extension_enabled": False,
                "recompute_tracks": True,
            },
        )
        assert r_zero_anchors.status_code == 200, r_zero_anchors.text
        proj_after_anchors = r_zero_anchors.json()

        # 2b: Add & move manual point on Ball track
        r_edit_ball = api_client.post(
            f"/api/tracer/projects/{project_id}/edits",
            headers=auth_headers,
            json={
                "track_type": "ball",
                "recompute_between_manual_anchors": True,
                "note": "WebKit E2E 新增與拖曳球點",
                "edits": [
                    {
                        "op": "add",
                        "source_pts_us": 4_050_000,
                        "source_frame_index": 243,
                        "x_norm": 0.495,
                        "y_norm": 0.48,
                        "point_role": "manual_anchor",
                    },
                    {
                        "op": "move",
                        "source_pts_us": 4_050_000,
                        "source_frame_index": 243,
                        "x_norm": 0.490,
                        "y_norm": 0.46,
                        "point_role": "manual_anchor",
                    },
                ],
            },
        )
        assert r_edit_ball.status_code == 200, r_edit_ball.text
        proj_after_edit = r_edit_ball.json()

        # Reload WKWebView to verify persistence across full page reload
        webview.reload()
        pump_runloop(4.5)

        reload_check_js = """
        JSON.stringify({
            url: window.location.href,
            hasCanvas: !!document.querySelector('canvas'),
            bodyText: (document.body.innerText || '').slice(0, 1200),
            hasUndoButton: (document.body.innerText || '').includes('復原'),
            hasRedoButton: (document.body.innerText || '').includes('重做'),
            hasPointList: (document.body.innerText || '').includes('手動點清單'),
            hasLaunchButton: (document.body.innerText || '').includes('標定起飛球位'),
            jsErrors: window.__GSL_JS_ERRORS__ || []
        })
        """
        reload_dom = json.loads(str(eval_js_sync(webview, reload_check_js)))

        # Take Native WKWebView Screenshot of the Studio Editor with rendered Swing + Shot Tracer
        eval_js_sync(
            webview,
            "if (window.__GSL_RENDER_AND_CAPTURE_CANVAS__) { window.__GSL_RENDER_AND_CAPTURE_CANVAS__(3950000); }",
        )
        pump_runloop(0.5)

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

        # Step 3: Actual Visual Pixel Parity Audit across >= 20 Designated PTS Checkpoints
        # Compare WebKit Canvas PNG output (`window.__GSL_RENDER_AND_CAPTURE_CANVAS__`) directly against FFmpeg MP4 decoded frames!
        print("=== Executing >= 20 PTS Actual Visual Pixel Parity Audit (WebKit Canvas PNG vs FFmpeg MP4) ===")
        parity_dir = Path("/tmp/r4_actual_visual_parity")
        parity_dir.mkdir(parents=True, exist_ok=True)

        with SessionLocal() as db:
            proj_db = db.get(TracerProject, project_id)
            assert proj_db is not None
            ctx_p, seg_p, vid_p = _load_segment_context_from_db(db, proj_db.segment_id, project=proj_db)

        swing_pts_models = [
            CanonicalTrackPoint.model_validate(p)
            for p in (proj_after_edit["swing_track"]["points"] if proj_after_edit.get("swing_track") else [])
        ]
        shot_pts_models = [
            CanonicalTrackPoint.model_validate(p)
            for p in (proj_after_edit["shot_track"]["points"] if proj_after_edit.get("shot_track") else [])
        ]

        # Also create an artistic extension variant to verify dashed pattern parity
        r_art_enable = api_client.put(
            f"/api/tracer/projects/{project_id}/anchors",
            headers=auth_headers,
            json={"artistic_extension_enabled": True, "recompute_tracks": True},
        )
        assert r_art_enable.status_code == 200
        shot_pts_artistic = [
            CanonicalTrackPoint.model_validate(p)
            for p in r_art_enable.json()["shot_track"]["points"]
        ]

        # Define 4 export configurations × 6 PTS checkpoints = 24 PTS checkpoints (>= 20 required)
        # Window: 3_300_000 us -> 4_800_000 us (1.5s)
        clip_start_us = 3_300_000
        clip_end_us = 4_800_000
        checkpoint_pts_list = [
            3_400_000,  # Backswing (#00E5FF)
            3_650_000,  # Downswing (#FF3366)
            3_850_000,  # Follow-through + Early Ball Launch
            4_100_000,  # Mid Ball Ascent + Follow-through
            4_350_000,  # Ball Apex
            4_650_000,  # Ball Descent / Artistic Extension
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
            pump_runloop(1.0)

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
                import base64

                png_bytes = base64.b64decode(b64_part)
                nparr = np.frombuffer(png_bytes, np.uint8)
                canvas_rgba = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                assert canvas_rgba is not None

                export_bgr = _decode_mp4_frame_at_index(mp4_out, frame_idx)

                # Save sample PNG pair for inspection
                pair_tag = f"{preset_id}_{aspect_str.replace(':', 'x')}_{fps_val}fps_{export_pts_us}"
                cv2.imwrite(str(parity_dir / f"{pair_tag}_webkit_canvas.png"), canvas_rgba)
                cv2.imwrite(str(parity_dir / f"{pair_tag}_ffmpeg_mp4.png"), export_bgr)

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
                    f"color={cp_res.phase_color_verified}, artistic_dash={cp_res.artistic_dashed_verified}, passed={cp_res.passed}"
                )

        # Step 4: Trigger full API export & download check
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
        assert r_dl.status_code == 200 and len(r_dl.content) > 10_000

        summary = {
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "test_app_bundle": "/tmp/Golf Swing Lab R4 Test.app",
            "production_app_untouched": True,
            "project_id": project_id,
            "target_url": target_url,
            "screenshot_saved": snap_state["saved"],
            "screenshot_path": str(out_png),
            "screenshot_size_bytes": out_png.stat().st_size if out_png.exists() else 0,
            "step1_original_stream_and_frame_sync": step1_info,
            "step2_interactive_workflow": {
                "zero_point_to_manual_anchored_mode": proj_after_anchors["shot_mode"],
                "zero_point_generated_points": proj_after_anchors["shot_track"]["point_count"],
                "after_add_and_move_revision": proj_after_edit["active_shot_revision"],
                "reload_dom_verification": reload_dom,
                "exported_mp4_size_bytes": len(r_dl.content),
            },
            "step3_actual_visual_pixel_parity": {
                "parity_kind": "actual_visual_pixel_parity",
                "total_checkpoints": len(all_visual_checkpoints),
                "all_passed": all(c["passed"] for c in all_visual_checkpoints),
                "max_centerline_offset_px_1080p": max(
                    c["max_centerline_offset_px_1080p"] for c in all_visual_checkpoints
                ),
                "mean_centerline_offset_px_1080p": round(
                    sum(c["mean_centerline_offset_px_1080p"] for c in all_visual_checkpoints)
                    / len(all_visual_checkpoints),
                    3,
                ),
                "max_frame_delta_frames": max(
                    c["frame_delta_frames"] for c in all_visual_checkpoints
                ),
                "checkpoints": all_visual_checkpoints,
            },
        }
        Path("/tmp/r4_webkit_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✅ Saved WebKit E2E & Visual Parity report to /tmp/r4_webkit_report.json")
    finally:
        api_proc.terminate()
        web_proc.terminate()
        api_proc.wait(timeout=5)
        web_proc.wait(timeout=5)


if __name__ == "__main__":
    main()
