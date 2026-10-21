# IMPLEMENTATION_STATE.md — 專案實作狀態與中斷恢復紀錄

## 最新開發策略執行狀態（Precision & Clean Motion Final Calibration）
1. **多訊號 Impact 真球出球閉環回饋精修**：`PASS`
   - 重構球體偵測資料流，實作 `GolfBallDetector.track_swing_launch_with_feedback`。
   - 當真球出球點被可靠觀測（observed_count >= 2 且通過高爾夫物理合理性檢核），自動將出球瞬間 (`launch_onset_ms`) 作為權威錨點回饋精修 Impact 事件。
   - Impact 時間不確定度收斂至 $\pm 16\text{ms}$，狀態精確升級為 `confirmed_strike`，並將 `"ball_flight_observed_launch"` 納入 `detection_sources`。
   - 2 分鐘原片實測精確捕獲 6 記真球啟動（#1, #6, #7, #8, #9, #11），未捕獲出球的揮桿誠實保留為 `estimated_strike`，絕不捏造出球來源。
2. **音訊抽取強健性與明確診斷記錄**：`PASS`
   - 建立 `AudioExtractionResult`，支援局部區間切片抽取與長影片動態 timeout（解除原固定 8 秒 timeout 限制）。
   - 明確記錄 `no_audio`、`timeout`、`too_short`、`error` 與 `ok` 狀態，並完整記錄至 `quality_summary` 與 `quality_metadata`。
3. **局部高 FPS 二次精修（Local High-FPS Refinement）**：`PASS`
   - 實作 `_refine_event_local_high_fps`，針對低信心度或粗步掃描之 Top 與 Impact 事件，僅在其前後 $\pm 200\text{ms}$ 視窗內執行全幀率（60 FPS, step_ms=16）密集取樣，精修速度零交越與減速峰值，耗時僅數十毫秒，徹底免去重跑全片開銷。
4. **誠信原則與檢測來源嚴格審計**：`PASS`
   - 嚴格落實「真正記錄各訊號參與」：音訊距擊球大於 60ms 或無音訊脈衝時，絕對不包含 `"audio_transient_consensus"`；無真球出球時絕對不包含 `"ball_flight_observed_launch"`。
   - 區分模型信心分數 (`confidence: 0.0~1.0`) 與真實時間不確定性 (`uncertainty_ms: 16/33/67`)。
5. **Clean Motion UI 視覺降級與誠信防線**：`PASS`
   - 單球側邊欄 `coachInsights` 嚴格基於本球可觀測指標證據；若資料不足或覆蓋率低於門檻，**絕不宣告身體問題**，僅顯示客觀動作階段影像檢視。
   - 徹底移除單鏡頭無法測量之「足底壓力」與「重心轉移至前腳/腳跟」偽宣稱，改用可觀測「身體垂直軸線平衡穩定度」。
   - Pro Mode 明確標記 `✓ MediaPipe 33 點骨架`，杜絕與 YOLO 17 點混稱。
   - 加入揮桿時間區間防殘留保護，超出該球範圍立即清空 Canvas。
6. **WebKit 與 Chrome 實測分別記錄**：`PASS`
   - Chrome 實測截圖保存於 `docs/screenshots/chrome/`。
   - WebKit 實測截圖透過 macOS 原生 `WebKit.framework` (PyObjC) 保存於 `docs/screenshots/webkit/01_webkit_render.png`。
