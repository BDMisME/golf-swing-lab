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
| **R10** | `GolfCoachProvider`（`none` 規則式預設 + `openai-compatible` 結構化驗證與捏造球速/距離攔截降級） | `uv run pytest tests/test_r8_r9_r10_report_export_and_coach.py -k coach` | 1 / 1 通過 | Real (`none`) + Mock (`httpx.MockTransport`) | `PASS` |
| **R11** | Dockerfiles (`api`, `worker`, `web`)、`infra/compose.prod.yml` 與 `infra/zeabur/template.yaml` 驗證 | `docker compose -f infra/compose.prod.yml config -q` | 語法與結構通過 | Real (本機驗證) / 遠端 Zeabur 缺 Token | 本機 `PASS` / 遠端 `EXTERNAL_BLOCKER` |
| **R12** | 前後端型別檢查 (`ruff`, `mypy`, `tsc`)、Vitest、Next.js 生產建置與 Chrome DevTools 瀏覽器 E2E 實測 | `uv run pytest -v` + `npm test` + `npm run build` + Chrome DevTools MCP | 後端 13/13、前端 3/3、8 路由全通過 | Real | `PASS` (真人 100+ 球 Golden Set 為 `NOT_VALIDATED`) |

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
