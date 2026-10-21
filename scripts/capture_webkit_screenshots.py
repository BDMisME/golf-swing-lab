#!/usr/bin/env python3
"""
使用 macOS 原生 WebKit.framework 實測渲染截圖
(scripts/capture_webkit_screenshots.py)
"""

import sys
import time
from pathlib import Path

import AppKit
import objc
import WebKit

OUT_DIR = Path("docs/screenshots/webkit")
OUT_DIR.mkdir(parents=True, exist_ok=True)


class WebKitSnapshotter(AppKit.NSObject):
    def init(self):
        self = objc.super(WebKitSnapshotter, self).init()
        self.done = False
        return self

    def webView_didFinishNavigation_(self, webview, navigation):
        print("WebKit 頁面導航完成，等待渲染穩定...")
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self, "takeSnapshot:", None, False
        )

    def takeSnapshot_(self, timer):
        config = WebKit.WKSnapshotConfiguration.alloc().init()
        def completion_handler(image, error):
            if error:
                print(f"截圖失敗: {error}")
            elif image:
                tiff_data = image.TIFFRepresentation()
                bitmap = AppKit.NSBitmapImageRep.imageRepsWithData_(tiff_data)[0]
                png_data = bitmap.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
                out_path = OUT_DIR / "01_webkit_render.png"
                png_data.writeToFile_atomically_(str(out_path), True)
                print(f"[OK] WebKit 截圖成功儲存至: {out_path}")
            self.done = True
            AppKit.NSApplication.sharedApplication().stop_(None)

        self.webview.takeSnapshotWithConfiguration_completionHandler_(config, completion_handler)


def capture_url(url: str):
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    snapshotter = WebKitSnapshotter.alloc().init()

    rect = AppKit.NSMakeRect(0, 0, 1280, 800)
    config = WebKit.WKWebViewConfiguration.alloc().init()
    webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, config)
    snapshotter.webview = webview
    webview.setNavigationDelegate_(snapshotter)

    nsurl = AppKit.NSURL.URLWithString_(url)
    req = AppKit.NSURLRequest.requestWithURL_(nsurl)
    webview.loadRequest_(req)

    print(f"正在透過 macOS WebKit.framework 載入: {url}")
    app.run()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:23000"
    capture_url(url)
