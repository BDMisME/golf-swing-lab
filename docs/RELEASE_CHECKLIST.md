# RELEASE_CHECKLIST.md — 最終交付與誠實度稽核清單

## 1. 核心工程與功能驗收清單

- [x] **Monorepo 與基礎設施 (`R0–R1`)**：`apps/web`、`apps/api`、`apps/worker`、`packages/analysis`、`packages/storage`、`packages/contracts`、`infra/`、`docs/`、`tests/` 結構完整；PostgreSQL 16、Redis 7、MinIO 容器健康運作，`/healthz` 與 `/readyz` 實測回傳 `200 OK`。
- [x] **身分驗證與權限隔離 (`R2`)**：Argon2id 密碼雜湊、HttpOnly Cookie + Bearer Token 雙軌驗證、Owner 跨用戶 `403 AUTH_FORBIDDEN` 隔離與 `AuditEvent` 稽核紀錄、Alembic `upgrade head -> downgrade base -> upgrade head` 正反向遷移通過。
- [x] **大檔分段續傳與媒體探測 (`R3`)**：S3/MinIO Multipart Upload (`initiate` / `sign` / `parts` / `complete`)、SHA256 與 ETag 驗證、HTTP Range `206 Partial Content` 串流、`ffprobe` H.264/HEVC/VFR/旋轉矩陣解析、損毀媒體 `422 INVALID_VIDEO_MEDIA` 攔截。
- [x] **背景任務佇列與韌性控制 (`R4`)**：Redis + RQ 非同步佇列、7 階段真實進度更新、冪等重入 (`idempotent_reused`)、手動取消 (`cancelled`)、孤兒任務 Heartbeat 逾時重啟與最大重試上限 (`max_attempts=3`)。
- [x] **長影片自動切球與 9 階段狀態機 (`R5`)**：Coarse-to-Fine 串流抽樣偵測、`IDLE -> ADDRESS_CANDIDATE -> TAKEAWAY -> BACKSWING -> TOP -> DOWNSWING -> IMPACT_ESTIMATED -> FOLLOW_THROUGH -> FINISH -> IDLE` 狀態機、IoU 重疊視窗去重、人工新增/調整/刪除揮桿區段且重新分析時保留 `manual_override=True` 標記。
- [x] **2D 骨架擷取與畫質旗標 (`R6`)**：Google MediaPipe `PoseLandmarker` (`pose_landmarker_lite.task`) 2D 關鍵點抽取、可觀測 DTL 幾何指標計算、低光 (`low_light`) / 多人干擾 (`multi_person`) / 晃動 (`camera_motion`) 自動降級旗標、前端 Canvas 骨架疊圖與 `±33ms` 逐幀控制。
- [x] **可解釋評分引擎 `score-v1` (`R7`)**：5 項子分數（軀幹前傾穩定 25%、頭部相對位移 15%、軌跡重複性 20%、上下桿節奏一致性 20%、收桿姿勢穩定 20%）、`<70%` 覆蓋率誠實閘門（強制 `overall_nullable = null`）、`怎麼算的？` 公式透明揭露、獨立 `ig_visual_score` 與四大分類排行榜。
- [x] **場次報告與雙球同步對照 (`R8`)**：場次摘要、共同問題診斷、雙球並排同步播放器與指標對照、人工校正歷史紀錄 (`AnalysisFeedback`)。
- [x] **精選短片與合輯匯出 (`R9`)**：FFmpeg 單球與 2–3 球連續合輯裁切匯出、支援 `original` 原始比例與 `9:16` (`720x1280`) 直式社群構圖、保留真實畫面絕不繪製假球軌。
- [x] **可插拔教練介面與防幻覺護欄 (`R10`)**：預設 `LLM_PROVIDER=none` 規則式繁體中文教練完整運作；`openai-compatible` 結構化驗證與違規詞彙（球速、飛行距離、曲球等）自動攔截降級；`/api/settings` 永不回傳明文 API Key。
- [x] **部署規格與 Zeabur 藍圖 (`R11`)**：`infra/docker/{api,worker,web}.Dockerfile`、`infra/compose.prod.yml`、`infra/zeabur/template.yaml` 與 `docs/DEPLOY_ZEABUR.md` 完整交付並通過 `docker compose config` 驗證。

---

## 2. 誠實揭露事項 (Honesty & Non-Validated Items)

1. **高爾夫物理量誠實邊界**：系統所有 API、資料庫與前端畫面均未猜測或宣稱單支 2D DTL 相機無法量測之球速、桿頭速度、飛行距離、甜蜜點、3D 旋轉角度或實際球路方向；所有擊球時間點均標示為 `impact_estimated`。
2. **真人 100+ 球 Golden Dataset 狀態 (`NOT_VALIDATED`)**：合成黃金測試集 (`tests/golden/synthetic_session_gt.json`) 已通過自動化驗證（Recall `1.00`, Precision `1.00`, Impact MAE `37.3ms`），但外部真人 iPhone 10–30 分鐘練習場標註影片（100+ 球）尚未提供，因此真人資料集泛化指標維持標記為 **`NOT_VALIDATED`**。
3. **Zeabur 遠端雲端部署狀態 (`EXTERNAL_BLOCKER`)**：本機 Docker Compose 與 Zeabur 部署規格檔已驗證通過；因環境未提供外部 `ZEABUR_TOKEN` 與雲端專案授權，遠端實機部署維持標記為 **`EXTERNAL_BLOCKER`**。
