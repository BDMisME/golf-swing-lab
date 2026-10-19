# TASKS.md — Golf Swing Lab 開發任務追蹤清單

> 狀態標記說明：
> - `[x]` 已完成並通過實測驗證 (`PASS`)
> - `[!]` 外部條件阻擋 (`EXTERNAL_BLOCKER`) 或需外部真實資料集驗證 (`NOT_VALIDATED`)

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

