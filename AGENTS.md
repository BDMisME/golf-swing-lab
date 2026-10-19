# AGENTS.md — Golf Swing Lab 自主開發規範與契約

## 1. 專案角色與核心定位
本專案為 **Golf Swing Lab（AI 高爾夫揮桿分析系統）**。
- **使用場景**：個人球友將 iPhone 固定於練習場後方（Down-the-Line, DTL）錄製 10–30 分鐘或上傳多段影片（`.MOV` / `.MP4`、HEVC / H.264、支援旋轉 metadata 與 VFR），系統於背景自動偵測每次揮桿、提取關鍵影格與 2D 骨架、計算可解釋且具信心度控制的內部動作指標分數、產出場次報告、排序 Top 精選球，並匯出單球或 2–3 球連續 MP4 合輯。
- **最高誠信原則（Truthfulness & Anti-Hallucination）**：
  1. 嚴禁編造或猜測 2D DTL 影片無法可靠觀測之物理量：包含**球速（Ball Speed）、桿頭速度（Clubhead Speed）、飛行距離（Carry/Total Distance）、擊球甜蜜點品質（Smash Factor / Sweet Spot）、精確 3D 身體旋轉角度、精確桿面角（Clubface Angle）、實際球路（Slice/Hook/Draw/Fade）**。
  2. 區分 `swing_candidate`（揮桿候選）、`valid_swing`（可信完整揮桿）、`practice_swing`（空揮）與擊球狀態 `confirmed_strike` / `estimated_strike` / `strike_unknown` / `no_ball`。疑似擊球時間一律標示為 `impact_estimated_ms` 並附推定依據與信心度。
  3. 動作評分（0–100）為**產品內部定義之可重現動作檢核指標**（附 `score_version`、公式、分項權重、信心度與 `怎麼算的？` 說明），絕不宣稱為職業教練認證或實際擊球結果分數。若有效分項權重覆蓋率 `< 70%`，必須設 `overall_nullable = null` 並顯示「無法可靠評分」。
  4. `LLM_PROVIDER=none` 為預設且必須完整運作（使用規則式證據驅動教學與提示）；不得要求使用者先提供 API Key 才可執行核心流程。

## 2. 開發輪次（R0–R12）與工作迴圈
每一輪必須嚴格執行：
`實作 (Implement) → 測試 (Test) → 審查 (Review) → 修復 (Fix, 同一根因最多 3 次) → 複驗 (Re-verify) → 記錄證據 (Record Proof) → Git Commit → 推進下一輪`

- **R0**：Repo 起始盤點、架構契約、API/DB/Scoring/Zeabur/Security 規格文件、驗收矩陣。
- **R1**：Monorepo 骨架（`apps/web`, `apps/api`, `apps/worker`, `packages/analysis`, `packages/storage`, `packages/contracts`）、Docker Compose（PostgreSQL, Redis, MinIO）、健康檢查 `/healthz` & `/readyz`、繁體中文 Mobile-First UI Shell。
- **R2**：身分驗證（HttpOnly Session / Bearer Token + Argon2id 密碼雜湊）、Owner 權限隔離、SQLAlchemy 2 + Alembic 資料模型與 Migration、API 錯誤合約與單元/整合測試。
- **R3**：Multipart 大檔直傳與續傳、S3/MinIO Presigned URL、SHA256 與 ETag 驗證、`ffprobe` 真實 PTS/VFR/旋轉/HEVC 解析、Safari 相容 H.264 Proxy 預覽與縮圖生成。
- **R4**：Redis + RQ 背景任務佇列、真實階段進度（upload / probe / proxy / coarse_scan / fine_scan / scoring / report）、Heartbeat、冪等排程、安全重試與取消、Worker 異常恢復。
- **R5**：Coarse-to-Fine 長影片自動揮桿候選偵測、事件狀態機（`IDLE → ADDRESS_CANDIDATE → TAKEAWAY → BACKSWING → TOP → DOWNSWING → IMPACT_ESTIMATED → FOLLOW_THROUGH → FINISH → IDLE`）、原片 PTS 時間碼映射、IoU 去重、人工邊界與標籤校正 UI。
- **R6**：MediaPipe Pose Landmarker 2D 關鍵點抽取、可觀測 DTL 幾何指標計算、低光/遮擋/多人/相機晃動之品質旗標（Review Flags）、前端 Canvas 骨架疊圖與真實時間碼逐幀步進。
- **R7**：Score v1 可解釋評分引擎（軀幹前傾穩定 25%、頭部相對位移 15%、軌跡重複性 20%、上下桿節奏一致性 20%、收桿姿勢穩定 20%）與獨立 IG 視覺呈現分數、70% 覆蓋率閘門、`怎麼算的？` 透明揭露、類別排序與人工覆寫。
- **R8**：場次完整報告、共同問題摘要、各球比較表、雙球同步對照播放器（支援依 `impact_estimated_ms` 或 `top_ms` 對齊，跨 FPS/Timebase 對齊）、手動回饋紀錄（`analysis_feedback`）。
- **R9**：FFmpeg 精準時間碼裁切匯出（單球 MP4、2–3 球連續精選合輯、原始比例與 9:16 直式構圖、保留真實畫面不畫假球軌）、短效簽名下載。
- **R10**：`GolfCoachProvider` 介面、`none`（規則式繁體中文教練報告）與 `openai-compatible` Adapter（含 Pydantic 結構化輸出驗證、Timeout、預算上限、隱私授權控制與 Mock 契約測試）。
- **R11**：Zeabur 多服務 Dockerfile 與部署配置（`gsl-web`, `gsl-api`, `gsl-worker`, PostgreSQL, Redis, MinIO）、部署指南與自動化檢查腳本；若缺外部 Zeabur 帳號授權則如實標記 `EXTERNAL_BLOCKER`。
- **R12**：端到端整合驗收、Golden Set 評估腳本與基準報告、瀏覽器實測證據、安全與授權總稽核、交付清單核對。

## 3. 驗證狀態定義
- `PASS`：已撰寫真實程式碼，並實際執行自動化測試或瀏覽器操作取得通過證據。
- `FAIL`：測試或檢查未通過，需進入診斷與修復循環。
- `BLOCKED` / `EXTERNAL_BLOCKER`：受限於外部帳號權限（如 Zeabur Token、遠端私人儲存）無法於本機自主完成。
- `NOT_VALIDATED`：程式碼與合成測試已通過，但尚未有外部真實 iPhone 10–30 分鐘人工標註 Golden Set 原片進行實測指標驗證。**絕不可將 `BLOCKED` 或 `NOT_VALIDATED` 偽稱為 `PASS`**。

## 4. 中斷恢復機制
每次完成任務或輪次時，必須更新：
1. `IMPLEMENTATION_STATE.md`
2. `TASKS.md`
3. `docs/TEST_REPORT.md`
並執行 Git Commit，確保任何時候皆可由 `IMPLEMENTATION_STATE.md` 無縫續接。
