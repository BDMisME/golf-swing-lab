# SECURITY.md — 資安治理、隱私保護與第三方開源授權清單

## 1. 身分驗證與授權控制
- **密碼儲存**：採用 `argon2-cffi`（Argon2id）雜湊儲存使用者密碼，禁止明文或弱雜湊。
- **Session 與 Token**：登入簽發 HMAC-SHA256 簽章 Token，寫入 `HttpOnly; SameSite=Lax`（生產環境啟用 `Secure`）Cookie，同時支援 API Header Bearer 驗證。
- **物件層級權限隔離（BOLA 防護）**：所有資料庫查詢與物件存取皆強制過濾或比對 `owner_id == current_user.id`；跨用戶存取一律回傳 `403 Forbidden` 並記錄於 `audit_events`。

## 2. 影片與物件儲存安全
- **私有儲存桶**：S3 / MinIO Bucket 預設為 Private，禁止公開列出（Public List）或永久公開讀取。
- **短效簽名與保護串流**：預覽與匯出下載一律透過短效 Presigned URL（預設 TTL `900` 秒）或經由驗證 Owner 權限之 `/api/videos/{id}/stream` 與 `/api/exports/{id}/download` 端點存取。
- **上傳防護**：
  - 檢查副檔名與 MIME Type（僅允許 `.mov`, `.mp4`, `video/quicktime`, `video/mp4`）。
  - 清洗檔名防止 Path Traversal（例如 `../../etc/passwd` 自動正規化為安全 basename 並以 UUID 作為儲存 Key）。
  - 限制單檔上限 `MAX_UPLOAD_BYTES`（預設 8 GiB）與最長影片時長 `MAX_VIDEO_DURATION_SEC`（預設 1800 秒 / 30 分鐘）。

## 3. 秘密管理與外部 API 隱私
- `.env` 已列入 `.gitignore`，絕不提交任何真實密碼或 API Key 至 Git。
- `LLM_API_KEY` 僅儲存於伺服器端，`/api/settings` 僅回傳 `has_api_key: boolean`，絕不在前端 Bundle、API 回應或日誌中洩漏金鑰。
- 當 `LLM_PROVIDER=none` 時，系統完全不發出任何外部 LLM 網路請求。即使啟用外部 LLM，預設僅傳送結構化匿名數值指標，除非使用者明確勾選允許傳送關鍵影格縮圖。

## 4. 第三方套件與模型授權稽核（License Audit）

| 組件 / 套件 | 用途 | 授權條款 | 商用與私有部署合規性 |
|---|---|---|---|
| Google MediaPipe (`mediapipe`) | 2D 人體骨架關鍵點推論 | Apache License 2.0 | 合規，可合法用於生產系統 |
| OpenCV (`opencv-python-headless`) | 影像幀讀取與基礎矩陣運算 | Apache License 2.0 | 合規 |
| FFmpeg / ffprobe (系統執行檔) | 影片封裝解析、轉碼與裁切 | LGPL v2.1+ / GPL v2+ (CLI 外部呼叫) | 透過子行程 CLI 呼叫並於 Dockerfile 鎖定版本 |
| FastAPI / Pydantic / SQLAlchemy / Alembic | 後端 API 與 ORM | MIT License | 合規 |
| Redis / RQ (`rq`) | 背景任務佇列 | BSD-3-Clause | 合規 |
| Next.js / React / Tailwind CSS / Lucide | 前端 UI 框架與圖示 | MIT / ISC License | 合規 |
| GolfDB / SwingNet | **僅作為文獻研究參考** | CC BY-NC 4.0（非商用） | **本專案未引入任何 GolfDB 程式碼、模型權重或資料集**，自行實作 Apache-2.0 相容之狀態機演算法 |
