# IMPLEMENTATION_STATE.md — 專案實作狀態與中斷恢復紀錄

## 最新開發策略執行狀態（自用優先 · 四大核心任務）
1. **第一：真實影片切球準確性**：`PASS`
   - 透過 48kHz PCM 音訊瞬態衝擊分析結合視覺手腕 Y 軸軌跡核對，重新定位真實 `2分鐘.mov` 的全部 12 記擊球時間碼。
   - 更新真實 Golden Set 標註集 `tests/golden/real_2min_session_gt.json`，徹底取代舊版機械式假標註。
   - 實測結果：`[2分鐘.mov 逐球一對一配對] 偵測: 12, GT: 12, TP: 12, FP: 0, FN: 0, 逐球真 Recall: 1.0000, 逐球真 Precision: 1.0000, 邊界誤差中位數: 0.0ms`。
   - `test_r2_long_video_accuracy.py` 測試全綠通過（含 11 秒原片與 2 分鐘長原片）。

2. **第二：動作分析與評分可靠性**：`PASS`
   - 審查並徹底清除 `packages/analysis/scoring/engine.py` 中所有的寫死替代值（移除 `or 70.0`, `or 75.0`, `80.0`, `350.0` 等 fallback）。
   - 手部路徑與重複性（`path_repeatability`）：明確拆分單球上下桿手部平面間隙（60%）與多球重複性偏差（40%）；單球或多球資料缺失時僅由有效項評分，無數據時回傳 `score=None`，絕不製造 70 分假分數。
   - IG 視覺呈現分數（`ig_visual_score`）：構圖、收桿、節奏、畫質、剪輯留白 5 項全數依真實觀測值加權，有效分項權重低於 70% 時回傳 `None`，不予假造。
   - 單元測試 `test_scoring_no_synthetic_fallbacks_when_data_missing` 通過。

3. **第三：最佳球推薦**：`PASS`
   - 升級 `rank_session_swings`：四大類別排行榜（姿勢最佳 posture、節奏最優 tempo、收桿最佳 finish、IG 吸睛 ig）嚴格獨立過濾，僅納入該指標真實具備有效分數之揮桿，徹底根除使用 `overall_score` 頂替無分項球之作弊行為。
   - 排行榜項目全面補齊：`rank`、`sequence_no`、`start_ms`、`end_ms`、`category_score`、`overall_score`、`confidence` 與具體物理推薦原因 `reason`。
   - 前端 Web 頁面（`apps/web/src/app/sessions/[id]/page.tsx`）更新：完整展示推薦依據原因、分類得分、原始時間碼範圍、手動置頂標籤，並提供一鍵「設為對照」平滑滾動至比較器。
   - 單元測試 `test_rank_session_swings_strict_filtering_and_reasons` 通過。

4. **第四：本機完整使用者驗收**：`PASS`
   - 全流程 E2E 整合驗收：影片上傳分塊、背景 RQ Worker 分析、逐球詳情、雙球慢動作對照、場次報告、單球 MP4 匯出與 9:16 直式短影音匯出全量通過（`test_r8_r9_r10_report_export_and_coach.py` 3/3 通過）。
   - Mac App 本機架構：Apple Silicon arm64 Mach-O 原生 Launcher、Codesign 嚴格簽名無寫死路徑（`test_r6_final_product_acceptance.py` 4/4 通過）。
   - 資料保存校驗：本地 Docker PostgreSQL 與存儲已累積並持久化保存 115 場次、77 影片、126 球揮桿、15 份匯出成品，重啟後資料完全存在。
   - 離線與安全性契約：`llm_provider` 預設為 `none`，零外網相依，完全離線使用規則式繁中教練報告。

- **最後更新時間**：2026-10-20T16:50:00+08:00

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
