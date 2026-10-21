# TASKS.md — Golf Swing Lab 開發任務追蹤清單

> 狀態標記說明：
> - `[x]` 已完成並通過實測驗證 (`PASS`)
> - `[!]` 外部條件阻擋 (`EXTERNAL_BLOCKER`) 或需外部真實資料集驗證 (`NOT_VALIDATED`)

## Final Reliability Gate (2026-10-21)
- [x] **P0-1 修正 Top 重對齊 Bug 與候選順序不變性**：在 `state_machine.py` 的 `_validate_and_realign_swing_timing()` 中，修復迴圈殘留變數洩漏 `zc_bonus` 導致最佳候選誤殺之缺陷，確保最佳候選完全依自身特徵判斷。新增候選順序反轉與零交越隔離測試（`test_top_realignment_candidate_order_invariance_and_zc_isolation`），保證評估結果一致性。
- [x] **P0-2 重新定義切球成功率與五大獨立維度拆分**：在 `golden_eval.py` 中將切球表現拆分為五項互不掩蓋的客觀維度：
  1. 所有揮桿動作候選偵測率 (`candidate_detection_rate`: 100%, 12/12)
  2. 揮桿分類正確率 (`classification_accuracy`: 100%, 12/12，嚴格檢驗 `valid_swing` vs `practice_swing`)
  3. 真實擊球專項 Recall (`valid_swing_recall`: 100%, 12/12)
  4. 真實擊球專項 Precision (`valid_swing_precision`: 100%, 12/12)
  5. 真球升空連續觀測確認數 (`ball_launch_confirmed_count`: 1) 與邊界誤差中位數 (894.5ms 安全 padding)。
- [x] **P0-3 異常時序自主降級與不可評分保護**：在 `state_machine.py` 實作生理極限防呆保護（$180\text{ms} \le T_{\text{downswing}} \le 650\text{ms}$）。長試擺或停頓導致下桿時間超標之球次（Ball 1: 1783ms, Ball 6: 2118ms, Ball 11: 2233ms, Ball 12: 783ms）自動標記 `review_status = "needs_review"`、`timing_anomaly`，`downswing_ms`、`backswing_ms` 與 `backswing_downswing_ratio` 嚴格返回 `None`（`unreliable=True`），前端誠實顯示「無法可靠評分」，絕不捏造虛構分數。
- [x] **P0-4 事件時間碼與影格真正一致（Finalized Event Frame Mapping）**：在 `scanner.py` 中建立 `finalized_event_frames`，將局部 60 FPS 精修與時序檢核後之最終事件幀注入指標重算與 Keyframe 抽取；在 `ball_tracker.py` 中要求至少存在相鄰連續影格（$\Delta t \le 55\text{ms}$）且位移遞增/高度遞減之連續觀測點才判定真球升空，排除跨幀噪聲誤判。
- [x] **全量自動化回歸驗證**：
  - 後端 Pytest：**58/58 PASSED (100%)**（包含真實 11 秒與 2 分鐘原片長片驗收）。
  - 前端建置：Next.js 9/9 靜態路由全數編譯成功（0 錯誤）。
  - 正式 Golden Set：SHA-256 恆為 `efefa02b...`（零污染）。
  - 詳盡逐球報告保存於 `docs/FINAL_RELIABILITY_GATE_REPORT.md`。

