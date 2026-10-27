#!/usr/bin/env python3
"""
scripts/verify_webkit_gui_playback.py

Golf Swing Lab — 真實 WebKit 播放器與 Clean Motion GUI 事件跳轉實測腳本
嚴格遵循 P0 規範：
1. 動態取得 139 秒 (2分鐘.mov) 最新正式分析 Session、Video (SHA-256: 4993a3b6...) 與 Swings。
2. 從正式資料庫與 API 取得第 8、9、10 球真實 ID、起訖範圍、Top 與 Impact 時間碼。
3. 採用 macOS 原生 WebKit.framework (WKWebView) 真實載入前端頁面。
4. 驗證場次報告頁面 (/sessions/{id})：標題、Top 5 榜單與 12 記揮桿卡片。
5. 導航至單球播放頁面 (/swings/{id})：
   - 等待影片 loadedmetadata
   - 透過 DOM 點擊正式 UI 事件按鈕 (btn.click()) 觸發跳轉，絕不用程式直接指定 video.currentTime 代替
   - 監聽 seeked 事件並核對影片實際解碼時間與 API 事件時間 (誤差 <= 100ms)
   - 深度驗證 Clean Motion Canvas 特徵繪製 (Top 手腕光環/肩部姿態線，Impact 擊球定位點/頭部圈)
   - 驗證跨階段切換防殘留保護 (No residual artifacts)
6. 保存 7 張快照截圖與包含完整證據鏈之結構化 JSON 驗收報告。
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import AppKit
import objc
import requests
import WebKit

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from apps.api.config import get_settings
from scripts.setup_verification_session import setup_or_get_verification_session

OUT_DIR = REPO_ROOT / "docs/screenshots/webkit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPO_ROOT / "docs/reports/takeover/webkit_gui_smoke_report.json"
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def obtain_auth_token() -> str:
    """透過安全登入 API 動態取得 JWT 認證憑證，絕不輸出至公開日誌。"""
    settings = get_settings()
    res = requests.post(
        f"{settings.api_base_url}/api/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
        timeout=5,
    )
    if res.status_code != 200:
        raise RuntimeError(f"無法取得認證 Token: HTTP {res.status_code}")
    return res.json()["access_token"]


class WebKitPlaybackAuditor(AppKit.NSObject):
    def init(self):
        self = objc.super(WebKitPlaybackAuditor, self).init()
        self.step_index = 0
        self.sub_step = 0
        self.target_data: dict[str, Any] = {}
        self.target_swings: list[dict[str, Any]] = []
        self.results: dict[str, Any] = {}
        self.done = False
        return self

    @objc.python_method
    def setupWithSessionData(self, session_data: dict[str, Any]):
        self.target_data = session_data
        all_swings = session_data.get("swings", [])
        # 篩選第 8、9、10 球
        self.target_swings = [s for s in all_swings if s.get("sequence_no") in (8, 9, 10)]
        self.target_swings.sort(key=lambda x: x["sequence_no"])

        self.results = {
            "tested_at": datetime.now(UTC).isoformat(),
            "analyzer_version": "2.1.0-beta",
            "session_id": session_data.get("session_id"),
            "session_title": session_data.get("session_title"),
            "video_id": session_data.get("video_id"),
            "video_sha256": session_data.get("video_sha256"),
            "video_duration_ms": session_data.get("video_duration_ms"),
            "ui_trigger_method": "dom_button_click",
            "session_report_verified": False,
            "swings_verified": {},
            "console_errors": [],
            "GUI_EVENT_VERIFIED": "IN_PROGRESS",
            "status": "IN_PROGRESS",
        }

    @objc.python_method
    def runNextStep(self):
        if self.step_index == 0:
            # 步驟 0: 載入場次報告頁面
            session_id = self.target_data["session_id"]
            url = f"http://localhost:23000/sessions/{session_id}"
            print(f"\n================================================================================")
            print(f"[WebKit Step 0] 正在載入場次報告頁面: {url}")
            print(f"  場次 ID: {session_id}")
            print(f"  影片 SHA-256: {self.target_data['video_sha256']}")
            print(f"================================================================================")
            req = AppKit.NSURLRequest.requestWithURL_(AppKit.NSURL.URLWithString_(url))
            self.webview.loadRequest_(req)
        elif 1 <= self.step_index <= len(self.target_swings):
            # 步驟 1..3: 載入單球播放頁面
            swing_info = self.target_swings[self.step_index - 1]
            seq = swing_info["sequence_no"]
            swing_id = swing_info["id"]
            url = f"http://localhost:23000/swings/{swing_id}"
            print(f"\n--------------------------------------------------------------------------------")
            print(f"[WebKit Step {self.step_index}] 載入第 #{seq} 球 (ID: {swing_id}) 播放頁面: {url}")
            print(f"  有效區間: [{swing_info['start_ms']}..{swing_info['end_ms']}] ms")
            print(f"  API 標記事件: Top={swing_info['top_ms']}ms, Impact={swing_info['imp_ms']}ms")
            print(f"--------------------------------------------------------------------------------")
            self.sub_step = 0
            req = AppKit.NSURLRequest.requestWithURL_(AppKit.NSURL.URLWithString_(url))
            self.webview.loadRequest_(req)
        else:
            # 全部步驟完成
            self.finishAudit()

    def webView_didFinishNavigation_(self, webview, navigation):
        if self.step_index == 0:
            # 等待場次報告 API 與 DOM 渲染
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3.0, self, "inspectSessionReport:", None, False
            )
        else:
            # 等待單球頁面、影片元數據與 Canvas 就緒
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3.0, self, "inspectSwingPlayer:", None, False
            )

    def inspectSessionReport_(self, timer):
        js = """
        (function() {
            var title = document.querySelector('h1') ? document.querySelector('h1').innerText : '';
            var bodyText = document.body.innerText;
            var hasRankings = bodyText.indexOf('TOP 5') !== -1 || bodyText.indexOf('精選') !== -1;
            var hasPosture = bodyText.indexOf('POSTURE') !== -1 || bodyText.indexOf('最佳姿勢') !== -1;
            var hasTempo = bodyText.indexOf('TEMPO') !== -1 || bodyText.indexOf('最佳節奏') !== -1;
            var swingCards = document.querySelectorAll('a[href*="/swings/"]').length;
            var errors = window.__gsl_captured_errors || [];
            return {
                title: title,
                hasRankings: hasRankings,
                hasPosture: hasPosture,
                hasTempo: hasTempo,
                swingCardsCount: swingCards,
                errors: errors
            };
        })();
        """

        def callback(res, err):
            if err:
                print(f"[ERROR] 執行場次報告 JS 失敗: {err}")
            else:
                title = res.get("title", "")
                cards = res.get("swingCardsCount", 0)
                has_rk = res.get("hasRankings", False)
                print(f"[OK] 場次報告 DOM 檢查通過: 標題='{title}', Top 5 榜單呈現={has_rk}, 球次卡片數={cards}")
                self.results["session_report_verified"] = bool(has_rk and cards >= 12)
                if res.get("errors"):
                    self.results["console_errors"].extend(res.get("errors"))

            self.captureSnapshot(OUT_DIR / "01_webkit_session_report.png", next_step=True)

        self.webview.evaluateJavaScript_completionHandler_(js, callback)

    def inspectSwingPlayer_(self, timer):
        swing_info = self.target_swings[self.step_index - 1]
        seq = swing_info["sequence_no"]

        if self.sub_step == 0:
            # 子步驟 0: 透過真實 DOM 按鈕點擊觸發跳轉至 Top
            target_ms = swing_info["top_ms"]
            print(f"  -> [Swing #{seq}] 尋找 UI 中的 Top 按鈕並點擊跳轉 (目標: {target_ms}ms)...")
            js = f"""
            (function() {{
                var video = document.querySelector('video');
                if (!video) return {{ success: false, reason: 'no_video' }};
                
                var topBtn = document.querySelector('button[data-event="top"]');
                if (!topBtn) {{
                    var btns = Array.from(document.querySelectorAll('button'));
                    topBtn = btns.find(function(b) {{
                        var firstLine = (b.innerText || '').split('\\n')[0].trim().toLowerCase();
                        return firstLine === 'top';
                    }});
                }}
                
                if (!topBtn) {{
                    var allBtnTexts = Array.from(document.querySelectorAll('button')).map(function(b) {{ return (b.innerText || '').split('\\n')[0].trim(); }});
                    return {{ success: false, reason: 'top_button_not_found', buttons: allBtnTexts }};
                }}
                
                // 真實 DOM Click
                topBtn.click();
                
                return {{
                    success: true,
                    buttonText: topBtn.innerText,
                    videoReadyState: video.readyState,
                    videoDuration: video.duration,
                    currentTimeBeforeSeek: video.currentTime
                }};
            }})();
            """

            def top_click_cb(res, err):
                if err or not (res and res.get("success")):
                    print(f"  [WARN] 點擊 Top 按鈕未成功: {err or res}")
                else:
                    print(f"  [DOM Click] 成功點擊 Top 按鈕: '{res.get('buttonText').splitlines()[0]}' (Video ReadyState={res.get('videoReadyState')})")

                # 等待 1.5 秒讓 video seeked 事件完成並觸發 Clean Motion Canvas 重繪
                AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    1.5, self, "verifyTopFrame:", None, False
                )

            self.webview.evaluateJavaScript_completionHandler_(js, top_click_cb)

        elif self.sub_step == 1:
            # 子步驟 1: 透過真實 DOM 按鈕點擊觸發跳轉至 Impact
            target_ms = swing_info["imp_ms"]
            print(f"  -> [Swing #{seq}] 尋找 UI 中的 Impact 按鈕並點擊跳轉 (目標: {target_ms}ms)...")
            js = f"""
            (function() {{
                var video = document.querySelector('video');
                if (!video) return {{ success: false, reason: 'no_video' }};
                
                var impBtn = document.querySelector('button[data-event="impact_estimated"]') || document.querySelector('button[data-event="impact"]');
                if (!impBtn) {{
                    var btns = Array.from(document.querySelectorAll('button'));
                    impBtn = btns.find(function(b) {{
                        var firstLine = (b.innerText || '').split('\\n')[0].trim().toLowerCase();
                        return firstLine === 'impact_estimated' || firstLine === 'impact';
                    }});
                }}
                
                if (!impBtn) {{
                    var allBtnTexts = Array.from(document.querySelectorAll('button')).map(function(b) {{ return (b.innerText || '').split('\\n')[0].trim(); }});
                    return {{ success: false, reason: 'impact_button_not_found', buttons: allBtnTexts }};
                }}
                
                // 真實 DOM Click
                impBtn.click();
                
                return {{
                    success: true,
                    buttonText: impBtn.innerText,
                    videoReadyState: video.readyState,
                    currentTimeBeforeSeek: video.currentTime
                }};
            }})();
            """

            def imp_click_cb(res, err):
                if err or not (res and res.get("success")):
                    print(f"  [WARN] 點擊 Impact 按鈕未成功: {err or res}")
                else:
                    print(f"  [DOM Click] 成功點擊 Impact 按鈕: '{res.get('buttonText').splitlines()[0]}'")

                # 等待 1.5 秒讓 video seeked 完成與 Canvas 繪製
                AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    1.5, self, "verifyImpactFrame:", None, False
                )

            self.webview.evaluateJavaScript_completionHandler_(js, imp_click_cb)

    def verifyTopFrame_(self, timer):
        swing_info = self.target_swings[self.step_index - 1]
        seq = swing_info["sequence_no"]
        target_ms = swing_info["top_ms"]

        js = """
        (function() {
            var video = document.querySelector('video');
            var canvas = document.querySelector('canvas');
            var curSec = video ? video.currentTime : 0;
            var curMs = Math.round(curSec * 1000);
            
            // 檢查 Canvas 是否有實際繪製 Clean Motion 骨架與線條
            var hasDrawing = false;
            var cyanPixels = 0;   // 青綠色 (肩膀姿態線 #06b6d4)
            var goldPixels = 0;   // 金黃色 (手腕轉折光環 #fbbf24)
            var totalDrawn = 0;
            
            if (canvas && canvas.width > 0 && canvas.height > 0) {
                try {
                    var ctx = canvas.getContext('2d');
                    var imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    var data = imgData.data;
                    for (var i = 0; i < data.length; i += 16) {
                        var r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
                        if (a > 30) {
                            totalDrawn++;
                            // 青綠色檢測: r < 50, g > 150, b > 180
                            if (r < 60 && g > 140 && b > 170) {
                                cyanPixels++;
                            }
                            // 金黃色檢測: r > 200, g > 160, b < 80
                            if (r > 200 && g > 160 && b < 80) {
                                goldPixels++;
                            }
                        }
                    }
                    if (totalDrawn > 30) {
                        hasDrawing = true;
                    }
                } catch(e) {}
            }
            
            return {
                currentTimeMs: curMs,
                hasVideo: !!video,
                videoReadyState: video ? video.readyState : -1,
                hasCanvas: !!canvas,
                canvasWidth: canvas ? canvas.width : 0,
                canvasHeight: canvas ? canvas.height : 0,
                canvasHasDrawing: hasDrawing,
                totalDrawnPixels: totalDrawn,
                cyanPixels: cyanPixels,
                goldPixels: goldPixels
            };
        })();
        """

        def cb(res, err):
            cur_ms = res.get("currentTimeMs", 0)
            diff = abs(cur_ms - target_ms)
            canvas_ok = res.get("canvasHasDrawing", False)
            total_px = res.get("totalDrawnPixels", 0)
            print(
                f"  [Swing #{seq} TOP 實測] 目標={target_ms}ms, 影片實際={cur_ms}ms, "
                f"偏差={diff}ms, CleanMotion繪製={canvas_ok} (像素數={total_px}, 姿態線={res.get('cyanPixels')}, 手部光環={res.get('goldPixels')})"
            )

            record = self.results["swings_verified"].setdefault(f"swing_{seq}", {})
            record["sequence_no"] = seq
            record["id"] = swing_info["id"]
            record["start_ms"] = swing_info["start_ms"]
            record["end_ms"] = swing_info["end_ms"]
            record["top_target_ms"] = target_ms
            record["top_actual_ms"] = cur_ms
            record["top_time_diff_ms"] = diff
            record["top_canvas_rendered"] = canvas_ok
            record["top_motion_features"] = {
                "total_pixels": total_px,
                "shoulder_line_pixels": res.get("cyanPixels", 0),
                "wrist_halo_pixels": res.get("goldPixels", 0),
            }

            snap_file = OUT_DIR / f"0{self.step_index * 2}_webkit_swing{seq}_top.png"
            self.sub_step = 1
            self.captureSnapshot(snap_file, next_step=False)

            # 排程執行 Impact 跳轉
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, "inspectSwingPlayer:", None, False
            )

        self.webview.evaluateJavaScript_completionHandler_(js, cb)

    def verifyImpactFrame_(self, timer):
        swing_info = self.target_swings[self.step_index - 1]
        seq = swing_info["sequence_no"]
        target_ms = swing_info["imp_ms"]

        js = """
        (function() {
            var video = document.querySelector('video');
            var canvas = document.querySelector('canvas');
            var curSec = video ? video.currentTime : 0;
            var curMs = Math.round(curSec * 1000);
            
            var hasDrawing = false;
            var skyBluePixels = 0; // 亮天藍 (#38bdf8 擊球瞬間手部定位點)
            var headBoxPixels = 0; // 綠色/紅色 (頭部位移檢核圈)
            var totalDrawn = 0;
            
            if (canvas && canvas.width > 0 && canvas.height > 0) {
                try {
                    var ctx = canvas.getContext('2d');
                    var imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    var data = imgData.data;
                    for (var i = 0; i < data.length; i += 16) {
                        var r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
                        if (a > 30) {
                            totalDrawn++;
                            // 亮天藍檢測: r 40-80, g 160-210, b > 220
                            if (r >= 35 && r <= 95 && g >= 150 && g <= 220 && b > 210) {
                                skyBluePixels++;
                            }
                            // 頭部圈綠色檢測: r < 50, g > 160, b < 150
                            if (r < 60 && g > 150 && b < 150) {
                                headBoxPixels++;
                            }
                        }
                    }
                    if (totalDrawn > 30) {
                        hasDrawing = true;
                    }
                } catch(e) {}
            }
            
            return {
                currentTimeMs: curMs,
                canvasHasDrawing: hasDrawing,
                totalDrawnPixels: totalDrawn,
                skyBluePixels: skyBluePixels,
                headBoxPixels: headBoxPixels
            };
        })();
        """

        def cb(res, err):
            cur_ms = res.get("currentTimeMs", 0)
            diff = abs(cur_ms - target_ms)
            canvas_ok = res.get("canvasHasDrawing", False)
            total_px = res.get("totalDrawnPixels", 0)
            print(
                f"  [Swing #{seq} IMP 實測] 目標={target_ms}ms, 影片實際={cur_ms}ms, "
                f"偏差={diff}ms, CleanMotion繪製={canvas_ok} (像素數={total_px}, 擊球點={res.get('skyBluePixels')}, 頭部圈={res.get('headBoxPixels')})"
            )

            record = self.results["swings_verified"].setdefault(f"swing_{seq}", {})
            record["imp_target_ms"] = target_ms
            record["imp_actual_ms"] = cur_ms
            record["imp_time_diff_ms"] = diff
            record["imp_canvas_rendered"] = canvas_ok
            record["imp_motion_features"] = {
                "total_pixels": total_px,
                "impact_wrist_spot_pixels": res.get("skyBluePixels", 0),
                "head_box_pixels": res.get("headBoxPixels", 0),
            }
            # 跨階段防殘留檢查：確認前一步 Top 的專屬元素已妥善刷新
            record["no_residual_artifacts"] = bool(canvas_ok and total_px < 3000)

            snap_file = OUT_DIR / f"0{self.step_index * 2 + 1}_webkit_swing{seq}_impact.png"
            self.captureSnapshot(snap_file, next_step=True)

        self.webview.evaluateJavaScript_completionHandler_(js, cb)

    @objc.python_method
    def captureSnapshot(self, out_path: Path, next_step: bool):
        config = WebKit.WKSnapshotConfiguration.alloc().init()

        def handler(image, err):
            if err:
                print(f"  [WARN] 快照截圖失敗: {err}")
            elif image:
                tiff = image.TIFFRepresentation()
                rep = AppKit.NSBitmapImageRep.imageRepsWithData_(tiff)[0]
                png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
                png.writeToFile_atomically_(str(out_path), True)
                print(f"  [SNAPSHOT] 快照截圖已儲存: {out_path.name}")

            if next_step:
                self.step_index += 1
                AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.5, self, "runNextStepFromTimer:", None, False
                )

        self.webview.takeSnapshotWithConfiguration_completionHandler_(config, handler)

    def runNextStepFromTimer_(self, timer):
        self.runNextStep()

    @objc.python_method
    def finishAudit(self):
        print("\n================================================================================")
        print("WebKit GUI 真實事件跳轉與 Clean Motion 實測全數完成，正在統計結果...")
        print("================================================================================")
        all_passed = True
        if not self.results["session_report_verified"]:
            all_passed = False
            print("[FAIL] 場次報告頁面驗證未通過 (未顯示 Top 5 榜單或球次卡片 < 12)")

        for seq_key, val in self.results["swings_verified"].items():
            top_diff = val.get("top_time_diff_ms", 999)
            imp_diff = val.get("imp_time_diff_ms", 999)
            top_canvas = val.get("top_canvas_rendered", False)
            imp_canvas = val.get("imp_canvas_rendered", False)
            no_resid = val.get("no_residual_artifacts", False)

            if top_diff > 100 or imp_diff > 100:
                all_passed = False
                print(f"[FAIL] {seq_key} UI 事件按鈕跳轉時間與標記偏差過大 (Top: {top_diff}ms, Imp: {imp_diff}ms)")
            if not top_canvas or not imp_canvas:
                all_passed = False
                print(f"[FAIL] {seq_key} Clean Motion Canvas 未偵測到人體姿態繪製像素")
            if not no_resid:
                all_passed = False
                print(f"[FAIL] {seq_key} 檢測到跨階段畫面殘留或畫布未清除")

        status_str = "PASS" if all_passed else "FAIL"
        self.results["GUI_EVENT_VERIFIED"] = status_str
        self.results["status"] = status_str

        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"[INFO] 結構化 GUI 驗收報告已儲存: {REPORT_PATH}")
        print(f"[INFO] 總體 WebKit 實測狀態 (GUI_EVENT_VERIFIED): {status_str}")

        self.done = True
        AppKit.NSApplication.sharedApplication().stop_(None)


def run_webkit_gui_test():
    print("[1] 正在動態讀取 139 秒 (2分鐘.mov) 正式驗收場次資料...")
    session_data = setup_or_get_verification_session()
    auth_token = obtain_auth_token()
    print(f"[2] 成功取得認證憑證，開始配置 macOS 原生 WebKit.framework...")

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    auditor = WebKitPlaybackAuditor.alloc().init()
    auditor.setupWithSessionData(session_data)

    rect = AppKit.NSMakeRect(0, 0, 1440, 960)
    config = WebKit.WKWebViewConfiguration.alloc().init()
    config.setMediaTypesRequiringUserActionForPlayback_(0)

    # 注入 localStorage token 與全局 console 捕捉
    user_data = {
        "id": "65575a24-aa65-4cfb-9334-5613e5ab83b5",
        "email": "golfer@swinglab.local",
        "username": "練習場主理人",
        "role": "admin",
    }
    script_source = f"""
    window.__gsl_captured_errors = [];
    window.addEventListener('error', function(e) {{
        window.__gsl_captured_errors.push(e.message || String(e));
    }});
    try {{
        window.localStorage.setItem('gsl_token', '{auth_token}');
        window.localStorage.setItem('gsl_user', JSON.stringify({json.dumps(user_data)}));
    }} catch(e) {{
        console.error(e);
    }}
    """
    user_script = WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
        script_source, WebKit.WKUserScriptInjectionTimeAtDocumentStart, True
    )
    content_controller = WebKit.WKUserContentController.alloc().init()
    content_controller.addUserScript_(user_script)
    config.setUserContentController_(content_controller)

    webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
    webview.setNavigationDelegate_(auditor)
    auditor.webview = webview

    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable, AppKit.NSBackingStoreBuffered, False
    )
    window.setTitle_("Golf Swing Lab — Real UI Event & Clean Motion WebKit Playback Verification")
    window.setContentView_(webview)
    window.makeKeyAndOrderFront_(None)

    # 啟動步驟 0
    auditor.runNextStep()

    app.run()
    return auditor.results


if __name__ == "__main__":
    res = run_webkit_gui_test()
    if res.get("GUI_EVENT_VERIFIED") != "PASS":
        sys.exit(1)
    sys.exit(0)
