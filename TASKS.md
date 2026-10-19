# TASKS.md — Golf Swing Lab 工程任務分解與驗收追蹤表

| Task ID | 輪次 | 任務名稱 | 需求追溯 | 前置任務 | 驗收條件 (DoD) | 狀態 | 證據與備註 |
|---|---|---|---|---|---|---|---|
| `T-R0-01` | R0 | 工作區盤點、Git 初始化與環境確認 | §8 R0 | - | 確認 Python 3.12, Node 24, pnpm, uv, Docker, FFmpeg 9.0 | `PASS` | `git init`, `ffmpeg 9.0.2_1` 已就緒 |
| `T-R0-02` | R0 | 建立核心規格與設計契約文件 | §8 R0, §5.3 | `T-R0-01` | `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/SCORING_POLICY.md`, `docs/API.md`, `docs/SECURITY.md`, `docs/DEPLOY_ZEABUR.md`, `docs/OPERATIONS.md`, `docs/GOLDEN_DATASET.md`, `docs/TEST_REPORT.md`, `docs/RELEASE_CHECKLIST.md` 齊全 | `PASS` | 全數文件已寫入並完成交叉核對 |
| `T-R1-01` | R1 | 建立 Python Monorepo 與 Docker Compose 基礎設施 | §5.1, §8 R1 | `T-R0-02` | `pyproject.toml`, `infra/compose.dev.yml` (PG 16, Redis 7, MinIO) 啟動正常 | `PENDING` | |
| `T-R1-02` | R1 | 實作 API `/healthz` 與 `/readyz` 及基礎框架 | §6.2, §8 R1 | `T-R1-01` | FastAPI 啟動、連線檢查 PG/Redis/S3、測試通過 | `PENDING` | |
| `T-R1-03` | R1 | 建立 Next.js (App Router) 繁體中文 Mobile-First UI Shell 與 CI Workflow | §5.1, §7.1, §8 R1 | `T-R1-01` | 導覽列、深色專業介面、TypeScript / Build 通過、`.github/workflows/ci.yml` 建立 | `PENDING` | |
| `T-R2-01` | R2 | SQLAlchemy 2 資料模型（14 張核心表）與 Alembic Migration | §6.1, §8 R2 | `T-R1-02` | Alembic `upgrade head` / `downgrade base` / `upgrade head` 通過 | `PENDING` | |
| `T-R2-02` | R2 | Argon2id 認證、Session/Token 與 Owner 權限隔離 | §2 P0, §6.2, §8 R2 | `T-R2-01` | 未登入 `401`、跨用戶 `403`、Sessions CRUD 測試通過 | `PENDING` | |
| `T-R3-01` | R3 | S3/MinIO Multipart 大檔分段上傳、續傳、Abort 與校驗 | §2 P0, §6.2, §8 R3 | `T-R2-02` | Initiate / Sign / Upload Part / Complete / Abort、冪等與續傳整合測試通過 | `PENDING` | |
| `T-R3-02` | R3 | `ffprobe` PTS/VFR/旋轉/HEVC 解析、Safari H.264 Proxy 與 HTTP Range 串流 | §2 P0, §4.1, §8 R3 | `T-R3-01` | 測試 H.264/HEVC/VFR/旋轉 MOV 檔解析、Proxy 產生與 `206 Partial Content` | `PENDING` | |
| `T-R4-01` | R4 | Redis/RQ Worker 背景任務排程、真實進度、Heartbeat、重試與取消 | §2 P0, §4.3, §8 R4 | `T-R3-02` | 冪等排隊、進度更新、Worker 重啟孤兒任務恢復、安全重試上限測試通過 | `PENDING` | |
| `T-R5-01` | R5 | Coarse-to-Fine 揮桿候選偵測、9 階段事件狀態機、IoU 去重與 Golden 評估器 | §4.1, §4.2, §8 R5 | `T-R4-01` | 合成多球/空揮/休息影片偵測、PTS 時間碼對應、手動新增/微調/刪除 API 測試通過 | `PENDING` | |
| `T-R6-01` | R6 | MediaPipe 2D 關鍵點抽取、DTL 幾何指標、異常畫質旗標與骨架疊圖資料 | §3.1, §8 R6 | `T-R5-01` | 30/60fps、旋轉、低光、多人/遮擋案例測試通過，缺失關鍵點不產生假數值 | `PENDING` | |
| `T-R7-01` | R7 | Score v1 可解釋評分引擎、70% 覆蓋率閘門、IG 視覺分與四大排行榜 | §3.3, §8 R7 | `T-R6-01` | Deterministic 重算、`<70%` 覆蓋率回傳 `null`、「怎麼算的？」明細與排序測試通過 | `PENDING` | |
| `T-R8-01` | R8 | 場次報告 API、共同問題分析、雙球對照資料與校正回饋留存 | §2 P1, §8 R8 | `T-R7-01` | 場次統計從資料表精確重建、`analysis_feedback` 留存且重算不覆蓋人工註記 | `PENDING` | |
| `T-R9-01` | R9 | FFmpeg 單球與 2–3 球合輯 MP4 匯出（原始比例與 9:16） | §2 P1, §8 R9 | `T-R8-01` | 匯出 MP4 時長誤差 `<0.2s`、畫幅比例正確、可於 Safari 播放與下載 | `PENDING` | |
| `T-R10-01` | R10 | `GolfCoachProvider` 介面、`none` 規則式教練與 `openai-compatible` Adapter | §11, §8 R10 | `T-R8-01` | 無 Key 完整運作且不發外網請求；Mock Provider 契約與例外降級測試通過 | `PENDING` | |
| `T-R11-01` | R11 | Web / API / Worker 完整前端整合、Dockerfiles 與 Zeabur 部署配置 | §10, §8 R11 | `T-R9-01`, `T-R10-01` | 全部前端頁面串接真實 API、Dockerfiles 建置驗證、Zeabur 模板配置齊全 | `PENDING` | |
| `T-R12-01` | R12 | 瀏覽器實機 E2E 驗收、Benchmark 基準測量與最終稽核報告 | §8 R12, §9 | `T-R11-01` | 瀏覽器實際走通登入→新增場次→上傳影片→背景分析→時間軸校正→骨架與評分→雙球比較→報告→匯出 MP4 | `PENDING` | |
