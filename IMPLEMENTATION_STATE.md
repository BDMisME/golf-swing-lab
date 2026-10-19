# IMPLEMENTATION_STATE.md — 專案實作狀態與中斷恢復紀錄

## 當前進度總覽
- **目前輪次**：**R12 已完成**（R0 至 R12 全部完成，且 Zeabur 雲端生產環境已成功部署上線，Google Gemini 3.8 Flash 原生教練已整合並通過單元與端對端驗收）。
- **最後更新時間**：2026-10-19T17:25:00+08:00

## 各輪次狀態矩陣 (R0–R12)

| 輪次 | 名稱 | 狀態 | 驗證證據摘要 |
|---|---|---|---|
| **R0** | Repo 盤點、架構契約與規格文件 | `PASS` | 10 份核心規格文件與 `.env.example` 完整建立 (`fd64eb4`) |
| **R1** | Monorepo 骨架、Docker 基礎設施與健康檢查 | `PASS` | `/healthz` 與 `/readyz` (Postgres 16, Redis 7, MinIO) 實測 `200 OK` |
| **R2** | Auth、Owner 權限隔離、SQLAlchemy 2 + Alembic | `PASS` | Alembic 正反向遷移通過，`test_r1_r2_auth_and_models.py` 3/3 通過 |
| **R3** | Multipart 大檔續傳、Range `206`、ffprobe VFR/HEVC/旋轉 | `PASS` | `test_r3_r4_upload_probe_and_worker.py` 4/4 通過 |
| **R4** | Redis/RQ 背景佇列、階段進度、取消與重試上限 | `PASS` | 冪等重入、手動取消、Heartbeat 逾時恢復、自癒背景執行緒與 `max_attempts=3` 測試通過 |
| **R5** | Coarse-to-Fine 自動切球、9 階段狀態機與時間軸校正 | `PASS` | 合成黃金測試集 Recall=1.00, Precision=1.00, Impact MAE=37.3ms |
| **R6** | MediaPipe 2D 關鍵點、幾何指標、畫質旗標與骨架疊圖 | `PASS` | `pose_landmarker_lite.task` 實測通過，支援 60fps、低光與多人干擾旗標 |
| **R7** | Score v1 可解釋評分、70% 覆蓋率閘門與 4 榜排序 | `PASS` | 10 次重跑方差 `0.0`，`<70%` 覆蓋率強制回傳 `None` |
| **R8** | 場次報告、雙球同步對照與人工校正回饋留存 | `PASS` | `PATCH /api/swings/{id}` 與 `force=true` 保留人工標記實測通過 |
| **R9** | FFmpeg 單球與多球合輯 MP4 匯出（原比例與 `9:16`） | `PASS` | 產出合法 H.264 MP4 (`720x1280` 9:16 與原始比例)，可串流下載 |
| **R10** | `GolfCoachProvider`（支援 Gemini 3.8 Flash / OpenAI / 規則式） | `PASS` | 原生支援 `gemini-3.8-flash`；防幻覺攔截自動退回；API Key 絕不外洩；單元測試通過 |
| **R11** | Zeabur 雲端多服務架構與部署 | `PASS` | 建立 GitHub Repo `BDMisME/golf-swing-lab`；Zeabur 生產上線 (`6ad5d29697597fca990714a3`)；前後端連線就緒 |
| **R12** | 全流程 E2E、瀏覽器實測與 Golden Set 評估報告 | `PASS` / `NOT_VALIDATED` | Pytest 14/14、Vitest 3/3、Next Build 8/8、Puppeteer 線上全流程實測通過；真人 100+ 球資料集標記 `NOT_VALIDATED` |

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
