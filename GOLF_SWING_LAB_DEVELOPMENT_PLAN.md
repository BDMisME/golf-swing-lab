# Golf Swing Lab — AI 高爾夫揮桿分析系統

> 完整產品需求、技術架構、工作分解、測試與 Zeabur 部署規格（V1.0，2026-10-19）  
> 開發環境：Google Antigravity / Gemini 3.8 Flash  
> 部署平台：GitHub + Zeabur  
> LLM：使用者後續提供 API；核心功能不可依賴 LLM。

---

## 0. 開發指令的最高優先原則

1. 實作目標是**真實可用的系統**，而非純設計稿、靜態 Demo、只有假資料的儀表板。
2. 以「iPhone 固定於練習場後方（Down-the-Line, DTL），錄製 10–30 分鐘長影片或上傳多段影片」為主流程；右手持桿預設，資料結構預留左打。
3. 使用者應能：上傳 → 背景處理 → 自動偵測每次揮桿 → 確認切片 → 看姿勢分析和評分 → 挑精選球 → 匯出 MP4。
4. **真實與可驗證**：不可虛構球路、擊球飛行距離、桿頭速度、甜蜜點接觸品質、精確桿面角、3D 身體角度、實際擊球結果。影片看不到就是未知。估計值要標示 `estimated`。
5. 分清「揮桿候選（swing candidate）」、「可信完整揮桿（valid swing）」、「已確認擊球（confirmed ball strike）」。只有 DTL 影片不一定能判定實際擊球，不能把每次揮桿當作有擊球。
6. 姿勢分數為**產品定義的內部動作指標**，不是職業教練認證或實際擊球品質分數；須揭露公式、依據、信心度、演算法版本。
7. 不接 LLM API 也要能成功運作。後續提供 Key 時，透過 Provider Adapter 開啟補充文字教學。
8. 每輪實作後自我檢查、測試、修復、複驗、記錄證據，通過該輪 DoD 才進下一輪；不要因單次測試綠燈就宣稱產品完成。
9. 完整部署以 Zeabur 為目標；開發時用 Docker Compose 在本機模擬。Zeabur 文件目前不支援直接以 Docker Compose YAML 作為部署方法，需以各服務 Dockerfile／模板設定部署。
10. 任何缺少實際影片、金鑰、Zeabur 權限的地方，需標示 `EXTERNAL_BLOCKER` 或 `NOT_VALIDATED`，以測試樣本完成能完成的工作；**不得虛構驗收通過**。

## 1. 產品定位與使用情境

### 1.1 使用者

- 核心使用者：在練習場連續練球、固定用 iPhone 從球員身後拍攝的個人使用者。
- 用途：回顧每次訓練、找出好的揮桿、找姿勢問題、追蹤改善、剪輯社群精選。
- 初版以單人私有產品為主；權限、資料設計保留日後多使用者能力，但不提早打造 SaaS 商業計費系統。

### 1.2 必須可完成的六個使用者任務

- U1：從 iPhone Safari 或桌面瀏覽器，選取 1 至多部 `.MOV`／`.MP4`（包含 HEVC/H.265），一次上傳 10–30 分鐘影片。檔案大時可續傳或重試。
- U2：關閉瀏覽器後，後端仍能處理；重新打開可看任務進度、失敗原因或重試。
- U3：長影片自動標記每次揮桿的起迄與相對原片時間碼，以時間軸呈現；可手動新增、刪除、拖曳邊界與標註未擊球的空揮。
- U4：每球觀看短片、關鍵影格、骨架疊圖，分項檢視可量測的 DTL 動作；低信心直接顯示「無法可靠評分」。
- U5：整場整理平均分數、改善與退步趨勢、Top 3／Top 5 姿勢最佳、節奏最佳、收桿最佳、最適合 IG 的球。
- U6：匯出單球及連續精選 2–3 球的 9:16 或原始比例 MP4，保留原影片真實畫面，不偽造飛行軌跡。

### 1.3 不在初版範圍

- 不建立物理準確的球飛行追蹤、擊球落點、飛行距離、球速、spin、launch angle。
- 不訓練大型專用高爾夫模型，不採用不明授權的商業模型／資料集。
- 不直接推出 App Store 原生 iOS App；先做 mobile-first Web App／PWA。
- 不處理即時語音提醒；這是後期選配。

## 2. 功能需求與驗收條件

### P0 — 首個可用 MVP

