# Golf Swing Lab — 安全性與權限審查報告 (Security Review)

## 1. 執行摘要
本報告記錄 Golf Swing Lab 針對 R7–R10 輪次實施之安全性強化與合規稽核成果。系統定位為個人 iPhone DTL 高爾夫揮桿分析之 Mac 獨立應用程式與本機服務，嚴格遵循最小權限原則、資料隔離與隱私保護。

---

## 2. 身份驗證與憑證安全 (Credentials & Authentication)

### 2.1 移除硬編碼與預設金鑰
- **Session Secret**：
  - 開發模式（`ENV=development`）僅在未提供時給予警告並使用暫時性開發金鑰。
  - 正式生產模式（`ENV=production`）啟動時執行 `validate_security_posture()` 嚴格檢驗，若發現 `SESSION_SECRET` 未設定或為預設值，API 服務立即拒絕啟動（Fail-Fast）。
- **管理員密碼**：
  - 正式環境強制禁止使用弱密碼（如 `admin123` 等預設值），密碼雜湊採用業界標準 Argon2id 演算法。
- **物件儲存（S3 / MinIO）憑證**：
  - 正式環境禁止使用預設 `minioadmin` 帳號密碼，強制要求自訂安全 Access Key 與 Secret Key。

### 2.2 本機 API 網路邊界安全 (Network Binding)
- 所有後端 API 與內部資料服務（PostgreSQL, Redis, MinIO）預設嚴格綁定 `127.0.0.1` 本機迴路位址。
- 嚴禁未經授權暴露於練習場公共 Wi-Fi 或區域網路（LAN），防止中間人攻擊或本機資料窺探。

---

## 3. 資料隱私與本機 AI 推論 (Privacy & On-Device Processing)

| 組件名稱 | 運作模式 | 資料流向 | 授權條款 | 隱私合規評估 |
| :--- | :--- | :--- | :--- | :--- |
| **Ultralytics YOLOv8-pose** | 本機執行 (Apple Silicon MPS / CPU) | 100% 本地運算，不發送任何影格至外網 | AGPL-3.0 (Local Weights Execution) | 通過：零資料外洩風險 |
| **Golf Ball Tracker (Kalman + YOLO)** | 本機執行 | 100% 本地運算 | MIT | 通過：完全離線運作 |
| **Google MediaPipe Pose** | 本機執行 (C++ / TFLite) | 100% 本地運算 | Apache-2.0 | 通過：完全離線運作 |
| **FFmpeg** | 本機原生 CLI 二進位程式 | 本機影片裁切與代理生成 | LGPL-2.1+ | 通過：本地轉碼 |
| **內建 AI 教練 (LLM_PROVIDER=none)** | 本機規則式引擎 | 100% 本地客觀幾何與時間碼推論 | 專案原生 (Proprietary) | 通過：無需 API Key，零網路相依 |
| **外部 LLM 介接 (OpenAI-compatible / Gemini)** | 需使用者主動授權配置 API Key | 僅傳輸去識別化之定格截圖與數值指標 | 服務商商業 TOS | 通過：具備 Pydantic 校驗與防偽攔截網 |

---

## 4. 防偽安全網與誠信原則控制 (Anti-Hallucination & Safety Rails)

針對生成式 AI 可能產生之幻覺與偽造物理量，系統在輸入輸出兩端建立了強制防禦：
1. **系統提示詞硬約束**：
   - 嚴格禁止編造或推論球速、桿頭速度、飛行距離、甜蜜點接觸品質。
   - 嚴格禁止在單相機未標定下輸出具體長度單位（如公分、厘米、cm、英吋、inches）。
   - 嚴格禁止推論未經雷達感測之真實飛行球路（如 Slice、Hook、Draw、Fade、左曲、右曲）或精確桿面角度。
2. **輸出安全攔截器（FORBIDDEN_HALLUCINATION_TERMS）**：
   - 當外部模型輸出包含任何違規名詞或未授權臆測時，系統自動拋出例外並**平滑降級退回規則式報告（`RuleBasedCoachProvider`）**，確保呈現在球友面前的分析結論 100% 客觀真實。

---

## 5. 結論
Golf Swing Lab 在架構設計上嚴格落實資料私隱保全與本機優先原則。正式環境安全性檢查已納入自動化測試與 CI 流程，安全性審查判定為 **PASS**。