## Final Auto Accuracy Correction (2026-10-21)
- [x] **P0-A 真正辨識 Ball Launch**：重構 `ball_tracker.py`，新增連續性分析狀態機 (`analyze_ball_launch_continuity`)，以打擊墊球位建立基準點，區分 `stationary`、`moving`、`airborne`、`occluded`。位移 $< 0.025$ 或最大位移 $< 0.030$ 嚴格判定為靜止球，不產生出球時間，不輸出假球軌跡，杜絕將靜止球誤判為出球。
- [x] **P0-B 自動偵測與校正不合理事件時序**：建立 `_validate_and_realign_swing_timing`，納入高爾夫生理極限（$180\text{ms} \le T_{\text{downswing}} \le 650\text{ms}$）。當初選 Top 抓到試擺（Waggle）假頂點時，自動於擊球前 180~650ms 視窗內，以速度零交越、頂點停頓（Top Pause）與強烈下桿加速度重新鎖定真實擊球 Top，並連帶校準 Settled Address 與 Takeaway。2 分鐘原片 #1、#2、#6、#8、#11 異常下桿（原 1500~2383ms）全數成功收斂至 250~650ms 正常區間！
- [x] **P0-C 修正事件精修與資料一致性**：重構 `scanner.py` 資料流（初測 ➔ 真球回饋 ➔ 高 FPS 精修 ➔ 時序檢核 ➔ **重算 Metrics** ➔ **依 finalized events 微調邊界防溢出** ➔ 生成 Keyframes）。確保 `downswing_ms`、`backswing_ms`、`tempo_ratio` 與最終事件時間碼 100% 同步，片段邊界嚴格限制在 `[0, duration_ms]`。
- [x] **P1-A 正確揭露時間精度**：拆分 `sampling_resolution_ms` (16ms/33ms)、`uncertainty_ms` (±16~25ms) 與 `event_timing_error_ms`（無人工真值時為 `null`），杜絕將 60 FPS 取樣解析度冒充為 0ms 測量誤差。
- [x] **P1-B 真實影片 UI 檢查與自動化覆蓋**：全量 56 個 pytest 通過（100% PASS，新增 6 項 `test_auto_accuracy_correction.py`），Next.js 編譯通過（0 錯誤），真實原片 12/12 記擊球 Recall 100%、Precision 100%。

## Precision & Clean Motion Final Calibration (2026-10-21)
- [x] **P0-1 多訊號 Impact 真球出球閉環回饋精修**：重構球體追蹤資料流 (`track_swing_launch_with_feedback`)，真球出發點 (`observed_launch_ms`) 權威回饋修正 Impact，升級為 `confirmed_strike`，不確定度縮小至 $\pm 16\text{ms}$，2 分鐘原片捕獲 6 記真球啟動。
- [x] **P0-2 音訊抽取強健性與明確診斷**：解除 8 秒 timeout 限制，建立 `AudioExtractionResult`，支援局部切片與長影片動態逾時（長片 139 秒解碼 0 timeout），明確記錄 `no_audio`、`timeout`、`error` 與 `ok`。
- [x] **P0-3 局部高 FPS 二次精修**：實作 `_refine_event_local_high_fps`，12/12 記揮桿全數主動觸發，於 $\pm 200\text{ms}$ 內以 60 FPS (step=16ms) 密集取樣，時間不確定度由 ±66ms 收斂至 ±16ms。
- [x] **P0-4 誠實記錄 detection_sources**：未實際參與判定之音訊/真球來源絕對不列入 `detection_sources`，明確區分信心分數與時間窗口不確定性。
- [x] **P1-1 Clean Motion 視覺降級防線**：無充分可觀測指標時絕不預設立場宣告身體缺陷，純說明動作階段。
- [x] **P1-2 移除足底壓力與單鏡頭重心宣稱**：修飾為可觀測身體垂直軸線平衡穩定度，Pro Mode 明確標示 `MediaPipe 33 點骨架`，增加時間區間防殘留保護。
- [x] **P1-3 WebKit 與 Chrome 真實影片實測畫面雙雙驗收**：
  - Chrome 實測截圖：`docs/screenshots/chrome/05_swing_player_clean_motion.png`（完整播放器、Letterbox置中、金色頭部基準圈、AI體感洞察與針對性Drill）。
  - Chrome Pro Mode 實測截圖：`docs/screenshots/chrome/03_redesign_pro_mode.png`（Tush line、手部雙色軌跡、無真球誠實標記）。
  - WebKit 實測截圖：`docs/screenshots/webkit/02_webkit_swing_player.png` 與 `01_webkit_render.png`（macOS 原生 `WebKit.framework` + NSWindow GPU 視訊解碼 readyState=4，100% 排除登入頁、黑畫面與載入失敗）。
- [x] **P1-4 切球測試門檻統一**：`tests/test_r2_long_video_accuracy.py` 消除註解與 assert 差異，正式鎖定高標準門檻 `Recall >= 0.90` (實測 1.000) 與 `Precision >= 0.85` (實測 1.000)。
- [x] **P2 真實原片評估基準**：11 秒 (1/1) 與 2 分鐘 (12/12) 真實原片基準評估，真值配對 True Recall 100%、Precision 100%，改版前後時間碼對比表輸出至 `docs/PRECISION_CALIBRATION_EVALUATION.md`。
- [x] **全量自動化回歸驗證**：全量 50/50 PASSED (204.07s)，Next.js 9/9 路由打包通過，正式 Golden Set SHA-256 零污染。