7. **全量品質與回歸驗證**：`PASS`
   - 後端全量測試：**50 / 50 PASSED (100%)** in 168.50s（包含新加入的 5 個回歸校準專項測試）。
   - 正式真值校驗：`tests/golden/real_2min_session_gt.json` SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`（0 污染）。
   - 前端打包：`npm run build` 9/9 靜態路由頁面打包成功。
   - 真實原片評估基準：`docs/PRECISION_CALIBRATION_EVALUATION.md` 完整輸出逐球時間碼、多訊號來源與真值指標（11s 與 2min 原片 True Recall 100%, Precision 100%）。
- **最後更新時間**：2026-10-21T12:50:00+08:00
- **最新驗收報告**：`docs/PRECISION_CALIBRATION_EVALUATION.md`、`docs/CLEAN_MOTION_REDESIGN_REPORT.md` 與 `docs/TEST_REPORT.md`

## 前期重大里程碑狀態（Auto Precision & Clean Motion UI Redesign）
1. **多訊號融合自動事件判定（Multi-Signal Event Detection）**：`PASS`
   - 重構 `SwingPhaseStateMachine` 與 `scanner.py`，整合手腕速度零交越、Top Pause 最小速度、肩部/骨盆旋轉反轉、下桿制動峰值、48kHz 音訊瞬態衝擊（0.18s 極速抽取）與真球出發點。
   - 每個偵測事件包含客觀來源 (`detection_sources`) 與合理不確定區間 (`uncertainty_ms`)，擊球狀態標示為 `confirmed_strike` 或 `estimated_strike`。
2. **Waggle / Practice Lift 抑制機制（Settled Address Anchor）**：`PASS`
   - 辨識起桿前微小晃動、試擺與靜止等待，鎖定起桿前最後靜止基準點（Settled Address），徹底排除瞄球微晃動與前置假動作，鎖定真實上桿發起點。
3. **極簡動態輔助線 Clean Motion UI（CleanMotionOverlay）**：`PASS`
   - 全新獨立組件 `apps/web/src/components/CleanMotionOverlay.tsx`，徹底解決五顏六色骨架與繁雜輔助線問題。
   - 預設「AI 教練模式」最多同時顯示 2 個標記，依 Address/Top/Downswing/Impact/Finish 自動流轉主題：
     - Address：金黃色站姿穩定框（頭部/臀部）與脊椎軸線
     - Top：手腕頂點位置與轉肩參考線
     - Downswing：手部動態路徑（$t \le \text{currentTime}$，不劇透未來）
     - Impact：桿身釋放平面與出球觀測點（嚴守誠信原則：無真球不畫假球軌）
     - Finish：收桿平衡金黃色垂直平衡軸
   - 徹底移除直接疊在人體關節上的交錯文字標籤與左上角常駐 5 色圖例，資訊移至底部 Coach HUD 提示列。
   - 統一色彩語義：青綠觀測點 (`#00f5d4`)、金黃站姿參考 (`#ffd166`)、亮紅超標警示 (`#ff5470`)。
   - 保留「專業模式 (Pro Mode)」開關，供深度分析者自選 33 點完整骨架、雙色手部軌跡、Tush Line 與即時數值儀表板。
4. **個人化體感教練體驗升級**：`PASS`
   - 單球側邊欄自動提煉每球最關鍵 1~2 項體感動作核心問題（如：骨盆旋轉不足、收桿提前煞車、頭部側移），並配對 2 項針對性實體自主 Drill。
5. **逐幀播放器與視覺同步**：`PASS`
   - 支援 `requestVideoFrameCallback` 零延遲繪製對齊，支援精確 `±1f / ±5f` 步進控制。
