# Golf Swing Lab R4 — macOS 原生應用程式打包與 `WKWebView` 實測報告 (`MAC_RELEASE_VERIFICATION.md`)

- **驗證日期**：2026-10-31 (Asia/Taipei)
- **目標環境**：macOS Apple Silicon (`arm64`)
- **應用程式版本**：`Golf Swing Lab.app` v1.4.0 (`CFBundleIdentifier = com.golfswinglab.desktop`)

---

## 1. `scripts/build_mac_app.sh` 安全升級驗證

### 1.1 修復之安全隱憂與新增保護機制
1. **移除危險無條件刪除**：移除舊版直接對 `/Applications/Golf Swing Lab.app` 與 `~/Desktop/Golf Swing Lab.app` 執行無條件 `rm -rf` 的行為；預設僅安裝至 `/Applications/Golf Swing Lab.app`，**絕不觸碰使用者 `~/Desktop`**。
2. **Bundle ID 驗證**：覆寫前使用 `/usr/libexec/PlistBuddy` 檢查目標 `.app` 的 `CFBundleIdentifier`，若非 `com.golfswinglab.desktop` 立即中止並拒絕覆寫。
3. **自動備份與一鍵回滾 (`--rollback`)**：
   - 升級前自動將既有 `/Applications/Golf Swing Lab.app` 完整備份至 `~/.golfswinglab/backups/app_bundles/Golf_Swing_Lab_<timestamp>.app`。
   - 支援 `./scripts/build_mac_app.sh --rollback` 一鍵還原至最近一次備份版本。
4. **Staging 原子替換與 Ad-hoc 簽章**：先於 `/tmp/gsl_app_stage_*/Golf Swing Lab.app` 完成 Mach-O `launcher` 編譯、圖示產生、`codesign --force --deep --sign -` 簽章與 `codesign --verify` 驗證後，才原子替換至 `/Applications/Golf Swing Lab.app`。
5. **使用者資料 100% 隔離**：打包與安裝過程完全不觸碰 `~/.golfswinglab/storage`、`~/.golfswinglab/session_secret` 與 PostgreSQL 資料目錄。

### 1.2 實機執行證據
- 建置指令：`./scripts/build_mac_app.sh` -> `EXIT_CODE=0`
- 備份產物：`/Users/mathew/.golfswinglab/backups/app_bundles/Golf_Swing_Lab_20261031_171042.app`
- `Info.plist` 驗證：
  - `CFBundleIdentifier`: `com.golfswinglab.desktop`
  - `CFBundleShortVersionString`: `1.4.0`
- `codesign -dv "/Applications/Golf Swing Lab.app"`：
  - `Executable=/Applications/Golf Swing Lab.app/Contents/MacOS/GolfSwingLab`
  - `Format=app bundle with Mach-O thin (arm64)`
  - `Signature=adhoc`

---

## 2. 原生 macOS `WKWebView` 視窗載入與渲染驗證

- **驗證腳本**：[verify_r4_webkit.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/scripts/verify_r4_webkit.py)
- **目標 URL**：`http://localhost:23000/tracer-studio/bdc28c60-74b8-4f9b-9e77-338a3d6336b1`（對應實拍 `11s_iphone.mov` 片段 `e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d`）
- **原生截圖證據**：`docs/r4/webkit_tracer_studio.png`（檔案大小：`542,442 bytes`，解析度：`1440×920` Retina）
- **DOM 與 JS Console 檢查結果 (`/tmp/r4_webkit_report.json`)**：
  - `hasCanvas`: `true` (`canvasCount = 1`)
  - `buttonCount`: `39`（含播放控制 `-5F / -1F / +1F / +5F`、5 大時間錨點快捷鍵、逐幀點位新增/移動/刪除、Copy-on-Write 修訂回滾、6 種特效風格與匯出面板）
  - `jsErrors`: `[]`（**0 筆 JavaScript 執行期錯誤或 Unhandled Rejection**）
  - 畫面呈現內容：成功載入並顯示 `✨ 11s_iphone.mov — R4 Tracer Studio 實測`、`原片 SHA256: 9df04b7b244f5678... · 正向解析度: 1080x1920 @ 60.04fps`、`Swing: NEEDS_REVIEW (Rev #1)`、`Shot: UNAVAILABLE (Rev #1)` 與完整繁體中文編輯器工作台。
