# API.md — Golf Swing Lab REST API 合約規格

## 1. 認證與權限原則
- 除 `/healthz`、`/readyz`、`POST /api/auth/login` 外，所有 `/api/*` 端點皆須通過身分驗證（支援 `HttpOnly` Session Cookie `gsl_session` 或 `Authorization: Bearer <token>`）。
- 未登入請求一律回傳 `401 Unauthorized`。
- 嘗試存取非本人（`owner_id != current_user.id`）之 `session`、`video`、`upload`、`job`、`swing`、`export` 一律回傳 `403 Forbidden`。

## 2. 統一錯誤回應格式（Error Contract）
所有錯誤回應均符合以下 JSON 結構，且絕不暴露伺服器內部 Stack Trace：
```json
{
  "code": "RESOURCE_FORBIDDEN",
  "message": "您沒有權限存取此資源",
  "details": {},
  "request_id": "req_01j8..."
}
```

## 3. 端點總覽

| HTTP 方法 | 路徑 | 說明 | 冪等性 |
|---|---|---|---|
| `GET` | `/healthz` | 行程存活檢查（Liveness） | Yes |
| `GET` | `/readyz` | 資料庫、Redis、S3 儲存就緒檢查（Readiness） | Yes |
| `POST` | `/api/auth/login` | 管理員/使用者登入，簽發 HttpOnly Cookie 與 Token | Yes |
| `POST` | `/api/auth/logout` | 登出並清除 Session Cookie | Yes |
| `GET` | `/api/auth/me` | 取得目前登入使用者資訊 | Yes |
| `GET` | `/api/sessions` | 取得使用者的練習場次列表（含統計摘要） | Yes |
| `POST` | `/api/sessions` | 建立新練習場次（日期、球桿、左右手、DTL 視角、備註） | No |
| `GET` | `/api/sessions/{id}` | 取得單一場次詳情與所屬影片列表 | Yes |
| `POST` | `/api/uploads/initiate` | 驗證大小/MIME/配額，建立 Multipart Upload（支援 `idempotency_key`） | Yes |
| `POST` | `/api/uploads/{id}/parts/sign` | 簽發指定 `part_number` 的短效上传 URL 與上傳資訊 | Yes |
| `PUT` | `/api/uploads/{id}/parts/{part_number}/content` | 分段二進位上傳端點（寫入 S3/MinIO 並回傳真實 ETag 與 SHA256） | Yes |
| `POST` | `/api/uploads/{id}/complete` | 驗證所有 Parts 與物件實際存在，執行 `ffprobe` 解析並入庫 | Yes |
| `POST` | `/api/uploads/{id}/abort` | 中止並清理未完成的 Multipart Upload | Yes |
| `GET` | `/api/videos/{id}` | 取得影片 metadata 與短效播放 URL | Yes |
| `GET` | `/api/videos/{id}/stream` | 支援 `Range: bytes=...` 的受保護影片串流（Safari 相容 `206 Partial Content`） | Yes |
| `POST` | `/api/videos/{id}/analyze` | 將影片排入背景分析佇列（冪等，已分析中則回傳既有 Job） | Yes |
| `GET` | `/api/jobs/{id}` | 查詢背景任務狀態、階段、進度百分比、Heartbeat 與錯誤碼 | Yes |
| `POST` | `/api/jobs/{id}/retry` | 安全重試失敗或逾時任務（受最大重試次數保護） | Yes |
| `POST` | `/api/jobs/{id}/cancel` | 取消排隊或執行中之分析任務 | Yes |
| `GET` | `/api/videos/{id}/swings` | 取得影片的所有揮桿片段（支援 Cursor 分頁與狀態篩選） | Yes |
| `POST` | `/api/videos/{id}/swings` | 手動新增遺漏的揮桿片段並觸發該段指標與評分計算 | No |
| `GET` | `/api/swings/{id}` | 取得單一揮桿詳情：階段事件、2D 骨架關鍵點、量測指標、Score v1 與教練提示 | Yes |
| `PATCH` | `/api/swings/{id}` | 人工校正起迄時間碼、標籤（`valid_swing` / `practice_swing` / `rejected`）、擊球狀態與備註，並留存修訂紀錄與重算分數 | Yes |
| `DELETE` | `/api/swings/{id}` | 刪除誤判之揮桿片段（記錄 Audit 與 Feedback） | Yes |
| `GET` | `/api/sessions/{id}/report` | 取得場次完整報告、分項趨勢、共同問題、四大類別排行榜與 AI 教練報告 | Yes |
| `POST` | `/api/sessions/{id}/favorites` | 手動將某球加入/排除特定精選分類或調整排序 | Yes |
| `POST` | `/api/exports` | 建立單球或 2–3 球連續 MP4 合輯匯出任務（支援 `original` 與 `9:16`） | Yes |
| `GET` | `/api/exports` | 取得使用者的匯出任務列表 | Yes |
| `GET` | `/api/exports/{id}` | 取得匯出任務狀態與短效下載連結 | Yes |
| `GET` | `/api/exports/{id}/download` | 受保護的 MP4 匯出檔案下載（支援 Range 與 iPhone Safari 下載） | Yes |
| `GET` | `/api/settings` | 取得個人預設設定與 LLM Provider 狀態（絕不回傳明文 API Key） | Yes |
| `PUT` | `/api/settings` | 更新預設球桿、慣用手、評分權重配置與 LLM Provider 設定 | Yes |