6. **全量品質與回歸驗證**：`PASS`
   - 後端全量測試：**45 / 45 PASSED (100%)** in 177.49s（包含真實 11 秒短片與 2 分鐘 139 秒長片 12/12 切球測試全數通過）。
   - 正式真值校驗：`tests/golden/real_2min_session_gt.json` 於測試前後 SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`（0 污染）。
   - 前端打包：`npm run build` 9/9 靜態路由頁面打包成功。
   - 視覺存證：改版前後各階段畫面截圖完整留存於 `docs/screenshots/baseline_clean_redesign/` 與 `docs/screenshots/redesign_clean_motion/`。
- **最後更新時間**：2026-10-21T12:00:00+08:00
- **最新驗收報告**：`docs/CLEAN_MOTION_REDESIGN_REPORT.md`、`docs/R13_GOLDEN_INTEGRITY_REPORT.md` 與 `docs/TEST_REPORT.md`

## 前期重大里程碑狀態（R13.1: Final Integrity Hotfix）
1. **P0-1 前後端事件契約與狀態完全統一**：`PASS`
   - 後端統一以 `status` (machine_suggested / human_verified / uncertain)、`source`、`frame`、`verified_at` 為權威契約。
   - 前端 `/audit` 修正舊欄位誤用，支援即時人工確認標記、影格號顯示、更新時間戳記與相對演算法原始值的偏移量（`Δ +xx ms (+xf)`）。
   - 經瀏覽器實測驗證，確認後重新整理頁面狀態持久保留，微調按鈕與 Snap 音訊吸附即時反映。

2. **P0-2 禁止測試污染正式 Golden Set 與完整 Round-Trip 重置**：`PASS`
   - 備份正式真值檔至 `tests/golden/backups/real_2min_session_gt.backup.json`，清理先前殘留之 6 筆測試 history，鎖定乾淨真值基準 SHA-256 為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`。
   - 所有具寫入行為之 API 與整合測試全面改用 pytest `tmp_path` 與 FastAPI `dependency_overrides[get_audit_registry]`，正式檔案在測試執行前後 SHA-256 保持完全一致（0 污染）。
   - 修復 `reset_swing_to_machine()`，重置時完整同步恢復 `events` 內部時間與影格、頂層快捷欄位 (`impact_ms` 等)、`start_ms`/`end_ms`、`downswing_ms`/`backswing_ms` 與 `tempo_ratio`，Round-Trip 測試 `test_golden_set_reset_round_trip` 實測 100% 通過。

3. **P0-3 嚴格修正 Event Accuracy 驗收依據**：`PASS`
   - `packages/analysis/evaluation/golden_eval.py` 嚴格限制：僅有標記為 `human_verified` 之事件納入正式人工真值 MAE 計算。
   - 未獲人工確認之事件一律標示為 `NOT_VALIDATED` 或 `PROVISIONAL`，並輸出樣本數 (`sample_count`)、總候選數、覆蓋率、中位數偏差與最大誤差，絕不以機器演算法建議值充當人工真值。

4. **P1-4 依高爾夫運動學修復揮桿節奏定義**：`PASS`
   - 節奏嚴格採用運動學標準：`Backswing = Top - Takeaway`、`Downswing = Impact - Top`、`Tempo Ratio = Backswing / Downswing`。
   - 徹底廢除將 Address 靜止瞄球時間併入上桿之舊邏輯；事件時序不符或缺少必要事件時，`tempo_ratio` 嚴格返回 `null`。

5. **P1-5 保護 Golden Set API 安全性與隱私**：`PASS`
   - `GET /api/audit/golden-sets` 及所有 `/api/audit/*` 端點全面加入 `current_user: User = Depends(get_current_user)` 認證防護，未授權請求嚴格返回 `401 Unauthorized`。
   - 關聯影片查詢限定於 `Video.owner_id == current_user.id`，落實租戶隔離。
   - 回傳 DTO 全面移除伺服器本機絕對檔案路徑暴露。


## 關鍵重大缺陷排除紀錄 (18% Proxy 卡死根因與修復)
1. **iPhone 空間音訊與 60fps 轉碼負載**：
   - **根因**：iPhone 17 Pro Max 拍攝 HEVC 影片帶有 4 聲道空間音訊 (`apple_apac`) 與定時元數據，FFmpeg 轉碼時發生解析衝突與耗時逾時。
   - **修復**：加入 `-map 0:v:0 -map 0:a:0? -sn -dn` 隔離空間音訊；限制 Proxy 為 720p 30fps，採用 `-preset ultrafast` 與 `-crf 26`，轉碼速度提升 10 倍以上。