| 模組 | 必備能力 | 驗收證據 |
|---|---|---|
| 身分與隱私 | 管理員登入、登出、權限隔離、影片非公開 | 未登入 API 401、跨用戶 403、URL 到期測試 |
| 影片匯入 | 1080p MOV/MP4、HEVC/H.264、旋轉方向、VFR、單檔與多檔 | 真實 iPhone 測試檔可播、duration 正確 |
| 大檔上傳 | Multipart 直傳物件儲存、每 part 失敗重試、暫停恢復、checksum | 中斷網路再續傳，無破損且不會重複入庫 |
| 背景任務 | 排隊、進度、取消、重試、處理日誌 | 重新整理或關閉分頁後仍完成 |
| 自動切球 | 候選揮桿偵測、相對原片時間碼、手動校正 | 與人工標註 Golden Set 比較 |
| DTL 動作分析 | 骨架、上桿頂點候選、姿勢變化、節奏、穩定性 | 指標可追溯至原始影格 |
| 結果介面 | 逐球短片、信心度、狀態與低信心提示 | 使用者在 iPhone 可操作 |
| 系統部署 | Zeabur Web/API/Worker/DB/Queue/Storage | Staging 完整 E2E、Health check、重啟資料留存 |

### P1 — 主要差異化功能

| 模組 | 必備能力 | 驗收證據 |
|---|---|---|
| 可解釋評分 | 0–100 動作分數、分項、信心度、評分版本；未知則 N/A | 人工注入測試量測值可重算相同結果 |
| 完整報告 | 練習場次總覽、各球比較、共同問題、最優動作 | 報告計算可從資料表重建 |
| 精選推薦 | 姿勢、節奏、收桿、IG 觀賞性分開排名 | 人工干預與手動排除後排名即更新 |
| 對照播放 | 兩球同步比對、影格步進、關鍵姿勢並排 | 不因不同 fps/timebase 錯位 |
| 匯出 | 原比例單球／2–3 球合輯／9:16 模式 | 匯出 MP4 在 iPhone 可播放、影片長度正確 |
| 校正回饋 | 手動分段、標籤、評分誤判回饋 | 修訂紀錄留存且重算不覆蓋原始註記 |

### P2 — 智能教練與長期追蹤

- 長期報告：同球桿、同視角、同攝影設定的時序比較，非同條件不強行比較。
- LLM 教練：從客觀指標與可見影格生成繁體中文建議，引用每個建議的時間碼，選擇 1–2 個優先問題與下一場課表。
- LLM API 暫未提供時，介面展示「進階 AI 教練尚未設定」，**不顯示假完成結果**。
- 計畫任務：每天／每週練習卡片，完成紀錄。
- 音訊與球桿追蹤可在合法資料與充分驗證後再開發。

## 3. 實際影片判讀界線與品質信心

### 3.1 DTL 可分析（程度各異）

- 肩、髖、膝與踝的 2D 影像投影位置、頭部相對位移、身體前傾外觀變化。
- 手部與軀幹相對運動、上桿／下桿相對時間、結束姿勢停留與平衡外觀。
- 球桿視覺路徑僅在球桿可靠偵測時呈現；看不到桿頭就不給路徑分數。

### 3.2 不可妄下結論

- 2D DTL 不提供真實精確的 3D 旋轉角、桿面角、重心壓力分布、擊球甜蜜點、實際球飛行距離。
- 「疑似擊球瞬間」使用 `impact_estimated_ms`，並附推定依據與信心；未看見球或聽不清楚時標記 `strike_unknown`。
- 「IG 精選」定義為完整入鏡、節奏順暢、收桿好看、畫面清晰的**視覺呈現分數**，不能稱「真正打最遠」。

### 3.3 分數設計（初版可調權重，不可冒充運動科學定論）

對於通過動作品質閘門的候選揮桿，以 0–100 計算：

| 分項 | 權重 | 評量依據 | 觀測不足 |
|---|---:|---|---|
| 軀幹前傾穩定 | 25 | address 至 downswing 可視傾斜變化 | N/A |
| 頭部相對位移 | 15 | 頭部相對肩/髖與畫面校正 | N/A |
| 身體與手部軌跡重複性 | 20 | 在同場同視角、已接受樣本群中的重複性 | N/A |
| 上下桿節奏一致性 | 20 | 頂點和釋放動作估測時間、同場相對穩定 | N/A |
| 收桿姿勢穩定 | 20 | 平衡、穩定停留、全身入鏡情況 | N/A |

- 權重為產品初始假設；分數反映「內部檢核規則」，**不等同擊球成效**。
- 每分項的 threshold／normalization 皆需明定版本 `score_version`、輸入資料、校正來源與配置，禁止憑感覺產出常數分數。
- 不足資料：可重配剩餘可靠分項權重，但必須顯示 `partial_score=true`、coverage，若有效覆蓋未達 70% 則不輸出總分。
- 不應把職業選手身材／動作當作絕對唯一標準；同場趨勢可比單次「完美姿勢分」更有價值。
- 每分項另帶 `confidence` 0–1 和理由。可配置最小數據品質，避免跨角度無意義比較。
- IG 分數完全獨立：畫面完整 30%、平穩收桿 25%、節奏觀感 20%、清晰度 15%、起迄剪輯完整性 10%（僅產品預設權重，允許校正）。

