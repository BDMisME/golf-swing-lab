#!/usr/bin/env python3
"""
使用 macOS 原生 WebKit.framework 實測渲染真實揮桿影片畫面與 Clean Motion 動態標記
(scripts/capture_webkit_screenshots.py)
"""

import json
import sys
import time
from pathlib import Path

import AppKit
import objc
import WebKit

OUT_DIR = Path("docs/screenshots/webkit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TOKEN = (
    "eyJzdWIiOiI2NTU3NWEyNC1hYTY1LTRjZmItOTMzNC01NjEzZTVhYjgzYjUiLCJlbWFpbCI6ImdvbGZlckBzd2luZ2xhYi5sb2NhbCIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc5MzE3MTYyNn0."
    "5c32796215e240200cd296c37cede178add16a155ed5e3754e02e6b931b24c8a"
)


class WebKitSnapshotter(AppKit.NSObject):
    def init(self):
        self = objc.super(WebKitSnapshotter, self).init()
        self.done = False
        self.step = 0
        return self

    def webView_didFinishNavigation_(self, webview, navigation):
        print("WebKit 頁面導航完成，開始等待 React 渲染與影片就緒...")
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "preparePlayback:", None, False
        )

    def preparePlayback_(self, timer):
        # 點擊 top 事件按鈕跳轉至上桿頂點，觸發影片解碼與 Clean Motion 繪製
        js = """
        (function() {
            var topBtn = Array.from(document.querySelectorAll('button')).find(function(b) {
                return b.innerText && b.innerText.indexOf('top') !== -1;
            });
            if (topBtn) {
                topBtn.click();
            }
            var video = document.querySelector('video');
            if (video) {
                video.muted = true;
                video.play().catch(function() {});
            }
            return {
                clickedTop: !!topBtn,
                hasVideo: !!video,
                readyState: video ? video.readyState : -1,
                hasCanvas: !!document.querySelector('canvas')
            };
        })();
        """

        def js_callback(result, error):
            if error:
                print(f"JS 執行警告: {error}")
            else:
                print(f"頂點跳轉與狀態確認: {result}")
            # 等待 3 秒讓影片影格解碼並讓 Canvas 穩定繪製
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3.0, self, "takeSnapshot:", None, False
            )

        self.webview.evaluateJavaScript_completionHandler_(js, js_callback)

    def takeSnapshot_(self, timer):
        # 暫停影片以固定影格並拍攝高解析度快照
        self.webview.evaluateJavaScript_completionHandler_(
            "var v = document.querySelector('video'); if (v) v.pause();", None
        )

        config = WebKit.WKSnapshotConfiguration.alloc().init()

        def completion_handler(image, error):
            if error:
                print(f"截圖失敗: {error}")
            elif image:
                tiff_data = image.TIFFRepresentation()
                bitmap = AppKit.NSBitmapImageRep.imageRepsWithData_(tiff_data)[0]
                png_data = bitmap.representationUsingType_properties_(
                    AppKit.NSBitmapImageFileTypePNG, None
                )
                out_path = OUT_DIR / "02_webkit_swing_player.png"
                png_data.writeToFile_atomically_(str(out_path), True)
                print(f"[OK] WebKit 真實影片截圖成功儲存至: {out_path}")

                # 同時覆蓋 01_webkit_render.png
                fallback_path = OUT_DIR / "01_webkit_render.png"
                png_data.writeToFile_atomically_(str(fallback_path), True)
                print(f"[OK] 同步覆蓋更新: {fallback_path}")
            self.done = True
            AppKit.NSApplication.sharedApplication().stop_(None)

        self.webview.takeSnapshotWithConfiguration_completionHandler_(config, completion_handler)


def capture_swing(swing_id: str, token: str = DEFAULT_TOKEN):
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    snapshotter = WebKitSnapshotter.alloc().init()

    rect = AppKit.NSMakeRect(0, 0, 1440, 960)
    config = WebKit.WKWebViewConfiguration.alloc().init()

    # 允許自動播放與媒體載入（無需手勢互動）
    config.setMediaTypesRequiringUserActionForPlayback_(0)

    # 注入 localStorage token 避開登入頁面跳轉
    user_data = {
        "id": "65575a24-aa65-4cfb-9334-5613e5ab83b5",
        "email": "golfer@swinglab.local",
        "username": "練習場主理人",
        "role": "admin",
    }
    script_source = f"""
    try {{
        window.localStorage.setItem('gsl_token', '{token}');
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
    snapshotter.webview = webview
    webview.setNavigationDelegate_(snapshotter)

    # 建立 NSWindow 並掛載 webview，開啟 macOS GPU 視訊硬體解碼
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False
    )
    window.setContentView_(webview)
    window.orderFrontRegardless()
    snapshotter.window = window

    url = f"http://localhost:23000/swings/{swing_id}"
    nsurl = AppKit.NSURL.URLWithString_(url)
    req = AppKit.NSURLRequest.requestWithURL_(nsurl)
    webview.loadRequest_(req)

    print(f"正在透過 macOS WebKit.framework 載入真實單球頁面: {url}")
    app.run()


if __name__ == "__main__":
    swing_id = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "090204f5-d42a-4fa0-b72e-f07741e5cca7"
    )
    capture_swing(swing_id)