2. **Debian Linux 容器缺少 OpenGL 渲染庫**：
   - **根因**：Docker Debian-slim 映像未預載 `libegl1` 與 `libgles2`，導致 MediaPipe 0.10+ 初始化 PoseLandmarker 時拋出 `libEGL.so.1: cannot open shared object file`。
   - **修復**：在 `infra/docker/api.Dockerfile` 與 `infra/docker/worker.Dockerfile` 安裝 `libegl1` 與 `libgles2`。
3. **長影片 ffprobe PTS 全幀解析逾時**：
   - **根因**：雲端有限 CPU 解碼長達數分鐘之 HEVC 全量畫面導致逾時超過 60 秒。
   - **修復**：改採 `packet=pts_time` 搭配 `-read_intervals %+30`，僅讀取 MP4/MOV 封包索引，解析時間由 60+ 秒降至 0.08 秒，並加上超時保護。
4. **豆包 (doubao-seed-2.1-lite) 多模態 API 調適**：
   - 移除 OpenAI 特有之 `response_format: {"type": "json_object"}` 解決 API plan 端點等待 hang 死問題；引導純 JSON 輸出。
   - 採「代表球（痛點球 + 標竿球）精選策略」，token 規模縮減 80%，推理耗時由 >90s 縮短至 56s，徹底避免 ReadTimeout。
5. **使用者體驗專項修復（影片播放、慢動作解析、揮桿軌跡與秒開）**：
   - **串流認證與 Format Error 修復**：瀏覽器原生 `<video>` 標籤不帶 SPA Bearer 標頭，在串流 URL 補齊 `?token=...`，後端 `stream_video` 加上 proxy/raw storage key 容錯降級，徹底解決黑畫面與格式錯誤問題。
   - **高爾夫揮桿軌跡 (Swing Path)**：Canvas 繪製螢光天藍色上桿路徑 (`#00f0ff`)、熾熱亮紅色下桿路徑 (`#ff2a5f`)、TOP 與 IMPACT 關鍵事件文字標籤，以及站位頭部基準金黃色虛線圈。
   - **慢動作播放與逐幀解析**：實作 `1.0x 原速`、`0.5x 慢速`、`0.25x 超慢動作`，以及 `±33ms` 逐幀前進/後退控制。
   - **頁面秒開與 AI 報告快取**：後端引入 `_COACH_REPORT_CACHE` 快取，前端頁面改採兩階段非同步加載，場次首屏 300ms 內秒開渲染。
   - **人工標籤校正與重算**：在單球卡片提供「轉為正式擊球 / 設為空揮」即時切換。
6. **真實原片揮桿判定與小白球出球動態軌跡 (Ball Tracer) 升級**：
   - **空揮誤判與 N/A 噪音球根除**：修復狀態機對下桿深度的僵硬門檻，只要具備清晰頂點、下桿加速與平衡收桿，即判定為 `valid_swing`；在掃描器中直接過濾無完整事件之走動/撿球背景視窗，真實 2 分鐘原片由原本 17 記（含 7 個 N/A 噪音）精確收斂為 12 記完整正式揮桿，100% 覆蓋。
   - **高爾夫轉播級小白球出球動態軌跡 (Ball Launch Tracer)**：在 Impact 瞬間定位地面球位，根據手腕釋放平面與透視深度拋物線，動態繪製霓虹螢光綠至電光黃的 Toptracer 追蹤軌跡與飛行白球粒子。

## 各輪次狀態矩陣 (R0–R12)