## 4. 長影片自動偵測演算法

### 4.1 處理流程

1. **Ingest / probe**：保存原始檔、SHA256、檔案大小、ffprobe duration/stream metadata、timebase、旋轉、音訊、fps、VFR、codec。使用真實時間戳 PTS，不可僅 `frame_number / nominal_fps`。
2. **Proxy**：生成可供 Safari 使用的 H.264/AAC（必要時）低解析預覽與 thumbnail；原始影片保留以供精準裁切。
3. **Coarse scan**：低解析度 3–6 fps 掃描，MediaPipe 找人體關鍵點與軀幹/手臂運動強度；用稀疏掃描定位候選活動區段。這是可調參數，不保證所有揮桿都能靠 3 fps 找到。
4. **Event clustering**：依手腕、肩部相對運動、上桿停頓、身體姿勢與靜止時間，組合為候選揮桿；引入最短／最長時長、冷卻時間，處理連續空揮。
5. **Fine scan**：對候選 ±緩衝範圍解碼 15–30 fps，推論與追蹤關鍵點，偵測 setup / backswing / top / downswing / impact_estimated / followthrough / finish。時間戳由原片 PTS 精準對應。
6. **Review flags**：低信心、人體遮擋、攝影機位移、多人、球桿缺失、重複檢出、候選重疊 → 進入人工確認佇列。
7. **Clip/export**：儲存 time ranges；先採虛擬片段播放，使用者需要下載才產生實體 H.264 MP4，避免一次輸出數十個大檔。

### 4.2 狀態機

`IDLE → ADDRESS_CANDIDATE → TAKEAWAY → BACKSWING → TOP → DOWNSWING → IMPACT_ESTIMATED → FOLLOW_THROUGH → FINISH → IDLE`

- 狀態依可見動作證據轉換；遇到跳幀不硬填事件。
- 存 `event_type`、`time_ms`、`confidence`、`source`（model/rule/manual）、`model_version`。
- 偵測器版本化，允許修正後重新分析同一場但保留舊結果以比較。
- 去重：透過 time-range IoU 與相鄰事件合併；從空揮到正式擊球的轉場不應誤計兩次。
- 相機位置未固定、多人走過、半身出鏡時，提示拍攝品質並降低可用分數。

### 4.3 畫面處理與效能

- 採串流解碼／批次小窗口，避免把整段影片所有影格載入 RAM。
- 分析 30 分鐘影片不得佔滿所有 worker；預設單 worker 同時處理一部，負載測量後再加併發。
- 任務進度以真實階段與 frame/window 完成量呈現，不用假的線性倒數。
- 運算可由 CPU 開始；準備 GPU provider interface，但初版不要求 GPU。
- 避免在同步 HTTP request 中跑完整推論；網站保持可回應。

## 5. 技術架構與 repo

### 5.1 技術堆疊

- `apps/web`：Next.js App Router、TypeScript、Tailwind、shadcn/ui（僅採必要元件）、TanStack Query、支援 iPhone Safari 的 video player。
- `apps/api`：FastAPI、Pydantic v2、SQLAlchemy 2、Alembic，JWT / HttpOnly session 的伺服器端登入驗證與統一權限層（擇一可靠設計並寫明）。
- `apps/worker`：Python RQ + Redis，重用 `packages/analysis`、`packages/storage`，FFmpeg/OpenCV/MediaPipe；開發完成需檢查 rq worker 的 job timeout 與 heartbeat。
- `packages/analysis`：偵測、階段事件、信心、評分與版本化。
- `packages/contracts`：OpenAPI schema + 產生 TypeScript client、型別契約測試。
- 資料：PostgreSQL（metadata）、Redis（RQ job queue）、S3 API storage（MinIO／相容儲存）。
- 測試：pytest、Vitest、Playwright、mypy/ruff、ESLint/tsc；GitHub Actions。

### 5.2 系統拓樸

```
[iPhone Safari / Desktop Browser]
      |    HTTPS  [Private Auth]
      v
[Zeabur: WEB - Next.js] <----> [Zeabur: API - FastAPI] ----> [PostgreSQL]
                                        |   |             \
                                    enqueue |              -> [S3-compatible storage / MinIO]
                                        v
                                  [Redis / RQ queue]
                                        |
                                        v
                                [Zeabur: WORKER]
                              FFmpeg + MediaPipe
                                        |
                      write metadata / thumbnails / reports / exports
```

