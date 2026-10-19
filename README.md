# Golf Swing Lab — AI 高爾夫揮桿分析系統

Golf Swing Lab 是一套專為高爾夫個人練習場（Driving Range）打造的 **Down-the-Line（DTL，球員身後視角）長影片自動切球、2D 骨架動作量測、可解釋評分與精選影片匯出系統**。

## 核心特色與誠信原則

1. **大檔與長影片友善（U1 / U2）**：支援 iPhone Safari / 桌面瀏覽器選取 `.MOV` / `.MP4`（H.264 / HEVC、旋轉 metadata、VFR 可變影格率），透過 Multipart 分段直傳 S3/MinIO 物件儲存，支援單段重試與斷點續傳；關閉瀏覽器後背景 Worker 仍持續處理。
2. **Coarse-to-Fine 自動揮桿偵測與人工校正（U3）**：低解析度稀疏掃描定位活動區段，再以高幀率搭配 MediaPipe Pose Landmarker 與 9 階段事件狀態機（`IDLE → ADDRESS_CANDIDATE → TAKEAWAY → BACKSWING → TOP → DOWNSWING → IMPACT_ESTIMATED → FOLLOW_THROUGH → FINISH → IDLE`）精準標記每次揮桿與相對原片 PTS 時間碼。支援手動新增、刪除、微調起迄與標註空揮。
3. **2D DTL 可解釋評分與骨架疊圖（U4）**：嚴格遵守 2D 單視角物理限制——**絕不捏造飛行距離、球速、桿頭速度、桿面角、甜蜜點或 3D 身體旋轉角**。所有動作分數（0–100）皆為產品內部定義之可重現指標（附 `score_version`、公式、分項權重、信心度與「怎麼算的？」明細），當有效覆蓋率低於 70% 時直接顯示「無法可靠評分（N/A）」。
4. **整場報告、雙球對照與 Top 精選推薦（U5）**：自動彙整場次統計、分項趨勢，並獨立排名「姿勢最佳」、「節奏最佳」、「收桿最佳」與「IG 視覺呈現最佳」，支援同場雙球同步對照與逐幀步進。
5. **真實畫面 MP4 匯出（U6）**：支援單球與 2–3 球連續精選合輯匯出（原始比例或 9:16 直式構圖），保留真實畫面，不繪製虛假球飛行軌跡。
6. **可插拔 LLM 教練 Adapter**：預設 `LLM_PROVIDER=none` 完全不需外部 API Key 即可運作（產出證據驅動之規則式繁體中文教學與課表）；設定 `openai-compatible` 時可基於客觀量測數據與時間碼生成補充建議。

## Monorepo 結構

```text
golf-swing-lab/
├── apps/
│   ├── web/                  # Next.js (App Router, TypeScript, Tailwind CSS)
│   ├── api/                  # FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2
│   └── worker/               # Python RQ Worker (FFmpeg + MediaPipe 分析與匯出)
├── packages/
│   ├── analysis/             # 揮桿偵測、Pose 抽取、事件狀態機、Score v1、Golden Set 評估與 LLM Adapter
│   ├── storage/              # S3 / MinIO Multipart 與短效簽名 URL 封裝
│   └── contracts/            # OpenAPI Schema 與前後端共享型別契約
├── infra/
│   ├── docker/               # Web / API / Worker Dockerfiles
│   ├── zeabur/               # Zeabur 多服務部署設定與範本
│   └── compose.dev.yml       # 本機開發環境 (PostgreSQL, Redis, MinIO, API, Worker, Web)
├── tests/
│   ├── fixtures/             # 合成測試影片產生器與輕量測試樣本
│   ├── golden/               # Golden Set 標註 Schema 與匿名範例
│   └── e2e/                  # Playwright 端到端測試
└── docs/                     # PRD、架構、API、評分政策、安全、維運、測試與部署文件
```

## 本機快速啟動

1. 複製環境變數設定：
   ```bash
   cp .env.example .env
   ```
2. 啟動基礎設施（PostgreSQL、Redis、MinIO）：
   ```bash
   docker compose -f infra/compose.dev.yml up -d postgres redis minio
   ```
3. 執行資料庫遷移與啟動後端 API / Worker：
   ```bash
   uv sync
   uv run alembic -c apps/api/alembic.ini upgrade head
   uv run uvicorn apps.api.main:app --reload --port 8000
   uv run python -m apps.worker.main
   ```
4. 啟動前端 Web：
   ```bash
   pnpm --dir apps/web install
   pnpm --dir apps/web dev
   ```
5. 預設管理員帳號（可於 `.env` 修改）：
   - 帳號：`golfer@swinglab.local`
   - 密碼：`GolfSwingLab!2026`
