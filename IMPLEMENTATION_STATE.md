# IMPLEMENTATION_STATE.md — 專案實作狀態與中斷恢復紀錄

## 最新開發策略執行狀態（Round 2: Production Acceptance & Independent Accuracy Audit）
1. **P0-1：Ground Truth 證據來源聲明修正與接觸片保存**：`PASS`
   - `docs/reports/takeover/independent_human_gt_2min.json` 驗證狀態正式更正為 `developer_assisted_visual_annotation`，明確標註 139 秒影片為 Development Set。
   - 誠實揭露外部獨立精度標記為 `NOT_VALIDATED`（絕不偽稱為盲測真值）。
   - 擷取保存關鍵球（#8、#9、#10）連續影格接觸片至 `docs/reports/takeover/contact_sheets/`，詳實記錄 Top/Impact 時間碼判定證據。
2. **P0-2：正式 Worker 30fps Proxy 作為主要驗收路徑**：`PASS`
   - 依據 `apps/worker/tasks.py` 生成 Safari 相容 720p/30fps H.264 Proxy 與縮圖，並作為主要驗收對象。
   - 30fps Proxy 驗收指標（Primary Target）：
     - 揮桿分類正確率：**100.0% (12/12)**
     - Top MAE：**66.7 ms（2.0 影格 @ 30fps）**
     - Impact MAE：**41.1 ms（1.2 影格 @ 30fps）**
     - 生理下桿符合率：**100.0%**
     - 自動通過率：**100.0%**
     - 時序異常球數：**0 球**
   - 60fps 原片路徑對齊指標（Development Set Alignment）：
     - Top MAE：**89.0 ms（5.3 影格 @ 60fps）**（由接管前的 179.3 ms 縮小 50%）
     - Impact MAE：**27.8 ms（1.7 影格 @ 60fps）**
   - 60fps 原片 vs 30fps Proxy 逐球事件對齊誤差中位數 < 34ms，PTS 與影格解碼完全同步。
3. **P0-3：改善 Top 事件候選與下桿發動轉折點（Downswing Initiation）**：`PASS`
   - 左右手腕平滑可見度加權融合（`_midpoint`）：杜絕 DTL 視角單側遮擋飄移拉偏。
   - 頂點停頓蓄力期（Top Pause Plateau）轉折判定：在手腕高位蓄力區加入 `is_crest` 幾何高度閘門，並鎖定向下速度突變之下桿爆發啟動點（Transition Breakaway Launch）；結合生理下桿時長（200~380ms）先驗約束，徹底消除 #8、#9、#10 偏早 150~330ms 的系統性偏差。
4. **P0-4：校準 Confidence 與 Timing Uncertainty**：`PASS`
   - 嚴格分離 Sampling Resolution（16~33ms）、Timing Uncertainty（Top 保守標記 60~80ms，Impact 33~55ms）與 Heuristic Confidence（封頂 0.88）。
   - 杜絕將 16ms 影格解析度冒充定位誤差，或骨架清晰即宣稱 0.96 假高分。
5. **P0-5：負樣本分類驗證與 Top 5 可信度**：`PASS`
   - 6 類負樣本測試 100% 通過（空揮、Waggle、走動、撿球、調整站姿、出鏡）。
   - Top 5 榜單（最佳姿勢、最佳節奏、最佳收桿、IG 精選）基於可觀測幾何指標排序，標註為啟發式推薦，絕不宣稱球速、距離、球路或擊球甜蜜點。
6. **P1：日常使用驗收與服務健康**：`PASS`
   - 11 秒短片（`測試影片/11秒.mov`）：成功自動辨識單球完整揮桿（Top 3473ms, Impact 3807ms, ds 334ms, score 73.2）。
   - 後端全量測試：**74 / 74 PASSED (100%)**。
   - 前端打包：`npm --prefix apps/web run build` 9/9 頁面成功。
- **最後更新時間**：2026-10-23T12:30:00+08:00
- **最新基準版本**：`fix/autonomous-event-accuracy-recovery`
- **正式驗收報告檔案**：`docs/reports/takeover/production_acceptance_report.json`、`docs/reports/takeover/fixed_proxy.json`、`docs/reports/takeover/fixed_original.json`