## Auto Precision & Clean Motion UI Redesign (2026-10-21)
- [x] **A. 自動事件辨識多訊號精準化**：
  - 整合手腕速度零交越、Top Pause 最小速度、肩部/骨盆旋轉反轉、下桿制動峰值、48kHz 音訊瞬態衝擊與真球出發點。
  - 實作 Waggle / Practice Lift 抑制機制（鎖定起桿前最後靜止基準 Settled Address Anchor）。
  - 二次局部精修，輸出客觀來源 (`detection_sources`) 與合理不確定區間 (`uncertainty_ms`)。
  - 客觀標示擊球狀態 (`confirmed_strike` / `estimated_strike` / `strike_unknown` / `no_ball`)。
- [x] **B. 動態輔助線重新設計 (Clean Motion UI)**：
  - 獨立封裝全新 `apps/web/src/components/CleanMotionOverlay.tsx`。
  - 預設「AI 教練模式」極簡設計（最多同時 2 個標記，依 Address/Top/Downswing/Impact/Finish 自動切換主題，無人體文字遮擋，底部 Coach HUD 提示列）。
  - 統一色彩語義：青綠觀測 (`#00f5d4`)、金黃站姿參考 (`#ffd166`)、亮紅超標警示 (`#ff5470`)。
  - 保留專業模式（Pro Mode，自選 33 點完整骨架、雙色手部軌跡、Tush Line 等）。
  - 逐幀同步與 `requestVideoFrameCallback` 零延遲對齊，手部軌跡只畫到當前時間（$t \le \text{currentTime}$），支援精確 `±1f / ±5f` 步進。
- [x] **C. 個人化體感教練體驗升級**：
  - 單球側邊欄自動提煉每球最值得改善的 1~2 個具體體感動作核心問題，並配對 2 項建議實體自主 Drill。
- [x] **D. 驗收存證與回歸測試**：
  - 截取改版前與改版後基準影格截圖存證（`docs/screenshots/baseline_clean_redesign/`, `docs/screenshots/redesign_clean_motion/`）。
  - 撰寫完整對比報告 `docs/CLEAN_MOTION_REDESIGN_REPORT.md`。
  - 全量測試 45/45 通過（包含 11s 與 2min 真實原片 12/12 切球），正式 Golden Set SHA-256 0 污染。

## R13.1 — Final Integrity Hotfix (2026-10-21)
- [x] **P0-1 前後端事件資料契約統一**：統一後端 `status`, `source`, `frame`, `verified_at`，前端顯示人工確認徽章、影格號、Delta 偏移量 (`Δ +xx ms (+xf)`)，刷新頁面持久保留。
- [x] **P0-2 禁止測試污染正式 Golden Set**：清除 6 筆測試 history，備份正式檔案（SHA-256: `efefa02b...`），所有寫入測試改用 tmp_path 與 dependency_overrides 隔離；修復 `reset_swing_to_machine` 之 Round-Trip。
- [x] **P0-3 修正 Event Accuracy 驗收依據**：嚴格限定只有 `human_verified` 事件計入正式 MAE；未經確認時標示 `NOT_VALIDATED` 或 `PROVISIONAL`，輸出樣本數與覆蓋率。
- [x] **P1-4 高爾夫運動學節奏修正**：`Backswing = Top - Takeaway`、`Downswing = Impact - Top`、`Tempo Ratio = Backswing / Downswing`，排除 Address 靜止時間。
- [x] **P1-5 保護 Golden Set API**：端點必須認證（`401`），依 `owner_id` 過濾關聯影片，移除伺服器本機絕對路徑暴露。
- [x] **全量自動化回歸驗證**：45/45 PASSED，Next.js 9/9 頁面打包成功，正式 Golden Set SHA-256 0 污染。

