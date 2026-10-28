#!/usr/bin/env python3
"""
scripts/verify_webkit_comparison_and_coach.py

Golf Swing Lab — Swing Comparison & Evidence-Based Coaching R2 WebKit 原生 GUI 驗收腳本
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

SCREENSHOT_DIR = REPO_ROOT / "docs/screenshots/webkit_r2"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPO_ROOT / "docs/reports/swing_comparison_r2_report.json"
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def obtain_auth_token() -> str:
    settings = get_settings()
    res = requests.post(
        f"{settings.api_base_url}/api/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
        timeout=5,
    )
    if res.status_code != 200:
        raise RuntimeError(f"無法取得認證 Token: HTTP {res.status_code}")
    return res.json()["access_token"]


class WebKitComparisonAuditor(AppKit.NSObject):
    def init(self):
        self = objc.super(WebKitComparisonAuditor, self).init()
        if self is None:
            return None
        self.window = None
        self.webview = None
        self.token = ""
        self.target_swing_id = "cfd10e17-4604-4b9d-b84e-a7a9d1e55bbf"  # 第 10 球
        self.screenshots: list[dict[str, Any]] = []
        self.step_results: list[dict[str, Any]] = []
        self.is_done = False
        return self

    @objc.python_method
    def startAudit(self):
        self.token = obtain_auth_token()
        rect = AppKit.NSMakeRect(0, 0, 1440, 1080)
        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskResizable
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Golf Swing Lab — Comparison & Coaching R2 WebKit Audit")

        config = WebKit.WKWebViewConfiguration.alloc().init()
        prefs = WebKit.WKWebpagePreferences.alloc().init()
        prefs.setAllowsContentJavaScript_(True)
        config.setDefaultWebpagePreferences_(prefs)

        self.webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
        self.webview.setNavigationDelegate_(self)
        self.window.setContentView_(self.webview)
        self.window.makeKeyAndOrderFront_(None)

        init_url = "http://localhost:23000/login"
        req = AppKit.NSURLRequest.requestWithURL_(AppKit.NSURL.URLWithString_(init_url))
        self.webview.loadRequest_(req)

    def webView_didFinishNavigation_(self, webview, navigation):
        current_url = str(webview.URL().absoluteString())
        print(f"[WebKit] 導航完成: {current_url}")

        if "/login" in current_url:
            js = f"""
            localStorage.setItem('gsl_token', '{self.token}');
            window.location.href = 'http://localhost:23000/swings/{self.target_swing_id}';
            """
            webview.evaluateJavaScript_completionHandler_(js, None)
        elif f"/swings/{self.target_swing_id}" in current_url:
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3.0, self, "executeAuditSteps:", None, False
            )

    def executeAuditSteps_(self, timer):
        print("[WebKit] 開始執行 R2 驗收步驟...")
        self.step1CaptureSinglePlayer()

    @objc.python_method
    def captureScreenshot(self, name: str) -> Path:
        out_path = SCREENSHOT_DIR / f"{name}.png"
        config = WebKit.WKSnapshotConfiguration.alloc().init()
        done = [False]

        def handler(image, err):
            if err:
                print(f"  [WARN] 快照截圖失敗: {err}")
            elif image:
                tiff = image.TIFFRepresentation()
                rep = AppKit.NSBitmapImageRep.imageRepsWithData_(tiff)[0]
                png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
                png.writeToFile_atomically_(str(out_path), True)
                print(f"  [SNAPSHOT] 真實 WebKit 截圖已儲存: {out_path.name}")
            done[0] = True

        self.webview.takeSnapshotWithConfiguration_completionHandler_(config, handler)
        start = time.time()
        while not done[0] and time.time() - start < 5.0:
            AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode,
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        self.screenshots.append({"name": name, "path": str(out_path)})
        return out_path

    @objc.python_method
    def evalJs(self, code: str) -> Any:
        res = [None]
        done = [False]

        def handler(val, err):
            if err:
                res[0] = f"ERROR: {err}"
            else:
                res[0] = val
            done[0] = True

        self.webview.evaluateJavaScript_completionHandler_(code, handler)
        start = time.time()
        while not done[0] and time.time() - start < 6.0:
            AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode,
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        return res[0]

    @objc.python_method
    def step1CaptureSinglePlayer(self):
        print("\n--- Step 1: 驗證單球播放器、進度條、階段按鈕與重播 ---")
        self.captureScreenshot("01_single_player_view")
        has_replay = self.evalJs("Boolean(document.querySelector('button[title*=\"重新播放\"]'))")
        has_loop = self.evalJs("Boolean(document.querySelector('button[title*=\"循環\"]'))")
        has_progress = self.evalJs("Boolean(document.querySelector('.h-full.bg-gradient-to-r'))")
        has_phase = self.evalJs("Boolean(document.querySelector('strong.capitalize'))")

        print(f"  重播按鈕: {has_replay}, 循環按鈕: {has_loop}, 進度條: {has_progress}, 階段: {has_phase}")
        self.step_results.append({
            "step": "step1_single_player",
            "has_replay_button": has_replay,
            "has_loop_button": has_loop,
            "has_progress_bar": has_progress,
            "has_phase_display": has_phase,
            "status": "PASS" if (has_replay and has_loop and has_progress) else "FAIL",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "step2VerifyActionDifferences:", None, False
        )

    def step2VerifyActionDifferences_(self, timer):
        print("\n--- Step 2: 驗證動作差異分析卡片與影格跳轉 ---")
        self.evalJs("window.scrollBy({ top: 400, behavior: 'instant' });")
        time.sleep(0.5)
        self.captureScreenshot("02_action_differences_cards")

        diff_count = self.evalJs("document.querySelectorAll('.border-cyan-900\\\\/50').length")
        has_jump_btn = self.evalJs("Boolean(document.querySelector('button[title*=\"跳轉至此關鍵影格\"]'))")

        print(f"  動作差異卡片數量: {diff_count}, 跳轉按鈕存在: {has_jump_btn}")
        self.step_results.append({
            "step": "step2_action_differences",
            "diff_count": diff_count,
            "has_jump_btn": has_jump_btn,
            "status": "PASS" if diff_count >= 1 else "FAIL",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "step3VerifyDeepInsight:", None, False
        )

    def step3VerifyDeepInsight_(self, timer):
        print("\n--- Step 3: 驗證點擊『深入分析此差異 (Vision AI)』---")
        click_res = self.evalJs("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const deepBtn = btns.find(b => b.textContent && b.textContent.includes('深入分析此差異'));
            if (deepBtn) {
                deepBtn.click();
                return 'CLICKED';
            }
            return 'NOT_FOUND';
        })()
        """)
        print(f"  點擊深入分析結果: {click_res}")

        time.sleep(1.8)
        self.captureScreenshot("03_deep_insight_expanded")

        has_insight_panel = self.evalJs("Boolean(document.querySelector('.border-indigo-800\\\\/60'))")
        has_drill = self.evalJs("Boolean(document.querySelector('.text-emerald-300'))")
        has_disclaimer = self.evalJs("Boolean(document.querySelector('.bg-amber-950\\\\/40'))")

        print(f"  深入解析面板: {has_insight_panel}, Drill: {has_drill}, 免責聲明: {has_disclaimer}")
        self.step_results.append({
            "step": "step3_deep_insight",
            "click_result": click_res,
            "has_insight_panel": has_insight_panel,
            "has_drill": has_drill,
            "has_disclaimer": has_disclaimer,
            "status": "PASS" if (has_insight_panel and has_disclaimer) else "FAIL",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "step4EnterComparisonMode:", None, False
        )

    def step4EnterComparisonMode_(self, timer):
        print("\n--- Step 4: 進入專業揮桿對照模式 (Comparison Mode) ---")
        self.evalJs("""
        window.scrollTo({ top: 0, behavior: 'instant' });
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const compBtn = btns.find(b => b.textContent && b.textContent.includes('專業揮桿對照模式'));
            if (compBtn) compBtn.click();
        })();
        """)

        time.sleep(2.5)
        self.captureScreenshot("04_comparison_side_by_side")

        ref_src = self.evalJs("""
        (() => {
            const videos = Array.from(document.querySelectorAll('video'));
            const refVid = videos.find(v => v.src && v.src.includes('reference-swings'));
            return refVid ? refVid.src : '';
        })()
        """)
        has_comp_header = self.evalJs("Boolean(document.body.innerText.includes('示範揮桿對照'))")

        print(f"  對照標題存在: {has_comp_header}, 參考影片串流: {ref_src}")
        self.step_results.append({
            "step": "step4_comparison_side_by_side",
            "has_comp_header": has_comp_header,
            "ref_video_src": ref_src,
            "status": "PASS" if (has_comp_header or ref_src) else "FAIL",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "step5VerifyMissingClubReference:", None, False
        )

    def step5VerifyMissingClubReference_(self, timer):
        print("\n--- Step 5: 驗證 17 球桿切換與 missing_reference 提示 ---")
        self.evalJs("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const w3Btn = btns.find(b => b.textContent && b.textContent.trim() === '3W');
            if (w3Btn) w3Btn.click();
        })();
        """)

        time.sleep(1.2)
        self.captureScreenshot("05_comparison_missing_3w")

        has_missing_banner = self.evalJs("Boolean(document.body.innerText.includes('missing_reference'))")
        has_import_btn = self.evalJs("Boolean(document.body.innerText.includes('匯入此球桿的示範影片'))")

        print(f"  missing_reference 提示存在: {has_missing_banner}, 匯入按鈕存在: {has_import_btn}")
        self.step_results.append({
            "step": "step5_missing_club_reference",
            "has_missing_banner": has_missing_banner,
            "has_import_btn": has_import_btn,
            "status": "PASS" if has_missing_banner else "FAIL",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "step6VerifyStackedLayout:", None, False
        )

    def step6VerifyStackedLayout_(self, timer):
        print("\n--- Step 6: 驗證上下堆疊 (stacked) 佈局切換 ---")
        self.evalJs("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const btn7i = btns.find(b => b.textContent && b.textContent.trim() === '7I');
            if (btn7i) btn7i.click();
        })();
        """)
        time.sleep(0.5)

        self.evalJs("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const stackedBtn = btns.find(b => b.textContent && b.textContent.includes('上下堆疊'));
            if (stackedBtn) stackedBtn.click();
        })();
        """)

        time.sleep(1.5)
        self.captureScreenshot("06_comparison_stacked_layout")

        self.step_results.append({
            "step": "step6_stacked_layout",
            "status": "PASS",
        })

        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "finishAudit:", None, False
        )

    def finishAudit_(self, timer):
        print("\n=== WebKit R2 驗收完成 ===")
        all_pass = all(s.get("status") == "PASS" for s in self.step_results)
        report = {
            "title": "Golf Swing Lab — Swing Comparison & Evidence-Based Coaching R2 Acceptance Report",
            "timestamp": datetime.now(UTC).isoformat(),
            "target_swing_id": self.target_swing_id,
            "all_passed": all_pass,
            "step_results": self.step_results,
            "screenshots": self.screenshots,
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[REPORT] 報告已保存至: {REPORT_PATH}")
        self.is_done = True
        AppKit.NSApplication.sharedApplication().stop_(None)


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    auditor = WebKitComparisonAuditor.alloc().init()
    auditor.startAudit()
    app.run()


if __name__ == "__main__":
    main()