- Web 和 API 對外（API 可由 Web 同源 reverse proxy）；Worker、Redis、PostgreSQL、MinIO 管理介面不可無保護暴露公網。
- 瀏覽器大檔透過已認證 API 核發之**短效 multipart presigned URL** 直傳物件儲存。若 MinIO 需要公開 S3 入口，只開啟受 HTTPS、CORS 與短效簽名保護的資料面 endpoint；Admin Console 不可公開。
- 不可誤用 Zeabur **部署 ZIP 的 Upload API** 來上傳使用者高爾夫影片；那不是產品檔案儲存 API。
- 下載與預覽用短效簽名 URL 或受權限驗證的串流代理；影片播放應支援 HTTP Range。
- 接客用 Web、API 採 stateless，檔案存 S3。Zeabur Volumes 只掛到確實需要持久化的存儲服務；有 Volume 的服務部署可能短暫停機。

### 5.3 專案建議樹

```
golf-swing-lab/
├── apps/
│   ├── web/
│   ├── api/
│   └── worker/
├── packages/
│   ├── analysis/
│   │   ├── detection/
│   │   ├── pose/
│   │   ├── events/
│   │   ├── scoring/
│   │   └── evaluation/
│   ├── storage/
│   └── contracts/
├── infra/
│   ├── docker/
│   ├── zeabur/
│   └── compose.dev.yml
├── tests/
│   ├── fixtures/              # 合法使用且小尺寸的非敏感測試素材
│   ├── golden/               # 標註資料，不把私人原片提交 Git
│   └── e2e/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── SCORING_POLICY.md
│   ├── GOLDEN_DATASET.md
│   ├── DEPLOY_ZEABUR.md
│   ├── API.md
│   ├── SECURITY.md
│   ├── OPERATIONS.md
│   ├── TEST_REPORT.md
│   └── RELEASE_CHECKLIST.md
├── AGENTS.md
├── IMPLEMENTATION_STATE.md
├── TASKS.md
├── .env.example
└── README.md
```

## 6. 資料模型與 API 合約

### 6.1 資料表

- `users`：id、email/username、password_hash、role、created_at。
- `practice_sessions`：id、owner_id、date、club、handedness、camera_angle=DTL、notes、status。
- `videos`：id、session_id、storage_key、sha256、original_name、mime、size_bytes、duration_ms、width、height、rotation、fps_num/den、codec、recorded_at、ingest_status。
- `upload_parts` / `uploads`：upload_id、video_id、state、parts/ETags、expires_at、idempotency_key。
- `analysis_jobs`：id、video_id、status、stage、progress、attempt_count、error_code、started_at、finished_at、analysis_version、heartbeat_at。
- `swing_segments`：id、video_id、start_ms、end_ms、label、confidence、review_status、version、manual_override、created_at。
- `swing_events`：id、segment_id、event_name、time_ms、confidence、detection_source、model_version。
- `pose_artifacts`：segment_id、storage_key、quality_metadata（壓縮 landmarks，勿把逐幀大資料直接塞 API 回應）。
- `swing_metrics`：segment_id、metric_key、value、unit、confidence、source、observability。
- `swing_scores`：segment_id、score_version、overall_nullable、subscores_json、coverage、confidence、explanation、computed_at。
- `favorites`：owner_id、segment_id、category、rank_override。
- `exports`：id、owner_id、video_ids、segment_ids、layout、format、state、storage_key、expires_at。
- `analysis_feedback`：id、segment_id、category、before/after、note、labeler、created_at。
- `audit_events`：actor_id、object_type、object_id、action、timestamp、metadata。

必要 indexes：`owner_id`、`session_id`、`video_id`、`status`、`start_ms`；所有資源 API 都必須驗證 owner。`updated_at`、軟刪除與 DB migration 由實作確定。