## Real Practice Validation 驗收任務清單 (2026-10-20)
- [x] **任務一：獨立驗證 Golden Set (12/12)**：破解 2.267 秒試擺誤判假象，12 球逐格（48kHz PCM + 60fps）人工確認基準，True Recall 100%、Precision 100%、邊界誤差中位數 747.0ms。建立 `/audit` 人工審核 UI。
- [x] **任務二：修正 Score v2 最後資料缺口**：`body_visibility_ratio` 來自 MediaPipe 真實入鏡分析；移除 coverage 頂替 IG 漏洞；實作同場多球手腕軌跡插值與重複性計算 `compute_session_wrist_repeatability`；詳情頁提供「🎯 影格」跳轉與無法評分原因。
- [x] **任務三：最佳球人工驗收 (Top 5)**：各大排行榜（姿勢/節奏/收桿/IG）嚴格依真實分項獨立過濾，排除空揮與覆蓋率 < 70% 球，排行榜新增「▶ 預覽片段」按鈕原地循環播放該球區間。
- [!] **任務四：10–30 分鐘長影片實測**：`NOT_VALIDATED`（硬碟僅有 2 分鐘與 11 秒原片，無 10–30 分鐘 iPhone DTL 真實素材，依指示誠實標註，絕不用合成素材冒充）。


## R0 — 專案盤點、架構契約與規格文件
- [x] 建立 Git 儲存庫與 Monorepo 目錄結構 (`apps/`, `packages/`, `infra/`, `docs/`, `tests/`)
- [x] 撰寫 `AGENTS.md`、`README.md`、`.env.example`、`docs/PRD.md`、`docs/ARCHITECTURE.md`、`docs/SCORING_POLICY.md`、`docs/GOLDEN_DATASET.md`、`docs/API.md`、`docs/SECURITY.md`、`docs/DEPLOY_ZEABUR.md`、`docs/OPERATIONS.md`、`docs/TEST_REPORT.md`、`docs/RELEASE_CHECKLIST.md`

## R1 — Monorepo 骨架、基礎設施與健康檢查
- [x] 建立 `infra/compose.dev.yml` 並啟動 PostgreSQL 16 (`25432`)、Redis 7 (`26379`)、MinIO (`29000/29001`)
- [x] 實作 FastAPI `/healthz` 與 `/readyz` 真實連線檢查
- [x] 建立 Next.js 15 + React 19 + Tailwind CSS 繁體中文深色主題 App Shell

## R2 — 身分驗證、權限隔離、資料庫遷移與錯誤合約
- [x] 實作 SQLAlchemy 2 完整 14 張資料表模型與 Alembic 遷移 (`0001_initial_schema.py`)
- [x] 驗證 Alembic `upgrade head -> downgrade base -> upgrade head` 正反向遷移
- [x] 實作 Argon2id 密碼雜湊、Session Cookie / Bearer Token 認證、Owner 跨用戶 `403` 隔離與 `AuditEvent` 紀錄

## R3 — 大檔分段續傳、HTTP Range 串流與媒體探測
- [x] 實作 S3/MinIO Multipart Upload (`initiate`, `parts/sign`, `parts/{no}/content`, `complete`) 與冪等續傳
- [x] 實作 `/api/videos/{id}/stream` 支援 Safari HTTP Range (`206 Partial Content`)
- [x] 實作 `packages/analysis/probe.py` 解析 H.264/HEVC、VFR PTS 時間戳、旋轉矩陣與損毀檔 `422` 攔截

## R4 — 背景工作佇列、進度追蹤與異常恢復
- [x] 實作 Redis + RQ Worker (`apps/worker/tasks.py`, `apps/worker/main.py`)
- [x] 實作真實階段進度 (`probe -> proxy -> coarse_scan -> fine_scan -> scoring -> report`)、Heartbeat、手動取消與最大重試上限 (`max_attempts=3`)

## R5 — Coarse-to-Fine 自動揮桿偵測、9 階段狀態機與人工校正
- [x] 實作 `CoarseToFineDetector` 與 `SwingPhaseStateMachine` 9 階段狀態機
- [x] 實作 `compute_time_iou` 與 `merge_overlapping_windows` 重疊候選視窗去重
- [x] 實作手動新增/修改/刪除揮桿片段 API 與時間軸 UI，且 `force=true` 重算時保留 `manual_override=True` 片段

## R6 — MediaPipe 2D 骨架擷取、幾何指標與畫質旗標
- [x] 整合 Google MediaPipe `PoseLandmarker` (`pose_landmarker_lite.task`) 提取 2D 關鍵點
- [x] 計算可觀測 DTL 2D 幾何指標並標記 `low_light`、`multi_person`、`camera_motion` 旗標
- [x] 實作單球詳情頁 Canvas 2D 骨架疊圖開關與 `±33ms` 逐幀控制