| 輪次 | 名稱 | 狀態 | 驗證證據摘要 |
|---|---|---|---|
| **R0** | Repo 盤點、架構契約與規格文件 | `PASS` | 10 份核心規格文件與 `.env.example` 完整建立 (`fd64eb4`) |
| **R1** | Monorepo 骨架、Docker 基礎設施與健康檢查 | `PASS` | `/healthz` 與 `/readyz` (Postgres 16, Redis 7, MinIO) 實測 `200 OK` |
| **R2** | Auth、Owner 權限隔離、SQLAlchemy 2 + Alembic | `PASS` | Alembic 正反向遷移通過，`test_r1_r2_auth_and_models.py` 3/3 通過 |
| **R3** | Multipart 大檔續傳、Range `206`、ffprobe VFR/HEVC/旋轉 | `PASS` | 實測 290MB (37 分塊) 續傳、SHA256 校驗與 packet PTS 取樣全數通過 |
| **R4** | Redis/RQ 背景佇列、階段進度、取消與重試上限 | `PASS` | 冪等重入、Heartbeat 自癒、工作狀態即時更新 10%~100% 驗證通過 |
| **R5** | Coarse-to-Fine 自動切球、9 階段狀態機與時間軸校正 | `PASS` | 真實長影片 `2分鐘.mov` 自動精準切出 17 記揮桿候選片段 |
| **R6** | MediaPipe 2D 關鍵點、幾何指標、畫質旗標與骨架疊圖 | `PASS` | 線上 Debian 容器加載 MediaPipe 成功，提取 33 點 2D 骨架與畫質旗標 |
| **R7** | Score v1 可解釋評分、70% 覆蓋率閘門與 4 榜排序 | `PASS` | 每球獨立計算軀幹前傾、頭部穩定、軌跡重複、節奏一致與收桿平衡 |
| **R8** | 場次報告、雙球同步對照與人工校正回饋留存 | `PASS` | 雙球播放器依 Impact/Top 對齊播放實測通過，Chrome 瀏覽器正常渲染 |
| **R9** | FFmpeg 單球與多球合輯 MP4 匯出（原比例與 `9:16`） | `PASS` | 產出合法 H.264 MP4 (`720x1280` 9:16 與原始比例)，可串流下載 |
| **R10** | `GolfCoachProvider`（支援豆包 / Gemini / OpenAI / 規則式） | `PASS` | 豆包 `doubao-seed-2.1-lite` 實測回傳高品質繁中動作分析與訓練課表 |
| **R11** | Zeabur 雲端多服務架構與部署 | `PASS` | GitHub `BDMisME/golf-swing-lab` 自動部署至 Zeabur，前後端與 Worker 正常運行 |
| **R12** | 全流程 E2E、瀏覽器實測與真實影片驗收報告 | `PASS` | 真實影片 `11秒.mov` (2球) 與 `2分鐘.mov` (17球) 於本機及 Zeabur 正式站 100% 跑通，Chrome 控制台與畫面截圖齊備 |

## Zeabur 遠端生產環境部署資訊
- **Zeabur 專案**：`golf-swing-lab` (`6ad5d29697597fca990714a3`)
- **Web 前端網址**：`https://golf-swing-lab.zeabur.app`
- **API 後端網址**：`https://golf-swing-lab-api.zeabur.app`
- **GitHub 儲存庫**：`https://github.com/BDMisME/golf-swing-lab` (`main`)

## 本機服務連接埠與啟動方式（無衝突配置）
- **PostgreSQL 16**：`localhost:25432` (`infra/compose.dev.yml`)
- **Redis 7**：`localhost:26379` (`infra/compose.dev.yml`)
- **MinIO S3**：`localhost:29000` / Console `localhost:29001` (`infra/compose.dev.yml`)
- **FastAPI (`gsl-api`)**：`http://localhost:28000` (`uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 28000`)
- **RQ Worker (`gsl-worker`)**：`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run python -m apps.worker.main`
- **Next.js (`gsl-web`)**：`http://localhost:23000` (`cd apps/web && npm run start -- -p 23000`)
- **預設體驗帳號**：`golfer@swinglab.local` / 密碼：`GolfSwingLab!2026`