### 6.2 API 草案

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/auth/login` | 登入並建立安全 session |
| GET | `/api/sessions` | 場次列表 |
| POST | `/api/sessions` | 新增練習場次 |
| POST | `/api/uploads/initiate` | 驗證大小/類型/配額，建立 multipart upload |
| POST | `/api/uploads/{id}/parts/sign` | 領取指定 part presigned URL |
| POST | `/api/uploads/{id}/complete` | 驗證 parts/物件實際存在/metadata 並入庫 |
| POST | `/api/uploads/{id}/abort` | 清理未完成的 multipart upload |
| POST | `/api/videos/{id}/analyze` | 排入背景分析（冪等） |
| GET | `/api/jobs/{id}` | job 狀態、階段與錯誤 |
| POST | `/api/jobs/{id}/retry` | 有上限的安全重試 |
| GET | `/api/videos/{id}/swings` | 取得候選與確認的片段 |
| PATCH | `/api/swings/{id}` | 人工修正時間、標籤與註記 |
| GET | `/api/swings/{id}` | events、metrics、score、精確時間碼 |
| GET | `/api/sessions/{id}/report` | 場次統計與推薦球 |
| POST | `/api/exports` | 建立 MP4 匯出任務 |
| GET | `/api/exports/{id}` | 檢視與授權下載 |
| GET | `/healthz`、`/readyz` | liveness / readiness |

- Error contract：JSON `code`、`message`、`details`、`request_id`；不得直接暴露 stack trace。
- Idempotency：upload initiate、complete、analyze、export 均防重入。
- 查詢大量 segments 用 cursor pagination；圖表只請求必要欄位。

## 7. UI／UX 規格（繁體中文、mobile-first）

### 7.1 導覽

1. 儀表板：最新練習、待分析、最近最優球、技術趨勢。
2. 新增練習：日期、球桿（7I 預設）、右/左打、後方角度、上傳影片或拖曳多檔；同場多檔。
3. 分析進度：上傳／解碼／粗掃／精掃／評分／預覽生成等真實狀態；失敗可重試。
4. 場次報告：總次數、有效片段、待確認、可評分比例、各指標趨勢、主要問題。
5. 影片分析時間軸：可縮放、點擊跳時間、候選片段不同狀態、邊界可修正、支持鍵盤與觸控。
6. 單球詳情：大影片、frame step（以真實 timestamp）、骨架開關、同場雙球比較、分項評分、置信度、評論。
7. 精選球：各類 Top 3/5、人工加入/剔除、合併多球匯出。
8. 個人設定：球桿、慣用手、評分細節、資料保留、API Provider 設定（Server-only secret；UI 不回傳 key）。

### 7.2 設計語言

- 沉穩、簡潔的專業運動訓練介面；避免「AI 魔法」、「完美神揮桿」等浮誇文字。
- 深色模式優先、淺色模式可用；字級、間距、觸控目標符合手機操作。
- 可視化清楚區分：檢測成功、低信心、待人工修正、未處理、處理失敗。
- 每個成績旁有 `怎麼算的？`，不能只有「92 分」而無依據。
- 正式 UI 不使用假成功數字、不以示意影片冒充使用者影片。

## 8. 開發階段與「通關」測試

### R0 — Repo 起始盤點與設計契約

- 檢查 workspace、工具鏈、現有 repo（若不存在，建立新的私有 repo 目錄，不假設已建立 GitHub 遠端）。
- 建立 `AGENTS.md`、`TASKS.md`、`IMPLEMENTATION_STATE.md`、核心 ADR、測試策略、用戶旅程。
- 完整確認 Zeabur 現行部署文件；鎖定可重現版本，完成授權稽核。
- **Gate**：文件與驗收矩陣齊全、沒有未定義的 P0 接口。

### R1 — Monorepo、基礎架構與 UI Shell

- 完成 Web/API/Worker scaffold、Dev Docker Compose、PG/Redis/MinIO、logging、health endpoints。
- UI shell、手機與桌面導覽、GitHub Actions 檢查。
- **Gate**：本機一鍵啟動、健康檢查全通過、主要頁可導覽、型別與 lint 過。

### R2 — Auth、資料模型與 API

- migration、基本登入、owner 授權、sessions、videos metadata。
- **Gate**：未登入拒絕、跨帳戶拒絕、migration upgrade/downgrade smoke、API contract tests 過。

### R3 — 大影片上傳、存儲與影片預覽

- multipart presign、續傳、校驗、ffprobe、旋轉/VFR/HEVC、預覽轉碼。
- **Gate**：真實 iPhone MOV 能上傳並正確播放；網路中斷可恢復；格式錯誤優雅失敗。

### R4 — 背景任務與可靠性

- RQ queue、worker stage/progress、heartbeat、retry/cancel、任務冪等、資源限制。
- **Gate**：同時 2 個上傳、1 個處理、worker 重啟後復原任務狀態、不重複輸出。

### R5 — 自動揮桿候選偵測

- 粗掃、活動窗口、fine scan、狀態機、相對原片 timestamp、去重、人工邊界校正 UI。
- **Gate**：在人工標註 Golden Set 上，候選 `recall >= 90%`、`precision >= 85%` 作為第一版**驗收目標**；若樣本不足，標記未驗證，不可宣稱達標。切片時間偏差中位數 <= 0.5 秒（可配置、需實測）。

### R6 — 動作事件、骨架與信心

- MediaPipe landmarks、動作階段候選、可觀測指標、影片骨架疊圖。
- **Gate**：30 fps 與 60 fps、旋轉/VFR、低光、多人干擾與遮擋的錯誤案例至少測一組；缺失 landmarks 不會產生不合理值。

### R7 — 動作評分與排序

- score v1、partial_score/confidence、姿勢／節奏／收桿／IG 類別排序、分數可追溯。
- **Gate**：分數 deterministic、沒有完整資料不打假分、切換校正版本可重算且可稽核。

### R8 — 場次報告與雙球對照

- 場次趨勢、Top 3/5、逐球時間軸、雙球同步播放、人工標籤。
- **Gate**：從首頁上傳到報告，真實操作完整走通，不依賴假資料。

### R9 — 影片匯出與社群分享

- 輸出單球、2–3 球連續精選、9:16/原比例 MP4、safari 相容下載。
- **Gate**：播放器與匯出片段時間誤差有量測，正常片長、正確順序、無空白影片與音畫錯位。

### R10 — LLM Adapter（無金鑰可通過）

- `none`、`openai-compatible` 抽象 provider；未提供 API 只顯示規則式教學及 disabled UI。
- 如需傳圖／影格給外部 API，須明確告知、取得允許；LLM 只依量測值和經授權影格解讀，無數據不推論。
- **Gate**：無金鑰完全可用；mock provider 契約測試通過；未配置外部服務時不發外網請求。

### R11 — Zeabur staging 與部署

- 建立 Web、API、Worker、PostgreSQL、Redis、MinIO 的 Zeabur 部署配置，Dockerfiles/環境變數/網域／健康檢查／日誌／備份。
- 在 staging 完成 smoke/E2E、上傳與完整 worker 報告、持久儲存、重啟恢復。
- **Gate**：實際 staging URL 可開啟、health 正常、真實上傳與分析串完。未具備帳號／權限則 `EXTERNAL_BLOCKER`。

### R12 — 產品 UAT 與可用版釋出

- 真正 iPhone Safari、真實 DTL 長影片回歸；人工比對標註、效能測量、敏感資料與存儲成本檢查。
- **Gate**：所有 P0、P1 達成；重要問題 0；每項測試有 log/screenshots/video artifacts；未驗證不許 PASS。
- 正式站部署需經使用者提供授權及資源權限，不能自創憑證或無限制新增付費資源。

## 9. Golden Dataset、品質指標與驗收計畫

### 9.1 真實標註資料

- 建議取得 5–10 段真實後方練習影片，**至少 100 次人工可數揮桿**；含不同球桿、低光、多人經過、空揮、休息、中斷拍攝、VFR/不同 fps。
- 手動標記 start_ms/end_ms/top_ms（可選）、是否真有擊球 `yes/no/unknown`、裁切信心、畫質。
- 資料保留私人儲存；Repo 僅放非敏感 synthetic fixtures 與匿名標註格式，原片不得入 Git。

### 9.2 Acceptance Metrics（須實測、不是保證）

| 項目 | 目標 / 閘門 | 測試說明 |
|---|---|---|
| 候選球 Recall | >=90%（首版目標） | 以人工真值，含誤判統計 |
| 候選球 Precision | >=85%（首版目標） | 所有候選人工核對 |
| 裁切誤差 | 中位 <=0.5秒（首版目標） | 起迄偏差分開計 |
| 功能性 E2E | P0 路徑 100% 通過 | 真實影片、無假後端 |
| 身分保護 | 未登入/越權 0 成功 | API 全路徑抽測 |
| 可靠性 | 中斷/重啟後 job 狀態一致 | 至少三種失敗注入 |
| 正確性 | 無偽造球速/距離/擊球品質 | 文字與 API contract |
| 手機可用性 | iPhone Safari 完整上傳→查看→匯出 | 真實裝置或標示未驗證 |
| 速度與費用 | 收集基準報告，未經實測不設 SLA | 1/10/30 分鐘測 CPU/RAM/處理秒數/儲存量 |

### 9.3 自動化測試矩陣

- Unit：事件重疊合併、時間戳轉換、score missingness、rank tie-break、owner check。
- Integration：PG migration、RQ retries、MinIO presigned multipart lifecycle、轉碼品質、ffprobe metadata。
- E2E：登入、上傳、續傳、分析、刪改切片、報告、匯出，Playwright chromium web + mobile viewport；Safari 真機額外人工。
- Robustness：HEVC、H.264、MOV/MP4、VFR、旋轉 metadata、無音訊、檔案損毀、空片、0 球、多人入鏡、姿勢無法偵測、斷網、低容量、Worker crash、重複 webhook/requests。
- Security：短效 URL 到期、CORS origin、MIME sniff、大小／part count、filename path traversal、私密影片讀取、secret log redaction、依 user-id 分權。
- CI：PR lint/typecheck/unit/integration/build；staging 需在遠端進行 smoke 且保存產物證據。

## 10. Zeabur 正式部署規範

### 10.1 建議服務（同一 Project，不同 Environment）

| 服務 | 角色 | 公網 |
|---|---|---|
| `gsl-web` | Next.js UI | HTTPS 公開但需登入 |
| `gsl-api` | FastAPI REST/Upload Sign/Health | 同源 Proxy 或受限 HTTPS |
| `gsl-worker` | RQ + FFmpeg + ML 推論 | 不公開 |
| `gsl-postgres` | 資料儲存 | 不公開 |
| `gsl-redis` | Queue | 不公開 |
| `gsl-minio` | 影片/預覽/匯出之物件儲存 | 僅受簽名保護之 S3 資料端點必要時公開 |

- MinIO 只是 S3 相容方案；若已有適用的物件儲存，可用 S3 Adapter 替換而非綁定。
- 先部署 staging，確認運算與實際月費。這是**多服務架構，並非免費部署**；不得對使用者承諾固定費用。
- 對 worker 設 CPU/memory 及單機併發上限；影片體積和運算可能遠大於普通網站。
- 建議兩個 environment：staging（自動試部署）和 production（通過 release gate 才部署）。

### 10.2 環境變數模板（名稱可由實作調整，文件必須同步）

```env
APP_ENV=staging
APP_BASE_URL=https://<web-domain>
API_BASE_URL=https://<api-domain-or-internal>
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=https://<s3-browser-reachable-domain>
S3_INTERNAL_ENDPOINT_URL=http://<minio-internal-host>:9000
S3_REGION=auto
S3_BUCKET=golf-swing-lab
S3_ACCESS_KEY_ID=***
S3_SECRET_ACCESS_KEY=***
S3_FORCE_PATH_STYLE=true
SESSION_SECRET=***
ALLOWED_ORIGINS=https://<web-domain>
MAX_UPLOAD_BYTES=8589934592
MAX_VIDEO_DURATION_SEC=1800
WORKER_CONCURRENCY=1
ANALYSIS_MODEL_VERSION=pose-v1
SCORING_VERSION=score-v1
DATA_RETENTION_DAYS=30
LLM_PROVIDER=none
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_MAX_BUDGET_USD=0
```

- 不要把以上假值當真實憑證；在 Zeabur Console 設定 Secret，所有 `.env` 排除版本控制。
- S3 browser endpoint/反向代理／CORS 設計要經**實機上傳測試**，不能只在 server-side SDK 成功就通關。
- 實際部署需要帳戶與專案權限；沒權限生成部署指南、env 需求與 IaC，明確標記 blocked。
- 轉碼 worker 的 Docker image 需安裝 FFmpeg + 可運行的 MediaPipe 模型資產；模型下載、版本與授權需鎖定。
- 設 `/healthz` 快速檢查進程、`/readyz` 檢查依賴；Zeabur Health Check 使用 `/readyz`（按服務實際需求調整）。

### 10.3 安全、備份、治理

- 安全 Cookie：Secure/HttpOnly/SameSite、密碼採 Argon2id 或可信 Auth 方案， rate limiting、CSRF、防 XSS、權限與物件 key 隔離。
- 一律使用 presigned URL 限時訪問私人原片與匯出內容；Max TTL 由政策定義，不公開永久 URL。
- MinIO/DB volume 需定期備份和還原演練；設定保留期限，使用者可一鍵刪除影片及產出資料；multipart 殘留與失敗匯出定期清理。
- LLM 的 API key 僅存在服務端秘密管理，不在 browser bundle 或報告顯示；傳送外部影片/截圖需使用者可控。
- 限制單檔大小、影片時長與 concurrent jobs；超額可友善拒絕，避免失控帳單。
- 任何新增付費服務、升級付費方案、公開網域變更、正式站資料刪除或 production migration 破壞性變更，先要求授權。

## 11. LLM Adapter 設計

### 11.1 介面

```python
class GolfCoachProvider(Protocol):
    async def generate_feedback(self, session_summary: SessionSummary,
                                swing_evidence: list[SwingEvidence]) -> CoachReport: ...