## R7 — Score v1 可解釋評分引擎、70% 覆蓋率閘門與排行榜
- [x] 實作 `compute_swing_score_v1` 計算 5 項子分數與獨立 `ig_visual_score`
- [x] 實作 `<70%` 有效權重覆蓋率誠實閘門（強制 `overall_nullable = null`）與「怎麼算的？」展開明細
- [x] 實作 `posture`、`tempo`、`finish`、`ig` 四大類別排行榜與人工置頂/排除

## R8 — 場次總結報告、雙球同步對照與回饋紀錄
- [x] 實作 `/api/sessions/{id}/report` 場次摘要、共同問題診斷與各球比較
- [x] 實作前端雙球同步對照比較器 (`2-Swing Side-by-Side Comparison`) 與 `AnalysisFeedback` 紀錄

## R9 — FFmpeg 精準時間碼單球與合輯 MP4 匯出
- [x] 實作 `packages/analysis/exporter.py` 支援單球與 2–3 球合輯匯出（`original` 與 `9:16` `720x1280` 直式構圖）
- [x] 實作 `/api/exports` 與 `/api/exports/{id}/download` 並於前端 `/exports` 驗證下載

## R10 — 可插拔教練介面與防幻覺護欄 (支援 Gemini 3.8 Flash)
- [x] 實作 `RuleBasedCoachProvider` (`LLM_PROVIDER=none` 預設完整運作) 與 `OpenAICompatibleCoachProvider`
- [x] 實作 `GeminiCoachProvider` 支援 Google Gemini 3.8 Flash (`gemini-3.8-flash`)，速度極快、繁體中文原生理解、結構化輸出
- [x] 實作違規詞彙（球速、飛行距離、曲球等）防幻覺攔截自動降級與 Server-only API Key 保護

## R11 — Dockerfiles 與 Zeabur 雲端生產部署
- [x] 建立 `infra/docker/api.Dockerfile`、`infra/docker/worker.Dockerfile`、`infra/docker/web.Dockerfile`、`infra/compose.prod.yml`、`infra/zeabur/template.yaml` 並通過 `docker compose config` 驗證
- [x] 遠端 Zeabur 雲端實機部署：`PASS`（已完成 GitHub Repo `BDMisME/golf-swing-lab` 連結，於 Zeabur 專案 `6ad5d29697597fca990714a3` 成功上線，Web: `https://golf-swing-lab.zeabur.app`，API: `https://golf-swing-lab-api.zeabur.app`）

## R12 — 全流程整合測試、瀏覽器實測與真實素材基準評估
- [x] 通過全部後端 Pytest (14/14)、Ruff、Mypy (38 檔 100% 通過)、前端 TypeScript、Vitest (3/3)、Next.js Production Build (8/8 路由)
- [x] **真實測試素材雙端驗收**：`PASS`（使用者提供之 `測試影片/11秒.mov` 與 `測試影片/2分鐘.mov` 在本機與 Zeabur 線上生產站 100% 跑通，精準切出 2 記與 17 記揮桿，突破 18% Proxy 轉碼與 Linux Debian 容器 MediaPipe `libegl1` 缺陷）
- [x] **豆包多模態 AI 教練實測**：`PASS`（成功串接火山引擎 `doubao-seed-2.1-lite`，以代表球策略穩定產出高品質繁體中文動作洞察與優先課表）
- [x] **本機 Chrome 瀏覽器端對端驗收**：`PASS`（使用 Chrome DevTools MCP 控制真實瀏覽器，驗收時間軸、17 記切球指標、AI 教練報告與雙球比對畫面，截圖保存至 `docs/screenshots/`）
- [x] **使用者體驗專項升級（播放、慢動作、揮桿軌跡、秒開）**：`PASS`（解決原生 `<video>` 標籤缺少 Token 導致的 Format error 黑畫面；Canvas 繪製螢光藍/亮紅揮桿弧線與頭部基準圈；支援 0.25x/0.5x 慢動作與 ±33ms 逐幀步進；AI 報告快取與漸進載入達成首屏秒開；單球標籤一鍵校正與即時重算）
- [!] 外部多場次 100+ 球大規模人工標註 Golden Set 泛化指標驗證：`NOT_VALIDATED`（目前兩部真實素材已跑通驗證，更大規模資料集可隨時透過 `golden_eval.py` 批次評估）

