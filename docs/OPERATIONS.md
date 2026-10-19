# OPERATIONS.md — 系統維運、佇列監控與備份清理指南

## 1. 背景任務（RQ Worker）管理與容錯
- **佇列設計**：使用 Redis + RQ（佇列名稱：`gsl-analysis` 與 `gsl-exports`）。
- **Job Timeout 與 Heartbeat**：
  - 單一分析任務預設 `RQ_JOB_TIMEOUT_SEC=3600`（60 分鐘），Worker 每完成一個處理批次更新 `analysis_jobs.heartbeat_at` 與 `progress`（0–100）。
  - 若 Worker 因容器重啟或 OOM 中斷，API 或新啟動之 Worker 偵測到 `status = 'running'` 且 `heartbeat_at` 逾時超過 180 秒之孤兒任務，允許使用者或系統透過 `POST /api/jobs/{id}/retry` 安全重試（預設最多 `attempt_count <= 3`）。
- **記憶體安全**：
  - 影片分析採用串流讀取（OpenCV / FFmpeg 依時間區段讀取），禁止將整部 30 分鐘影片的所有影格一次載入記憶體。
  - Worker 預設 `WORKER_CONCURRENCY=1`，確保單機 CPU 與記憶體穩定。

## 2. 儲存空間治理與定期清理
- **Multipart 殘留清理**：`uploads` 表中超過 `expires_at`（24 小時）仍處於 `initiated` 或 `uploading` 狀態之任務，由清理程序呼叫 `abort_multipart_upload` 釋放 S3 碎片空間。
- **資料保留政策（Retention）**：依 `DATA_RETENTION_DAYS`（預設 30 天）清理過期之匯出檔（`exports`），並提供使用者刪除場次/影片時連動刪除 S3 原始檔、Proxy 檔與骨架產物。

## 3. 健康檢查端點
- `GET /healthz`：回傳 `200 OK` 與服務版本，確認 API 行程存活。
- `GET /readyz`：實際檢測 PostgreSQL (`SELECT 1`)、Redis (`PING`) 與 S3 Bucket 連線狀態；任一依賴異常時回傳 `503 Service Unavailable`。