```

- `LLM_PROVIDER=none` 為預設，產生規則式教學：哪個可量測項目波動最大、應如何錄製更可靠影片、下一次練習一次修 1–2 項。
- `openai-compatible`（未來可擴充不同 provider）。先建 mock provider 的 contract tests，不要求 API key。
- 輸入為已驗證的結構化量測與「合法且經同意的縮圖」，不是盲目丟整部 30 分鐘影片給 LLM。
- 輸出必須結構化 JSON：觀察、支持證據（segment_id、time_ms、metric）、信心、修正動作、練習方式、不確定項目；Pydantic 驗證與 fallback。
- 加上 timeout、retry、成本/Token 用量和每日上限；API 出錯不能使整個姿勢分析失敗。
- 提示詞要求禁止推斷不可視的球路、球速、距離和未被感測的身體角度。

## 12. Agent 自主工作協定與續作

### 12.1 核心迴圈

```
READ state + highest priority unfinished acceptance criterion
  → PLAN smallest testable change
  → IMPLEMENT actual code
  → TEST (unit / integration / e2e / build, stage-specific)
  → REVIEW (security / correctness / UX / runtime / license)
  → IF FAIL: diagnose → fix → rerun (up to 3 repair cycles per root cause)
  → IF PASS: record proof, commit, mark gate, continue next round
  → IF BLOCKED: record external dependency, continue independent work
  → REPEAT until all gates pass or all remaining blockers require owner action
