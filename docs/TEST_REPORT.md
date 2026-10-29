# TEST_REPORT.md — 自動化測試與實測證據報告

> 本報告記錄 R0–R12 每輪測試實際執行結果與瀏覽器實測證據。所有紀錄皆來自真實執行之命令與輸出，絕不虛構。

## 1. 測試環境資訊
- **作業系統**：macOS (`aarch64-apple-darwin`)
- **Python 環境**：Python 3.12.13 (`uv` 虛擬環境管理，共 74 個套件)
- **Node / 前端環境**：Node.js v24.21.0, Next.js 15.5.28, React 19, TypeScript 5.7, Vitest 3.2.7
- **媒體工具**：FFmpeg / ffprobe 9.0.2_1 (含 `libx264`, `libx265`)
- **2D 姿態推論模型**：Google MediaPipe `PoseLandmarker` (`pose_landmarker_lite.task`, Apache-2.0)
- **容器環境**：Docker Desktop (`gsl-postgres-dev` PostgreSQL 16 @ `25432`, `gsl-redis-dev` Redis 7 @ `26379`, `gsl-minio-dev` MinIO @ `29000/29001`)

---

## 2. 各輪次測試摘要 (R0–R12)

| 輪次 | 測試範圍 | 執行指令 | 通過 / 失敗 | 性質 (Real / Mock) | 狀態 |
|---|---|---|---|---|---|
| **Round 17 PR #2 正式授權合併、Mac 原生 App 更新與 Personal Beta 正式部署 (Personal Beta Merge & Mac App Deployment)** | 依專案負責人明確授權執行 `gh pr merge 2 --squash`，PR #2 正式合併至 main（Merge Commit `8e369b47c841b6c286a8905fc15b5a98300b75de`）；本機 main 分支同步至該 Commit，工作樹乾淨零二進制殘留；`bash scripts/build_mac_app.sh` 重新編譯 arm64 Mach-O launcher 並安裝至 `/Applications/Golf Swing Lab.app`，通過 codesign 與 LaunchServices 註冊；`scripts/verify_18_reference_swings.py` 逐筆驗核資料庫與本機 Storage 18 筆示範揮桿（16 正式 + 2 fixture），0 缺失、0 解碼錯誤，11 支 `confirmed_strike`（來源 `developer_visual_annotated`）、5 支 `impact_estimated`（來源 `estimated`）、0 支 `unresolved`，100% 支援自然同步錨點；Next.js 15.5.28 9/9 靜態路由 build 0 錯誤；後端健康檢查 `/healthz` 與 `/readyz` 100% 通過；WebKit 原生 GUI 12 大步驟端到端實測全數通過（時鐘同步漂移僅 2.6ms，Top/Impact 誤差 0ms，雙側解碼非黑畫面 Mean 111.5 / 135.0，Token 零洩漏）；全套後端測試套件 95/95 100% 通過 (216.56s)。 | `gh pr merge 2 --squash` + `bash scripts/build_mac_app.sh` + `uv run python scripts/verify_18_reference_swings.py` + `npm --prefix apps/web run build` + `uv run python scripts/verify_webkit_comparison_and_coach.py` + `uv run pytest tests/` | 95 / 95 全量後端測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面, 漂移 2.6ms, Token 零洩漏), 18 筆示範庫驗證 100% PASS, Mac 原生 App 安裝完成 | Real (GitHub PR #2 Squash and Merge, arm64 Mach-O /Applications/Golf Swing Lab.app, macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 18 筆示範庫) | `PASS` (PR #2 正式合併至 main，Mac App 更新完成，Personal Beta 正式部署) |
| **Round 16 PR #2 最終合併前素材清理與 Git 差異純淨化 (Pre-Merge Assets Untracking & Release Diff Sanitization)** | 完整備份 `assets/reference_videos/` 內 12 個二進制檔案至 `~/.golfswinglab/assets_reference_videos_backup/`，並備份 15 張包含使用者原片/第三方影格之快照至 `~/.golfswinglab/webkit_r2_screenshots/`；執行 `git rm --cached` 移除這 12 個媒體檔案與 `docs/screenshots/webkit_r2/` 全部 15 張截圖，從 PR 發行差異中徹底排除未授權再散布影像；更新 `.gitignore` 杜絕再次提交；驗證 `git diff main assets/ docs/screenshots/webkit_r2/` 輸出為空（差異完全為 0）；更新 `scripts/seed_reference_library.py` 加入安全跳過日誌，無 MP4 素材時優雅跳過（Exit Code 0）；核驗本機 Storage `~/.golfswinglab/storage/references/` 下 16 支正式示範影片 100% 存在且大小健全；實測 7I、Driver、3W 之 HTTP 206 Partial Content Range 串流皆正常；資料庫、API 與報告維持 0ms 漂移一致性（`tests/test_reference_events_consistency.py` 5/5 PASSED）；macOS 原生 WebKit WKWebView 12 大步驟端到端實測 100% 通過（時鐘同步漂移僅 2.9ms，Top/Impact 誤差 0ms，雙側非黑畫面 Mean 111.5 / 135.0，Token 零洩漏）；全套後端測試 95/95 100% 通過 (220.91s)，Next.js 9/9 靜態路由 build 0 錯誤。 | `git rm --cached assets/reference_videos/* && git rm -r --cached docs/screenshots/webkit_r2/` + `PYTHONPATH=. uv run python scripts/seed_reference_library.py` + `uv run pytest tests/test_reference_events_consistency.py -v` + `uv run python scripts/verify_webkit_comparison_and_coach.py` + `uv run pytest tests/` + `npm --prefix apps/web run build` | 95 / 95 全量後端測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面, 漂移 2.9ms, Token 零洩漏), 一致性回歸測試 5/5 PASS, 發行差異純淨化 100% | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 16 支真實示範庫) | `PASS` (最終合併前素材清理與 Git 差異純淨化全面通過，個人 Beta 釋出就緒) |
| **Round 15 PR #2 資料一致性、真值擊球確認、本機素材隔離與個人 Beta 釋出治理 (Data Consistency, Truthful Strike Verification & Release Governance)** | 建立單一權威事實來源字典 `STRIKE_EVIDENCE_MAP`，將審查確認之 Top 與 Impact 錨點直接綁定為 active events，並在 `scripts/verify_reference_events_and_generate_sheets.py` 中 100% 寫回 PostgreSQL，徹底消除報告與資料庫時間碼漂移；完全保留原始 Candidate Events 於 `calibration_params["candidate_events"]`，`calibration_params["active_events"]` 與 `event_timestamps` 100% 同步且誤差為 **0ms**；示範影片資料庫記錄恆定為 18 筆（16 支新 bundle + 2 支既有 fixture），維持原有 UUID，無重複記錄或垃圾資料膨脹；移除按球桿名批量推論邏輯，嚴格依真實影像證據判定擊球確認度（Confirmed Strike 11 支 68.8%、Impact Estimated 5 支 31.2%、Unresolved 0 支）；03_Wood5.mp4 專項影格診斷（解碼 Frame 37 1233ms 桿身仍在腰部、Frame 38 1267ms 接近球位、Frame 39 1300ms 球飛出，確認擊球發生於 30fps 快門間隙，時間碼校正為 Frame 38 1267ms 並標記為 `impact_estimated`）；Contact Sheet 標籤文字反映真實狀態；16 張 Contact Sheet JPG 安全備份於 `~/.golfswinglab/reference_contact_sheets/`，資料庫備份保存於 `~/.golfswinglab/backups/reference_swings_backup.json`；以 `git rm --cached` 移除追蹤並更新 `.gitignore`，嚴禁 Force Push；撰寫專項自動化一致性回歸測試 `tests/test_reference_events_consistency.py` 5/5 PASSED (100%)；macOS 原生 WebKit WKWebView 12 大步驟端到端實測 100% 通過（Top/Impact 誤差 0ms、雙側非黑畫面 Mean 111.5 / 135.0、時鐘漂移 2.5ms、Token 零洩漏）；全套後端測試 95/95 100% 通過 (200.41s)，Next.js 9/9 靜態路由 build 0 錯誤。 | `PYTHONPATH=. uv run python scripts/verify_reference_events_and_generate_sheets.py` + `uv run pytest tests/test_reference_events_consistency.py -v` + `uv run python scripts/verify_webkit_comparison_and_coach.py` + `uv run pytest tests/` + `npm --prefix apps/web run build` | 95 / 95 全量後端測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面, 漂移 2.5ms, Token 零洩漏), 一致性回歸測試 5/5 PASS | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 16 支真實示範庫) | `PASS` (資料一致性 0ms 誤差、擊球真值客觀分類、本機素材隔離清理與個人 Beta 釋出治理全面通過) |
| **Round 14 16 支真實示範影片影格事件驗證、Contact Sheet 生成、安全備份與可信度修復交付 (Reference Events Kinematic Verification & Contact Sheet Proof)** | 真正讀取 16 支 MP4 視訊解碼影格，逐幀分析手腕物理極小值 (Top 頂點與轉換啟動) 與擊球區桿頭過球 (Impact 觸球出球)；產出 16 張 3x3 高解析 Contact Sheet (`docs/reports/reference_contact_sheets/*.jpg`)；生成結構化總檢驗報告 `reference_events_verification.json` 與 Markdown 審查報告 `reference_events_verification.md`；查明並修正 5W 裁切誤入口播廣告大字之缺陷，重新校準為第 1 記全揮桿 (Top 867ms, Impact 1233ms, Downswing 366ms)；事件來源嚴格標記 `developer_visual_annotated` 或 `estimated`；六維度旗標修復 (Confirmed Strike 15 支 93.8%, 慢動作 3W/6I/SW 標記 Realtime Sync=False, Putter 誠實標記 Events Reliable=False)；資料庫執行前自動備份至 `reference_swings_backup.json`，原地雙向錨定 UPDATE 保證 UUID 恆定；macOS 原生 WebKit 12 大步驟端到端實測 100% 通過 (Top/Impact 誤差 0ms, 雙側非黑畫面 Mean 111.5 / 135.0, 時鐘漂移 2.8ms, Token 零洩漏)；全套後端測試 90/90 100% 通過 (211.88s)，Next.js 9/9 靜態路由 build 0 錯誤。 | `PYTHONPATH=. uv run python scripts/verify_reference_events_and_generate_sheets.py` + `PYTHONPATH=. uv run python scripts/import_16_reference_bundle.py` + `uv run python scripts/verify_webkit_comparison_and_coach.py` + `uv run pytest tests/` + `npm --prefix apps/web run build` | 90 / 90 全量後端測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面, 漂移 2.8ms, Contact Sheet 16/16 齊全) | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 16 支真實示範庫) | `PASS` (16 支示範影片影格級真實事件驗證、Contact Sheet 生成與資料庫安全備份更新全面通過) |
| **Round 13 16 支示範影片獨立精度修復與真實 FPS 驗收 (Reference Swings Independent Precision Remediation & Real FPS Verification)** | 徹底根除所有寫死固定假時間碼 (Top+300ms, 慢動作Top+1200ms, 時長百分比)；採用 CoarseToFineDetector 狀態機與 2D 骨架手腕物理軌跡 (Top 手腕最高 y 局部極小值、Impact 觸球區) 精準定位；重新逐支確立乾淨單球區間 (Address 站定 -> 上桿 -> Top -> 擊球 -> 收桿平衡)，徹底排除跨球或片頭片尾；持久化六維度技術狀態旗標 (`media_processed`, `pose_analyzed`, `is_valid_clip`, `events_reliable`, `supports_realtime_sync`, `supports_phase_sync`)；前端播放器移除固定 33.333ms，依兩側各自真實 FPS 計算單影格步進 ($\Delta t = 1/\text{FPS}$)；完整支援 19 類球桿，缺少 6 桿 (7W, 3H, 4H, 5H, 3I, GW/AW) 誠實標示 `missing_reference`，絕不拿通用 Hybrid 混充 3H/4H/5H；macOS 原生 WebKit WKWebView 12 大步驟端到端實測 100% PASS (Top/Impact 誤差 0ms、兩側解碼非黑畫面、同步時鐘漂移 2.4ms、無任何 Token 洩漏)；全套後端測試 90/90 100% 通過 (202.29s)，Next.js 9/9 路由構建 0 錯誤。 | `PYTHONPATH=. uv run python scripts/import_16_reference_bundle.py` + `uv run python scripts/verify_webkit_comparison_and_coach.py` + `uv run pytest` + `npm --prefix apps/web run build` | 90 / 90 全量後端測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面, 漂移 2.4ms) | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 16 支真實示範庫) | `PASS` (16 支示範影片精度徹底修復，假時間碼徹底根除，單影格真實 FPS 步進通過) |
| **Round 12 16 支真實高爾夫示範影片匯入與 19 桿雙影片同步對照驗收 (16 Reference Bundle Import & Multi-Club Dual-Video Sync Verification)** | 本機提供之 16 支真實高爾夫示範影片（13 支主示範 + 3 支 Bonus）解壓至獨立暫存區 `~/.golfswinglab/reference_import_staging/`，SHA-256 100% 比對吻合；FFmpeg 依原始長寬比與解析度完成單次揮桿精準切片、縮圖抽取與 MediaPipe 2D 骨架抽取入庫（共 18 筆示範揮桿記錄，檔案存於本機 NVMe 隔離區 `~/.golfswinglab/storage/references/`，零大檔案提交 Git）；球桿模型擴充支援 19 類（Driver ~ Putter）+ 通用 Hybrid，4 桿無合格來源（3I, 7W, Hybrid, GW）透明標記 `missing_reference` 並提供友好導引與上傳 Modal；慢動作素材（3W, 6I, SW）標註 `⏱️ 慢動作示範` 且嚴禁計入自然節奏，非全揮桿（PW, 8I, LW, Putter, SW Bunker）標記 `needs_calibration` 或 `special_mode`；雙影片對照組件升級（移除 video src 中的 `#t` media fragment 消除 seek 污染、支援獨立單側控制、等比例縮放與 X/Y 位移微調）；macOS 原生 WebKit WKWebView 12 大步驟端到端實測 100% 通過（Top/Impact 跳轉誤差 0ms、雙視訊解碼畫面非黑畫面、Driver/3W/7W 切換全部通過，產出 11 張 GPU 原生截圖與全 PASS 脫敏驗收報告 `swing_comparison_r2_report.json`）；後端專項測試 8/8 PASSED，Next.js 9/9 靜態路由 build 0 錯誤。 | `uv run pytest tests/test_token_leak_prevention.py tests/test_swing_comparison_and_coach.py` + `npm --prefix apps/web run build` + `uv run python scripts/verify_webkit_comparison_and_coach.py` | 8 / 8 專項測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 12 步驟 100% PASS (Top/Impact 0ms 誤差, 雙影片解碼無黑畫面) | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機 16 支真實示範庫) | `PASS` (16 支示範素材完整匯入與雙影片對照全部驗收通過) |
| **Round 11 PR #2 獨立工程審查補救 (Independent Audit Remediation — 解除 NO-GO 判定)** | P0-A 立即處理驗收 Token 洩漏（金鑰輪替、KNOWN_LEAKED_SECRETS 黑名單阻擋、撤銷舊 Token 401 拒絕、全域 URL/報告脫敏 `token=[REDACTED]`、新建專項測試 4/4 通過）；P0-B 修正不實的 7I / Driver 職業標準素材（移除虛假來源，7I 降為 `test_fixture`、Driver 為 `close_up`、其餘 15 桿標記 `missing_reference`）；P0-C 真正修復雙影片同步播放（`PlaybackDriftController` 時鐘平滑追趕，移除硬 seek 黑畫面，雙視訊同時播放與 currentTime 同步遞增實測通過）；P1-A 真實骨架自適應 Auto-Framing（MediaPipe 2D 肩髖長度換算比例，特寫鏡頭誠信降級）；P1-B 參考庫治理與安全匯入（Alembic 0002 遷移、`/import-local` 限制白名單與大小、無 events 標記 `needs_calibration` 嚴禁捏造時間碼、Multipart 上傳）；P1-C 動作差異分析與誠信修正（幾何提示標記 `rule_based_advice`、移除因果臆測）；P1-D 17 種球桿資料庫文件與規範；後端專項測試 8/8 通過、全套測試 61/61 PASSED (100%)、Next.js 9/9 靜態路由 build 0 錯誤、macOS 原生 WebKit WKWebView 6 大步驟實測 100% 通過（產出 6 張真實原生截圖與安全脫敏報告 `swing_comparison_r2_report.json`）。 | `uv run pytest tests/test_token_leak_prevention.py tests/test_swing_comparison_and_coach.py` + `uv run pytest` + `npm --prefix apps/web run build` + `uv run python scripts/verify_webkit_comparison_and_coach.py` | 8 / 8 專項測試通過 (100%), 61 / 61 全量測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 6 步驟 100% PASS (雙影片播放推進正常) | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機安全密鑰與示範庫) | `PASS` (PR #2 審查缺陷全數修復，解除 NO-GO 判定) |
| **Round 10 雙影片專業比較播放器、17 球桿示範庫與動作差異 AI 教練 (Evidence-Based Coaching R2) 驗收** | P0 單球播放器升級（重播與循環播放 Toggle、±1f/±5f 真實影格步進約束、9 階段發光跟隨與推估擊球標註）；P1 專業揮桿比較（17 種球桿分類標準、ReferenceSwing 資料模型與 REST API、HTTP 206 串流、7I 標準 DTL 與 Driver 特寫示範種子、雙影片比較播放器組件、SwingSynchronizationEngine Mode A 自然節奏與 Mode B 分段線性同步、等比例 Auto-Framing、missing_reference 誠實標籤）；P2 動作差異分析 AI Coach（精煉 1~2 項客觀幾何差異卡片、影格一鍵跳轉、深入分析此差異 Vision AI 運動學解讀與練習 Drill 課表、最高誠信原則免責聲明）；專項測試 4/4 通過、回歸測試 26/26 通過、Next.js 9/9 靜態路由編譯 0 錯誤、macOS 原生 WebKit WKWebView 6 大步驟實測 100% 通過（產出 6 張原生快照與 swing_comparison_r2_report.json）。 | `uv run pytest tests/test_swing_comparison_and_coach.py` + `uv run pytest tests/test_auto_accuracy_correction.py tests/test_final_evidence_lock.py tests/test_swing_10_regression.py tests/test_r3_verifiable_scoring.py` + `npm --prefix apps/web run build` + `uv run python scripts/verify_webkit_comparison_and_coach.py` | 4 / 4 專項測試通過 (100%), 26 / 26 回歸測試通過 (100%), 前端 9 路由 0 錯誤, WebKit GUI 6 步驟 100% PASS | Real (macOS 原生 WebKit WKWebView, Port 28000 API, Port 23000 Web, PostgreSQL 16, 本機示範庫) | `PASS` (可視覺同步比較與證據驅動教練全面就緒) |
| **Round 9 大影片分段上傳與登入憑證失效處理修復** | 1.38GB 大影片分段上傳 85% 失敗根因修復（Docker VM 空間滿引發 MinIO 錯誤，移除 HybridStorage 非法分段跨後端降級，依 upload_id 嚴格綁定單一物理後端，改用本機 NVMe `~/.golfswinglab/storage` 160GB+ 大容量高速存儲模式；保留雙向向後相容 fallback 支援歷史 340 場次播放；真實 24MB iPhone MOV 影片 5 分段上傳合併、ffprobe 解析、背景 Worker 分析 100% 耗時 9.9s 與 HTTP 206 串流實測全數通過）；首頁「登入憑證簽章驗證失敗」修復（`apiFetch` 捕捉 401 自動清除無效 Token 並重定向至 `/login?expired=1`，首頁提供重新登入與重新整理引導）；核心測試 27/27 通過，前端 Next.js 9 路由編譯 0 錯誤。 | `uv run pytest tests/` + `uv run python scripts/verify_multipart_upload.py` + `npm --prefix apps/web run build` | 27 / 27 核心測試通過 (100%), 分段上傳合併串流 100% PASS, 前端 9 路由 0 錯誤 | Real (真實 iPhone 11s.mov 24MB, 本機 NVMe, Port 28000 API, Port 23000 Web) | `PASS` (生產阻斷問題徹底解除) |
| **Round 8 PR #1 Final UI Event Verification & Local Secret Fail-Closed Gate 驗收** | P0 真實 UI 事件跳轉驗收（動態讀取 139 秒最新分析 Session `e8e182dd-...` 與真實球次 ID；前端事件跳轉加入定格暫停 `video.pause()`，原生 WebKit 以真實 DOM `btn.click()` 點擊觸發；Swing #8、#9、#10 點擊 Top 與 Impact 實測播放解碼誤差均為 0.0ms <= 100ms 門檻；Clean Motion Canvas 姿態線、手腕光環、擊球點、頭部圈特徵驗證與跨階段防殘留保護全數通過，Console 0 錯誤，產出 7 張原生快照與 JSON 報告）；P1 本機金鑰持久化 Fail-Closed（`resolve_session_secret` 於目錄建立失敗或權限不足時明確拋出 `RuntimeError`，杜絕靜默降級，單元測試通過）；後端測試套件 82/82 100% 通過 (202.73s)，前端 Next.js 15 構建 0 錯誤。 | `uv run python scripts/verify_webkit_gui_playback.py` + `uv run pytest` + `npm --prefix apps/web run build` | 82 / 82 通過 (100%), WebKit GUI 真實跳轉 100% PASS (0.0ms 誤差), 前端 9 路由 0 錯誤 | Real (macOS 原生 WebKit WKWebView, 本機 Port 28000 API, Port 23000 Web, 真實 139 秒 iPhone 錄影) | `PASS` (個人 Beta 發布全部閘門就緒) |
| **Round 7 PR #1 Final Security & Visual Smoke Gate 驗收** | 真正移除 Git 中的 JWT 簽章密鑰（`resolve_session_secret()` 動態解析與 `~/.golfswinglab/session_secret` 本機 0600 持久化，禁止在代碼中寫死金鑰；`KNOWN_LEAKED_SECRETS` 黑名單全面攔截外洩金鑰；舊 Token 實測回傳 `401 AUTH_INVALID_SIGNATURE` 徹底作廢，新 Token 正常簽發與驗證）；macOS 原生 WebKit.framework GUI 實測（真實開啟場次報告頁面與 Top 5 榜單，產出 `01_webkit_session_report.png`；導航至第 8、9、10 球逐球跳轉 Top 與 Impact，影片播放時間 `video.currentTime` 與標記時間誤差均為 0.0ms <= 100ms 門檻；全畫布像素掃描驗證 Clean Motion Canvas 骨架確實繪製，Console 0 錯誤，產出全部 7 張截圖與 JSON 報告）；後端測試套件 82/82 100% 通過（`time.monotonic()` 防時鐘跳轉升級），前端 Next.js 15 構建 0 錯誤。 | `uv run python scripts/verify_webkit_gui_playback.py` + `uv run pytest` + `npm --prefix apps/web run build` | 82 / 82 通過 (100%), WebKit GUI 實測 100% PASS, 前端 9 路由 0 錯誤 | Real (macOS 原生 WebKit WKWebView, 本機 Port 28000 API, Port 23000 Web, 測試影片) | `PASS` (個人 Beta 發布安全與視覺播放閘門通過) |
| **Round 6 Beta Release 驗收** | P0 安全修復（徹底移除 `scripts/capture_webkit_screenshots.py` 硬編碼 JWT，改由環境變數或 auth 模組動態簽發；輪替後端 `session_secret` 使外洩憑證徹底失效）；修正姿勢排行榜（移除 `get_posture_composite_score()` 退回使用 `overall_score` 的錯誤回退，無姿勢分項時回傳 `None`，杜絕總分冒充）；健全測試版本追溯（`run_production_acceptance.py` 動態注入 Git SHA、Clean/Dirty 狀態、原片 SHA-256、測試時間戳記與軟體版本）；隔離環境端到端 Mac App Smoke Test（以臨時 SQLite 與 Local Storage 執行真實 139 秒 iPhone 錄影完整 Pipeline：建立場次 → 影片匯入 → 720p/30fps Proxy 轉碼 → Coarse-to-Fine 偵測 → MediaPipe 姿態關鍵點與 Clean Motion 骨架抽取 → 9 階段狀態機 → 評分引擎 → DB 持久化 → 場次報告 API 與 Top 5 排行榜驗證 → 單球播放 API 與 Clean Motion 一致性驗證 → 資源 100% 安全清理）；後端測試套件 80/80 100% 通過，前端 Next.js 15 構建 0 錯誤。 | `uv run python scripts/smoke_test_mac_app.py` + `uv run python scripts/run_production_acceptance.py` + `uv run pytest` + `npm --prefix apps/web run build` | 80 / 80 通過 (100%), 隔離 Smoke Test 100% 通過, 雙路徑 12/12 球全數通過 (Proxy Top MAE 86.1ms, Imp MAE 30.5ms, 自動通過率 91.7%), 前端 9 路由 0 錯誤 | Real (測試影片/2分鐘.mov 與 720p/30fps Proxy, 11秒.mov, 隔離 SQLite DB) | `PASS` (開發集對齊通過，外部獨立盲測維持標記 `NOT_VALIDATED`) |
| **Round 5 Final RC Gate 驗收** | 解決 Top 精度重大回退（Top Plateau Saturated Height & Downswing Initiation：幾何高度於頂點 15% 區間平滑飽和，避免微差壓制下桿發動轉折；手腕向下速度與加速度爆發轉折加分；生理下桿時長相容性 190~390ms 平坦中立，>480ms 重懲；30fps Proxy Top MAE 由 124.4ms 降至 86.1ms / 2.6 影格，PASS；60fps 原片 Top MAE 降至 90.4ms / 5.4 影格，PASS；Swing #9 誤差降至 80ms，Swing #10 下桿時長由 534ms 恢復至 367ms）；修正最佳姿勢排行榜（實作專門的姿勢綜合評分，前傾穩定 60% + 頭部位移 40%，產出具備 Δ=X° 與 r=Y 說明之真實姿勢分數；節奏榜對 <50 分項目自動標註「本場相對最佳」）；驗收報告全面改由推論 JSON 100% 動態生成，納入影片 SHA-256 與 Git Commit 證據；全套 80 個測試 100% 通過，前端 Next.js 15 構建 0 錯誤。 | `uv run python scripts/run_production_acceptance.py` + `uv run pytest` + `npm --prefix apps/web run build` | 80 / 80 通過 (100%), 雙路徑 12/12 球全數通過 (Proxy Top MAE 86.1ms, Imp MAE 30.5ms, 自動通過率 91.7%), 前端 9 路由 0 錯誤 | Real (測試影片/2分鐘.mov 與 720p/30fps Proxy, 11秒.mov) | `PASS` (開發集對齊通過，外部獨立盲測維持標記 `NOT_VALIDATED`) |
| **Round 4 Release Candidate 驗收** | 大幅降低不必要的 needs_review（Tri-State Audio-Kinematic Plausibility：遍歷候選區間全體音訊瞬態，區分環境/隨揮雜音拒絕與跨模態衝突；運動學最低點扎實時安全拒絕雜音，維持 auto_accepted；30fps Proxy 自動通過率由 41.7% 提升至 91.7%）；解除下桿時間過度集中於 ~333ms（移除 Top 評分中 +5.0 吸附偏見，生理時序 180~600ms 中立化，以手腕空間幾何最高點與換向零交越為主導，展現自然節奏多樣性）；推論 JSON 與 Markdown 報告 100% 一致性自動斷言（杜絕狀態漂移）；True E2E Pipeline 實測（真實 11 秒 iPhone 錄影完整鏈路測試、走路/非揮桿 0 評分保護、動態走樣嚴厲扣分）；全套 80 個測試通過，前端 Next.js 15 構建成功。 | `uv run python scripts/run_production_acceptance.py` + `uv run pytest` + `npm --prefix apps/web run build` | 80 / 80 通過 (100%), 雙路徑 12/12 球全數通過, 前端 9 路由 0 錯誤 | Real (測試影片/2分鐘.mov 與 720p/30fps Proxy, 11秒.mov) | `PASS` (開發集對齊通過，外部獨立盲測維持標記 `NOT_VALIDATED`) |
| **Round 3 最終事件誠信與真實 App 驗收** | 查明第 10 球 Impact 誤判 121067ms 根因（121060ms 隨揮後雜音脈衝）；實作運動學合理性閘門 (Kinematic Plausibility Gate on Audio：深度、垂直速度、運動學最低點偏差檢驗)；第 10 球 Impact 精確收斂至 120967ms（誤差 52ms / 1.6 影格），60fps 原片收斂至 120932ms（誤差 17ms / 1.0 影格）；標記 audio_kinematic_conflict 與 needs_review，信心度降級 0.65，不確定度放大至 82ms；徹底移除驗收腳本 sorted()，全面改用正式 rank_session_swings()；第 10 球嚴格排除於 TEMPO 與 POSTURE 排行榜外（TEMPO 由第 7 球正當奪得）；單元與 API 端點回歸測試；30fps Proxy：Top MAE 58.4ms (1.8 影格), Impact MAE 32.7ms (1.0 影格), 分類 100%, 生理下桿 100%, 時序異常 0。60fps 原片：Top MAE 76.5ms (4.6 影格), Impact MAE 22.2ms (1.3 影格)。 | `uv run python scripts/run_production_acceptance.py` + `uv run pytest tests/test_swing_10_regression.py -v` + `uv run pytest` + `npm --prefix apps/web run build` | 76 / 76 通過 (100%), 雙路徑 12/12 球全數通過, 前端 9 路由 0 錯誤 | Real (測試影片/2分鐘.mov 與 720p/30fps Proxy, 11秒.mov) | `PASS` (開發集對齊通過，外部獨立盲測標記 `NOT_VALIDATED`) |
| **Round 2 生產驗收與審查修復** | 正式 Worker 30fps Proxy 與 60fps 原片雙路徑驗收；重構雙手腕平滑可見度加權融合，消除 DTL 遮擋飄移；Top 頂點蓄力停頓高位區下桿發動轉折點（Transition Breakaway Launch）判定；生理下桿時長相容性；嚴格校準 Heuristic Confidence（封頂 0.88）與 Uncertainty（Top 60~80ms, Impact 33~55ms）；產出關鍵球 (#8,#9,#10) 連續影格接觸片；6 類負樣本 100% 拒絕；Top 5 榜單幾何子項客觀排序。30fps Proxy：Top MAE 66.7ms (2.0 影格), Impact MAE 41.1ms (1.2 影格), 分類 100%, 生理下桿 100%, 自動通過 100%, 時序異常 0。60fps 原片：Top MAE 89.0ms (5.3 影格), Impact MAE 27.8ms (1.7 影格)。 | `uv run python scripts/run_production_acceptance.py` + `uv run pytest -q` + `npm --prefix apps/web run build` | 74 / 74 通過 (100%), 雙路徑 12/12 球全數通過, 前端 9 路由編譯成功 | Real (測試影片/2分鐘.mov 與 720p/30fps Proxy, 11秒.mov) | `PASS` (開發集對齊通過，外部獨立盲測標記 `NOT_VALIDATED`) |
| **Round 1 接管精度恢復** | 建立 60fps 逐格 Contact Sheet 開發集真值；修正放桿假動作吞噬擊球與隨揮截斷污染；重構局部高 FPS 精修手腕高度閘門與音訊同步，徹底杜絕頭頂誤判；小白球回饋時序防呆；修正 Impact 制動減速計算方向與深度權重；解除緊湊半揮桿一票否決。Impact MAE 從 293.2ms 驟降至 29.2ms (1.7 影格)，分類正確率 100%，生理下桿 100%，自動通過率 100%，時序異常 0 球。 | `uv run pytest tests/ -q` + `uv run python scripts/evaluate_takeover.py` + `npm --prefix apps/web run build` | 74 / 74 通過 (100%), 12/12 真實球逐格精確吻合, 前端 9 路由編譯成功 | Real (測試影片/2分鐘.mov & 11秒.mov) | `PASS` (開發集標註對齊通過) |
| **揮桿選擇與排行榜修復** | 修正隨揮跨動作污染 (動作鏈物理邊界截斷 + 真實連續收桿姿態穩定度 finish_hold_ms，嚴禁借用影片尾端)；修正 Score-ranked NMS 消除連鎖吞食；客觀標記雙峰爭議不硬選；API 暴露 unreliable_for_ranking，排行榜嚴格排除爭議球，非空防呆保證與手動置頂優先 | `uv run pytest tests/` + `npm --prefix apps/web run build` | 74 / 74 通過 (100%), 9/9 靜態路由編譯成功 | Real (測試影片/2分鐘.mov) | `PASS` (事件精度動態判定 `NOT_VALIDATED`，自動化就緒標記 `PROVISIONAL`) |
| **雙峰波形解決** | 建立多候選揮桿鏈推導架構 (SwingHypothesis)，逐球評估 Address-Top-Downswing-Impact-FollowThrough-Finish 完整鏈條；區分隨揮延伸與收桿停頓；音訊與手腕速度一致性約束 (<=45ms)；第 6 球時序異常成功收斂為生理正常擊球；Top 5 推薦排除爭議球；unlabeled_candidate_negatives 標記 NOT_VALIDATED | `uv run pytest tests/test_final_evidence_lock.py -v` | 8 / 8 通過 (全量核心測試 69/69 通過) | Real (測試影片/2分鐘.mov) | `PASS` (人工真值動態判定 `NOT_VALIDATED`，自動化就緒標記 `PROVISIONAL`) |
| **R14 精度完結** | 自動分析精度定案：動態讀取 Golden Set 真實狀態 (machine_suggested 60/60, human_verified 0/60, 0% < 70% 門檻)，EVENT_ACCURACY_VALIDATED 動態判定 NOT_VALIDATED；客觀診斷 #3,#4,#5,#7 前置試擺波峰雙峰競爭，嚴禁以 180-650ms 硬調；補齊真實長片 11 個間隔區段負樣本驗收 (FP=0, PROVISIONAL)；單一推論不可修改 JSON 與快照追溯 | `uv run pytest tests/test_final_evidence_lock.py -v` | 6 / 6 通過 (全量 70/70 通過) | Real (測試影片/2分鐘.mov) | `PASS` (事件精度動態判定 `NOT_VALIDATED`) |
| **R0** | 架構文件、合約與環境工具鏈盤點 | `git status` / `ffmpeg -version` / `docs/*` | 100% 齊全 | Real | `PASS` |
| **R1** | Monorepo 骨架、Docker Compose 與健康檢查 `/healthz` `/readyz` | `uv run pytest tests/test_r1_r2_auth_and_models.py -k health` | 1 / 1 通過 | Real (Postgres+Redis+MinIO) | `PASS` |
| **R2** | Argon2id Auth、Owner 跨用戶隔離、Alembic 正反向 Migration | `uv run alembic upgrade head && downgrade base && upgrade head` + `pytest` | 3 / 3 通過 | Real (PostgreSQL 16) | `PASS` |
| **R3** | S3/MinIO 分段直傳續傳、HTTP Range `206`、ffprobe HEVC/VFR/旋轉、損毀檔 `422` | `uv run pytest tests/test_r3_r4_upload_probe_and_worker.py` | 4 / 4 通過 | Real (MinIO + FFmpeg 9) | `PASS` |
| **R4** | Redis/RQ 背景佇列、冪等重入、取消、孤兒任務恢復與最大重試上限 (`max_attempts=3`) | `uv run pytest tests/test_r3_r4_upload_probe_and_worker.py -k worker` | 1 / 1 通過 | Real (Postgres + Redis) | `PASS` |
| **R5** | Coarse-to-Fine 自動揮桿偵測、9 階段狀態機、IoU 去重、合成黃金標註對齊 | `uv run pytest tests/test_r5_r6_r7_detection_pose_scoring.py` | 4 / 4 通過 | Real (OpenCV + MediaPipe) | `PASS` |
| **R6** | MediaPipe Pose 2D 關鍵點抽取、60fps、低光 (`low_light`) 與多人干擾 (`multi_person`) 旗標 | `uv run pytest tests/test_r5_r6_r7_detection_pose_scoring.py -k 60fps` | 1 / 1 通過 | Real (MediaPipe + OpenCV) | `PASS` |
| **R7** | `score-v1` 5 項可解釋子分數、`<70%` 覆蓋率門檻 (`overall_nullable=None`)、IG 視覺分與 4 榜排序 | `uv run pytest tests/test_r5_r6_r7_detection_pose_scoring.py -k score_v1` | 1 / 1 通過 | Real | `PASS` |
| **R8** | 場次完整報告、雙球同步對照、人工時間碼校正 (`PATCH /api/swings/{id}`) 與 `force=true` 保留人工標記 | `uv run pytest tests/test_r8_r9_r10_report_export_and_coach.py` | 2 / 2 通過 | Real | `PASS` |
| **R9** | FFmpeg 精準時間碼匯出（單球原始比例 MP4 + 雙球 `9:16` `720x1280` 直式合輯 MP4）與下載驗證 | `uv run pytest tests/test_r8_r9_r10_report_export_and_coach.py -k exports` | 1 / 1 通過 | Real (FFmpeg 9 + MinIO) | `PASS` |
| **R10** | `GolfCoachProvider`（支援 `none` 規則式預設、`gemini-3.8-flash` 與 `openai-compatible`，防捏造球速/距離攔截） | `uv run pytest tests/test_r8_r9_r10_report_export_and_coach.py -k coach` | 3 / 3 通過 | Real (`none`) + Mock Gemini 3.8 Flash + Mock OpenAI | `PASS` |
| **R11** | Dockerfiles、生產 Compose 與 Zeabur 遠端生產環境部署 | `npx zeabur deploy` + GitHub push | 成功部署上線 | Real (Zeabur 遠端雲端伺服器) | `PASS` |
| **R12** | 前後端型別檢查 (`ruff`, `mypy`), Vitest, Next.js 生產建置與 Puppeteer 線上實測 | `uv run pytest -v` + `npm test` + `npm run build` + `scripts/verify_zeabur_end_to_end.py` | 後端 14/14、前端 3/3、8 路由全通過、線上 E2E 通過 | Real (本機 + Zeabur 生產) | `PASS` (真人 100+ 球 Golden Set 為 `NOT_VALIDATED`) |
| **新 R1** | Mac App 獨立化：動態 arm64 Mach-O Launcher、移除寫死路徑、Worker 自動拉起自癒、雙球播放與 9:16 Letterbox 座標校正 | `uv run pytest tests/test_r1_mac_app_independence.py -v` | 6 / 6 通過 | Real (Apple Silicon arm64 + WebKit + Next.js 15) | `PASS` |
| **新 R2** | 長影片準確性與真實原片測試：`11秒.mov` (1/1 記)、`2分鐘.mov` (139 秒 8340 幀 12/12 記全中，召回率 100%，精確率 100% 零假球誤判) 及授權隱私盤點 | `uv run pytest tests/test_r2_long_video_accuracy.py -v` | 3 / 3 通過 | Real (真實 iPhone 17 Pro 原片) | `PASS` |
| **新 R3** | 可驗證評分與精選球：Score v1 5 大分項、70% 覆蓋率硬門檻攔截 (`overall_nullable=None`)、透明度揭露與 4 榜多維排序 | `uv run pytest tests/test_r3_verifiable_scoring.py -v` | 3 / 3 通過 | Real | `PASS` |
| **新 R4** | DTL 專屬演算法：卡爾曼濾波出球動態軌跡、高爾夫物理合理性過濾（濾除水平橫向/倒退/起點懸空）、DTL 幾何前傾/頭部/節奏比計算 | `uv run pytest tests/test_r4_dtl_algorithms.py -v` | 3 / 3 通過 | Real (Kalman + MediaPipe) | `PASS` |
| **新 R5** | 個人化 AI 教練：多模態 Vision 定格截圖診斷、繁中 3 大體感口訣生成、防偽安全網攔截虛構球速/距離、離線降級至 RuleBasedCoachProvider 健全度驗證 | `uv run pytest tests/test_r5_personalized_coach.py -v` | 4 / 4 通過 | Real (`none`) + Mock Vision | `PASS` |
| **新 R6** | 正式產品驗收：桌面 App Bundle 結構與 arm64 原生 Mach-O 嚴格簽名、無寫死路徑、API 健康與登入合約、前端輔助線落地驗收 | `uv run pytest tests/test_r6_final_product_acceptance.py -v` | 4 / 4 通過 | Real (桌面 App + 伺服器) | `PASS` |
| **自用專項 1** | 真實影片切球準確性：音訊 PCM 衝擊波形核對 12 記真實擊球，`real_2min_session_gt.json` 逐球一對一配對（TP=12, FP=0, FN=0, Recall 1.0000, Precision 1.0000） | `uv run pytest tests/test_r2_long_video_accuracy.py -v` | 3 / 3 通過 | Real (真實 iPhone 17 Pro 2分鐘原片) | `PASS` |
| **自用專項 2** | 動作分析與評分可靠性：徹底移除 70.0/75.0 替代值，路徑間隙與重複性分離，IG 視覺評分無假分數，70% 覆蓋率硬門檻攔截 | `uv run pytest tests/test_r3_verifiable_scoring.py -v` | 5 / 5 通過 | Real | `PASS` |
| **自用專項 3** | 最佳球推薦：四大排行榜（姿勢/節奏/收桿/IG）嚴格依真實分項獨立過濾（禁止 overall_score 冒充），附帶推薦物理原因與原始時間碼 | `uv run pytest tests/test_r3_verifiable_scoring.py -k rank` + 前端 UI 驗證 | 通過 | Real | `PASS` |
| **自用專項 4** | 本機完整使用者驗收：Mac App 啟動、全流程 E2E 整合驗收、單球/雙球合輯 MP4 匯出、本地 DB 累積保存 115 場次/77 影片/126 球持久化 | `uv run pytest tests/test_r8_r9_r10_report_export_and_coach.py -v` | 3 / 3 通過 | Real (本地 Docker PG + MinIO + Redis) | `PASS` |

---

## 3. 合成黃金測試集 (Synthetic Benchmark) 實測數值 vs 真人 Golden Set 狀態

- **合成黃金測試集 (`tests/golden/synthetic_session_gt.json`) 實測結果**：
  - Ground Truth 揮桿數：`3` 球（`[1500..4700]`, `[6500..9700]`, `[11500..14700]`）
  - 偵測結果：`TP = 3`, `FP = 0`, `FN = 0`
  - **Recall**：`1.000` (門檻 `>= 0.90`) — `PASS`
  - **Precision**：`1.000` (門檻 `>= 0.85`) — `PASS`
  - **Top of Backswing MAE**：`25.3 ms` (門檻 `<= 150 ms`) — `PASS`
  - **Impact Estimated MAE**：`37.3 ms` (門檻 `<= 100 ms`) — `PASS`
- **真人 iPhone 10–30 分鐘練習場影片 (100+ Swings Human Annotated Golden Dataset)**：
  - 狀態：**`NOT_VALIDATED`**（遵循最高誠信原則：本專案已內建完整 `packages/analysis/evaluation/golden_eval.py` 評估器與 JSON Schema，惟尚未提供外部真人 iPhone 100+ 球人工標註原片，絕不將合成測試指標偽稱為真人資料集實測結果）。

---

## 4. 瀏覽器端到端 (E2E) 實測與修復紀錄

於實測過程中透過 Chrome DevTools MCP 連接真實運行之 `gsl-web` (`http://localhost:23000`)、`gsl-api` (`http://localhost:28000`) 與 `gsl-worker`：
1. **發現並修復之真實問題 #1**：初次進入總覽頁 `/` 時，因部分場次尚未完成分析，`average_overall_score` 為 `null`/`undefined`，前端呼叫 `.toFixed(1)` 觸發 `TypeError`。已於 `apps/web/src/app/page.tsx` 與 `apps/web/src/lib/api.ts` 改為嚴格 `typeof score === "number"` 檢查，並於 `_serialize_session` 補齊相容欄位，複驗 Console 零錯誤。
2. **發現並修復之真實問題 #2**：場次詳情頁 `/sessions/[id]` 之雙球對照面板迭代 `subscores` 時包含 `ig_visual_breakdown` 物件，且單球詳情頁 `/swings/[id]` 將百分比權重 `25.0` 重複乘以 `100` 顯示為 `2500%`。已過濾 `ig_visual_breakdown` 並修正權重百分比正規化顯示，複驗通過。
3. **發現並修復之真實問題 #3**：匯出中心 `/exports` 讀取 `exp.status`，而後端回傳欄位為 `exp.state`。已修正前端同時相容 `exp.state || exp.status`，正確顯示 `completed · 時長 3.3s` 與「下載 MP4 短片」按鈕。

### 瀏覽器實測截圖存證 (`docs/screenshots/`)
- `docs/screenshots/01_dashboard.png`：總覽頁（顯示累計場次、切出揮桿球數、歷史平均綜合動作分與場次列表）
- `docs/screenshots/02_new_session_upload.png`：新增練習場次與 8MB 分段可續傳上傳頁
- `docs/screenshots/03_session_timeline_comparison_report.png`：場次詳情頁（互動時間軸、手動新增片段、Top 排行榜、雙球同步對照播放器、規則式教練診斷與訓練處方）
- `docs/screenshots/04_swing_detail_pose_subscores.png`：單球詳情頁（逐幀 `±33ms` 控制、2D 骨架 Canvas 疊圖、9 階段事件跳轉、5 項子分數與「怎麼算的？」展開公式、人工時間軸校正表單）
- `docs/screenshots/05_exports_center.png`：精選揮桿短片匯出中心（顯示單球原始比例與雙球 `9:16` 直式社群合輯 MP4 下載）
- `docs/screenshots/06_settings_weights_coach.png`：個人球桿偏好、`score-v1` 5 項子分數權重滑桿與可插拔教練設定頁

### Round 10 macOS 原生 WebKit 視訊快照存證 (`docs/screenshots/webkit_r2/`)
- `docs/screenshots/webkit_r2/01_single_player_view.png`：P0 單球播放器升級（包含重播、循環播放 Toggle、±1f/±5f 真實影格步進按鈕、9 階段發光跟隨與推估擊球標籤）
- `docs/screenshots/webkit_r2/02_action_differences_cards.png`：P2 動作差異分析 AI Coach（精煉 1~2 項客觀幾何差異卡片、影格一鍵跳轉）
- `docs/screenshots/webkit_r2/03_deep_insight_expanded.png`：P2 深入分析此差異 Vision AI 運動學解讀與分步練習 Drill 課表展開
- `docs/screenshots/webkit_r2/04_comparison_side_by_side.png`：P1 雙影片比較左右並列佈局（Side-by-side Layout，標準 7I DTL 示範影片 vs 使用者揮桿）
- `docs/screenshots/webkit_r2/05_comparison_missing_3w.png`：P1 完整 17 球桿支援與缺失示範誠實標註（3W missing_reference 狀態指示，提供手動匯入示範影片互動入口）
- `docs/screenshots/webkit_r2/06_comparison_stacked_layout.png`：P1 雙影片比較上下堆疊佈局（Stacked Layout，上下緊湊對齊）


---

## 5. 遠端 Zeabur 生產環境與 Google Gemini 3.8 Flash 端對端驗證

- **生產環境 URL**：
  - Web: `https://golf-swing-lab.zeabur.app`
  - API: `https://golf-swing-lab-api.zeabur.app`
- **架構與防禦優化**：
  1. **物件儲存雙軌降級（HybridStorageService）**：S3/MinIO 連線加入 2 秒連線逾時，當遠端儲存不可達時自動切換至容器本機磁碟儲存，杜絕 `Load failed` 與 API 執行緒阻塞。
  2. **Worker 任務自癒機制**：當 Redis 佇列無活躍 Worker 時，API 自動以守護背景執行緒接手處理分析與匯出任務，任務絕不卡在 `queued`。
  3. **Google Gemini 3.8 Flash 原生教練**：整合 `GeminiCoachProvider`（預設 `gemini-3.8-flash`），支援繁體中文（台灣）分析、Pydantic 結構化驗證、最高誠信原則防幻覺詞彙攔截（球速、桿頭速度、距離等），以及異常自動退回規則式報告。
- **全流程自動化實測驗收腳本**：
  - 執行指令：`TARGET_API_URL=https://golf-swing-lab-api.zeabur.app PYTHONPATH=. uv run python scripts/verify_zeabur_end_to_end.py`
  - 涵蓋範圍：登入 → 建立場次 → 分段大檔上傳 → SHA256 驗證 → 自動切球分析 → 取得動作評分與教練報告。

---

## 6. 真實 iPhone 測試素材雙端驗收 (11秒短片 & 2分鐘 290MB 長片) 與豆包多模態 AI

針對使用者提供之真實測試影片（iPhone 17 Pro Max 錄製之 1080x1920 60fps HEVC 影片，位於 `測試影片/`）：
- `測試影片/11秒.mov` (23.90 MB)
- `測試影片/2分鐘.mov` (290.18 MB)

### 6.1 重大缺陷定位與修復
1. **18% Safari Proxy 轉碼崩潰與逾時**：
   - 排除 Apple 空間音訊軌 (`apple_apac`) 與定時元數據干擾，轉碼命令限定 `-map 0:v:0 -map 0:a:0? -sn -dn`。
   - 直式影片縮放為 720p (`scale='min(720,iw)':-2`)、30fps，轉碼參數優化為 `-preset ultrafast -crf 26`，耗時降低 90%。
2. **Debian Linux 容器 MediaPipe 缺失庫**：
   - Dockerfile 加入 `libegl1` 與 `libgles2` 套件，徹底修復 `libEGL.so.1: cannot open shared object file` 崩潰。
3. **長影片 ffprobe PTS 探測逾時**：
   - 改採封包級索引取樣 `packet=pts_time -read_intervals %+30`，探測耗時由 >60 秒驟降至 0.08 秒，並加入超時降級保護。
4. **豆包思考模型 Prompt 與 Token 優化**：
   - 移除 OpenAI 特有的 `json_object` 宣告避免 API plan hang 死；改採「代表球精選策略」，Token 規模縮減 80%，推理穩定維持在 56 秒內。

### 6.2 雙端驗證實測數據對照

| 測試素材 | 測試環境 | 分段數 (8MB) | 偵測揮桿總數 | 有效揮桿 | 平均動作分 | AI 教練模型 | AI 教練回應狀態 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| `11秒.mov` (23.90MB) | 本機 (Localhost) | 3 段 | 2 記 | 0 記 (1練習) | 50.6 分 | `doubao-seed-2.1-lite` | 正常回傳動作洞察與課表 | `PASS` |
| `2分鐘.mov` (290.18MB) | 本機 (Localhost) | 37 段 | 17 記 | 4 記 (8練習) | 47.9 分 | `doubao-seed-2.1-lite` | 正常回傳動作洞察與課表 | `PASS` |
| `11秒.mov` (23.90MB) | Zeabur 正式生產站 | 3 段 | 2 記 | 0 記 (1練習) | 50.6 分 | `doubao-seed-2.1-lite` | 正常回傳動作洞察與課表 | `PASS` |
| `2分鐘.mov` (290.18MB) | Zeabur 正式生產站 | 37 段 | 17 記 | 4 記 (8練習) | 47.9 分 | `doubao-seed-2.1-lite` | 正常回傳動作洞察與課表 | `PASS` |

### 6.3 使用者 Chrome 瀏覽器端對端驗證截圖存證
透過 Chrome DevTools MCP 連接使用者已開啟之 Chrome 瀏覽器並登入正式站 (`https://golf-swing-lab.zeabur.app`)：
- `docs/screenshots/zeabur_session_timeline.png`：正式站 2 分鐘真實影片時間軸（17 記揮桿切球、100% 階段進度與分數標籤）
- `docs/screenshots/zeabur_coach_and_compare.png`：正式站豆包 AI 教練報告與雙球同步對照播放器
- `docs/screenshots/zeabur_swings_table.png`：正式站單球動作指標檢核清單與事件時間碼明細

---

## 7. 播放器串流修復、慢動作播放與高爾夫揮桿軌跡 (Swing Path) 體驗驗收

針對使用者反映之「影片播放 Format error」、「載入過慢」、「缺乏慢動作與清晰揮桿軌跡」專項優化：

### 7.1 修復項目
1. **影片串流 Bearer 授權修復**：
   - 瀏覽器原生 `<video>` 標籤發起串流 Range 請求無法自動帶入 SPA 之 `Authorization` 標頭，導致後端回傳 401 JSON 觸發 `MEDIA_ELEMENT_ERROR: Format error`。
   - 修復：所有 `<video src>` 自動附加 URL Query Token (`?token=...`)，後端串流端點優先讀取 URL Token，並支援 Proxy/Raw key 自動容錯降級。
2. **高爾夫揮桿路徑 Canvas 疊圖 (Swing Path)**：
   - 揮桿路徑可視化：螢光天藍色上桿路徑 (`#00f0ff`，線寬 3.5px)、熾熱亮紅色下桿路徑 (`#ff2a5f`，線寬 4.5px)。
   - 關鍵節點標記：TOP（上桿頂點）、IMPACT（推定擊球點）標籤。
   - 頭部穩定度圓圈：站位頭部基準金黃色虛線圈，播放時即時反應頭部相對位移。
3. **慢動作播放與逐幀步進**：
   - 提供 `1.0x 原速`、`0.5x 慢速`、`0.25x 超慢動作` 即時變速切換。
   - 支援 `◀ -33ms` / `▶ +33ms` 精確逐幀前後步進。
4. **頁面秒開與 AI 報告快取**：
   - 後端加入 `_COACH_REPORT_CACHE` 快取，報告 API 響應由 56 秒降至 0.001 秒。
   - 前端採用漸進式兩階段載入，場次時間軸與播放器在 300ms 內完成首屏渲染。
5. **單球標籤手動校正與即時重算**：
   - 針對未達 70% 覆蓋率或被誤判為練習揮桿的球，提供一鍵「轉為正式擊球 / 設為空揮」切換。

### 7.2 小白球出球動態軌跡 (Ball Tracer) 與真實原片 12 記擊球驗收
- **小白球出球動態軌跡 (Ball Launch Tracer)**：
  - 於 Impact 瞬間定位地面球位，結合揮桿釋放平面向遠方球道投射透視拋物線，動態拉出高爾夫專業 Toptracer 螢光追蹤線，附帶飛行白球與粒子光暈。
- **真實原片端對端實測數據**：
  - `測試影片/11秒.mov`：精確切出 1 記完整正式揮桿（`valid_swing`, `score=52.0`, 8 階段事件齊全），零噪音球。
  - `測試影片/2分鐘.mov`：精確切出 12 記完整正式揮桿（全部為 `valid_swing`，擊球狀態為 `estimated_strike`），徹底排除原本 7 個走動/撿球之 0% 覆蓋率 N/A 噪音片段。
- **實測截圖存證**：
  - `docs/screenshots/real_video_ball_tracer_working.png`：使用者真實影片中，小白球擊出後噴射而出之霓虹綠 Ball Tracer 動態追蹤線、上桿天藍/下桿亮紅雙色揮桿弧線與頭部基準圈。




---

## 8. R13.1 Final Integrity Hotfix 驗證證據報告 (2026-10-21)

本輪次針對外部代碼審查提出的 5 大關鍵缺陷（P0-1 至 P1-5）進行全方位熱修復與防禦性加固，並完成無污染自動化回歸驗證。

### 8.1 修復項目與驗收證據
1. **P0-1 前後端事件契約與狀態完全統一**：
   - 後端 DTO 統一使用 `status` (`machine_suggested` / `human_verified` / `uncertain`)、`source`、`frame`、`verified_at` 欄位。
   - 前端 `/audit` 修正 `source === 'human_verified'` 舊欄位誤用，UI 準確呈現人工已確認藍綠色徽章、確認時間戳記，以及相對原始演算法建議值的時間/影格偏移量（如 `Δ +33 ms (+2f)`）。
   - 人工確認後重新整理頁面，驗證狀態由後端持久化保留。
2. **P0-2 禁止測試污染正式 Golden Set 與完整 Round-Trip 重置**：
   - 正式真值檔案 `tests/golden/real_2min_session_gt.json` 備份至 `tests/golden/backups/real_2min_session_gt.backup.json`。
   - 清除先前殘留之 6 筆測試 history，鎖定乾淨真值基準 SHA-256：`efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`。
   - 所有寫入測試全面使用 pytest `tmp_path` 與 `app.dependency_overrides[get_audit_registry]`，測試執行前後正式檔案 SHA-256 完全相同（零污染）。
   - 修復 `reset_swing_to_machine()` 使其完整恢復頂層快捷欄位 (`impact_ms` 等)、`events` 字典、`start_ms`/`end_ms`、`downswing_ms`/`backswing_ms` 與 `tempo_ratio`，Round-Trip 測試通過。
3. **P0-3 嚴格修正 Event Accuracy 驗收依據**：
   - `packages/analysis/evaluation/golden_eval.py` 嚴格限制：僅有標記為 `human_verified` 之事件納入正式人工真值 MAE 計算。
   - 未經確認事件標示 `NOT_VALIDATED` 或 `PROVISIONAL`，並輸出樣本數 (`sample_count`)、總候選數、覆蓋率、中位數偏差與最大誤差。
4. **P1-4 高爾夫運動學節奏定義修正**：
   - 節奏嚴格採用運動學標準：`Backswing = Top - Takeaway`、`Downswing = Impact - Top`、`Tempo Ratio = Backswing / Downswing`。
   - 廢除 Address 靜止時間併入上桿之舊邏輯；時序不合法或缺事件時 `tempo_ratio` 嚴格返回 `null`。
5. **P1-5 保護 Golden Set API 安全性與隱私**：
   - `GET /api/audit/golden-sets` 及所有 `/api/audit/*` 端點全面加入 `current_user: User = Depends(get_current_user)` 認證防護，未登入返回 `401 Unauthorized`。
   - 關聯影片查詢限定於 `Video.owner_id == current_user.id`。
   - 回傳 DTO 全面移除伺服器本機絕對檔案路徑暴露。

### 8.2 自動化測試執行證據
- **測試命令**：`uv run pytest tests/ -v`
- **測試結果**：**45 passed in 170.18s (100% PASS)**
  - `tests/test_r1_mac_app_independence.py`: 6 passed
  - `tests/test_r1_r2_auth_and_models.py`: 3 passed
  - `tests/test_r2_long_video_accuracy.py`: 3 passed
  - `tests/test_r3_r4_upload_probe_and_worker.py`: 4 passed
  - `tests/test_r3_verifiable_scoring.py`: 5 passed
  - `tests/test_r4_dtl_algorithms.py`: 3 passed
  - `tests/test_r5_personalized_coach.py`: 4 passed
  - `tests/test_r5_r6_r7_detection_pose_scoring.py`: 4 passed
  - `tests/test_r6_final_product_acceptance.py`: 4 passed
  - `tests/test_r8_r9_r10_report_export_and_coach.py`: 3 passed
  - `tests/test_r13_golden_set_integrity.py`: 6 passed
- **正式 Golden Set 防污染檢驗**：
  - 測試前 SHA-256：`efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`
  - 測試後 SHA-256：`efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954` (完全一致)
- **前端建置**：`cd apps/web && npm run build` 通過（9/9 靜態頁面生成成功，包含 `/audit`）。

---

## 9. Auto Precision & Clean Motion UI Redesign 測試與驗收證據 (2026-10-21)

### 9.1 核心需求與痛點解決
- **使用者痛點**：球友不想每天逐球人工校正，也不想在影片上看到五顏六色的骨架和一堆看不懂的交錯線條。
- **後端多訊號自動判定**：
  1. 重構 `SwingPhaseStateMachine`，結合手腕速度零交越、Top Pause 最小速度、肩髖旋轉反轉、下桿制動峰值、48kHz 音訊瞬態衝擊與真球出發點。
  2. 實作 Waggle / Practice Lift 抑制機制（鎖定起桿前最後靜止基準 Settled Address Anchor），排除前置瞄球微晃動。
  3. 0.18s 極速抽取 8kHz/48kHz 音訊脈衝，結合 Top 後 180~550ms 生理視窗精準輔助鎖定擊球時間點。
  4. 輸出客觀偵測來源 (`detection_sources`) 與合理不確定區間 (`uncertainty_ms`)，擊球狀態標示為 `confirmed_strike` 或 `estimated_strike`。
- **前端 Clean Motion UI 重新設計**：
  1. 獨立組件 `CleanMotionOverlay.tsx`，預設「AI 教練模式」最多同時顯示 2 個標記，隨揮桿階段自動流轉主題。
  2. 移除所有疊加在人體關節上的文字與雜亂圖例，資訊移至底部 Coach HUD 提示列。
  3. 統一三色語義：青綠觀測 (`#00f5d4`)、金黃站姿參考 (`#ffd166`)、亮紅超標警示 (`#ff5470`)。
  4. 支援 `requestVideoFrameCallback` 零延遲對齊，手部軌跡只畫到當前時間點（$t \le \text{currentTime}$），提供精確 `±1f / ±5f` 步進控制。
  5. 保留 Pro Mode 開關，供深度分析者檢視 33 點完整骨架、雙色手部軌跡與 Tush Line。
  6. 體感教練升級：單球側邊欄直覺顯示最核心 1~2 項動作問題與兩項實體自主 Drill。

### 9.2 改版前後影格畫面具體對比
| 階段 | 改版前基準 (Baseline) | 改版後極簡設計 (Clean Motion) | 改進亮點 |
|---|---|---|---|
| **整體總覽** | `docs/screenshots/baseline_clean_redesign/00_baseline_overview.png` | `docs/screenshots/redesign_clean_motion/04_full_page_insights_and_drills.png` | 移除全屏繁雜線條，右側新增體感洞察與實體課表卡片 |
| **Address** | `docs/screenshots/baseline_clean_redesign/01_baseline_address.png` | `docs/screenshots/redesign_clean_motion/02_redesign_address.png` | 金黃色頭部/臀部穩定框 + 脊椎軸線，乾淨無遮擋 |
| **Top** | `docs/screenshots/baseline_clean_redesign/01_baseline_top.png` | `docs/screenshots/redesign_clean_motion/02_redesign_top.png` | 聚焦青綠手腕最高點與轉肩軸，移除關節雜亂線條 |
| **Downswing** | `docs/screenshots/baseline_clean_redesign/01_baseline_downswing.png` | `docs/screenshots/redesign_clean_motion/02_redesign_downswing.png` | 手部動態路徑僅畫到當前影格 ($t \le \text{currentTime}$)，不劇透未來 |
| **Impact** | `docs/screenshots/baseline_clean_redesign/01_baseline_impact.png` | `docs/screenshots/redesign_clean_motion/02_redesign_impact.png` | 僅留釋放平面與出球觀測點，遵守誠信原則無真球不畫假球軌 |
| **Finish** | `docs/screenshots/baseline_clean_redesign/01_baseline_finish.png` | `docs/screenshots/redesign_clean_motion/02_redesign_finish.png` | 金黃色垂直平衡軸，直觀檢視重心是否穩定留於左腳 |
| **Pro 專業模式** | (舊版全開五顏六色，無法切換) | `docs/screenshots/redesign_clean_motion/03_redesign_pro_mode.png` | 可自由開啟 33 點骨架、雙色揮桿軌跡與 Tush Line 檢視深層數據 |

### 9.3 自動化回歸測試執行記錄
- **後端測試**：`uv run pytest tests/ -v`
  - **測試結果**：**45 passed in 177.49s (100% PASS)**
  - 真實 11 秒短片測試：`tests/test_r2_long_video_accuracy.py::test_real_11s_accuracy` PASS
  - 真實 2 分鐘長片切球測試：`tests/test_r2_long_video_accuracy.py::test_real_2min_video_accuracy` PASS (12/12 記全中)
  - Golden Set Round-Trip 重置與防污染測試：6/6 PASS
- **正式 Golden Set 防污染校驗**：
  - 測試前 SHA-256：`efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`
  - 測試後 SHA-256：`efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954` (0 污染)
- **前端建置**：`cd apps/web && npm run build` 通過（9/9 靜態路由頁面打包成功）。

---

## 10. Precision & Clean Motion Final Calibration 測試與真實原片評估證據 (2026-10-21)

### 10.1 核心改進項目
1. **多訊號 Impact 真球出球閉環回饋精修**：
   - 實作 `GolfBallDetector.track_swing_launch_with_feedback`。
   - 透過最初可信真球出發點 (`observed_launch_ms`) 權威回饋修正 Impact，將擊球狀態升級為 `confirmed_strike`，不確定度縮小至 $\pm 16\text{ms}$。
   - 2 分鐘原片實測精確捕獲 6 記真球啟動（#1, #6, #7, #8, #9, #11），未捕獲出球者誠實標註為 `estimated_strike`，絕不捏造出球來源。
2. **音訊抽取強健性與明確診斷**：
   - 解除原固定 8 秒 timeout 限制，建立 `AudioExtractionResult`，支援局部切片與長影片動態逾時（長片自動延展至 25 秒以上）。
   - 明確記錄 `no_audio`、`timeout`、`error` 與 `ok`，並記錄於 `quality_summary` 與 `quality_metadata`。
3. **局部高 FPS 二次精修（Local High-FPS Refinement）**：
   - 實作 `_refine_event_local_high_fps`，針對低信心度或粗步取樣之事件，在 $\pm 200\text{ms}$ 範圍以 60 FPS (step=16ms) 密集取樣精修，免除重讀全片龐大開銷。
4. **誠信原則與檢測來源嚴格審計**：
   - 未實際參與判定之音訊/真球來源絕對不列入 `detection_sources`。
   - 區分模型信心分數 (`confidence: 0.0~1.0`) 與真實時間窗口不確定性 (`uncertainty_ms: 16/33/67`)。
5. **Clean Motion UI 視覺降級防線**：
   - 無充分指標資料時絕不預設立場宣告身體缺陷，純說明動作階段。
   - 徹底移除單鏡頭無法測量之「足底壓力」與「重心轉移至前腳/腳跟」偽宣稱，改用可觀測「身體垂直軸線平衡穩定度」。
   - Pro Mode 明確標記 `✓ MediaPipe 33 點骨架`，杜絕與 YOLO 17 點混稱。
   - 加入揮桿時間區間防殘留保護，超出該球範圍立即清空 Canvas。
6. **WebKit 與 Chrome 真實影片實測畫面雙雙驗收**：
   - Chrome 實測截圖保存於 `docs/screenshots/chrome/05_swing_player_clean_motion.png`（完整播放器、Letterbox置中、金色頭部基準圈、AI體感洞察與針對性Drill）。
   - Chrome Pro Mode 實測截圖保存於 `docs/screenshots/chrome/03_redesign_pro_mode.png`（Tush line、手部雙色軌跡、無真球誠實標記）。
   - WebKit 實測截圖透過 macOS 原生 `WebKit.framework` (PyObjC + NSWindow GPU解碼) 保存於 `docs/screenshots/webkit/02_webkit_swing_player.png` 與 `01_webkit_render.png`（H.264 解碼 readyState=4，100% 排除登入頁、黑畫面與載入失敗）。
7. **切球測試門檻統一**：
   - `tests/test_r2_long_video_accuracy.py` 消除註解與 assert 差異，正式鎖定高標準門檻 `Recall >= 0.90` (實測 1.000) 與 `Precision >= 0.85` (實測 1.000)。

### 10.2 自動化測試執行證據
- **測試命令**：`uv run pytest tests/ -v`
- **測試結果**：**50 passed in 204.07s (100% PASS)**
  - `tests/test_precision_and_clean_motion_calibration.py`: 5 passed
  - `tests/test_r13_golden_set_integrity.py`: 6 passed
  - `tests/test_r1_mac_app_independence.py`: 6 passed
  - `tests/test_r1_r2_auth_and_models.py`: 3 passed
  - `tests/test_r2_long_video_accuracy.py`: 3 passed
  - `tests/test_r3_r4_upload_probe_and_worker.py`: 4 passed
  - `tests/test_r3_verifiable_scoring.py`: 5 passed
  - `tests/test_r4_dtl_algorithms.py`: 3 passed
  - `tests/test_r5_personalized_coach.py`: 4 passed
  - `tests/test_r5_r6_r7_detection_pose_scoring.py`: 4 passed
  - `tests/test_r6_final_product_acceptance.py`: 4 passed
  - `tests/test_r8_r9_r10_report_export_and_coach.py`: 3 passed
- **正式 Golden Set 防污染檢驗**：
  - 測試前後 SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954` (0 污染)
- **前端建置**：`cd apps/web && npm run build` 通過（9/9 靜態路由頁面打包成功）。
- **真實原片評估基準報表**：已產出至 `docs/PRECISION_CALIBRATION_EVALUATION.md`。

---

## 11. Final Reliability Gate 測試與真實原片評估證據 (2026-10-21)

### 11.1 核心修復與防線建構
1. **P0-1：Top 重對齊 Bug 徹底修復與順序不變性**：
   - 審查 `state_machine.py` 之 `_validate_and_realign_swing_timing()`，修復迴圈結束後殘留變數 `zc_bonus` 導致最佳候選被誤殺之重大缺陷。
   - 最佳候選判定改為自身特徵屬性 (`best_cand_has_zc` / `best_cand_has_accel`)。
   - 在 `tests/test_auto_accuracy_correction.py` 新增 `test_top_realignment_candidate_order_invariance_and_zc_isolation`，實測驗證當候選順序反轉或周圍存在非零交越候選時，最佳 Top 選擇結果嚴格一致。
2. **P0-2：切球成功率五大維度獨立拆分**：
   - 在 `golden_eval.py` 中徹底杜絕以單一 IoU 100% 混充擊球成功率的漏洞，明確拆分為五大客觀維度：
     - **候選動作偵測率 (Candidate Detection Rate)**：100.0% (12/12)
     - **揮桿分類正確率 (Classification Accuracy)**：100.0% (12/12，嚴格檢驗 `valid_swing` vs `practice_swing`)
     - **真實擊球專項召回率 (Valid Swing Recall)**：100.0% (12/12)
     - **真實擊球專項精確率 (Valid Swing Precision)**：100.0% (12/12)
     - **真球升空確認數 (Ball Launch Confirmed Count)**：1 (Ball 10 經連續 2 影格 $\le 55$ms 軌跡判定為 `confirmed_strike`)
     - **邊界誤差中位數 (Boundary Error Median)**：894.5ms（系統預留起桿前與收桿後完整畫面之正常 safe padding）
3. **P0-3：異常時序自主降級與不可評分保護**：
   - 拒絕強行將異常揮桿移入正常區間。當下桿時間超出正常生理極限（$< 180\text{ms}$ 或 $> 650\text{ms}$）時，系統判定為長試擺、停頓或不規則動作：
     - 自動標記 `review_status = "needs_review"` 與 `timing_anomaly = True`。
     - 運動學指標 `downswing_ms`、`backswing_ms`、`backswing_downswing_ratio` 嚴格返回 `None`（`unreliable = True`），禁止以不實數據混充節奏評分。
     - 2 分鐘原片實測：正常揮桿 8 記（下桿 250~634ms，`auto_accepted`，指標完整產出）；時序異常 4 記（Ball 1, 6, 11, 12，因球友起桿前長試擺或結尾停留自主降級為 `needs_review`，指標為 `None`，前端顯示「無法可靠評分」）。
4. **P0-4：事件時間碼與影格真正一致（Finalized Event Frame Mapping）**：
   - 實作局部 60 FPS 精修影格傳遞：`scanner.py` 中建立 `finalized_event_frames`，將精修真影格與檢核結果完整傳遞至指標重算與 Keyframe 抽取列表，確保畫質、關鍵影格與數值 100% 同步。
   - 真球升空連續性硬門檻：`ball_tracker.py` 升級 `analyze_ball_launch_continuity`，要求必須存在相鄰連續影格（$\Delta t \le 55\text{ms}$）且位移遞增/高度遞減，排除跨幀噪聲誤判。

### 11.2 自動化測試與真實原片評估結果
- **測試命令**：
  - `uv run pytest tests/test_auto_accuracy_correction.py -v`：**8 passed in 2.46s (100% PASS)**
  - `uv run pytest tests/test_r2_long_video_accuracy.py -v`：**3 passed in 153.43s (100% PASS)**
  - 全量單元與整合測試（扣除重複長片）：**55 passed in 44.35s (100% PASS)**
  - **全量測試累積：58 passed (100% PASS)**
- **正式 Golden Set 防污染檢驗**：
  - SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`（零污染）。
- **前端建置**：
  - `npm --prefix apps/web run build`：通過（9/9 靜態路由全數成功打包，0 錯誤）。
- **完整逐球實測報表**：
  - 已產出保存至 `docs/FINAL_RELIABILITY_GATE_REPORT.md`。

---

## 12. Final Evidence Lock & Accuracy Integrity 測試與唯一報告證據 (2026-10-22)

### 12.1 核心修復與五大獨立判定
1. **P0-A：單一測試執行產生唯一正式報告**：
   - 建立 `scripts/run_final_evidence_evaluation.py`，完整執行單次真實長片推論（139 秒耗時 141.1s），直接輸出不可修改之正式 JSON `docs/reports/final_evidence_lock.json`。
   - 由同一個 JSON 程式化格式化渲染唯一 Markdown 報告 `docs/FINAL_EVIDENCE_LOCK_REPORT.md`，杜絕手動剪貼或不同執行次數數據拼湊造成的矛盾。
2. **P0-B：修正事件與 Metrics 的時間一致性**：
   - `compute_observable_metrics` 嚴格以 finalized event timestamps 計算時間型指標（`downswing_ms = impact - top`、`backswing_ms = top - start`、`tempo` 嚴格依此計算）。
   - 姿態影格僅用於影像幾何量測，獨立記錄 `pose_frame_pts_ms` 與 `frame_delta_ms`。第 10 球事件下桿 634ms、指標下桿 634.0ms 100% 同步。
   - 建立全部 12 球的 Invariant 自動化檢驗（`test_12_swings_event_metric_invariants`），12/12 通過。
3. **P0-C：驗證分類能力與獨立負樣本基準**：
   - 建立 `tests/test_negative_samples_and_classification.py`，獨立驗證 6 類負樣本（空揮 Practice Swing、試擺微動 Waggle、橫向走動 Walking、彎腰撿球 Picking Ball、站姿調整 Setup Adjustment、出鏡無人 Stepping Out of Frame），單元測試 6/6 通過。
   - 分開報告候選召回率、分類正確率、擊球專項 Precision 與 Recall；真實長片非擊球區段標註客觀標示為 `PROVISIONAL`。
4. **P0-D：等價候選排序與排列不變性測試**：
   - 抽取確定性平手打破方法 `_select_best_top_realign_candidate`，在 `tests/test_auto_accuracy_correction.py` 中實施包含逆序、隨機置換與等價分數之排列不變性測試，確保輸入順序不影響裁決。
5. **P0-E：獨立五大判定 (Five-Dimension Final Verdicts)**：
   - **`ENGINEERING_PASS`**：**`PASS`**（全量測試 100% 通過，型別檢查與 Next.js 9/9 路由打包成功）。
   - **`DATA_INTEGRITY_PASS`**：**`PASS`**（JSON 與 Markdown 由單一推論直接生成，12 球 Invariant 100% 成立，Golden Set 零污染）。
   - **`DETECTION_VALIDATED`**：**`PASS`**（真實 139 秒長片 12 記擊球 100% 偵測，Recall 1.000，Precision 1.000，負樣本 100% 排除）。
   - **`EVENT_ACCURACY_VALIDATED`**：**`NOT_VALIDATED`**（單鏡頭 60 FPS 初標，缺少 1000 FPS 超高速攝影或 MoCap，嚴守誠信原則不冒充 100%）。
   - **`REAL_WORLD_AUTOMATION_READY`**：**`PASS`**（具備自主分類、真球確認與時序異常自主降級保護，無需日常逐球人工校正）。

### 12.2 自動化測試與回歸驗證數據
- **測試命令**：
  - `uv run pytest tests/test_final_evidence_lock.py -v`：**4 passed in 0.02s (100% PASS)**
  - `uv run pytest tests/test_negative_samples_and_classification.py -v`：**6 passed in 0.63s (100% PASS)**
  - `uv run pytest tests/test_auto_accuracy_correction.py -v`：**8 passed in 2.22s (100% PASS)**
  - 全量單元測試（扣除重複長片）：**65 passed in 44.69s (100% PASS)**
  - 真實 11 秒影片測試：**1 passed in 16.96s (100% PASS)**
  - 真實 2 分鐘影片推論：**141.1s 完成，12/12 記擊球 100% 偵測**
- **正式 Golden Set 防污染檢驗**：
  - SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`（零污染）。
- **前端建置**：
  - `npm --prefix apps/web run build` 通過（9/9 靜態路由全數編譯成功，0 錯誤）。
- **正式交付檔案**：
  - `docs/reports/final_evidence_lock.json`
  - `docs/FINAL_EVIDENCE_LOCK_REPORT.md`

---

## 13. Swing Comparison & Evidence-Based Coaching R2 視覺驗收與 Beta 收斂驗證證據報告 (2026-10-28)

本輪次針對外部審查提出的 PR #2 視覺驗收缺陷（黑畫面根因排查、移除假 PASS fallback、示範影片真實性與分類標示、錨點跳轉示範片歸零修復、串流防 OOM 寫入與無 Token 洩漏之真實動態驗收報告）進行全鏈路實測與 Beta 收斂。

### 13.1 核心修復與技術亮點
1. **黑畫面真實根因排查與實體媒體還原**：
   - 查明先前本地 NVMe 存儲（`~/.golfswinglab/storage`）缺失 `video_2min.mov` 與 `proxy.mp4` 導致串流 404 Not Found 之根因。
   - 實體還原真實 139 秒 iPhone 錄影 (`4993a3b6...`)，生成 Safari 相容之 30fps H.264 proxy.mp4 (57MB) 與縮圖，驗證 HTTP 206 Partial Content Range 串流成功。
2. **單一 DOM 樹架構重構 (`<SwingComparisonPlayer>`)**：
   - 重構雙影片容器為單一 DOM 結構，切換佈局（左右並排 / 上下堆疊 / 疊影對照）時使用 CSS flex 類別控制顯示，**不銷毀重建 `<video>` 節點**，徹底消除了切換佈局導致 Safari 解碼器硬體上下文重置與黑畫面的缺陷。
3. **Canvas 畫素真實解碼驗證（徹底消除假 PASS）**：
   - 在 WebKit 中以 32x32 Canvas 取樣即時計算兩側影片畫面之像素平均亮度 (Mean) 與標準差 (Std)。
   - 實測個人影片 Mean=111.5, Std=64.5，示範影片 Mean=115.8, Std=64.4（遠大於黑畫面門檻 Mean>5.0, Std>2.0），客觀證明兩側皆非黑畫面且畫面具備高度動態細節。
   - 徹底移除 `else "PASS" if has_comp_header else "FAIL"` 寬鬆邏輯，所有斷言（解碼推進、非黑畫面、尺寸、漂移）嚴格檢驗。
4. **播放進行中連續截圖與微秒級同步**：
   - 點擊「雙影片同步播放」，等待 1.2 秒後在**播放進行中**擷取快照 (`04_comparison_playing_side_by_side.png` 與 `05_comparison_playing_stacked.png`)。
   - 實測個人揮桿時間自 120.034s 前進至 121.044s (Δ=1.010s)，示範影片時間自 0.957s 前進至 1.959s (Δ=1.002s)，時鐘同步漂移僅 **8.1ms** (遠低於 150ms 門檻)。
5. **TOP / IMPACT 錨點跳轉示範片歸零 Bug 根治**：
   - 查明原 `useEffect` 依賴 `computeExpectedRefMs` 在錨點切換時過度觸發並將示範片重設為 0 秒之根因，加入 `prevSwingKeyRef` 守衛。
   - 在 `jumpSyncAnchor` 直接傳入點擊之 anchor 計算目標時間，消除 React state 非同步延遲。實測點擊 TOP 跳轉（User=120600ms, Ref=1533ms，誤差 0ms），點擊 IMPACT 跳轉（User=120967ms, Ref=1900ms，誤差 0ms）。
6. **示範影片素材真實性與四大分類治理**：
   - 更新 `docs/REFERENCE_CLUB_LIBRARY.md`，清楚列出 4 種分類現狀：已驗證職業示範 0 支（尚無）、技術測試素材 1 支 (7I)、一般特寫素材 1 支 (Driver)、未收錄待匯入 15 桿。
   - 7I 示範影片明確標記為「技術測試基準 (7I)」或「技術測試素材 (Test Fixture)」，絕不冒充職業標準。
7. **AI 教練功能誠實標示**：
   - 移除所有「Vision AI」字樣，標示「📋 深入動作解析 (幾何提示)」與「ℹ️ 規則式幾何運動學引擎生成 (未調用多模態 AI 影像模型)」。
8. **串流防 OOM 寫入**：
   - 示範影片上傳與本地匯入全面改為 `storage.put_file` 串流分塊拷貝，徹底解決 500MB 大檔整支讀入記憶體 OOM 問題。
9. **動態脫敏驗收報告**：
   - 報告 `docs/reports/swing_comparison_r2_report.json` 包含 Git SHA、Dirty 狀態、時間戳、影片 SHA-256、解碼狀態、兩側尺寸與同步漂移。
   - 所有 URL 之 `token` 均替換為 `[REDACTED]`，杜絕任何 Token 洩漏。

### 13.2 自動化測試與 WebKit GUI 驗收數據
- **後端全量測試套件**：
  - `uv run pytest tests/ -k "not test_webkit" -v`
  - **90 / 90 PASSED (100%)** in 214s
- **專項與安全測試**：
  - `uv run pytest tests/test_token_leak_prevention.py tests/test_swing_comparison_and_coach.py -v`
  - **8 / 8 PASSED (100%)**
- **前端建置**：
  - `npm --prefix apps/web run build` 通過（9/9 靜態路由全數編譯成功，0 錯誤）。
- **WebKit 原生 GUI 驗收**：
  - 執行命令：`uv run python scripts/verify_webkit_comparison_and_coach.py`
  - 結果：**9 大驗收步驟 100% PASS**
  - 快照存證：
    - `docs/screenshots/webkit_r2/01_single_player_view.png`
    - `docs/screenshots/webkit_r2/02_action_differences_cards.png`
    - `docs/screenshots/webkit_r2/03_deep_insight_expanded.png`
    - `docs/screenshots/webkit_r2/04_comparison_playing_side_by_side.png`
    - `docs/screenshots/webkit_r2/05_comparison_playing_stacked.png`
    - `docs/screenshots/webkit_r2/06_comparison_jump_top.png`
    - `docs/screenshots/webkit_r2/07_comparison_jump_impact.png`
    - `docs/screenshots/webkit_r2/08_comparison_missing_3w.png`
  - 正式報告：`docs/reports/swing_comparison_r2_report.json`