## 前期重大里程碑狀態（Final Reliability Gate）
1. **P0-1：Top 重對齊邏輯修復與候選順序不變性**：`PASS`
   - 修復 `packages/analysis/events/state_machine.py` 中 `_validate_and_realign_swing_timing` 的迴圈變數洩漏問題（原使用迴圈最後殘留的 `zc_bonus`，修正為追蹤最佳候選 `best_cand` 自身之 `best_cand_has_zc` 與運動學特徵）。
   - 新增 `test_top_realignment_candidate_order_invariance_and_zc_isolation` 單元測試，驗證候選順序反轉或變更時，最佳 Top 候選判定 100% 一致。
   - 尊重 180–650ms 作為常見參考，無客觀證據時不強行將不可靠事件移入正常區間。
2. **P0-2：切球成功率五維度獨立拆分與分類感知驗收**：`PASS`
   - 重構 `packages/analysis/evaluation/golden_eval.py` 與 `tests/test_r2_long_video_accuracy.py`，將單一 IoU 評估拆分：
     1. 候選片段偵測率（Candidate Window Detection Rate）：100.0% (12/12)
     2. 動作分類正確率（Action Classification Accuracy）：100.0% (12/12)
     3. 擊球專項 Recall / Precision（Valid Swing Specific）：Recall 100.0% / Precision 100.0%
     4. 關鍵事件定位品質（Top, Impact, Finish 定位誤差分佈）
     5. 真球起飛確認率（Confirmed Strike Rate）與邊界誤差（Boundary Error Median 894.5ms，保留安全緩衝區間）
   - 嚴格同步註解與 assert 門檻（Recall >= 0.90, Precision >= 0.85），絕不用較低門檻冒充達標。
3. **P0-3：異常時序自主降級與不可評分保護**：`PASS`
   - 審核 2 分鐘影片逐球表現：Ball 1 (1783ms)、Ball 6 (2118ms)、Ball 11 (2233ms)、Ball 12 (783ms) 存在起桿前長試擺或停頓。
   - 局部重分析若無法將時序收斂至生理範圍，標記 `timing_anomaly_detected`，`review_status` 降級為 `needs_review`，旗標加入 `timing_anomaly`。
   - `compute_observable_metrics` 依誠信原則將 `downswing_ms`、`backswing_ms` 與 `backswing_downswing_ratio`（tempo）的 `value` 設為 `None`，絕不捏造不可靠分數。
4. **P0-4：局部高 FPS 精修影格傳遞與時序防呆（Finalized Event Frame Mapping）**：`PASS`
   - `_refine_event_local_high_fps` 增強 Impact 減速峰值門檻，精修結果若違反生理下桿極限則保守拒絕，保留真實事件。
   - 精修產生的高 FPS 真實影格 (`FramePoseResult`) 封裝傳遞至 `finalized_event_frames`，優先供 `compute_observable_metrics` 與 Keyframe 提取使用，杜絕影格與 PTS 時間碼脫節。
5. **真球升空相鄰影格時間連續性強化**：`PASS`
   - `analyze_ball_launch_continuity` 要求至少存在一對時間連續相鄰（$\Delta t \le 55\text{ms}$）且位移遞增/高度遞減的連續 2 影格觀測點，杜絕時間不相鄰的兩點誤判。
6. **全量品質與回歸驗證**：`PASS`
   - 後端全量測試：**58 / 58 PASSED (100%)**（包含全新 8 項專項測試與真實長短片基準測試）。
   - 前端打包：`npm run build` 9/9 靜態路由頁面打包成功（0 錯誤）。
   - 正式真值校驗：`tests/golden/real_2min_session_gt.json` SHA-256 0 污染。
- **最後更新時間**：2026-10-21T20:28:00+08:00
- **最新驗收報告**：`docs/FINAL_RELIABILITY_GATE_REPORT.md` 與 `docs/TEST_REPORT.md`

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