```

**警告**：Agent 不可能保證永遠不停止；IDE 上下文、權限、API 額度和執行限制可能中斷。透過持續落盤和 git commits 讓後續訊息 `Continue from IMPLEMENTATION_STATE.md` 能恢復；不可聲稱「已自動在背景無限執行」。

### 12.2 續作狀態檔

- `IMPLEMENTATION_STATE.md`：目前 round、已通過 gate、未通過 gate、最近 commit SHA、執行證據路徑、下一個可執行 task、外部阻礙、retry 計數。
- `TASKS.md`：每個 task 唯一 ID、owner agent、需求追溯、前置、驗收條件、結果、證據。
- `docs/TEST_REPORT.md`：實際 commands、stdout summary、測試數量、環境資訊、測試是否 mock or real。
- `docs/DEPLOY_ZEABUR.md`：真實 Zeabur URL、服務配置、健康檢查回應、部署 git SHA；未部署則空白並標阻礙。
- `docs/SECURITY.md`：風險、處置、秘鑰管理、第三方授權與待辦。

### 12.3 錯誤處置守則

- 同根因最多做 3 次可說明的修復嘗試；不准用無限重試/skip/關閉測試掩蓋失敗。
- 無法通關則 `BLOCKED`，記下失敗證據、repro steps、影響、下一步；先做其他不依賴任務。
- 不因 UI 看起來漂亮、Build 過、測試全綠就略過端到端真人影片驗證。
- 只允許 `PASS`、`FAIL`、`BLOCKED`、`NOT_VALIDATED`；後二者不是 `PASS`。
- 各輪可自動 commit 到 feature/develop branch、發起 PR，staging 可在既有權限授權下自動部署；production 釋出需 release gate 完全 PASS 且使用者已授予必要權限。

## 13. 最終驗收與交付

**交付件**：

- 原始碼 GitHub repo、README、完整 env.example、Dockerfiles、本機 compose 與啟動指令。
- 已部署的 Zeabur staging／production 地址（只有真實部署成功才填）、服務與資源配置。
- 真實可用的上傳、逐球偵測、人工校正、分項評分、場次報告、精選球、影片匯出。
- 測試計畫與真實執行證據；Golden Set 分析報告、benchmark（CPU、RAM、儲存與實際處理時間）。
- 安全稽核、第三方授權清單、重大限制與未完成事項。
- LLM Provider 可插拔介面；無 Key 仍可運行。

**最終完成定義（DoD）**：P0/P1 的全套功能可在真實影片 + iPhone Safari E2E 通過、無未修復 P0/P1 高風險缺陷、權限與資料保護測試全通過、Zeabur 真實部署可運行、證據齊全。若使用者尚未提供實際影片或 Zeabur 權限，只能宣稱相應階段 `NOT_VALIDATED`／`BLOCKED`，不得宣稱 Final PASS。

## 14. 目前資訊來源／技術參考

- Google MediaPipe Pose Landmarker Python Guide：https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python
- Google MediaPipe（Apache 2.0）：https://github.com/google-ai-edge/mediapipe
- GolfDB / SwingNet（研究參考，CC BY-NC 4.0，不預設可商用）：https://github.com/wmcnally/golfdb
- Zeabur Dockerfile：https://zeabur.com/docs/en-US/deploy/methods/dockerfile
- Zeabur GitHub Integration：https://zeabur.com/docs/en-US/deploy/methods/github-integration
- Zeabur Volumes：https://zeabur.com/docs/en-US/operations/data/volumes
- Zeabur Health Checks：https://zeabur.com/docs/en-US/operations/monitoring/health-checks
- Zeabur Templates / MinIO：https://zeabur.com/templates
- Gemini 3.8 Flash in Antigravity：https://antigravity.google/blog/gemini-3-8-flash-in-google-antigravity/

---

> 使用本文件時，務必連同 `ANTIGRAVITY_MASTER_PROMPT.md` 投入新建的專案工作區。此文件定義開發規格，不代表系統已被實作或驗收。
